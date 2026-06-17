"""Testes das checagens de validade do teste A/B."""

import pandas as pd

from validacao import verificar_validade
from util import carrega


def _registro(data, grupo, gmv):
    return {"data": pd.Timestamp(data), "grupo": grupo, "compradores": 100,
            "comissao": 1000.0, "cashback": 300.0, "vendas_totais": float(gmv)}


def test_dataset_limpo_sem_critico():
    alertas = verificar_validade(carrega("C").df)
    assert "critico" not in [a.severidade for a in alertas]


def test_srm_exposicao_desbalanceada():
    linhas = [_registro(f"2011-01-{i+1:02d}", "Grupo 1", 50000) for i in range(20)]
    linhas += [_registro(f"2011-01-{i+1:02d}", "Grupo 2", 50000) for i in range(10)]
    alertas = verificar_validade(pd.DataFrame(linhas))
    assert any(a.severidade == "critico" for a in alertas)


def test_amostra_pequena_dispara_atencao():
    linhas = []
    for i in range(10):  # 10 < 14 dias recomendados
        linhas.append(_registro(f"2011-01-{i+1:02d}", "Grupo 1", 50000))
        linhas.append(_registro(f"2011-01-{i+1:02d}", "Grupo 2", 50000))
    alertas = verificar_validade(pd.DataFrame(linhas))
    assert any("Amostra pequena" in a.titulo for a in alertas)


def test_outlier_detectado():
    linhas = []
    for i in range(30):
        base = 50000 + (i % 5) * 1500  # variação natural -> MAD > 0
        linhas.append(_registro(f"2011-01-{i+1:02d}", "Grupo 1", base))
        linhas.append(_registro(f"2011-01-{i+1:02d}", "Grupo 2", base))
    linhas.append(_registro("2011-02-01", "Grupo 1", 600000))  # pico claro
    linhas.append(_registro("2011-02-01", "Grupo 2", 51000))
    alertas = verificar_validade(pd.DataFrame(linhas))
    assert any("anômalo" in a.titulo for a in alertas)
