"""
Registro dos testes A/B numa planilha de acompanhamento.

Cada teste analisado vira uma linha com: nome, descrição, período, variantes,
métrica de decisão, resultado, decisão, confiança e data da análise.

Dois destinos, com a mesma lógica de upsert (rodar o mesmo teste de novo
atualiza a linha em vez de duplicar):
- CSV local (sempre, sem configuração) — o mínimo exigido pelo case;
- Google Sheets (opcional, o diferencial) — exige uma credencial de service
  account; veja o README para o passo a passo de configuração.
"""

from __future__ import annotations

import csv
import os
from datetime import datetime

# Ordem das colunas da planilha. As 4 primeiras cobrem o mínimo do case
# (nome, descrição, resultado, decisão); as demais dão contexto ao gestor.
COLUNAS = [
    "nome_do_teste", "descricao", "periodo", "variantes", "metrica_decisao",
    "resultado", "decisao", "confianca", "data_analise",
]


def _brl(valor: float) -> str:
    """Formata número como moeda BR (sem depender do módulo de relatório)."""
    if valor is None or valor != valor:
        return "—"
    return "R$ " + f"{valor:,.0f}".replace(",", "_").replace(".", ",").replace("_", ".")


def montar_linha(ingestao, analise) -> dict:
    """Constrói a linha da planilha a partir da ingestão + análise."""
    a = analise
    ini, fim = a.periodo
    n_var = len(a.metricas)
    dias = a.metricas[0].n_dias if a.metricas else 0
    venc = a.metricas[0]

    if a.impacto_dia is not None and a.vice:
        ganho = f"+{_brl(a.impacto_dia)}/dia sobre {a.vice}"
    else:
        ganho = "sem comparação"

    resultado = (
        f"{a.vencedor} lidera em lucro líquido ({_brl(venc.lucro_dia)}/dia), "
        f"{ganho}. {a.teste_usado}, "
        f"p={('%.4f' % a.p_valor).replace('.', ',') if a.p_valor is not None else '—'}."
    )

    return {
        "nome_do_teste": f"Cashback {a.parceiro} — {ini.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}",
        "descricao": f"Teste A/B de % de cashback · {n_var} variantes · {dias} dias por variante",
        "periodo": f"{ini.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}",
        "variantes": ", ".join(m.grupo for m in sorted(a.metricas, key=lambda x: x.grupo)),
        "metrica_decisao": "Lucro líquido (comissão − cashback)",
        "resultado": resultado,
        "decisao": a.decisao,
        "confianca": a.confianca,
        "data_analise": datetime.now().strftime("%d/%m/%Y %H:%M"),
    }


# ----------------------------------------------------------------------------
# Destino 1: CSV local (sempre disponível)
# ----------------------------------------------------------------------------
def registrar_csv(linha: dict, caminho: str = "tracker.csv") -> str:
    """Grava a linha no CSV, atualizando se o teste já existir (upsert por nome)."""
    linhas = []
    if os.path.exists(caminho):
        with open(caminho, encoding="utf-8", newline="") as fh:
            linhas = list(csv.DictReader(fh))

    for i, existente in enumerate(linhas):
        if existente.get("nome_do_teste") == linha["nome_do_teste"]:
            linhas[i] = linha
            break
    else:  # não encontrou: acrescenta nova linha
        linhas.append(linha)

    with open(caminho, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUNAS)
        writer.writeheader()
        writer.writerows(linhas)
    return caminho


# ----------------------------------------------------------------------------
# Destino 2: Google Sheets (opcional, diferencial)
# ----------------------------------------------------------------------------
def registrar_sheets(linha: dict, credenciais: str, planilha: str,
                     aba: str = "Testes") -> str:
    """
    Grava a linha numa planilha do Google Sheets (upsert por nome do teste).

    Parâmetros:
    - credenciais: caminho do JSON da service account;
    - planilha: o ID (da URL) ou o nome exato da planilha;
    - aba: nome da aba/worksheet.

    Importado aqui dentro para que o CSV funcione mesmo sem gspread instalado.
    """
    import gspread
    from google.oauth2.service_account import Credentials

    escopos = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_file(credenciais, scopes=escopos)
    cliente = gspread.authorize(creds)

    # Abre por ID (preferível) e, se falhar, tenta pelo nome.
    try:
        doc = cliente.open_by_key(planilha)
    except Exception:
        doc = cliente.open(planilha)

    try:
        ws = doc.worksheet(aba)
    except gspread.WorksheetNotFound:
        ws = doc.add_worksheet(title=aba, rows=200, cols=len(COLUNAS))

    valores = ws.get_all_values()
    # Garante o cabeçalho: se a 1ª linha não for exatamente as COLUNAS,
    # insere o cabeçalho no topo (sem sobrescrever dados existentes).
    if not valores:
        ws.append_row(COLUNAS, value_input_option="USER_ENTERED")
    elif valores[0] != COLUNAS:
        ws.insert_row(COLUNAS, index=1, value_input_option="USER_ENTERED")
    valores = ws.get_all_values()

    nova = [linha[c] for c in COLUNAS]
    nomes_existentes = [r[0] for r in valores[1:]]  # coluna A, sem o cabeçalho
    if linha["nome_do_teste"] in nomes_existentes:
        idx = nomes_existentes.index(linha["nome_do_teste"]) + 2  # +1 cabeçalho, +1 base-1
        ws.update(range_name=f"A{idx}", values=[nova], value_input_option="USER_ENTERED")
    else:
        ws.append_row(nova, value_input_option="USER_ENTERED")

    return doc.url


# ----------------------------------------------------------------------------
# Orquestra: sempre CSV, e Sheets se houver credencial
# ----------------------------------------------------------------------------
def registrar(ingestao, analise, csv_path: str = "tracker.csv",
              credenciais: str | None = None, planilha: str | None = None,
              aba: str = "Testes") -> dict:
    """
    Registra o teste no CSV e, se credenciais + planilha forem informados,
    também no Google Sheets. Retorna os destinos gravados.
    """
    linha = montar_linha(ingestao, analise)
    saidas = {"csv": registrar_csv(linha, csv_path)}
    if credenciais and planilha:
        saidas["sheets"] = registrar_sheets(linha, credenciais, planilha, aba)
    return saidas


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "src")
    from ingestao import carregar_dataset
    from analise_engine import analisar

    ing = carregar_dataset(sys.argv[1])
    ana = analisar(ing.df, ing.parceiro)
    saidas = registrar(ing, ana)
    print(f"Registrado em: {saidas['csv']}")