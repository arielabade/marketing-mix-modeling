"""Job: next month's budget recommendation from the production (calibrated) model.

Writes reports/optimize/allocation_<name>.json and recommendation.json.
The uncalibrated model is optimised too, to show what the calibration changed.
"""

from __future__ import annotations

import argparse

from .. import settings
from ..optimize import optimize_budget
from ..registry import Registry
from .common import log, out_dir, setup, write_json
from .train import NAMES


def recommend(cfg: dict, reg: Registry, name: str, budget: float | None = None,
              bounds: dict | None = None) -> dict:
    version = reg.production(name)
    meta = reg.metadata(version)
    o = cfg["optimizer"]
    post = reg.posterior(version).thin(o["posterior_draws"])
    current = meta["current_daily_spend"]
    h = o["horizon_days"]
    total = budget if budget is not None else sum(current.values()) * h * o["budget_multiplier"]
    alloc = optimize_budget(post, current, total, h, bounds=bounds,
                            min_share=o["min_share_of_current"], max_share=o["max_share_of_current"])
    return {"model_version": version, "calibrated": meta.get("calibrated"), **alloc.to_dict()}


def run(cfg: dict) -> dict:
    reg = Registry(settings.path(cfg, "registry.path"))
    out = out_dir(cfg, "optimize")
    res = {}
    for label, name in NAMES.items():
        try:
            res[label] = recommend(cfg, reg, name)
        except FileNotFoundError:
            log.warning("no production version of %s", name)
            continue
        write_json(out / f"allocation_{label}.json", res[label])
        log.info("%s: expected gain R$ %.0f (90%% %.0f to %.0f), P(better) %.0f%%", label, res[label]["gain_mean"],
                 res[label]["gain_low"], res[label]["gain_high"], 100 * res[label]["prob_better"])
    if "calibrated" in res:
        write_json(out / "recommendation.json", res["calibrated"])
    return res


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile")
    run(setup(ap.parse_args(argv).profile))


if __name__ == "__main__":
    main()
