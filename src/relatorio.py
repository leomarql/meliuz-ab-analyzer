"""
Geração do relatório de teste A/B para o gestor.

Recebe o resultado da análise (src/analise_engine) e a saída da ingestão e
produz um arquivo HTML autocontido (gráficos embutidos em base64), pronto para
abrir no navegador, compartilhar ou exportar como PDF.

Decisões de design:
- HTML único e portátil: os gráficos são embutidos como imagens base64, então
  não há arquivos soltos para gerenciar.
- Hierarquia de gestor: a decisão vem primeiro, em destaque; os detalhes
  técnicos (métricas, estatística) vêm depois como apoio.
- Acento visual inspirado na identidade do Méliuz, usado com parcimônia.
"""

from __future__ import annotations

import base64
import io
from datetime import datetime

import matplotlib

matplotlib.use("Agg")  # backend sem janela, para gerar imagem em memória
import matplotlib.pyplot as plt
from jinja2 import Environment

# --- Paleta (acento rosa Méliuz + neutros) ---
ROSA = "#E6007E"      # vencedor / destaque
CINZA = "#9CA3AF"     # variantes não vencedoras
TEXTO = "#1F2937"
VERDE = "#047857"     # positivo
AMBAR = "#B45309"     # atenção / trade-off

# Cores distintas para diferenciar as variantes não vencedoras nos gráficos de
# linha (onde o cinza único deixava Grupo 2 e 3 indistinguíveis).
PALETA_LINHAS = ["#2563EB", "#D97706", "#0D9488", "#7C3AED"]

DIAS_ANO = 365  # base para anualizar o ganho diário


def brl_compacto(valor: float) -> str:
    """Moeda BR abreviada para manchete: 187245 -> 'R$ 187 mil'; 1.6e6 -> 'R$ 1,6 mi'."""
    if valor is None or valor != valor:
        return "—"
    if abs(valor) >= 1_000_000:
        return ("R$ " + f"{valor / 1_000_000:.1f}".replace(".", ",") + " mi")
    if abs(valor) >= 1_000:
        return "R$ " + f"{valor / 1_000:,.0f}".replace(",", ".") + " mil"
    return "R$ " + f"{valor:,.0f}".replace(",", ".")


# ----------------------------------------------------------------------------
# Formatação no padrão brasileiro
# ----------------------------------------------------------------------------
def brl(valor: float, casas: int = 0) -> str:
    """Formata um número como moeda BR: 60926 -> 'R$ 60.926'."""
    if valor is None or valor != valor:  # None ou NaN
        return "—"
    s = f"{valor:,.{casas}f}"
    # f-string usa ',' para milhar e '.' para decimal; troca para o padrão BR.
    s = s.replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {s}"


def pct(valor: float, casas: int = 1) -> str:
    """Formata uma fração como porcentagem BR: 0.042 -> '4,2%'."""
    if valor is None or valor != valor:
        return "—"
    return f"{valor * 100:.{casas}f}".replace(".", ",") + "%"


# ----------------------------------------------------------------------------
# Gráficos -> imagem base64 embutível no HTML
# ----------------------------------------------------------------------------
def _fig_para_base64(fig) -> str:
    """Converte uma figura matplotlib em data URI (PNG base64) para o <img src>."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    dados = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{dados}"


def _cores_por_variante(metricas, vencedor):
    """Rosa para o vencedor, cinza para o resto — guia o olho para a decisão."""
    return [ROSA if m.grupo == vencedor else CINZA for m in metricas]


def _grafico_lucro_dia(analise) -> str:
    """Barras do lucro líquido/dia por variante — a métrica que decide o teste."""
    metricas = analise.metricas
    nomes = [m.grupo for m in metricas]
    valores = [m.lucro_dia for m in metricas]
    cores = _cores_por_variante(metricas, analise.vencedor)

    fig, ax = plt.subplots(figsize=(7, 3.6))
    barras = ax.bar(nomes, valores, color=cores, width=0.6)
    ax.set_title("Lucro líquido por dia (comissão − cashback)", fontsize=12,
                 color=TEXTO, weight="bold", pad=12)
    ax.set_ylabel("R$ / dia", fontsize=9, color=TEXTO)
    # Marca como "equilíbrio" a variante cujo lucro é desprezível frente à maior
    # barra — evita que um valor ~zero pareça dado faltante para o gestor.
    maxabs = max((abs(v) for v in valores), default=1) or 1
    for b, v in zip(barras, valores):
        rotulo = brl(v)
        if abs(v) < 0.05 * maxabs:
            rotulo = f"{brl(v)} · equilíbrio"
        ax.text(b.get_x() + b.get_width() / 2, b.get_height(),
                rotulo, ha="center", va="bottom", fontsize=9, color=TEXTO)
    _estilo_eixo(ax)
    return _fig_para_base64(fig)


def _grafico_volume(analise) -> str:
    """Dois painéis: GMV/dia e compradores/dia — revela o trade-off de volume."""
    metricas = analise.metricas
    nomes = [m.grupo for m in metricas]
    cores = _cores_por_variante(metricas, analise.vencedor)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7, 3.4))
    ax1.bar(nomes, [m.gmv_dia for m in metricas], color=cores, width=0.6)
    ax1.set_title("GMV por dia", fontsize=11, color=TEXTO, weight="bold")
    ax1.set_ylabel("R$ / dia", fontsize=9, color=TEXTO)

    ax2.bar(nomes, [m.compradores_dia for m in metricas], color=cores, width=0.6)
    ax2.set_title("Compradores por dia", fontsize=11, color=TEXTO, weight="bold")
    ax2.set_ylabel("usuários / dia", fontsize=9, color=TEXTO)

    for ax in (ax1, ax2):
        _estilo_eixo(ax)
    fig.tight_layout()
    return _fig_para_base64(fig)


def _grafico_evolucao(ingestao, analise) -> str:
    """Linha do lucro líquido diário ao longo do tempo, por variante.

    Mostra que a vantagem do vencedor é consistente dia a dia (a intuição por
    trás da significância estatística), não fruto de um pico isolado."""
    df = ingestao.df.copy()
    df["lucro"] = df["comissao"] - df["cashback"]

    fig, ax = plt.subplots(figsize=(7, 3.4))
    idx_cor = 0
    for m in analise.metricas:
        d = df[df["grupo"] == m.grupo].sort_values("data")
        if m.grupo == analise.vencedor:
            cor, lw = ROSA, 2.4
        else:
            cor = PALETA_LINHAS[idx_cor % len(PALETA_LINHAS)]
            lw = 1.4
            idx_cor += 1
        ax.plot(d["data"], d["lucro"], label=m.grupo, color=cor, linewidth=lw)
    ax.set_title("Lucro líquido diário ao longo do teste", fontsize=12,
                 color=TEXTO, weight="bold", pad=12)
    ax.set_ylabel("R$ / dia", fontsize=9, color=TEXTO)
    ax.legend(frameon=False, fontsize=9)
    _estilo_eixo(ax)
    fig.autofmt_xdate()
    return _fig_para_base64(fig)


def _estilo_eixo(ax):
    """Remove molduras pesadas e suaviza o grid — visual limpo e legível."""
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#D1D5DB")
    ax.spines["bottom"].set_color("#D1D5DB")
    ax.tick_params(colors=TEXTO, labelsize=9)
    ax.grid(axis="y", color="#EEF0F2", linewidth=1)
    ax.set_axisbelow(True)


# ----------------------------------------------------------------------------
# Template HTML (Jinja2)
# ----------------------------------------------------------------------------
TEMPLATE_HTML = """<!DOCTYPE html>
<html lang="pt-br">
<head>
<meta charset="utf-8">
<title>Relatório A/B · {{ parceiro }}</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
         color: {{ texto }}; background: #F3F4F6; line-height: 1.55; padding: 32px; }
  .pagina { max-width: 880px; margin: 0 auto; background: #fff;
            border-radius: 14px; overflow: hidden;
            box-shadow: 0 1px 3px rgba(0,0,0,.08); }
  .cabecalho { padding: 28px 36px; border-bottom: 1px solid #E5E7EB; }
  .eyebrow { font-size: 12px; letter-spacing: .08em; text-transform: uppercase;
             color: {{ rosa }}; font-weight: 700; }
  .cabecalho h1 { font-size: 24px; margin: 4px 0 6px; }
  .meta { font-size: 13px; color: #6B7280; }
  .conteudo { padding: 28px 36px; }
  .decisao { border: 2px solid {{ rosa }}; border-radius: 12px;
             padding: 22px 24px; margin-bottom: 26px; background: #FFF5FA; }
  .decisao .rotulo { font-size: 12px; text-transform: uppercase;
                     letter-spacing: .06em; color: {{ rosa }}; font-weight: 700; }
  .decisao h2 { font-size: 26px; margin: 6px 0 10px; }
  .badges { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 6px; }
  .badge { font-size: 13px; padding: 5px 12px; border-radius: 999px;
           background: #fff; border: 1px solid #E5E7EB; }
  .badge.alta { color: {{ verde }}; border-color: {{ verde }}; }
  .badge.moderada { color: {{ ambar }}; border-color: {{ ambar }}; }
  .badge.inconclusivo { color: #6B7280; }
  h3 { font-size: 16px; margin: 26px 0 12px; padding-bottom: 6px;
       border-bottom: 1px solid #E5E7EB; }
  table { width: 100%; border-collapse: collapse; font-size: 14px; }
  th, td { text-align: right; padding: 9px 10px; border-bottom: 1px solid #F0F1F3; }
  th:first-child, td:first-child { text-align: left; }
  thead th { font-size: 12px; text-transform: uppercase; letter-spacing: .03em;
             color: #6B7280; }
  tr.vencedor td { background: #FFF5FA; font-weight: 600; }
  tr.vencedor td:first-child { color: {{ rosa }}; }
  .grafico { margin: 16px 0; text-align: center; }
  .grafico img { max-width: 100%; height: auto; }
  .nota { font-size: 13px; color: #6B7280; }
  .alerta { background: #FFFBEB; border-left: 3px solid {{ ambar }};
            padding: 12px 16px; border-radius: 0 8px 8px 0; margin: 8px 0;
            font-size: 14px; }
  .diag { padding: 12px 16px; border-radius: 0 8px 8px 0; margin: 8px 0;
          font-size: 14px; border-left: 3px solid #9CA3AF; background: #F9FAFB; }
  .diag.critico { border-left-color: #B91C1C; background: #FEF2F2; }
  .diag.atencao { border-left-color: {{ ambar }}; background: #FFFBEB; }
  .diag.info { border-left-color: {{ verde }}; background: #F0FDF4; }
  .diag .t { font-weight: 600; }
  .proximo { background: #FFF5FA; border: 1px solid {{ rosa }}; border-radius: 10px;
             padding: 16px 20px; font-size: 14px; margin: 8px 0; }
  .proximo .rotulo { font-size: 12px; text-transform: uppercase; letter-spacing: .06em;
                     color: {{ rosa }}; font-weight: 700; display: block; margin-bottom: 4px; }
  .projecao { background: #F0FDF4; border: 1px solid {{ verde }}; border-radius: 10px;
              padding: 16px 20px; font-size: 14px; margin: -10px 0 26px; }
  .projecao .num { font-size: 22px; font-weight: 700; color: {{ verde }}; }
  .projecao .cav { color: #6B7280; font-size: 12.5px; }
  .stat { font-size: 14px; background: #F9FAFB; border-radius: 10px;
          padding: 16px 20px; }
  .stat b { color: {{ texto }}; }
  .rodape { padding: 18px 36px; border-top: 1px solid #E5E7EB;
            font-size: 12px; color: #9CA3AF; }
</style>
</head>
<body>
<div class="pagina">
  <div class="cabecalho">
    <div class="eyebrow">Teste A/B · Cashback</div>
    <h1>{{ parceiro }}</h1>
    <div class="meta">Período analisado: {{ periodo_ini }} a {{ periodo_fim }}
      &nbsp;·&nbsp; {{ n_variantes }} variantes &nbsp;·&nbsp;
      Gerado em {{ gerado_em }}</div>
  </div>
  <div class="conteudo">

    <div class="decisao">
      <div class="rotulo">Recomendação</div>
      <h2>{{ decisao }}</h2>
      <div class="badges">
        <span class="badge {{ classe_confianca }}">Confiança: {{ confianca }}</span>
        {% if lift %}<span class="badge">Ganho sobre o 2º: {{ lift }}</span>{% endif %}
        {% if impacto %}<span class="badge">{{ impacto }}/dia</span>{% endif %}
      </div>
    </div>

    {% if projecao_ano %}
    <div class="projecao">
      Escalar o {{ vencedor }} projeta <span class="num">{{ projecao_ano }}/ano</span>
      de lucro adicional frente ao {{ vice }}, na escala do teste
      {% if proj_lo %}(entre {{ proj_lo }} e {{ proj_hi }} por ano, com 95% de
      confiança){% endif %}.
      <br><span class="cav">Projeção: assume o ganho diário mantido em volume
      comparável ao do teste — é uma estimativa, não uma garantia.</span>
    </div>
    {% endif %}

    <p class="nota">Qualidade dos dados: {{ linhas_validas }} de
      {{ linhas_originais }} observações válidas
      ({{ taxa_descarte }} descartadas{% if motivos %} — {{ motivos }}{% endif %}).</p>

    <h3>Métricas por variante</h3>
    <table>
      <thead><tr>
        <th>Variante</th><th>Lucro/dia</th><th>GMV/dia</th>
        <th>Compr./dia</th><th>Cashback %</th><th>Take rate</th>
        <th>Ticket médio</th>
      </tr></thead>
      <tbody>
      {% for m in linhas_tabela %}
        <tr class="{{ 'vencedor' if m.vencedor else '' }}">
          <td>{{ m.grupo }}</td><td>{{ m.lucro_dia }}</td><td>{{ m.gmv_dia }}</td>
          <td>{{ m.compradores_dia }}</td><td>{{ m.cashback_rate }}</td>
          <td>{{ m.take_rate }}</td><td>{{ m.ticket_medio }}</td>
        </tr>
      {% endfor %}
      </tbody>
    </table>

    <h3>Lucro líquido — a métrica de decisão</h3>
    <div class="grafico"><img src="{{ graf_lucro }}" alt="Lucro líquido por dia"></div>

    <h3>Volume: GMV e compradores</h3>
    <div class="grafico"><img src="{{ graf_volume }}" alt="GMV e compradores por dia"></div>
    {% for t in tradeoffs %}<div class="alerta">{{ t }}</div>{% endfor %}

    <h3>Consistência ao longo do tempo</h3>
    <div class="grafico"><img src="{{ graf_evolucao }}" alt="Evolução diária"></div>

    <h3>Validade do teste</h3>
    {% for d in validade %}<div class="diag {{ d.severidade }}"><span class="t">{{ d.titulo }}.</span> {{ d.detalhe }}</div>{% endfor %}

    <h3>Base estatística</h3>
    <div class="stat">
      Comparação entre <b>{{ vencedor }}</b> (1º) e <b>{{ vice }}</b> (2º) pelo
      <b>{{ teste }}</b>. Valor-p = <b>{{ p_valor }}</b>
      {%- if p_wilcoxon %} (Wilcoxon = {{ p_wilcoxon }}){%- endif %}.
      {% if significativo %}A diferença é estatisticamente significativa
      (p &lt; 0,05): há evidência para escalar com segurança.
      {% else %}A diferença <b>não</b> é estatisticamente significativa
      (p ≥ 0,05): recomenda-se estender o teste antes de decidir.{% endif %}
      {% if ic95_lo %}<br><br>O ganho médio do {{ vencedor }} é de
      <b>{{ impacto }}/dia</b>, com 95% de confiança entre
      <b>{{ ic95_lo }}</b> e <b>{{ ic95_hi }}</b> por dia.{% endif %}
    </div>

    {% if proximo_teste %}
    <h3>Próximo teste sugerido</h3>
    <div class="proximo">
      <span class="rotulo">Recomendação de growth</span>
      {{ proximo_teste }}
    </div>
    {% endif %}

  </div>
  <div class="rodape">Relatório gerado automaticamente · Solução de análise de
    testes A/B de cashback · Time de Growth</div>
</div>
</body>
</html>"""


def gerar_relatorio(ingestao, analise, caminho_saida: str) -> str:
    """
    Monta o relatório HTML a partir da ingestão + análise e grava em disco.

    Retorna o caminho do arquivo gerado.
    """
    a = analise
    linhas_tabela = [{
        "grupo": m.grupo,
        "vencedor": m.grupo == a.vencedor,
        "lucro_dia": brl(m.lucro_dia),
        "gmv_dia": brl(m.gmv_dia),
        "compradores_dia": f"{m.compradores_dia:,.0f}".replace(",", "."),
        "cashback_rate": pct(m.cashback_rate),
        "take_rate": pct(m.take_rate),
        "ticket_medio": brl(m.ticket_medio),
    } for m in a.metricas]

    contexto = {
        "rosa": ROSA, "texto": TEXTO, "verde": VERDE, "ambar": AMBAR,
        "parceiro": a.parceiro,
        "periodo_ini": a.periodo[0].strftime("%d/%m/%Y"),
        "periodo_fim": a.periodo[1].strftime("%d/%m/%Y"),
        "n_variantes": len(a.metricas),
        "gerado_em": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "decisao": a.decisao,
        "confianca": a.confianca,
        "classe_confianca": a.confianca.lower(),
        "lift": (pct(a.lift_pct, 1) if a.lift_pct is not None else None),
        "impacto": (brl(a.impacto_dia) if a.impacto_dia is not None else None),
        "linhas_validas": ingestao.linhas_validas,
        "linhas_originais": ingestao.linhas_originais,
        "taxa_descarte": pct(ingestao.taxa_descarte),
        "motivos": "; ".join(f"{k}: {v}" for k, v in ingestao.motivos_descarte.items()),
        "linhas_tabela": linhas_tabela,
        "graf_lucro": _grafico_lucro_dia(a),
        "graf_volume": _grafico_volume(a),
        "graf_evolucao": _grafico_evolucao(ingestao, a),
        "tradeoffs": a.tradeoffs,
        "vencedor": a.vencedor,
        "vice": a.vice or "—",
        "teste": a.teste_usado,
        "p_valor": (f"{a.p_valor:.4f}".replace(".", ",") if a.p_valor is not None else "—"),
        "p_wilcoxon": (f"{a.p_valor_wilcoxon:.4f}".replace(".", ",")
                       if a.p_valor_wilcoxon is not None else None),
        "significativo": a.significativo,
        "validade": [{"severidade": d.severidade, "titulo": d.titulo,
                      "detalhe": d.detalhe} for d in a.alertas_validade],
        "ic95_lo": (brl(a.ic95_impacto[0]) if a.ic95_impacto else None),
        "ic95_hi": (brl(a.ic95_impacto[1]) if a.ic95_impacto else None),
        "proximo_teste": (a.sugestao_proximo_teste.texto
                          if a.sugestao_proximo_teste
                          and a.sugestao_proximo_teste.padrao != "indefinido"
                          else None),
        # Impacto anualizado: só é projetado quando a decisão é escalar (significativa).
        "projecao_ano": (brl_compacto(a.impacto_dia * DIAS_ANO)
                         if a.significativo and a.impacto_dia is not None else None),
        "proj_lo": (brl_compacto(a.ic95_impacto[0] * DIAS_ANO)
                    if a.significativo and a.ic95_impacto else None),
        "proj_hi": (brl_compacto(a.ic95_impacto[1] * DIAS_ANO)
                    if a.significativo and a.ic95_impacto else None),
    }

    env = Environment(autoescape=True)
    html = env.from_string(TEMPLATE_HTML).render(**contexto)
    with open(caminho_saida, "w", encoding="utf-8") as fh:
        fh.write(html)
    return caminho_saida


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "src")
    from ingestao import carregar_dataset
    from analise_engine import analisar

    entrada = sys.argv[1]
    ing = carregar_dataset(entrada)
    ana = analisar(ing.df, ing.parceiro)
    nome = f"relatorios/relatorio_{ing.parceiro.replace(' ', '_').lower()}.html"
    caminho = gerar_relatorio(ing, ana, nome)
    print(f"Relatório gerado: {caminho}")