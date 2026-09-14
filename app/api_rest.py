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

import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.modelo import carregar_modelo
from app.services.inferencia_service import (
    FilaIndisponivelError,
    TarefaNaoEncontradaError,
    TextoInvalidoError,
    consultar_resultado,
    submeter_inferencia,
)


app = FastAPI(
    title="Servico de Inferencia - C1.A2",
    version="0.1.0",
)


modelo = None


class Entrada(BaseModel):
    texto: str


@app.exception_handler(TextoInvalidoError)
async def tratar_texto_invalido(
    request: Request,
    exc: TextoInvalidoError,
):
    return JSONResponse(
        status_code=400,
        content={"detail": str(exc)},
    )


@app.exception_handler(TarefaNaoEncontradaError)
async def tratar_tarefa_nao_encontrada(
    request: Request,
    exc: TarefaNaoEncontradaError,
):
    return JSONResponse(
        status_code=404,
        content={"detail": str(exc)},
    )


@app.exception_handler(FilaIndisponivelError)
async def tratar_fila_indisponivel(
    request: Request,
    exc: FilaIndisponivelError,
):
    return JSONResponse(
        status_code=503,
        content={"detail": str(exc)},
    )


@app.on_event("startup")
def _subir():
    """Carrega o modelo UMA vez. Este e o ponto-chave da Aula 6."""
    global modelo

    inicio = time.time()
    modelo = carregar_modelo()

    print(
        f"[startup] modelo carregado em "
        f"{time.time() - inicio:.3f}s"
    )


@app.get("/saude")
def saude():
    return {
        "status": "ok",
        "modelo_carregado": modelo is not None,
    }


@app.post("/predict-sync")
def predict_sync(entrada: Entrada):
    """Inferencia SINCRONA: o cliente espera a resposta."""
    if not entrada.texto.strip():
        raise HTTPException(
            status_code=400,
            detail="texto vazio",
        )

    inicio = time.time()

    resultado = modelo.prever(entrada.texto)

    resultado["tempo_ms"] = round(
        (time.time() - inicio) * 1000,
        2,
    )

    return resultado


@app.post("/predict", status_code=202)
def predict(entrada: Entrada):
    """Submete uma inferencia para processamento assincrono."""
    return {
        "id": submeter_inferencia(entrada.texto)
    }


@app.get("/resultado/{tarefa_id}")
def resultado(tarefa_id: str):
    """Consulta o estado ou resultado de uma inferencia."""
    return consultar_resultado(tarefa_id)