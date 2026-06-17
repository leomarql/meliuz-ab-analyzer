"""
Checagens de validade do teste A/B — analisa antes de decidir.

Antes de confiar numa decisão, é preciso desconfiar do teste. Este módulo roda
diagnósticos de qualidade do experimento (não dos dados brutos, que já foram
limpos na ingestão) e devolve alertas que o relatório e a CLI exibem:

- Balanceamento de exposição entre variantes (tipo Sample Ratio Mismatch);
- Tamanho de amostra suficiente para ter poder estatístico;
- Dias anômalos (outliers) que podem distorcer as médias.

A ideia é proteger contra decisões tiradas de um teste quebrado ou enviesado.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

MIN_DIAS_RECOMENDADO = 14       # abaixo disso, o teste tende a ter poder baixo
TOLERANCIA_EXPOSICAO = 0.05     # diferença aceitável no nº de observações (5%)
LIMIAR_OUTLIER = 3.5            # z-score robusto (regra de Iglewicz-Hoaglin)


@dataclass
class AlertaValidade:
    """Um diagnóstico de validade. severidade: 'info' | 'atencao' | 'critico'."""
    severidade: str
    titulo: str
    detalhe: str


def _zscore_robusto(serie: pd.Series) -> pd.Series:
    """
    Z-score robusto baseado em mediana e MAD (desvio absoluto mediano).

    É usada a versão robusta em vez do z-score clássico (média/desvio-padrão)
    porque a própria presença de outliers contamina a média e o desvio — então
    o método tradicional "esconderia" os picos que se quer justamente detectar.
    A constante 0.6745 calibra a escala para ficar comparável a um z normal.
    """
    mediana = serie.median()
    mad = (serie - mediana).abs().median()
    if mad > 0:
        return 0.6745 * (serie - mediana) / mad
    # MAD = 0 (série quase constante): cai para o z-score clássico, que ainda
    # detecta um pico isolado em meio a valores repetidos.
    desvio = serie.std(ddof=0)
    if desvio > 0:
        return (serie - serie.mean()) / desvio
    return pd.Series(0.0, index=serie.index)


def verificar_validade(df: pd.DataFrame) -> list[AlertaValidade]:
    """Roda os diagnósticos de validade sobre os dados limpos do teste."""
    alertas: list[AlertaValidade] = []
    grupos = sorted(df["grupo"].unique().tolist())
    contagens = {g: int((df["grupo"] == g).sum()) for g in grupos}
    n_min, n_max = min(contagens.values()), max(contagens.values())

    # 1) Balanceamento de exposição (Sample Ratio Mismatch)
    # É checada na EXPOSIÇÃO (nº de observações por variante), nunca em
    # compradores/vendas — porque essas são resultado do tratamento, e medir o
    # resultado confundiria o efeito real do teste com um desbalanceamento.
    if n_max > 0 and (n_max - n_min) / n_max > TOLERANCIA_EXPOSICAO:
        alertas.append(AlertaValidade(
            "critico", "Exposição desbalanceada entre variantes",
            f"As variantes têm números diferentes de observações ({contagens}). "
            "Num A/B saudável a exposição deve ser equilibrada — uma diferença "
            "grande sugere problema na divisão de tráfego ou na coleta, e pode "
            "invalidar a comparação."))

    # 2) Tamanho de amostra / poder estatístico
    if n_min < MIN_DIAS_RECOMENDADO:
        alertas.append(AlertaValidade(
            "atencao", "Amostra pequena (poder estatístico baixo)",
            f"A menor variante tem apenas {n_min} dias de dados "
            f"(recomendado ≥ {MIN_DIAS_RECOMENDADO}). O teste pode não ter poder "
            "para detectar diferenças reais; considere estender a coleta."))

    # 3) Dias anômalos (outliers) na série de GMV de cada variante
    total_outliers = 0
    exemplos: list[str] = []
    for g in grupos:
        d = df[df["grupo"] == g].sort_values("data")
        z = _zscore_robusto(d["vendas_totais"])
        out = d[z.abs() > LIMIAR_OUTLIER]
        total_outliers += len(out)
        for _, r in out.iterrows():
            exemplos.append(f"{g} em {r['data']:%d/%m/%Y}")
    if total_outliers:
        amostra = "; ".join(exemplos[:4]) + (" …" if len(exemplos) > 4 else "")
        alertas.append(AlertaValidade(
            "atencao", f"{total_outliers} dia(s) anômalo(s) detectado(s)",
            f"Dias com GMV muito acima do padrão da variante ({amostra}). "
            "Picos assim (promoções, sazonalidade ou erro de coleta) inflam as "
            "médias — vale checar se a decisão depende desses dias."))

    if not alertas:
        alertas.append(AlertaValidade(
            "info", "Nenhum problema de validade detectado",
            "Exposição equilibrada entre as variantes, amostra suficiente e sem "
            "dias anômalos relevantes na série de GMV."))
    return alertas


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "src")
    from ingestao import carregar_dataset

    ing = carregar_dataset(sys.argv[1])
    print(f"=== Validade do teste — {ing.parceiro} ===")
    for a in verificar_validade(ing.df):
        marca = {"info": "✓", "atencao": "⚠", "critico": "✗"}[a.severidade]
        print(f" {marca} [{a.severidade}] {a.titulo}\n   {a.detalhe}")