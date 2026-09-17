"""
Interface REST do servico de inferencia.

O QUE JA ESTA PRONTO:
- carregamento do modelo UMA vez, na subida
- rota sincrona /predict-sync, usada no laboratorio da Aula 6

TAREFAS:
- POST /predict -> colocar na fila e devolver o id
- GET /resultado/{id} -> devolver o resultado quando estiver pronto

Rodar:
    uvicorn app.api_rest:app --reload --host 0.0.0.0 --port 8000

Docs:
    http://localhost:8000/docs
"""

import logging
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.modelo import ModeloSentimento, carregar_modelo
from app.services.inferencia_service import (
    FilaIndisponivelError,
    TarefaNaoEncontradaError,
    TextoInvalidoError,
    consultar_resultado,
    submeter_inferencia,
    validar_texto,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)


app = FastAPI(
    title="Servico de Inferencia - C1.A2",
    version="0.1.0",
)


modelo: ModeloSentimento | None = None


class Entrada(BaseModel):
    texto: str


def obter_modelo() -> ModeloSentimento:
    """Devolve o modelo carregado ou falha se o startup ainda nao rodou."""
    if modelo is None:
        raise RuntimeError("Modelo ainda nao foi carregado.")
    return modelo


@app.exception_handler(TextoInvalidoError)
async def tratar_texto_invalido(
    request: Request,
    exc: TextoInvalidoError,
) -> JSONResponse:
    logger.warning(
        "REST erro de validacao | rota=%s | erro=%s",
        request.url.path,
        exc,
    )

    return JSONResponse(
        status_code=400,
        content={
            "detail": str(exc),
        },
    )


@app.exception_handler(TarefaNaoEncontradaError)
async def tratar_tarefa_nao_encontrada(
    request: Request,
    exc: TarefaNaoEncontradaError,
) -> JSONResponse:
    logger.warning(
        "REST tarefa nao encontrada | rota=%s | erro=%s",
        request.url.path,
        exc,
    )

    return JSONResponse(
        status_code=404,
        content={
            "detail": str(exc),
        },
    )


@app.exception_handler(FilaIndisponivelError)
async def tratar_fila_indisponivel(
    request: Request,
    exc: FilaIndisponivelError,
) -> JSONResponse:
    logger.error(
        "REST fila indisponivel | rota=%s | erro=%s",
        request.url.path,
        exc,
    )

    return JSONResponse(
        status_code=503,
        content={
            "detail": str(exc),
        },
    )


@app.on_event("startup")
def _subir() -> None:
    """
    Carrega o modelo uma unica vez no startup.
    """
    global modelo

    inicio = time.perf_counter()

    modelo = carregar_modelo()

    tempo_ms = round(
        (time.perf_counter() - inicio) * 1000,
        2,
    )

    logger.info(
        "REST startup | modelo carregado | tempo_ms=%s",
        tempo_ms,
    )


@app.get("/saude")
def saude() -> dict:
    """
    Informa se a API esta ativa e se o modelo foi carregado.
    """
    logger.info(
        "REST GET /saude | modelo_carregado=%s",
        modelo is not None,
    )

    return {
        "status": "ok",
        "modelo_carregado": modelo is not None,
    }


@app.post("/predict-sync")
def predict_sync(entrada: Entrada) -> dict:
    """
    Executa inferencia sincrona.
    O cliente aguarda a resposta.
    """
    texto_validado = validar_texto(entrada.texto)

    inicio = time.perf_counter()

    resultado = obter_modelo().prever(
        texto_validado,
    )

    resultado["tempo_ms"] = round(
        (time.perf_counter() - inicio) * 1000,
        2,
    )

    logger.info(
        "REST POST /predict-sync | tamanho=%s | tempo_ms=%s",
        len(texto_validado),
        resultado["tempo_ms"],
    )

    return resultado


@app.post("/predict", status_code=202)
def predict(entrada: Entrada) -> dict:
    """
    Submete uma inferencia para processamento assincrono.
    """
    inicio = time.perf_counter()

    tarefa_id = submeter_inferencia(
        entrada.texto,
    )

    tempo_ms = round(
        (time.perf_counter() - inicio) * 1000,
        2,
    )

    logger.info(
        "REST POST /predict | id=%s | tamanho=%s | tempo_ms=%s",
        tarefa_id,
        len(entrada.texto),
        tempo_ms,
    )

    return {
        "id": tarefa_id,
    }


@app.get("/resultado/{tarefa_id}")
def resultado(tarefa_id: str) -> dict:
    """
    Consulta o estado ou resultado de uma inferencia.
    """
    inicio = time.perf_counter()

    resposta = consultar_resultado(
        tarefa_id,
    )

    tempo_ms = round(
        (time.perf_counter() - inicio) * 1000,
        2,
    )

    logger.info(
        "REST GET /resultado/%s | status=%s | tempo_ms=%s",
        tarefa_id,
        resposta.get("status"),
        tempo_ms,
    )

    return resposta