"""Testes da ingestão: parser de moeda BR, limpeza e detecção de variantes."""

import math

import pytest

from ingestao import parse_moeda_br, carregar_dataset
from util import carrega


@pytest.mark.parametrize("entrada,esperado", [
    ("R$ 10.273", 10273.0),
    ("10.273", 10273.0),
    ("R$ 1.234,56", 1234.56),
    ("1.234.567", 1234567.0),
    ("-R$ 50", -50.0),
    (1500, 1500.0),
    (12.5, 12.5),
])
def test_parse_moeda_validos(entrada, esperado):
    assert abs(parse_moeda_br(entrada) - esperado) < 1e-6


@pytest.mark.parametrize("entrada", ["", "abc", "-", None, "nan"])
def test_parse_moeda_invalidos_viram_nan(entrada):
    assert math.isnan(parse_moeda_br(entrada))


def test_datasets_reais_carregam_sem_descarte():
    for nome in ["A", "B", "C"]:
        ing = carrega(nome)
        assert ing.linhas_validas == ing.linhas_originais
        assert ing.taxa_descarte == 0.0


def test_deteccao_dinamica_de_variantes():
    assert len(carrega("A").grupos) == 3
    assert len(carrega("B").grupos) == 3
    assert len(carrega("C").grupos) == 2


def test_remove_linhas_ruins(tmp_path):
    csv = tmp_path / "sujo.csv"
    csv.write_text(
        "Data,Grupos de usuários,Parceiro,compradores,comissão,cashback,vendas totais\n"
        "2011-01-01,Grupo 1,P,196,R$ 10.273,R$ 3.267,R$ 93.390\n"
        "2011-13-99,Grupo 1,P,100,R$ 5.000,R$ 1.000,R$ 40.000\n"   # data inválida
        "2011-01-03,,P,82,R$ 4.839,R$ 1.358,R$ 43.993\n"           # grupo vazio
        "2011-01-04,Grupo 2,P,-5,R$ 1.000,R$ 200,R$ 9.000\n"       # compradores negativo
        "2011-01-05,Grupo 2,P,120,R$ abc,R$ 800,R$ 30.000\n",      # comissão inválida
        encoding="utf-8")
    ing = carregar_dataset(str(csv))
    assert ing.linhas_validas == 1
    assert ing.linhas_descartadas == 4


def test_colunas_obrigatorias_faltando(tmp_path):
    csv = tmp_path / "incompleto.csv"
    csv.write_text("Data,Parceiro\n2011-01-01,P\n", encoding="utf-8")
    with pytest.raises(ValueError):
        carregar_dataset(str(csv))
