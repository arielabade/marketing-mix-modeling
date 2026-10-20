"""Shared plumbing for the jobs: settings, output folders, JSON that survives numpy."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from .. import settings

log = logging.getLogger("mmm")


def setup(profile: str | None = None) -> dict:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    return settings.load(profile)


def out_dir(cfg: dict, job: str) -> Path:
    d = settings.path(cfg, "reports.path") / job
    d.mkdir(parents=True, exist_ok=True)
    return d


def _default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (pd.Timestamp,)):
        return o.isoformat()
    if isinstance(o, pd.DataFrame):
        return o.to_dict(orient="records")
    return str(o)


def write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2, default=_default, ensure_ascii=False))


def read_json(path: Path):
    return json.loads(Path(path).read_text())
