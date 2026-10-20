"""Job: fit the MMM without and with geo-lift calibration, diagnose, register.

Writes reports/train/: diagnostics.json, roi_<name>.csv, fitted_<name>.csv,
contributions_<name>.csv; registers both models and promotes the calibrated
one if it passes the convergence gate.
"""

from __future__ import annotations

import argparse

from .. import settings
from ..data import load_mart
from ..data.features import model_frame
from ..model import diagnostics
from ..model.build import fit_mmm, scales
from ..model.posterior import channel_posterior, contributions, roi_table
from ..registry import Registry
from . import geolift
from .common import log, out_dir, read_json, setup, write_json

NAMES = {"uncalibrated": "mmm_uncalibrated", "calibrated": "mmm_calibrated"}


def run(cfg: dict) -> dict:
    mart = load_mart(cfg)
    frame = model_frame(mart, cfg)
    out = out_dir(cfg, "train")
    cal = geolift.calibration_frame(cfg)
    if cal is None:
        log.info("no geo-lift calibration found: running the geolift job first")
        geolift.run(cfg)
        cal = geolift.calibration_frame(cfg)
    reg = Registry(settings.path(cfg, "registry.path"))
    sc = scales(frame, cfg)
    ref = frame.tail(cfg["optimizer"]["reference_days"])
    current = {c: float(ref[c].mean()) for c in cfg["channels"]}
    report = {"window": {"start": str(frame.date.iloc[0].date()), "end": str(frame.date.iloc[-1].date()),
                         "days": len(frame)}, "calibration": cal.iloc[0].to_dict(), "models": {}}
    usable = read_json(out_dir(cfg, "geolift") / "readout.json")["decision"]["use_for_calibration"]
    report["calibration_used"] = bool(usable)
    for label, name in NAMES.items():
        if label == "calibrated" and not usable:
            # an inconclusive test says "we could not measure it", not "the effect is X":
            # feeding it to the model as a measurement would be inventing data
            log.warning("geo-lift verdict is not usable for calibration: calibrated model skipped")
            continue
        log.info("fitting %s model on %d days", label, len(frame))
        mmm = fit_mmm(frame, cfg, cal if label == "calibrated" else None)
        health = diagnostics.sampler_health(mmm)
        checks = diagnostics.predictive_checks(mmm, frame, cfg)
        checks.pop("fitted").to_csv(out / f"fitted_{label}.csv", index=False)
        roi = roi_table(mmm, frame, cfg)
        roi.to_csv(out / f"roi_{label}.csv", index=False)
        contributions(mmm, frame).rename_axis("date").reset_index().to_csv(out / f"contributions_{label}.csv",
                                                                             index=False)
        post = channel_posterior(mmm, sc)
        version = reg.save(name, mmm, post, {
            "calibrated": label == "calibrated", "diagnostics": health, "checks": checks,
            "window": report["window"], "current_daily_spend": current, "roi": roi.to_dict(orient="records"),
            "profile": cfg["profile"]})
        if health["converged"]:
            reg.promote(version)
        else:
            log.warning("%s did not converge (%s): registered, not promoted", version, health)
        report["models"][label] = {"version": version, "diagnostics": health, "checks": checks}
        log.info("%s: r-hat max %.3f, divergences %d, in-sample MAPE %.1f%%", label, health["rhat_max"],
                 health["divergences"], 100 * checks["posterior_predictive"]["mape"])
    write_json(out / "diagnostics.json", report)
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile")
    run(setup(ap.parse_args(argv).profile))


if __name__ == "__main__":
    main()
