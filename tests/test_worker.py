"""Testes unitarios para app.worker (retentativa e dead-letter)."""

import json

import pytest

from app import fila, worker


class FakeRedisClient:
    """Duplo de teste que registra as filas sem depender de Redis real."""

    def __init__(self) -> None:
        self.filas: dict[str, list[str]] = {}

    def rpush(self, nome_fila: str, valor: str) -> None:
        self.filas.setdefault(nome_fila, []).append(valor)


@pytest.fixture()
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> FakeRedisClient:
    cliente_fake = FakeRedisClient()
    monkeypatch.setattr(fila, "cliente", lambda: cliente_fake)
    return cliente_fake


def test_incrementar_tentativas_nao_altera_tarefa_original() -> None:
    tarefa = {"id": "t1", "texto": "ola"}

    tarefa_atualizada = worker.incrementar_tentativas(tarefa)

    assert tarefa_atualizada["tentativas"] == 1
    assert "tentativas" not in tarefa


def test_processar_falha_reenfileira_antes_do_limite(
    fake_redis: FakeRedisClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resultados_salvos: dict[str, dict] = {}
    monkeypatch.setattr(
        fila,
        "guardar_resultado",
        lambda tarefa_id, resultado: resultados_salvos.__setitem__(
            tarefa_id, resultado
        ),
    )

    tarefa = {"id": "t1", "texto": "ola", "tentativas": 0}

    worker.processar_falha(tarefa, ValueError("falha temporaria"))

    reenfileirada = json.loads(fake_redis.filas[fila.FILA_TAREFAS][0])
    assert reenfileirada["tentativas"] == 1
    assert resultados_salvos["t1"]["status"] == "retentando"
    assert worker.FILA_DEAD_LETTER not in fake_redis.filas


def test_processar_falha_envia_para_dead_letter_apos_limite(
    fake_redis: FakeRedisClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resultados_salvos: dict[str, dict] = {}
    monkeypatch.setattr(
        fila,
        "guardar_resultado",
        lambda tarefa_id, resultado: resultados_salvos.__setitem__(
            tarefa_id, resultado
        ),
    )

    tarefa = {
        "id": "t1",
        "texto": "ola",
        "tentativas": worker.MAX_TENTATIVAS - 1,
    }

    worker.processar_falha(tarefa, ValueError("falha definitiva"))

    assert fila.FILA_TAREFAS not in fake_redis.filas
    mensagem = json.loads(fake_redis.filas[worker.FILA_DEAD_LETTER][0])
    assert mensagem["tentativas"] == worker.MAX_TENTATIVAS
    assert mensagem["erro"] == "falha definitiva"
    assert resultados_salvos["t1"]["status"] == "erro"


def test_processar_tarefa_salva_resultado_em_caso_de_sucesso(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resultados_salvos: dict[str, dict] = {}
    monkeypatch.setattr(
        fila,
        "guardar_resultado",
        lambda tarefa_id, resultado: resultados_salvos.__setitem__(
            tarefa_id, resultado
        ),
    )

    class ModeloFalso:
        def prever(self, texto: str) -> dict:
            return {
                "texto": texto,
                "sentimento": "positivo",
                "confianca": 0.9,
            }

    tarefa = {"id": "t1", "texto": "ola mundo"}

    worker.processar_tarefa(ModeloFalso(), tarefa)

    assert resultados_salvos["t1"]["status"] == "pronto"
    assert resultados_salvos["t1"]["sentimento"] == "positivo"
