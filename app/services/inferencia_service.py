from redis.exceptions import RedisError

from app import fila


class TextoInvalidoError(ValueError):
    """Texto recebido para inferência é inválido."""


class FilaIndisponivelError(RuntimeError):
    """Não foi possível acessar a infraestrutura da fila."""


class TarefaNaoEncontradaError(LookupError):
    """O identificador informado não corresponde a uma tarefa existente."""


def validar_texto(texto: str) -> str:
    """Valida e normaliza o texto recebido."""
    if not texto or not texto.strip():
        raise TextoInvalidoError("O texto não pode ser vazio.")

    return texto.strip()


def enfileirar_inferencia(texto: str) -> str:
    """Coloca uma inferência na fila."""
    try:
        return fila.enfileirar(texto)
    except RedisError as exc:
        raise FilaIndisponivelError(
            "Não foi possível enviar a tarefa para processamento."
        ) from exc


def submeter_inferencia(texto: str) -> str:
    """Orquestra a submissão de uma inferência."""
    texto_validado = validar_texto(texto)
    return enfileirar_inferencia(texto_validado)


def consultar_resultado(tarefa_id: str) -> dict:
    """Consulta o estado ou resultado de uma tarefa."""
    try:
        resultado = fila.buscar_resultado(tarefa_id)
    except RedisError as exc:
        raise FilaIndisponivelError(
            "Não foi possível consultar a tarefa."
        ) from exc

    if resultado is None:
        raise TarefaNaoEncontradaError(
            f"Tarefa '{tarefa_id}' não encontrada."
        )

    return resultado