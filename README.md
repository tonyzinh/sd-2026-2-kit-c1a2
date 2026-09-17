# Serviço de Inferência Distribuído — C1.A2

**Sistemas Distribuídos e Computação em Nuvem · FAESA · 2026/2**

Serviço que recebe um texto e devolve a análise de sentimento (positivo/negativo),
exposto por **duas interfaces de comunicação** (REST e gRPC) e com **processamento
assíncrono via fila** (Redis), para que o cliente não fique bloqueado esperando a
inferência terminar.

---

## Sumário

- [Arquitetura](#arquitetura)
- [Fluxo assíncrono passo a passo](#fluxo-assíncrono-passo-a-passo)
- [Tratamento de falhas](#tratamento-de-falhas)
- [Como executar do zero](#como-executar-do-zero)
- [Testando a API](#testando-a-api)
- [Extensões opcionais implementadas](#extensões-opcionais-implementadas)
- [Rodando os testes automatizados](#rodando-os-testes-automatizados)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Referência das rotas REST](#referência-das-rotas-rest)
- [Referência do serviço gRPC](#referência-do-serviço-grpc)
- [Decisões de arquitetura](#decisões-de-arquitetura)
- [Solução de problemas](#solução-de-problemas)

---

## Arquitetura

O sistema é composto por **quatro processos independentes**, que podem rodar em
máquinas diferentes e escalar de forma isolada:

![Arquitetura do serviço: cliente REST fala com api_rest.py, que enfileira no Redis, consumido pelo worker.py, que chama modelo.py; cliente gRPC fala direto com servidor_grpc.py, que também chama modelo.py](docs/arquitetura.png)

**Por que essa divisão?**

- **REST** (`api_rest.py`) e **gRPC** (`servidor_grpc.py`) são duas *fachadas*
  independentes para o mesmo domínio de inferência. Ambas reutilizam a mesma
  regra de validação (`app/services/inferencia_service.py`) e o mesmo modelo
  (`app/modelo.py`), garantindo que **devolvem sempre o mesmo resultado** para o
  mesmo texto (ver `tests/test_paridade_rest_grpc.py`).
- **Fila (Redis)** desacopla quem pede (`api_rest.py`) de quem processa
  (`worker.py`): a rota `POST /predict` responde em milissegundos com um `id`,
  sem esperar a inferência rodar.
- **Worker** é um processo separado e pode ser **replicado** (2, 3, N instâncias)
  para dividir a carga — todas competem pela mesma fila Redis via `BLPOP`.
- **Modelo** é carregado **uma única vez** por processo (no `startup` do FastAPI,
  no construtor do serviço gRPC e no início do `worker`), nunca a cada
  requisição.

---

## Fluxo assíncrono passo a passo

1. Cliente faz `POST /predict {"texto": "..."}`.
2. `api_rest.py` valida o texto e chama `submeter_inferencia`, que coloca a
   tarefa na fila Redis (`fila.enfileirar`) com um `id` (UUID) e grava um
   status inicial `"na_fila"`.
3. A API responde **imediatamente** com `202 Accepted` e `{"id": "<uuid>"}` —
   o cliente não espera a inferência.
4. Em paralelo, o `worker.py` está bloqueado em `BLPOP tarefas`. Assim que a
   tarefa chega, ele a retira da fila, roda `modelo.prever(texto)` e grava o
   resultado em `resultado:<id>` com `status: "pronto"`.
5. O cliente consulta `GET /resultado/{id}` quantas vezes quiser. Enquanto o
   worker não processou, recebe `status: "na_fila"` (ou `"retentando"` em caso
   de falha temporária); quando pronto, recebe o resultado completo
   (sentimento, confiança, tempo de processamento).

---

## Tratamento de falhas

Implementado em `worker.py`:

- Se `modelo.prever()` lançar uma exceção, o worker **não derruba o processo**:
  captura o erro em `processar_tarefa` e decide o que fazer em
  `processar_falha`.
- **Retentativa:** a tarefa é reenfileirada (`rpush` em `tarefas`) até
  **3 tentativas** (`MAX_TENTATIVAS`). Durante isso, `GET /resultado/{id}`
  mostra `status: "retentando"` com o número da tentativa.
- **Dead-letter:** depois da 3ª falha, a tarefa vai para a fila
  `tarefas:dead-letter` (para inspeção manual/depuração) e o cliente recebe
  `status: "erro"` com a mensagem da falha.
- **Fila indisponível:** se o Redis cair, `api_rest.py` devolve
  `503 Service Unavailable` (`FilaIndisponivelError`) em vez de travar.
- **Texto inválido:** texto vazio devolve `400 Bad Request` no REST e
  `INVALID_ARGUMENT` no gRPC — mesma regra de validação nos dois protocolos.
- **Logs:** toda requisição (REST e gRPC) e todo evento do worker geram uma
  linha de log com id/tamanho da entrada/tempo de resposta, para
  acompanhar o sistema em execução.

---

## Como executar do zero

Pré-requisitos: **Python 3.12+**, **Docker** (para o Redis) e **git**.

> **Importante — ambiente virtual (`.venv`):** este projeto usa vários
> processos rodando ao mesmo tempo, cada um no seu próprio terminal. **Todo
> terminal novo abre "limpo"**, sem o `.venv` ativado — ative-o assim que
> abrir cada terminal, antes de rodar qualquer comando `python`/`pip`/
> `uvicorn`. Se o prompt não começar com `(.venv)`, ative com:
>
> ```bash
> # Windows (PowerShell):
> .venv\Scripts\activate
> # Linux/macOS:
> source .venv/bin/activate
> ```
>
> Sempre que este guia disser **"abra um novo terminal"**, lembre-se de
> ativar o `.venv` nele antes de continuar.

```bash
# 1. Clone o repositório e entre na pasta
git clone <url-do-seu-repositorio>
cd sd-2026-2-kit-c1a2

# 2. Crie e ative o ambiente virtual
python -m venv .venv

# Windows (PowerShell):
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# 3. Instale as dependências
pip install -r requirements.txt
```

```bash
# 4. Configure as variáveis de ambiente (opcional — o padrão já funciona)
copy .env.example .env      # Windows
# cp .env.example .env      # Linux/macOS
```

```bash
# 5. Suba o Redis (fila) em segundo plano
docker compose up -d

# verifique se subiu:
docker compose ps
```

```bash
# 6. Gere os stubs gRPC (necessário só uma vez, ou sempre que o .proto mudar)
python -m grpc_tools.protoc -I proto --python_out=. --grpc_python_out=. proto/inferencia.proto
# (ou use os scripts prontos)
# Windows: scripts\gerar_stubs.ps1
# Linux/macOS: bash scripts/gerar_stubs.sh
```

Agora abra **três terminais** — cada um fica ocupado rodando o seu processo,
então precisam ser janelas/abas diferentes. **Em cada um, ative o `.venv`
primeiro** (veja o aviso acima).

```bash
# Terminal A — API REST (lembre-se de ativar o .venv antes)
uvicorn app.api_rest:app --reload --port 8000
# docs interativas em http://localhost:8000/docs
```

```bash
# Terminal B — worker (lembre-se de ativar o .venv antes)
# pode rodar mais de um, em terminais diferentes (cada um com o .venv
# ativado), para demonstrar divisão de carga
python -m app.worker
```

```bash
# Terminal C — servidor gRPC (lembre-se de ativar o .venv antes)
python -m app.servidor_grpc
# escutando em localhost:50051
```

---

## Testando a API

Com os três processos do passo anterior no ar, abra um **quarto terminal**
(ative o `.venv` antes, como sempre) e rode:

```bash
# fluxo síncrono + assíncrono, usando o cliente de exemplo
python exemplos/cliente_rest.py "o atendimento foi otimo"
```

Ou manualmente com `curl`:

```bash
# síncrono — espera a resposta
curl -X POST http://localhost:8000/predict-sync \
  -H "Content-Type: application/json" \
  -d "{\"texto\": \"o atendimento foi otimo\"}"

# assíncrono — devolve o id na hora
curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d "{\"texto\": \"o atendimento foi otimo\"}"
# -> {"id": "b3f1..."}

# consulta o resultado usando o id devolvido acima
curl http://localhost:8000/resultado/b3f1...
```

Para verificar se a API está no ar e o modelo foi carregado:

```bash
curl http://localhost:8000/saude
```

---

## Extensões opcionais implementadas

Além do núcleo obrigatório, este projeto implementa as extensões sugeridas
em `TAREFAS.md`:

- **Cache de resultados para textos repetidos** — `ModeloComCache`
  (`app/modelo.py`) envolve o modelo e reaproveita o resultado quando o
  mesmo texto é enviado de novo, sem rodar o pipeline outra vez. O cache é
  por processo (REST, cada worker e o servidor gRPC têm o seu).
- **Latência média das inferências** — `GET /metricas` devolve
  `{"contagem": ..., "latencia_media_ms": ...}`, agregando **todas as
  instâncias** (REST, gRPC e workers) através de contadores no Redis
  (`app/fila.py`).
  ```bash
  curl http://localhost:8000/metricas
  ```
- **Processamento em lote pela interface REST** — `POST /predict-lote`
  recebe vários textos numa única chamada e devolve um resultado para cada
  um (equivalente ao RPC gRPC `PreverLote`).
  ```bash
  curl -X POST http://localhost:8000/predict-lote \
    -H "Content-Type: application/json" \
    -d "{\"textos\": [\"otimo produto\", \"pessimo atendimento\"]}"
  ```
- **Divisão de carga entre workers** — abra mais terminais (com o `.venv`
  ativado em cada um) e rode `python -m app.worker` em cada um; todos
  competem pela mesma fila Redis via `BLPOP`, então cada tarefa é processada
  por apenas um worker.

---

## Rodando os testes automatizados

```bash
pytest
```

- `tests/test_inferencia_service.py` — validação de texto, erros de fila.
- `tests/test_worker.py` — processamento, retentativa e dead-letter do worker.
- `tests/test_modelo_cache.py` — cache de resultados para textos repetidos.
- `tests/test_api_rest.py` — rotas `/predict-lote` e `/metricas`.
- `tests/test_paridade_rest_grpc.py` — garante que REST e gRPC devolvem o
  **mesmo resultado** para o mesmo texto (é pulado automaticamente se os
  stubs gRPC ainda não foram gerados — veja o passo 6 acima).

---

## Estrutura do projeto

```
sd-2026-2-kit-c1a2/
├── app/
│   ├── modelo.py                    # modelo de sentimento (treina/carrega 1x, offline)
│   ├── fila.py                      # acesso ao Redis: enfileirar, consumir, guardar resultado
│   ├── api_rest.py                  # interface REST (FastAPI): /predict-sync, /predict, /resultado/{id}
│   ├── worker.py                    # consumidor da fila: inferência, retentativa, dead-letter
│   ├── servidor_grpc.py             # interface gRPC: Prever, PreverLote
│   └── services/
│       └── inferencia_service.py    # regras compartilhadas entre REST e gRPC (validação, erros)
├── proto/
│   └── inferencia.proto             # contrato gRPC (mensagens e serviço)
├── exemplos/
│   └── cliente_rest.py              # cliente de exemplo (fluxo síncrono e assíncrono)
├── scripts/
│   ├── gerar_stubs.ps1              # gera os stubs gRPC (Windows)
│   └── gerar_stubs.sh               # gera os stubs gRPC (Linux/macOS)
├── tests/                           # testes automatizados (pytest)
├── docker-compose.yml               # sobe o Redis
├── requirements.txt                 # dependências Python
└── .env.example                     # variáveis de ambiente (REDIS_URL)
```

---

## Referência das rotas REST

| Método | Rota | Descrição | Resposta |
|---|---|---|---|
| `GET` | `/saude` | Verifica se a API está ativa e o modelo carregado | `200` |
| `POST` | `/predict-sync` | Executa a inferência e espera o resultado | `200` com resultado |
| `POST` | `/predict-lote` | Executa a inferência para vários textos numa chamada | `200` com lista de resultados |
| `POST` | `/predict` | Enfileira a inferência e devolve na hora | `202` com `{"id": ...}` |
| `GET` | `/resultado/{id}` | Consulta status/resultado de uma tarefa | `200` (status variável) ou `404` |
| `GET` | `/metricas` | Contagem e latência média das inferências (todas as instâncias) | `200` |

Documentação interativa (Swagger) em `http://localhost:8000/docs` com o
serviço no ar.

## Referência do serviço gRPC

Definido em `proto/inferencia.proto`:

| RPC | Entrada | Saída | Descrição |
|---|---|---|---|
| `Prever` | `PedidoPrever { texto }` | `RespostaPrever { texto, sentimento, confianca }` | Inferência de um único texto |
| `PreverLote` | `PedidoLote { textos[] }` | `RespostaLote { resultados[] }` | Inferência em lote (vários textos numa única chamada) |

O servidor gRPC chama o modelo **diretamente** (não passa pela fila Redis),
pois o objetivo aqui é demonstrar uma segunda tecnologia de comunicação
(RPC binário sobre HTTP/2), não um segundo fluxo assíncrono.

---

## Decisões de arquitetura

- **Modelo carregado uma única vez por processo:** `carregar_modelo()` é
  chamado no evento `startup` do FastAPI, no `__init__` do `ServicoInferencia`
  (gRPC) e no início de `worker.main()` — nunca dentro de uma rota ou de um
  laço de requisições.
- **Validação centralizada:** `app/services/inferencia_service.py` concentra a
  validação de texto e os erros de domínio (`TextoInvalidoError`,
  `FilaIndisponivelError`, `TarefaNaoEncontradaError`), reutilizados tanto pelo
  REST quanto pelo gRPC — evita duas implementações divergentes da mesma regra.
- **Fila como ponto único de desacoplamento:** só o par REST↔worker passa pela
  fila; o gRPC é síncrono por design, para ilustrar as duas abordagens lado a
  lado.
- **Escalabilidade horizontal do worker:** como o consumo usa `BLPOP` (bloqueio
  atômico no Redis), múltiplas instâncias de `worker.py` podem rodar ao mesmo
  tempo sem processar a mesma tarefa duas vezes.
- **Métricas nunca derrubam uma requisição:** `fila.registrar_latencia` e
  `fila.obter_metricas` capturam falhas do Redis (`RedisError`) e voltam um
  valor neutro em vez de propagar o erro — são um complemento observacional,
  não um requisito para a inferência funcionar.

---

## Solução de problemas

**`ModuleNotFoundError: inferencia_pb2`**
Os stubs gRPC não foram gerados. Rode o comando do passo 6 de
[Como executar do zero](#como-executar-do-zero).

**`redis.exceptions.ConnectionError` ou API devolvendo `503`**
O Redis não está no ar. Rode `docker compose up -d` e confira com
`docker compose ps`.

**`GET /resultado/{id}` devolve `404`**
O `id` não existe (verifique se copiou certo) ou o worker ainda não está
rodando para processar a fila.

**Quero simular divisão de carga entre workers**
Abra mais terminais e rode `python -m app.worker` em cada um — todos
competem pela mesma fila Redis.
