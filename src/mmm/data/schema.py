"""Contract for the mart tables the model reads.

Role in the pipeline
    Fails fast, with a readable message, when the mart changes shape: a renamed
    column or a negative spend should stop the run before sampling, not produce
    a confident model of broken data.
Input
    DataFrames as returned by ``source.read_table``.
Output
    The same DataFrames with dtypes coerced, or ``SchemaError``.
Dependencies
    pandas.
"""

from __future__ import annotations

import pandas as pd

# column -> kind ('date', 'str', 'num', 'bool', 'int')
SCHEMAS: dict[str, dict[str, str]] = {
    "media": {"data": "date", "uf": "str", "canal_id": "int", "canal": "str", "canal_mmm": "str",
              "tipo_investimento": "str", "investimento": "num", "impressoes": "num", "cliques": "num",
              "conversoes_plataforma": "num"},
    "sales": {"data": "date", "uf": "str", "pedidos": "num", "receita": "num", "novos_clientes": "num"},
    "controls": {"data": "date", "dia_semana": "int", "feriado_nacional": "bool", "evento_black_friday": "bool",
                 "evento_natal": "bool", "evento_dia_das_maes": "bool", "evento_qualquer": "bool",
                 "promocao_loja": "bool", "indice_preco": "num", "desconto_cupom": "num"},
    "geo_tests": {"teste_id": "int", "canal_mmm": "str", "multiplicador_investimento": "num",
                  "pre_inicio": "date", "inicio": "date", "fim": "date", "resfriamento_fim": "date",
                  "uf": "str", "grupo": "str"},
}
NON_NEGATIVE = {"media": ["investimento", "cliques"], "sales": ["pedidos", "receita"]}
UNIQUE_KEYS = {"media": ["data", "canal_id", "uf"], "sales": ["data", "uf"], "controls": ["data"],
               "geo_tests": ["teste_id", "uf"]}


class SchemaError(ValueError):
    pass


def validate(df: pd.DataFrame, kind: str) -> pd.DataFrame:
    """Check columns, coerce types, and enforce keys and non-negativity."""
    spec = SCHEMAS[kind]
    missing = [c for c in spec if c not in df.columns]
    if missing:
        raise SchemaError(f"{kind}: missing columns {missing}")
    df = df.copy()
    for col, t in spec.items():
        if t == "date":
            df[col] = pd.to_datetime(df[col])
        elif t == "num":
            df[col] = pd.to_numeric(df[col], errors="raise").astype(float)
        elif t == "int":
            df[col] = pd.to_numeric(df[col], errors="raise").astype(int)
        elif t == "bool":
            df[col] = df[col].astype(int).astype(bool)
        else:
            df[col] = df[col].astype(str)
    for col in NON_NEGATIVE.get(kind, []):
        if (df[col] < 0).any():
            raise SchemaError(f"{kind}: negative values in {col}")
    if df.duplicated(UNIQUE_KEYS[kind]).any():
        raise SchemaError(f"{kind}: duplicated key {UNIQUE_KEYS[kind]}")
    if df.empty:
        raise SchemaError(f"{kind}: no rows")
    return df
