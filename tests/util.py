"""Utilitários compartilhados pelos testes — carregam os datasets reais."""

import os

from ingestao import carregar_dataset
from analise_engine import analisar

_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

CAMINHOS = {
    "A": os.path.join(_DATA, "dataset_01_parceiroA.csv"),
    "B": os.path.join(_DATA, "dataset_02_parceiroB.csv"),
    "C": os.path.join(_DATA, "dataset_03_parceiroC.csv"),
}


def carrega(nome):
    """Retorna o ResultadoIngestao do parceiro (A, B ou C)."""
    return carregar_dataset(CAMINHOS[nome])


def analisa(nome):
    """Retorna (ingestao, analise) do parceiro."""
    ing = carrega(nome)
    return ing, analisar(ing.df, ing.parceiro)
