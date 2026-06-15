"""
Ingestão e limpeza dos datasets de teste A/B de cashback.

Responsável por:
- ler o CSV (qualquer parceiro, qualquer nº de variantes);
- converter valores em R$ no formato brasileiro ("R$ 10.273") para float;
- validar tipos e descartar/registrar linhas ruins (robustez a dados sujos);
- normalizar nomes de colunas e de grupos.

Nenhuma regra de negócio aqui — apenas dados limpos e confiáveis na saída.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

# Nomes de coluna esperados (após normalização). São mapeadas variações comuns
# para um schema interno estável, para o resto do código não depender de acentos.
COLUNAS_CANONICAS = {
    "data": "data",
    "grupos de usuarios": "grupo",
    "grupos de usuários": "grupo",
    "parceiro": "parceiro",
    "compradores": "compradores",
    "comissao": "comissao",
    "comissão": "comissao",
    "cashback": "cashback",
    "vendas totais": "vendas_totais",
}

COLUNAS_MONETARIAS = ["comissao", "cashback", "vendas_totais"]
COLUNAS_OBRIGATORIAS = ["data", "grupo", "compradores", "comissao", "cashback", "vendas_totais"]


@dataclass
class ResultadoIngestao:
    """Saída da ingestão: dados limpos + relatório de qualidade."""

    df: pd.DataFrame
    parceiro: str
    linhas_originais: int
    linhas_validas: int
    linhas_descartadas: int
    motivos_descarte: dict = field(default_factory=dict)
    grupos: list = field(default_factory=list)

    @property
    def taxa_descarte(self) -> float:
        if self.linhas_originais == 0:
            return 0.0
        return self.linhas_descartadas / self.linhas_originais


def parse_moeda_br(valor) -> float:
    """
    Converte um valor monetário em formato brasileiro para float.

    Aceita: "R$ 10.273", "10.273", "R$ 1.234,56", "1234,56", 1234, 1234.5.
    Regra BR: ponto = separador de milhar; vírgula = separador decimal.
    Retorna float('nan') quando não há número válido.
    """
    if valor is None:
        return float("nan")
    if isinstance(valor, (int, float)):
        return float(valor)

    s = str(valor).strip()
    if s == "" or s.lower() in {"nan", "none", "null", "-"}:
        return float("nan")

    # Remove tudo que não seja dígito, vírgula, ponto ou sinal de menos.
    s = re.sub(r"[^\d,.\-]", "", s)
    if s in {"", "-", ".", ","}:
        return float("nan")

    negativo = s.startswith("-")
    s = s.lstrip("-")

    if "," in s:
        # Vírgula é decimal -> pontos são milhares.
        s = s.replace(".", "").replace(",", ".")
    else:
        # Sem vírgula -> pontos são separadores de milhar (convenção BR do dataset).
        s = s.replace(".", "")

    try:
        num = float(s)
    except ValueError:
        return float("nan")
    return -num if negativo else num


def _normaliza_colunas(df: pd.DataFrame) -> pd.DataFrame:
    novos = {}
    for col in df.columns:
        chave = str(col).strip().lower()
        novos[col] = COLUNAS_CANONICAS.get(chave, chave.replace(" ", "_"))
    return df.rename(columns=novos)


def carregar_dataset(caminho: str) -> ResultadoIngestao:
    """
    Lê e limpa um dataset de teste A/B, retornando dados confiáveis + relatório
    de qualidade. Funciona para qualquer parceiro e qualquer nº de variantes
    sem alteração de código.
    """
    df = pd.read_csv(caminho, dtype=str)
    df = _normaliza_colunas(df)
    linhas_originais = len(df)

    faltando = [c for c in COLUNAS_OBRIGATORIAS if c not in df.columns]
    if faltando:
        raise ValueError(
            f"Dataset '{caminho}' não tem as colunas obrigatórias: {faltando}. "
            f"Colunas encontradas: {list(df.columns)}"
        )

    motivos = {}

    def marca(mascara: pd.Series, motivo: str) -> None:
        n = int(mascara.sum())
        if n:
            motivos[motivo] = motivos.get(motivo, 0) + n

    # --- Conversões de tipo ---
    # astype("string") + fillna garante texto mesmo com células vazias (NaN),
    # que no pandas 3.0 sobrevivem a astype(str) como float.
    df["data"] = pd.to_datetime(df["data"], errors="coerce", format="mixed")
    df["grupo"] = df["grupo"].astype("string").fillna("").str.strip()
    df["parceiro"] = df["parceiro"].astype("string").fillna("").str.strip()
    df["compradores"] = pd.to_numeric(df["compradores"], errors="coerce")
    for col in COLUNAS_MONETARIAS:
        df[col] = df[col].map(parse_moeda_br)

    # --- Regras de validade (linha descartada se qualquer uma falhar) ---
    invalida = pd.Series(False, index=df.index)

    m = df["data"].isna()
    marca(m, "data inválida ou ausente")
    invalida |= m

    m = df["grupo"].isin(["", "nan", "None", "null", "<NA>"])
    marca(m, "grupo ausente")
    invalida |= m

    for col in ["compradores"] + COLUNAS_MONETARIAS:
        m = df[col].isna()
        marca(m, f"{col} não numérico/ausente")
        invalida |= m

    m = df["compradores"] < 0
    marca(m, "compradores negativo")
    invalida |= m

    for col in COLUNAS_MONETARIAS:
        m = df[col] < 0
        marca(m, f"{col} negativo")
        invalida |= m

    # Duplicatas exatas de (data, grupo) — mantém a primeira, descarta o resto.
    chave_dup = df.duplicated(subset=["data", "grupo"], keep="first")
    marca(chave_dup & ~invalida, "duplicata de (data, grupo)")
    invalida |= chave_dup

    df_limpo = df.loc[~invalida].copy()
    df_limpo = df_limpo.sort_values(["grupo", "data"]).reset_index(drop=True)

    parceiro = (
        df_limpo["parceiro"].mode().iloc[0]
        if not df_limpo.empty and not df_limpo["parceiro"].mode().empty
        else "Desconhecido"
    )
    grupos = sorted(df_limpo["grupo"].unique().tolist())

    return ResultadoIngestao(
        df=df_limpo,
        parceiro=parceiro,
        linhas_originais=linhas_originais,
        linhas_validas=len(df_limpo),
        linhas_descartadas=linhas_originais - len(df_limpo),
        motivos_descarte=motivos,
        grupos=grupos,
    )


if __name__ == "__main__":
    import sys

    res = carregar_dataset(sys.argv[1])
    print(f"Parceiro: {res.parceiro}")
    print(f"Linhas: {res.linhas_validas}/{res.linhas_originais} válidas "
          f"({res.taxa_descarte:.1%} descartadas)")
    print(f"Variantes: {res.grupos}")
    if res.motivos_descarte:
        print("Motivos de descarte:", res.motivos_descarte)
    print(res.df.head())
