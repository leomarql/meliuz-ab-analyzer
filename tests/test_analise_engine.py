"""Testes do motor: métricas, decisão, ordenação, intervalo de confiança."""

from util import analisa


def test_vencedor_e_confianca():
    # Nos três datasets, o Grupo 1 vence com alta confiança.
    for nome in ["A", "B", "C"]:
        _, ana = analisa(nome)
        assert ana.vencedor == "Grupo 1"
        assert ana.confianca == "Alta"
        assert ana.significativo is True


def test_metricas_consistentes():
    # lucro/dia deve ser igual a comissão/dia menos cashback/dia.
    _, ana = analisa("A")
    for m in ana.metricas:
        assert abs(m.lucro_dia - (m.comissao_dia - m.cashback_dia)) < 1.0


def test_metricas_ordenadas_por_lucro():
    _, ana = analisa("A")
    lucros = [m.lucro_dia for m in ana.metricas]
    assert lucros == sorted(lucros, reverse=True)


def test_intervalo_de_confianca_contem_impacto():
    for nome in ["A", "B", "C"]:
        _, ana = analisa(nome)
        lo, hi = ana.ic95_impacto
        assert lo < hi
        assert lo <= ana.impacto_dia <= hi


def test_break_even_lift_indefinido():
    # No Parceiro C o 2º colocado fica em ~zero, então o lift % é indefinido.
    _, ana = analisa("C")
    assert ana.lift_pct is None
    assert ana.impacto_dia > 0
