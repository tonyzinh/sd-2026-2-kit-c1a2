"""
Interface REST do servico de inferencia.

- carregamento do modelo UMA vez, na subida
- POST /predict-sync -> inferencia sincrona
- POST /predict-lote -> inferencia sincrona para varios textos (extensao)
- POST /predict -> enfileira a tarefa e devolve o id (assincrono)
- GET /resultado/{id} -> devolve o resultado quando estiver pronto
- GET /metricas -> contagem e latencia media das inferencias (extensao)

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

from app import fila
from app.modelo import ModeloPrevisor, carregar_modelo
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


modelo: ModeloPrevisor | None = None


class Entrada(BaseModel):
    texto: str


class EntradaLote(BaseModel):
    textos: list[str]


def obter_modelo() -> ModeloPrevisor:
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

    fila.registrar_latencia(resultado["tempo_ms"])

    logger.info(
        "REST POST /predict-sync | tamanho=%s | tempo_ms=%s",
        len(texto_validado),
        resultado["tempo_ms"],
    )

    return resultado


@app.post("/predict-lote")
def predict_lote(entrada: EntradaLote) -> dict:
    """
    Extensao opcional: executa a inferencia (sincrona) para varios textos
    numa unica chamada REST. Equivalente ao RPC gRPC PreverLote.
    """
    inicio = time.perf_counter()

    textos_validados = [validar_texto(texto) for texto in entrada.textos]

    resultados = [
        obter_modelo().prever(texto) for texto in textos_validados
    ]

    tempo_ms = round(
        (time.perf_counter() - inicio) * 1000,
        2,
    )

    fila.registrar_latencia(tempo_ms)

    logger.info(
        "REST POST /predict-lote | quantidade=%s | tempo_ms=%s",
        len(textos_validados),
        tempo_ms,
    )

    return {
        "resultados": resultados,
        "tempo_ms": tempo_ms,
    }


@app.get("/metricas")
def metricas() -> dict:
    """
    Extensao opcional: numero de inferencias processadas e a latencia media,
    agregados entre TODAS as instancias (REST, gRPC e workers).
    """
    return fila.obter_metricas()


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