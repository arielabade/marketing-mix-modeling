"""Score the fitted models against the effects planted by the generator.

Role in the pipeline
    Final step of ``evaluate``: did the model recover the truth, with and
    without the geo-lift calibration? Possible here only because the data is
    simulated; on real data this table cannot exist.
Input
    MMM_GROUND_TRUTH_DIR (default ../ecommerce/data/ground_truth): files written
    by the ecommerce generator (gerador/verdade.py). Fitted ROI tables.
Output
    Comparison tables: ROI per channel (true vs estimated, uncalibrated and
    calibrated), geo-lift effect (true vs estimated), response curves.
Dependencies
    pandas, json.

This module deliberately bypasses ``mmm.data.guard``: it is the one place the
answer key is read, and ``tests/test_ground_truth_guard.py`` fails if any
other module references it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

from ..settings import ROOT


def truth_dir() -> Path:
    return Path(os.environ.get("MMM_GROUND_TRUTH_DIR", ROOT.parent / "ecommerce" / "data" / "ground_truth"))


def true_roi(start, end) -> pd.DataFrame:
    """True incremental revenue / spend per MMM channel over [start, end]."""
    c = pd.read_csv(truth_dir() / "contribuicao_diaria.csv", parse_dates=["data"])
    c = c[(c.data >= pd.Timestamp(start)) & (c.data <= pd.Timestamp(end)) & (c.canal_mmm != "base")]
    g = c.groupby("canal_mmm")[["investimento", "receita_incremental"]].sum()
    g["roi_true"] = g.receita_incremental / g.investimento.replace(0, np.nan)
    return g.rename_axis("channel").reset_index()


def true_marginal() -> pd.DataFrame:
    return pd.read_csv(truth_dir() / "roi_canal_mmm.csv").rename(columns={"canal_mmm": "channel"})


def true_geolift() -> dict:
    return json.loads((truth_dir() / "geolift_verdade.json").read_text())


def true_curves() -> pd.DataFrame:
    return pd.read_csv(truth_dir() / "curvas_resposta.csv").rename(columns={"canal_mmm": "channel"})


def compare_roi(estimates: dict[str, pd.DataFrame], start, end) -> pd.DataFrame:
    """One row per channel: true ROI and each model's estimate, error and interval coverage."""
    t = true_roi(start, end)
    out = t[["channel", "investimento", "roi_true"]].copy()
    for name, est in estimates.items():
        e = est.set_index("channel")
        out[f"roi_{name}"] = out.channel.map(e["roi_mean"])
        out[f"roi_{name}_low"] = out.channel.map(e["roi_low"])
        out[f"roi_{name}_high"] = out.channel.map(e["roi_high"])
        out[f"abs_error_{name}"] = (out[f"roi_{name}"] - out.roi_true).abs()
        out[f"covered_{name}"] = (out.roi_true >= out[f"roi_{name}_low"]) & (out.roi_true <= out[f"roi_{name}_high"])
    return out


def summary(cmp: pd.DataFrame, names: list[str]) -> dict:
    from scipy.stats import spearmanr

    res = {}
    for n in names:
        res[n] = {"mean_abs_roi_error": float(cmp[f"abs_error_{n}"].mean()),
                  "mean_abs_pct_error": float((cmp[f"abs_error_{n}"] / cmp.roi_true).mean()),
                  "rank_correlation": float(spearmanr(cmp.roi_true, cmp[f"roi_{n}"]).statistic),
                  "interval_coverage": float(cmp[f"covered_{n}"].mean())}
    return res
