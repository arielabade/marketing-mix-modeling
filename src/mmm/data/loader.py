"""Load and validate the four mart tables in one call.

Role in the pipeline
    Entry point of every job: ``load_mart(cfg)`` returns validated tables for
    the configured window.
Input
    Settings (``data.tables``, ``data.start``, ``data.end``) and a DataSource.
Output
    ``MartData`` with media, sales, controls and geo_tests DataFrames.
Dependencies
    mmm.data.source, mmm.data.schema.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from . import schema
from .source import DataSource, get_source


@dataclass
class MartData:
    media: pd.DataFrame      # data x canal x UF
    sales: pd.DataFrame      # data x UF
    controls: pd.DataFrame   # data
    geo_tests: pd.DataFrame  # teste x UF

    @property
    def dates(self) -> pd.DatetimeIndex:
        return pd.DatetimeIndex(sorted(self.controls["data"].unique()))


def load_mart(cfg: dict, source: DataSource | None = None) -> MartData:
    source = source or get_source(cfg)
    t = cfg["data"]["tables"]
    start, end = cfg["data"].get("start"), cfg["data"].get("end")
    media = schema.validate(source.read_table(t["media"], start, end), "media")
    sales = schema.validate(source.read_table(t["sales"], start, end), "sales")
    controls = schema.validate(source.read_table(t["controls"], start, end), "controls")
    geo = schema.validate(source.read_table(t["geo_tests"]), "geo_tests")
    # all three daily tables must cover the same days, or the model silently
    # treats a missing day of spend as zero spend
    days = set(controls["data"])
    if set(sales["data"]) != days:
        raise schema.SchemaError("sales and controls cover different days")
    if not set(media["data"]) <= days:
        raise schema.SchemaError("media has days outside the calendar")
    return MartData(media, sales, controls, geo)
