"""Mart contract: the model refuses malformed data before sampling."""

import pandas as pd
import pytest

from mmm.data.schema import SchemaError, validate


def _sales():
    return pd.DataFrame({"data": ["2024-01-01", "2024-01-01"], "uf": ["SP", "RJ"], "pedidos": [3, 1],
                         "receita": [900.0, 250.0], "novos_clientes": [1, 0]})


def test_valid_sales_pass_and_get_typed():
    out = validate(_sales(), "sales")
    assert pd.api.types.is_datetime64_any_dtype(out["data"]) and out["receita"].dtype == float


def test_missing_column_fails():
    with pytest.raises(SchemaError, match="missing"):
        validate(_sales().drop(columns="receita"), "sales")


def test_negative_revenue_fails():
    df = _sales()
    df.loc[0, "receita"] = -1
    with pytest.raises(SchemaError, match="negative"):
        validate(df, "sales")


def test_duplicate_key_fails():
    df = pd.concat([_sales(), _sales().iloc[:1]])
    with pytest.raises(SchemaError, match="duplicated"):
        validate(df, "sales")


def test_negative_spend_fails():
    df = pd.DataFrame({"data": ["2024-01-01"], "uf": ["SP"], "canal_id": [1], "canal": ["meta_prospeccao"],
                       "canal_mmm": ["meta"], "tipo_investimento": ["pago"], "investimento": [-5.0],
                       "impressoes": [100], "cliques": [3], "conversoes_plataforma": [0]})
    with pytest.raises(SchemaError, match="negative"):
        validate(df, "media")
