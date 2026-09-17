"""Teste de integracao: REST e gRPC devem devolver o mesmo resultado.

Requer os stubs gRPC gerados (veja README) - se nao existirem, o teste
e pulado com uma mensagem explicando o pre-requisito.
"""

import pytest
from fastapi.testclient import TestClient

inferencia_pb2 = pytest.importorskip(
    "inferencia_pb2",
    reason="gere os stubs gRPC antes de rodar este teste (veja README).",
)

from app.api_rest import app  # noqa: E402
from app.servidor_grpc import ServicoInferencia  # noqa: E402


class ContextoFalso:
    """Duplo de teste para grpc.ServicerContext: aborta levantando erro."""

    def abort(self, code: object, details: str) -> None:
        raise RuntimeError(f"{code}: {details}")


@pytest.mark.parametrize(
    "texto",
    [
        "o atendimento foi excelente e muito rapido",
        "produto pessimo, nao recomendo",
    ],
)
def test_rest_e_grpc_devolvem_o_mesmo_resultado(texto: str) -> None:
    with TestClient(app) as cliente_rest:
        resposta_rest = cliente_rest.post(
            "/predict-sync", json={"texto": texto}
        ).json()

    servico_grpc = ServicoInferencia()
    resposta_grpc = servico_grpc.Prever(
        inferencia_pb2.PedidoPrever(texto=texto),
        ContextoFalso(),
    )

    assert resposta_rest["sentimento"] == resposta_grpc.sentimento
    assert resposta_rest["confianca"] == pytest.approx(
        resposta_grpc.confianca
    )


def test_grpc_rejeita_texto_vazio_como_o_rest() -> None:
    with TestClient(app) as cliente_rest:
        resposta_rest = cliente_rest.post(
            "/predict-sync", json={"texto": "   "}
        )

    assert resposta_rest.status_code == 400

    servico_grpc = ServicoInferencia()
    with pytest.raises(RuntimeError):
        servico_grpc.Prever(
            inferencia_pb2.PedidoPrever(texto="   "),
            ContextoFalso(),
        )
