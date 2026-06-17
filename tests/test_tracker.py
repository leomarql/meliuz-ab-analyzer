"""Testes do tracker: colunas mínimas exigidas e upsert do CSV."""

import csv

from tracker import COLUNAS, montar_linha, registrar_csv
from util import analisa


def test_colunas_minimas_presentes():
    # O case exige no mínimo: nome, descrição, resultado e decisão.
    for c in ["nome_do_teste", "descricao", "resultado", "decisao"]:
        assert c in COLUNAS


def test_montar_linha_preenche_campos_exigidos():
    ing, ana = analisa("A")
    linha = montar_linha(ing, ana)
    for c in ["nome_do_teste", "descricao", "resultado", "decisao"]:
        assert linha[c].strip() != ""


def test_csv_upsert_nao_duplica(tmp_path):
    ing, ana = analisa("A")
    linha = montar_linha(ing, ana)
    caminho = str(tmp_path / "tracker.csv")

    registrar_csv(linha, caminho)
    registrar_csv(linha, caminho)  # mesmo teste de novo -> atualiza, não duplica
    linhas = list(csv.DictReader(open(caminho, encoding="utf-8")))
    assert len(linhas) == 1

    outro = dict(linha)
    outro["nome_do_teste"] = "Cashback Parceiro Z — teste diferente"
    registrar_csv(outro, caminho)  # teste novo -> acrescenta linha
    linhas = list(csv.DictReader(open(caminho, encoding="utf-8")))
    assert len(linhas) == 2
