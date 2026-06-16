"""
Sugestão do próximo teste — a camada propositiva (mentalidade de growth).

Decidir o teste atual é olhar para trás. Este módulo olha para frente: lê a
relação entre o **nível de cashback** e o **lucro líquido** entre as variantes e
propõe a próxima hipótese a testar.

A lógica:
- se o lucro cresce conforme o cashback CAI, o ótimo provavelmente está abaixo
  do menor nível testado -> sugere testar um tier mais baixo (até achar o piso
  em que o volume começa a desabar);
- se o lucro cresce conforme o cashback SOBE, o ganho de volume está superando o
  custo -> sugere testar um tier mais alto;
- se o lucro é maior num nível intermediário, há um ótimo interno -> sugere
  concentrar o próximo teste em torno dele.

Não substitui um novo experimento: aponta para onde apontar o próximo teste.
"""

from __future__ import annotations

from dataclasses import dataclass


def _brl(valor: float) -> str:
    """Número como moeda BR: 1234 -> 'R$ 1.234'."""
    return "R$ " + f"{valor:,.0f}".replace(",", ".")


def _pct(fracao: float) -> str:
    """Fração como porcentagem BR: 0.032 -> '3,2%'."""
    return f"{fracao * 100:.1f}".replace(".", ",") + "%"


@dataclass
class SugestaoProximoTeste:
    padrao: str                    # "cai" | "sobe" | "intermediario" | "indefinido"
    sensibilidade_pp: float | None  # ~R$/dia de lucro por ponto percentual de cashback
    nivel_sugerido: float | None    # cashback (fração) sugerido para o próximo teste
    texto: str                      # frase pronta para relatório/CLI


def _monotonica_decrescente(valores) -> bool:
    return all(valores[i] >= valores[i + 1] for i in range(len(valores) - 1))


def _monotonica_crescente(valores) -> bool:
    return all(valores[i] <= valores[i + 1] for i in range(len(valores) - 1))


def sugerir_proximo_teste(metricas) -> SugestaoProximoTeste:
    """Infere o padrão cashback x lucro e sugere o próximo nível a testar."""
    # Pares (taxa de cashback, lucro/dia), ordenados por cashback crescente.
    pares = sorted(((m.cashback_rate, m.lucro_dia) for m in metricas),
                   key=lambda x: x[0])
    cashbacks = [c for c, _ in pares]
    lucros = [l for _, l in pares]

    # Precisa de ao menos 2 níveis de cashback distintos para inferir tendência.
    if len(pares) < 2 or (cashbacks[-1] - cashbacks[0]) < 1e-9:
        return SugestaoProximoTeste(
            "indefinido", None, None,
            "Não há variação de cashback suficiente entre as variantes para "
            "sugerir um próximo nível.")

    # Sensibilidade: variação de lucro/dia por ponto percentual de cashback,
    # medida entre o menor e o maior nível testado.
    delta_pp = (cashbacks[-1] - cashbacks[0]) * 100
    sens = (lucros[-1] - lucros[0]) / delta_pp  # R$/dia por pp (negativo se lucro cai)
    menor_cb, maior_cb = cashbacks[0], cashbacks[-1]

    if _monotonica_decrescente(lucros):
        nivel = max(menor_cb - 0.01, menor_cb * 0.6)  # ~1pp abaixo, com piso
        texto = (
            f"O lucro líquido cresce conforme o cashback cai — cada 1 ponto "
            f"percentual a menos rendeu cerca de {_brl(abs(sens))}/dia a mais no "
            f"intervalo testado. Próximo teste sugerido: um tier abaixo do menor "
            f"nível atual (em torno de {_pct(nivel)} de cashback), para achar o "
            f"piso em que a queda de volume passa a anular o ganho de margem."
        )
        return SugestaoProximoTeste("cai", sens, nivel, texto)

    if _monotonica_crescente(lucros):
        nivel = maior_cb + 0.01
        texto = (
            f"O lucro líquido cresce conforme o cashback sobe — o ganho de volume "
            f"superou o custo do incentivo (cerca de {_brl(abs(sens))}/dia por "
            f"ponto percentual). Próximo teste sugerido: um tier acima do maior "
            f"nível atual (em torno de {_pct(nivel)} de cashback)."
        )
        return SugestaoProximoTeste("sobe", sens, nivel, texto)

    # Não monotônico: o melhor lucro está num nível intermediário (ótimo interno).
    idx_melhor = max(range(len(lucros)), key=lambda i: lucros[i])
    nivel = cashbacks[idx_melhor]
    texto = (
        f"O maior lucro ocorreu num nível intermediário de cashback "
        f"(~{_pct(nivel)}), sugerindo um ponto ótimo interno. Próximo teste "
        f"sugerido: estreitar a faixa em torno desse nível para refiná-lo."
    )
    return SugestaoProximoTeste("intermediario", sens, nivel, texto)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "src")
    from ingestao import carregar_dataset
    from analise_engine import analisar

    ing = carregar_dataset(sys.argv[1])
    ana = analisar(ing.df, ing.parceiro)
    s = sugerir_proximo_teste(ana.metricas)
    print(f"=== Próximo teste — {ing.parceiro} ===")
    print(f" Padrão: {s.padrao}")
    print(f" {s.texto}")