"""Export a slice of the live mart to parquet (the small profile's fixture).

Role in the pipeline
    Produces ``tests/fixtures/mart_small/*.parquet`` so CI and the end-to-end
    test run the full pipeline without a database. Run with the live source
    configured (``make snapshot``).
Input
    The configured live source (MySQL by default) and ``config/small.yaml``'s start date.
Output
    One parquet file per mart table. Never includes ground truth (the guard
    blocks it at the source).
Dependencies
    mmm.data.source.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from .. import settings
from .source import get_source


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(settings.ROOT / "tests" / "fixtures" / "mart_small"))
    a = ap.parse_args(argv)
    small = settings.load("small")
    cfg = settings.load("default")
    os.environ.setdefault("MMM_DATA_SOURCE", "mysql")
    src = get_source(cfg)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for key, table in cfg["data"]["tables"].items():
        df = src.read_table(table, None if key == "geo_tests" else small["data"]["start"])
        df.to_parquet(out / f"{table}.parquet", index=False)
        print(f"{table}: {len(df):,} rows")


if __name__ == "__main__":
    main()
