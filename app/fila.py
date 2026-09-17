"""
Auxiliares de fila (Redis) - PRONTO, use como esta.

A fila guarda tarefas pendentes e os resultados prontos.
Conceito da Aula 8: quem pede nao espera; um worker processa depois.
"""
import json
import os
import uuid
from typing import cast

import redis
from redis.exceptions import RedisError

REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
FILA_TAREFAS: str = "tarefas"
PREFIXO_RESULTADO: str = "resultado:"

# Extensao opcional: latencia media das inferencias, agregada entre TODOS os
# processos (REST, gRPC e workers) usando contadores no Redis.
CHAVE_METRICAS_CONTAGEM: str = "metricas:contagem"
CHAVE_METRICAS_SOMA_MS: str = "metricas:soma_ms"

_cliente: redis.Redis | None = None


def cliente() -> redis.Redis:
    global _cliente
    if _cliente is None:
        _cliente = redis.from_url(REDIS_URL, decode_responses=True)
    return _cliente


def enfileirar(texto: str) -> str:
    """Coloca uma tarefa na fila e devolve o id para consulta posterior."""
    tarefa_id = str(uuid.uuid4())
    tarefa = json.dumps({"id": tarefa_id, "texto": texto})
    cliente().rpush(FILA_TAREFAS, tarefa)
    cliente().set(PREFIXO_RESULTADO + tarefa_id,
                  json.dumps({"status": "na_fila"}))
    return tarefa_id


def proxima_tarefa(timeout: int = 5) -> dict | None:
    """Bloqueia ate chegar tarefa (ou timeout). Usado pelo worker."""
    # cast: os stubs do redis-py descrevem blpop() como Awaitable | list
    # porque o metodo e compartilhado com o cliente assincrono; aqui o
    # cliente e sempre sincrono, entao o retorno real e list | None.
    item = cast(
        "list | None",
        cliente().blpop([FILA_TAREFAS], timeout=timeout),
    )
    if item is None:
        return None
    return json.loads(item[1])


def guardar_resultado(tarefa_id: str, resultado: dict) -> None:
    cliente().set(PREFIXO_RESULTADO + tarefa_id, json.dumps(resultado))


def buscar_resultado(tarefa_id: str) -> dict | None:
    # cast: mesmo motivo de proxima_tarefa - get() e sincrono aqui.
    bruto = cast(
        "str | None",
        cliente().get(PREFIXO_RESULTADO + tarefa_id),
    )
    return json.loads(bruto) if bruto else None


def registrar_latencia(tempo_ms: float) -> None:
    """Acumula a latencia de uma inferencia no contador global.

    Metricas sao um complemento observacional: se o Redis estiver fora do
    ar, a falha e ignorada em vez de derrubar a requisicao que a originou.
    """
    try:
        cliente().incr(CHAVE_METRICAS_CONTAGEM)
        cliente().incrbyfloat(CHAVE_METRICAS_SOMA_MS, tempo_ms)
    except RedisError:
        pass


def obter_metricas() -> dict:
    """Devolve a contagem e a latencia media das inferencias ja processadas
    por qualquer instancia (REST, gRPC ou worker)."""
    try:
        contagem = int(cliente().get(CHAVE_METRICAS_CONTAGEM) or 0)
        soma_ms = float(cliente().get(CHAVE_METRICAS_SOMA_MS) or 0.0)
    except RedisError:
        return {"contagem": 0, "latencia_media_ms": 0.0}

    media_ms = round(soma_ms / contagem, 2) if contagem else 0.0
    return {"contagem": contagem, "latencia_media_ms": media_ms}
