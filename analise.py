#!/usr/bin/env python3
"""
CLI da solução de análise de testes A/B de cashback do Méliuz.

Um único comando executa o fluxo completo:
  ingestão  ->  análise/decisão  ->  relatório do gestor  ->  registro na planilha

Funciona para qualquer parceiro sem alterar o código — basta apontar o arquivo.
O registro no CSV é sempre feito; o Google Sheets é acionado quando você passa
a credencial e o ID da planilha.

Exemplos:
    python analise.py data/dataset_01_parceiroA.csv
    python analise.py data/dataset_03_parceiroC.csv \\
        --credenciais credenciais.json --planilha <ID_DA_PLANILHA>
"""

from __future__ import annotations

import argparse
import os
import sys

# Permite importar os módulos de src/ rodando a CLI da raiz do projeto.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from ingestao import carregar_dataset
from analise_engine import analisar
from relatorio import gerar_relatorio, brl
import tracker


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Analisa um teste A/B de cashback, gera o relatório do "
                    "gestor e registra o resultado na planilha de acompanhamento.")
    parser.add_argument("input",
                        help="Caminho do CSV do teste (qualquer parceiro).")
    parser.add_argument("--relatorio-dir", default="relatorios",
                        help="Pasta onde salvar o relatório HTML (padrão: relatorios).")
    parser.add_argument("--tracker", default="tracker.csv",
                        help="Caminho do CSV de acompanhamento (padrão: tracker.csv).")
    parser.add_argument("--credenciais", default=None,
                        help="JSON da service account do Google (ativa o Sheets).")
    parser.add_argument("--planilha", default=None,
                        help="ID da planilha do Google Sheets.")
    parser.add_argument("--aba", default="Testes",
                        help="Nome da aba na planilha (padrão: Testes).")
    args = parser.parse_args(argv)

    if not os.path.exists(args.input):
        parser.error(f"Arquivo não encontrado: {args.input}")

    # 1) Ingestão + 2) Análise
    ing = carregar_dataset(args.input)
    ana = analisar(ing.df, ing.parceiro)

    # 3) Relatório do gestor
    os.makedirs(args.relatorio_dir, exist_ok=True)
    nome_arq = f"relatorio_{ana.parceiro.replace(' ', '_').lower()}.html"
    caminho_rel = os.path.join(args.relatorio_dir, nome_arq)
    gerar_relatorio(ing, ana, caminho_rel)

    # 4) Registro na planilha (CSV sempre; Sheets se houver credencial)
    linha = tracker.montar_linha(ing, ana)
    tracker.registrar_csv(linha, args.tracker)

    url_sheets = None
    if args.credenciais and args.planilha:
        try:
            url_sheets = tracker.registrar_sheets(
                linha, args.credenciais, args.planilha, args.aba)
        except Exception as e:
            # Falha no Sheets não derruba o run: o CSV e o relatório já existem.
            print(f"[aviso] Não foi possível escrever no Google Sheets: {e}")

    _imprimir_resumo(ing, ana, caminho_rel, args.tracker, url_sheets)


def _imprimir_resumo(ing, ana, caminho_rel, caminho_tracker, url_sheets):
    """Imprime um resumo legível — é o que a ferramenta de IA relata de volta."""
    regua = "=" * 60
    print(regua)
    print(f" Análise de teste A/B — {ana.parceiro}")
    print(regua)
    print(f" Período: {ana.periodo[0]:%d/%m/%Y} a {ana.periodo[1]:%d/%m/%Y} · "
          f"{len(ana.metricas)} variantes · {ing.linhas_validas} obs. válidas "
          f"({ing.taxa_descarte:.1%} descartadas)")
    print()
    print(f" DECISÃO: {ana.decisao}")
    detalhe = f" Confiança: {ana.confianca}"
    if ana.impacto_dia is not None and ana.vice:
        detalhe += f" · ganho {brl(ana.impacto_dia)}/dia sobre {ana.vice}"
    if ana.p_valor is not None:
        detalhe += " · p=" + f"{ana.p_valor:.4f}".replace(".", ",")
    print(detalhe)
    if ana.ic95_impacto:
        lo, hi = ana.ic95_impacto
        print(f" Ganho com 95% de confiança: entre {brl(lo)} e {brl(hi)} por dia")
    if ana.alertas_validade:
        print()
        print(" Validade do teste:")
        marca = {"info": "✓", "atencao": "⚠", "critico": "✗"}
        for d in ana.alertas_validade:
            print(f"   {marca.get(d.severidade, '·')} {d.titulo}")
    print()
    print(f" Relatório:        {caminho_rel}")
    print(f" Tracker (CSV):    {caminho_tracker}")
    if url_sheets:
        print(f" Tracker (Sheets): {url_sheets}")
    s = ana.sugestao_proximo_teste
    if s is not None and getattr(s, "padrao", "indefinido") != "indefinido":
        print()
        print(" Próximo teste sugerido:")
        print(f"   {s.texto}")
    print(regua)


if __name__ == "__main__":
    main()