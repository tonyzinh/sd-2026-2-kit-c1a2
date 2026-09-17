"""Testes unitarios para a extensao opcional de cache (app.modelo)."""

from app.modelo import ModeloComCache


class ModeloContador:
    """Duplo de teste que conta quantas vezes prever() foi chamado."""

    def __init__(self) -> None:
        self.chamadas = 0

    def prever(self, texto: str) -> dict:
        self.chamadas += 1
        return {"texto": texto, "sentimento": "positivo", "confianca": 0.9}


def test_textos_repetidos_reaproveitam_o_resultado_em_cache() -> None:
    modelo_base = ModeloContador()
    modelo = ModeloComCache(modelo_base)

    modelo.prever("bom dia")
    modelo.prever("bom dia")
    modelo.prever("bom dia")

    assert modelo_base.chamadas == 1


def test_textos_diferentes_nao_compartilham_cache() -> None:
    modelo_base = ModeloContador()
    modelo = ModeloComCache(modelo_base)

    modelo.prever("bom dia")
    modelo.prever("boa noite")

    assert modelo_base.chamadas == 2


def test_resultado_cacheado_e_uma_copia_independente() -> None:
    modelo = ModeloComCache(ModeloContador())

    primeiro = modelo.prever("bom dia")
    primeiro["status"] = "pronto"

    segundo = modelo.prever("bom dia")

    assert "status" not in segundo
