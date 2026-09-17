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

REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
FILA_TAREFAS: str = "tarefas"
PREFIXO_RESULTADO: str = "resultado:"

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
