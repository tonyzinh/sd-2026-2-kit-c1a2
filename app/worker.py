"""
Worker: consome a fila e executa a inferencia.

Responsabilidades:
- consumir tarefas pendentes
- executar inferencia
- persistir resultados
- realizar retentativas em caso de falha
- encaminhar tarefas definitivamente falhas para dead-letter

Rodar:
    python -m app.worker

Mais de um worker pode ser executado simultaneamente.
"""

import json
import logging
import time

from app import fila
from app.modelo import carregar_modelo


MAX_TENTATIVAS = 3
FILA_DEAD_LETTER = "tarefas:dead-letter"


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


def executar_inferencia(modelo, texto: str) -> dict:
    """Executa a inferencia e devolve o resultado com a latencia."""
    inicio = time.perf_counter()

    resultado = modelo.prever(texto)

    resultado["status"] = "pronto"
    resultado["tempo_ms"] = round(
        (time.perf_counter() - inicio) * 1000,
        2,
    )

    return resultado


def salvar_resultado(tarefa_id: str, resultado: dict) -> None:
    """Persiste o resultado final de uma tarefa."""
    fila.guardar_resultado(
        tarefa_id,
        resultado,
    )


def obter_tarefa():
    """Obtém a próxima tarefa pendente."""
    return fila.proxima_tarefa(timeout=5)


def obter_numero_tentativas(tarefa: dict) -> int:
    """Obtém quantas tentativas de processamento já foram realizadas."""
    return tarefa.get("tentativas", 0)


def incrementar_tentativas(tarefa: dict) -> dict:
    """Cria uma nova representação da tarefa com a tentativa incrementada."""
    tarefa_atualizada = tarefa.copy()

    tarefa_atualizada["tentativas"] = (
        obter_numero_tentativas(tarefa) + 1
    )

    return tarefa_atualizada


def reenfileirar(tarefa: dict) -> None:
    """Devolve uma tarefa para a fila principal."""
    fila.cliente().rpush(
        fila.FILA_TAREFAS,
        json.dumps(tarefa),
    )


def enviar_para_dead_letter(tarefa: dict, erro: Exception) -> None:
    """Envia uma tarefa definitivamente falha para a dead-letter."""
    mensagem = {
        **tarefa,
        "erro": str(erro),
    }

    fila.cliente().rpush(
        FILA_DEAD_LETTER,
        json.dumps(mensagem),
    )


def registrar_status_retentativa(tarefa: dict) -> None:
    """Atualiza o estado visível ao cliente durante uma retentativa."""
    fila.guardar_resultado(
        tarefa["id"],
        {
            "status": "retentando",
            "tentativas": tarefa["tentativas"],
        },
    )


def registrar_status_erro(
    tarefa: dict,
    erro: Exception,
) -> None:
    """Registra o estado final de uma tarefa que falhou."""
    fila.guardar_resultado(
        tarefa["id"],
        {
            "status": "erro",
            "tentativas": tarefa["tentativas"],
            "erro": str(erro),
        },
    )


def processar_falha(
    tarefa: dict,
    erro: Exception,
) -> None:
    """Decide entre retentativa ou envio para dead-letter."""
    tarefa_atualizada = incrementar_tentativas(tarefa)

    tentativas = tarefa_atualizada["tentativas"]

    if tentativas < MAX_TENTATIVAS:
        registrar_status_retentativa(tarefa_atualizada)
        reenfileirar(tarefa_atualizada)

        logger.warning(
            "tarefa=%s falhou | tentativa=%s/%s | erro=%s",
            tarefa["id"],
            tentativas,
            MAX_TENTATIVAS,
            erro,
        )

        return

    enviar_para_dead_letter(
        tarefa_atualizada,
        erro,
    )

    registrar_status_erro(
        tarefa_atualizada,
        erro,
    )

    logger.error(
        "tarefa=%s enviada para dead-letter "
        "| tentativas=%s | erro=%s",
        tarefa["id"],
        tentativas,
        erro,
    )


def processar_tarefa(
    modelo,
    tarefa: dict,
) -> None:
    """Coordena o processamento de uma única tarefa."""
    try:
        resultado = executar_inferencia(
            modelo,
            tarefa["texto"],
        )

        salvar_resultado(
            tarefa["id"],
            resultado,
        )

        logger.info(
            "tarefa=%s processada | tamanho=%s | tempo_ms=%s",
            tarefa["id"],
            len(tarefa["texto"]),
            resultado["tempo_ms"],
        )

    except Exception as erro:  # noqa: BLE001
        processar_falha(
            tarefa,
            erro,
        )


def main() -> None:
    """Inicializa o worker e mantém o consumo da fila."""
    logger.info("carregando modelo")

    modelo = carregar_modelo()

    logger.info(
        "worker pronto | aguardando tarefas "
        "(Ctrl+C para sair)"
    )

    while True:
        tarefa = obter_tarefa()

        if tarefa is None:
            continue

        logger.info(
            "tarefa=%s recebida",
            tarefa["id"],
        )

        processar_tarefa(
            modelo,
            tarefa,
        )


if __name__ == "__main__":
    main()