"""Job: out-of-sample backtest (time-ordered) and validation against the ground truth.

Writes reports/evaluate/: backtest.csv, backtest_predictions.csv,
roi_vs_truth.csv, geolift_vs_truth.json, summary.json.
"""

from __future__ import annotations

import argparse

import pandas as pd

from ..data import load_mart
from ..data.features import model_frame
from ..model.diagnostics import backtest
from ..validation import ground_truth as gt
from . import geolift
from .common import log, out_dir, read_json, setup, write_json


def run(cfg: dict, skip_backtest: bool = False) -> dict:
    out = out_dir(cfg, "evaluate")
    train_dir = out_dir(cfg, "train")
    res: dict = {}
    if not skip_backtest:
        frame = model_frame(load_mart(cfg), cfg)
        ro = read_json(out_dir(cfg, "geolift") / "readout.json")
        cal = geolift.calibration_frame(cfg) if ro["decision"]["use_for_calibration"] else None
        bt = backtest(frame, cfg, cal)
        res["backtest_model"] = "calibrated" if cal is not None else "uncalibrated"
        bt.attrs["predictions"].to_csv(out / "backtest_predictions.csv", index=False)
        bt.to_csv(out / "backtest.csv", index=False)
        res["backtest"] = bt.to_dict(orient="records")
        log.info("backtest WAPE by fold: %s", [round(x, 3) for x in bt.wape])

    diag = read_json(train_dir / "diagnostics.json")
    w = diag["window"]
    est = {k: pd.read_csv(train_dir / f"roi_{k}.csv") for k in ("uncalibrated", "calibrated")
           if (train_dir / f"roi_{k}.csv").exists()}
    try:
        cmp = gt.compare_roi(est, w["start"], w["end"])
    except FileNotFoundError as e:
        log.warning("ground truth not available (%s): skipping validation", e)
        write_json(out / "summary.json", res)
        return res
    cmp.to_csv(out / "roi_vs_truth.csv", index=False)
    res["roi_recovery"] = gt.summary(cmp, list(est))
    ro = read_json(out_dir(cfg, "geolift") / "readout.json")
    tg = gt.true_geolift()
    res["geolift_vs_truth"] = {
        "true_lost_revenue": tg["receita_perdida_teste_mais_resfriamento"],
        "estimated_lost_revenue": ro["lost_revenue_mean"],
        "estimated_low": ro["lost_revenue_low"], "estimated_high": ro["lost_revenue_high"],
        "covered": ro["lost_revenue_low"] <= tg["receita_perdida_teste_mais_resfriamento"] <= ro["lost_revenue_high"],
        "true_relative_lift": -tg["lift_relativo_teste"], "estimated_relative_lift": ro["relative_lift_mean"],
        "true_test_roi": tg["iroas_teste"], "estimated_test_roi": ro["roi_mean"]}
    write_json(out / "geolift_vs_truth.json", res["geolift_vs_truth"])
    write_json(out / "summary.json", res)
    log.info("ROI recovery: %s", res["roi_recovery"])
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile")
    ap.add_argument("--skip-backtest", action="store_true")
    a = ap.parse_args(argv)
    run(setup(a.profile), a.skip_backtest)


if __name__ == "__main__":
    main()
