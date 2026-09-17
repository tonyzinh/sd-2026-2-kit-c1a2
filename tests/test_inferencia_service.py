"""Testes unitarios para app.services.inferencia_service."""

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app import fila
from app.services import inferencia_service as service


def test_validar_texto_remove_espacos_nas_bordas() -> None:
    assert service.validar_texto("  ola mundo  ") == "ola mundo"


@pytest.mark.parametrize("texto_invalido", ["", "   "])
def test_validar_texto_rejeita_texto_vazio(texto_invalido: str) -> None:
    with pytest.raises(service.TextoInvalidoError):
        service.validar_texto(texto_invalido)


def test_submeter_inferencia_enfileira_texto_validado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    textos_recebidos: list[str] = []

    def fake_enfileirar(texto: str) -> str:
        textos_recebidos.append(texto)
        return "tarefa-123"

    monkeypatch.setattr(fila, "enfileirar", fake_enfileirar)

    tarefa_id = service.submeter_inferencia("  bom dia  ")

    assert tarefa_id == "tarefa-123"
    assert textos_recebidos == ["bom dia"]


def test_submeter_inferencia_rejeita_texto_vazio_sem_tocar_fila(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fila_nao_deveria_ser_chamada(texto: str) -> str:
        raise AssertionError(
            "fila nao deveria ser chamada para texto invalido"
        )

    monkeypatch.setattr(fila, "enfileirar", fila_nao_deveria_ser_chamada)

    with pytest.raises(service.TextoInvalidoError):
        service.submeter_inferencia("   ")


def test_submeter_inferencia_traduz_falha_de_infraestrutura(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fila_indisponivel(texto: str) -> str:
        raise RedisConnectionError("redis fora do ar")

    monkeypatch.setattr(fila, "enfileirar", fila_indisponivel)

    with pytest.raises(service.FilaIndisponivelError):
        service.submeter_inferencia("ola")


def test_consultar_resultado_encontrado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        fila, "buscar_resultado", lambda tarefa_id: {"status": "pronto"}
    )

    resultado = service.consultar_resultado("tarefa-1")

    assert resultado == {"status": "pronto"}


def test_consultar_resultado_nao_encontrado(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fila, "buscar_resultado", lambda tarefa_id: None)

    with pytest.raises(service.TarefaNaoEncontradaError):
        service.consultar_resultado("inexistente")


def test_consultar_resultado_traduz_falha_de_infraestrutura(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fila_indisponivel(tarefa_id: str) -> dict | None:
        raise RedisConnectionError("redis fora do ar")

    monkeypatch.setattr(fila, "buscar_resultado", fila_indisponivel)

    with pytest.raises(service.FilaIndisponivelError):
        service.consultar_resultado("tarefa-1")
