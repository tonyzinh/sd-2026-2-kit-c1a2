"""Testes de integracao para as rotas REST (extensoes opcionais)."""

from fastapi.testclient import TestClient

from app.api_rest import app


def test_predict_lote_devolve_um_resultado_por_texto() -> None:
    with TestClient(app) as cliente:
        resposta = cliente.post(
            "/predict-lote",
            json={"textos": ["o atendimento foi otimo", "produto pessimo"]},
        )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert len(corpo["resultados"]) == 2
    assert corpo["resultados"][0]["texto"] == "o atendimento foi otimo"
    assert corpo["resultados"][1]["texto"] == "produto pessimo"


def test_predict_lote_rejeita_texto_vazio_no_meio_da_lista() -> None:
    with TestClient(app) as cliente:
        resposta = cliente.post(
            "/predict-lote",
            json={"textos": ["texto valido", "   "]},
        )

    assert resposta.status_code == 400


def test_metricas_expoe_contagem_e_latencia_media() -> None:
    with TestClient(app) as cliente:
        resposta = cliente.get("/metricas")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert "contagem" in corpo
    assert "latencia_media_ms" in corpo
