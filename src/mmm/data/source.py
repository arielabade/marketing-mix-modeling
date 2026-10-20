"""Data sources: where the mart tables come from.

Role in the pipeline
    The only module that talks to a database or a file store. Switching from
    the local MySQL to Cloud SQL, BigQuery or a parquet snapshot is a change of
    environment variables, not of code.
Input
    Table names from config (``data.tables``) and the environment:
      MMM_DATA_SOURCE      mysql | bigquery | parquet
      MMM_DATABASE_URL     SQLAlchemy URL (mysql/Cloud SQL), e.g.
                           mysql+pymysql://user:pass@host:3336/tecidos_marts
      MMM_BQ_PROJECT, MMM_BQ_DATASET   for BigQuery
      MMM_PARQUET_DIR      directory with <table>.parquet files
Output
    pandas DataFrames, one per table, filtered to [start, end] on ``data``.
Dependencies
    SQLAlchemy + PyMySQL (mysql), google-cloud-bigquery (optional extra),
    pyarrow (parquet). Every read goes through ``guard.check`` first.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Protocol

import pandas as pd

from . import guard


class DataSource(Protocol):
    def read_table(self, table: str, start: str | None = None, end: str | None = None) -> pd.DataFrame: ...


def _filter_dates(df: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    if "data" not in df.columns:
        return df
    df = df.assign(data=pd.to_datetime(df["data"]))
    if start:
        df = df[df["data"] >= pd.Timestamp(start)]
    if end:
        df = df[df["data"] <= pd.Timestamp(end)]
    return df.reset_index(drop=True)


class SqlSource:
    """MySQL or Cloud SQL for MySQL, through SQLAlchemy.

    Dates are filtered in SQL (the media mart has ~270k rows), with bound
    parameters; the table name comes from config and is checked against an
    identifier pattern before being interpolated.
    """

    def __init__(self, url: str):
        from sqlalchemy import create_engine

        guard.check(url.split("@")[-1])  # host/schema part only, never log credentials
        self.engine = create_engine(url, pool_pre_ping=True)

    def read_table(self, table, start=None, end=None):
        from sqlalchemy import text

        guard.check(table)
        if not table.replace("_", "").isalnum():
            raise ValueError(f"invalid table name {table!r}")
        where, params = [], {}
        if start:
            where.append("data >= :start")
            params["start"] = start
        if end:
            where.append("data <= :end")
            params["end"] = end
        has_date = table != "dim_testes_geo"
        sql = f"SELECT * FROM {table}" + (" WHERE " + " AND ".join(where) if where and has_date else "")
        with self.engine.connect() as con:
            df = pd.read_sql(text(sql), con, params=params if has_date else {})
        return _filter_dates(df, start, end) if has_date else df


class BigQuerySource:
    """BigQuery dataset holding the same mart tables (see docs/DEPLOY.md)."""

    def __init__(self, project: str, dataset: str):
        from google.cloud import bigquery  # optional dependency: pip install .[bigquery]

        guard.check(dataset)
        self.client = bigquery.Client(project=project)
        self.dataset = f"{project}.{dataset}"

    def read_table(self, table, start=None, end=None):
        from google.cloud import bigquery

        guard.check(table)
        has_date = table != "dim_testes_geo"
        sql = f"SELECT * FROM `{self.dataset}.{table}`"
        params = []
        if has_date and (start or end):
            conds = []
            if start:
                conds.append("data >= @start")
                params.append(bigquery.ScalarQueryParameter("start", "DATE", start))
            if end:
                conds.append("data <= @end")
                params.append(bigquery.ScalarQueryParameter("end", "DATE", end))
            sql += " WHERE " + " AND ".join(conds)
        job = self.client.query(sql, job_config=bigquery.QueryJobConfig(query_parameters=params))
        df = job.to_dataframe()
        return _filter_dates(df, start, end) if has_date else df


class ParquetSource:
    """A directory of <table>.parquet files: CI fixture or an offline snapshot."""

    def __init__(self, directory: str | Path):
        guard.check(str(directory))
        self.directory = Path(directory)

    def read_table(self, table, start=None, end=None):
        guard.check(table)
        f = self.directory / f"{table}.parquet"
        guard.check(str(f))
        return _filter_dates(pd.read_parquet(f), start, end)


def get_source(cfg: dict) -> DataSource:
    """Build the configured source. The only branch on backend in the codebase."""
    kind = os.environ.get("MMM_DATA_SOURCE", cfg["data"]["source"]).lower()
    if kind == "mysql":
        url = os.environ.get("MMM_DATABASE_URL")
        if not url:
            raise RuntimeError("MMM_DATABASE_URL is not set (see .env.example)")
        return SqlSource(url)
    if kind == "bigquery":
        return BigQuerySource(os.environ["MMM_BQ_PROJECT"], os.environ["MMM_BQ_DATASET"])
    if kind == "parquet":
        from ..settings import ROOT

        d = os.environ.get("MMM_PARQUET_DIR", str(ROOT / "tests" / "fixtures" / "mart_small"))
        return ParquetSource(d)
    raise ValueError(f"unknown data source {kind!r}")
