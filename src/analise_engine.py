"""
Motor de análise de testes A/B de cashback.

Recebe os dados já limpos (src/ingestao) e produz:
- métricas por variante (volume, receita, custo, eficiência);
- a decisão: qual variante escalar para 100% do tráfego;
- a base estatística da decisão (significância e confiança).

Métrica primária de decisão: LUCRO LÍQUIDO = comissão - cashback.
É a receita que o Méliuz recebe do parceiro menos o custo do incentivo pago
ao usuário. Maximizá-la é o objetivo ao escolher o nível de cashback a escalar.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy import stats

ALPHA = 0.05  # nível de significância para a decisão


@dataclass
class MetricasVariante:
    grupo: str
    n_dias: int
    compradores_total: float
    compradores_dia: float
    comissao_total: float
    comissao_dia: float
    cashback_total: float
    cashback_dia: float
    gmv_total: float
    gmv_dia: float
    lucro_total: float          # comissão - cashback (acumulado)
    lucro_dia: float            # média diária do lucro líquido  <- PRIMÁRIA
    ticket_medio: float         # GMV / comprador
    take_rate: float            # comissão / GMV
    cashback_rate: float        # cashback / GMV
    lucro_por_comprador: float  # lucro líquido / comprador


@dataclass
class ResultadoAnalise:
    parceiro: str
    periodo: tuple
    metricas: list                      # list[MetricasVariante], ordenada por lucro_dia desc
    vencedor: str
    vice: str | None
    lift_pct: float | None              # ganho % do vencedor sobre o vice (lucro/dia)
    p_valor: float | None               # teste pareado vencedor vs vice
    p_valor_wilcoxon: float | None      # backup não-paramétrico
    teste_usado: str
    significativo: bool
    confianca: str                      # "Alta" | "Moderada" | "Inconclusivo"
    decisao: str                        # frase acionável
    tradeoffs: list = field(default_factory=list)  # alertas de trade-off
    impacto_dia: float | None = None    # R$/dia adicionais do vencedor sobre o vice

    @property
    def resumo_uma_linha(self) -> str:
        return f"{self.decisao} (confiança: {self.confianca})."


def _metricas_grupo(df_g: pd.DataFrame) -> MetricasVariante:
    df_g = df_g.copy()
    df_g["lucro"] = df_g["comissao"] - df_g["cashback"]

    compradores_total = float(df_g["compradores"].sum())
    comissao_total = float(df_g["comissao"].sum())
    cashback_total = float(df_g["cashback"].sum())
    gmv_total = float(df_g["vendas_totais"].sum())
    lucro_total = comissao_total - cashback_total
    n_dias = int(len(df_g))

    def por_dia(total):
        return total / n_dias if n_dias else float("nan")

    def razao(num, den):
        return num / den if den else float("nan")

    return MetricasVariante(
        grupo=str(df_g["grupo"].iloc[0]),
        n_dias=n_dias,
        compradores_total=compradores_total,
        compradores_dia=por_dia(compradores_total),
        comissao_total=comissao_total,
        comissao_dia=por_dia(comissao_total),
        cashback_total=cashback_total,
        cashback_dia=por_dia(cashback_total),
        gmv_total=gmv_total,
        gmv_dia=por_dia(gmv_total),
        lucro_total=lucro_total,
        lucro_dia=por_dia(lucro_total),
        ticket_medio=razao(gmv_total, compradores_total),
        take_rate=razao(comissao_total, gmv_total),
        cashback_rate=razao(cashback_total, gmv_total),
        lucro_por_comprador=razao(lucro_total, compradores_total),
    )


def _serie_lucro_diario(df: pd.DataFrame, grupo: str) -> pd.Series:
    d = df[df["grupo"] == grupo].copy()
    d["lucro"] = d["comissao"] - d["cashback"]
    return d.set_index("data")["lucro"]


def analisar(df: pd.DataFrame, parceiro: str) -> ResultadoAnalise:
    """
    Analisa um teste A/B já limpo e devolve a decisão de qual variante escalar.

    Estatística: como as variantes rodam em paralelo nas mesmas datas, usamos um
    teste PAREADO por data (t pareado) entre o 1º e o 2º colocados em lucro/dia,
    com Wilcoxon como reforço não-paramétrico. Se as datas não casarem, caímos
    para o teste de Welch (amostras independentes).
    """
    grupos = sorted(df["grupo"].unique().tolist())
    metricas = [_metricas_grupo(df[df["grupo"] == g]) for g in grupos]
    metricas.sort(key=lambda m: m.lucro_dia, reverse=True)

    periodo = (df["data"].min().date(), df["data"].max().date())
    vencedor = metricas[0].grupo

    # Caso degenerado: só uma variante -> nada a comparar.
    if len(metricas) < 2:
        return ResultadoAnalise(
            parceiro=parceiro, periodo=periodo, metricas=metricas,
            vencedor=vencedor, vice=None, lift_pct=None, p_valor=None,
            p_valor_wilcoxon=None, teste_usado="—", significativo=False,
            confianca="Inconclusivo",
            decisao=f"Apenas uma variante ({vencedor}); sem comparação possível",
        )

    vice = metricas[1].grupo
    lucro_venc, lucro_vice = metricas[0].lucro_dia, metricas[1].lucro_dia
    impacto_dia = lucro_venc - lucro_vice
    # Lift % é indefinido quando o vice está em ~zero; nesse caso usamos só o
    # impacto absoluto (R$/dia) para comunicar o ganho.
    lift_pct = (impacto_dia / abs(lucro_vice)) if abs(lucro_vice) > 1e-6 else None

    # --- Teste estatístico: pareado por data quando possível ---
    s_venc = _serie_lucro_diario(df, vencedor)
    s_vice = _serie_lucro_diario(df, vice)
    pareado = pd.concat([s_venc, s_vice], axis=1, join="inner", keys=["v", "u"]).dropna()

    p_wilcoxon = None
    if len(pareado) >= 5 and (pareado["v"] - pareado["u"]).abs().sum() > 0:
        t_stat, p_val = stats.ttest_rel(pareado["v"], pareado["u"])
        teste = f"t pareado por data (n={len(pareado)} dias)"
        try:
            _, p_wilcoxon = stats.wilcoxon(pareado["v"], pareado["u"])
        except ValueError:
            p_wilcoxon = None
    else:
        t_stat, p_val = stats.ttest_ind(s_venc.dropna(), s_vice.dropna(), equal_var=False)
        teste = f"Welch (independentes, n={s_venc.notna().sum()} vs {s_vice.notna().sum()})"

    significativo = bool(np.isfinite(p_val) and p_val < ALPHA)
    if not np.isfinite(p_val):
        confianca = "Inconclusivo"
    elif p_val < 0.01:
        confianca = "Alta"
    elif p_val < ALPHA:
        confianca = "Moderada"
    else:
        confianca = "Inconclusivo"

    # --- Guardrails: o vencedor em lucro também lidera em volume/GMV? ---
    tradeoffs = _checa_tradeoffs(metricas)

    if significativo:
        decisao = f"Escalar {vencedor} para 100% do tráfego"
    else:
        decisao = (
            f"Inconclusivo — {vencedor} lidera em lucro/dia, mas sem significância "
            f"estatística (p={p_val:.3f}); recomendado estender o teste"
        )

    return ResultadoAnalise(
        parceiro=parceiro, periodo=periodo, metricas=metricas,
        vencedor=vencedor, vice=vice, lift_pct=lift_pct, p_valor=float(p_val),
        p_valor_wilcoxon=(float(p_wilcoxon) if p_wilcoxon is not None else None),
        teste_usado=teste, significativo=significativo, confianca=confianca,
        decisao=decisao, tradeoffs=tradeoffs, impacto_dia=impacto_dia,
    )


def _checa_tradeoffs(metricas: list) -> list:
    """Sinaliza quando o vencedor em lucro não lidera em métricas de crescimento."""
    venc = metricas[0]
    alertas = []
    melhor_gmv = max(metricas, key=lambda m: m.gmv_dia)
    melhor_compradores = max(metricas, key=lambda m: m.compradores_dia)
    if melhor_gmv.grupo != venc.grupo:
        dif = (melhor_gmv.gmv_dia - venc.gmv_dia) / melhor_gmv.gmv_dia
        alertas.append(
            f"{melhor_gmv.grupo} gera mais GMV/dia ({dif:.0%} acima do vencedor): "
            f"o vencedor lucra mais, mas movimenta menos volume."
        )
    if melhor_compradores.grupo != venc.grupo:
        dif = (melhor_compradores.compradores_dia - venc.compradores_dia) / melhor_compradores.compradores_dia
        alertas.append(
            f"{melhor_compradores.grupo} traz mais compradores/dia ({dif:.0%} acima): "
            f"avaliar impacto de longo prazo na base de usuários."
        )
    return alertas


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "src")
    from ingestao import carregar_dataset

    ing = carregar_dataset(sys.argv[1])
    res = analisar(ing.df, ing.parceiro)
    print(f"\n=== {res.parceiro} | {res.periodo[0]} a {res.periodo[1]} ===")
    print(f"{'Grupo':<10}{'Lucro/dia':>12}{'GMV/dia':>12}{'Compr/dia':>11}"
          f"{'Cashback%':>11}{'Take%':>8}")
    for m in res.metricas:
        print(f"{m.grupo:<10}{m.lucro_dia:>12,.0f}{m.gmv_dia:>12,.0f}"
              f"{m.compradores_dia:>11,.0f}{m.cashback_rate:>10.1%}{m.take_rate:>8.1%}")
    print(f"\nDecisão: {res.decisao}")
    print(f"Confiança: {res.confianca} | teste: {res.teste_usado} | p={res.p_valor:.4f}")
    if res.lift_pct is not None:
        print(f"Lift do vencedor sobre o vice: {res.lift_pct:+.1%} "
              f"(+R$ {res.impacto_dia:,.0f}/dia)")
    elif res.impacto_dia is not None:
        print(f"Ganho do vencedor sobre o vice: +R$ {res.impacto_dia:,.0f}/dia "
              f"(vice em ~zero; lift % indefinido)")
    for t in res.tradeoffs:
        print(f"  ⚠ {t}")
