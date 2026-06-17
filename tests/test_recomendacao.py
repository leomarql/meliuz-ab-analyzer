"""Testes da sugestão de próximo teste por elasticidade do cashback."""

from types import SimpleNamespace

from recomendacao import sugerir_proximo_teste
from util import analisa


def _v(cashback_rate, lucro_dia):
    return SimpleNamespace(cashback_rate=cashback_rate, lucro_dia=lucro_dia)


def test_padrao_cai_nos_dados_reais():
    # Nos três datasets o lucro sobe quando o cashback cai.
    for nome in ["A", "B", "C"]:
        _, ana = analisa(nome)
        assert sugerir_proximo_teste(ana.metricas).padrao == "cai"


def test_padrao_sobe():
    metricas = [_v(0.03, 100), _v(0.05, 200), _v(0.07, 300)]
    assert sugerir_proximo_teste(metricas).padrao == "sobe"


def test_padrao_intermediario():
    metricas = [_v(0.03, 100), _v(0.05, 300), _v(0.07, 150)]
    assert sugerir_proximo_teste(metricas).padrao == "intermediario"


def test_uma_variante_indefinido():
    assert sugerir_proximo_teste([_v(0.05, 100)]).padrao == "indefinido"
