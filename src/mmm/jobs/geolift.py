"""Job: design audit and readout of the geo-lift, plus the calibration row for the MMM.

Writes reports/geolift/: power.csv, mde.csv, controls.csv, readout.json,
series.csv, calibration.csv.
"""

from __future__ import annotations

import argparse

import pandas as pd

from ..data import load_mart
from ..data.features import geo_panel
from ..geolift import design, readout
from ..geolift.decision import decide
from ..model.calibration import lift_row
from .common import log, out_dir, setup, write_json


def run(cfg: dict) -> dict:
    g = cfg["geolift"]
    mart = load_mart(cfg)
    weekly, info = geo_panel(mart, g["test_id"])
    out = out_dir(cfg, "geolift")
    log.info("geo-lift %s: %d treated, %d control states, %d weeks", info["channel"], len(info["treated"]),
             len(info["control"]), len(weekly))

    # ---- design (pre-period only)
    controls = design.rank_controls(weekly, info["treated"], info["control"], info["start"])
    controls.to_csv(out / "controls.csv", index=False)
    pw = g["power"]
    designs = design.candidate_designs(weekly, info["treated"], info["start"])
    power = design.power_table(weekly, designs, info["control"] + [u for d in designs.values() for u in d],
                               info["start"], pw["effect_sizes"], pw["test_weeks"], pw["n_simulations"], pw["alpha"],
                               min_fit_weeks=min(g["min_pre_weeks"], max(len(weekly[weekly.index < info["start"]]) - 9, 4)))
    power.to_csv(out / "power.csv", index=False)
    mde = design.minimum_detectable_effect(power)
    mde.to_csv(out / "mde.csv", index=False)
    weeks_run = int(round(((info["end"] - info["start"]).days + 1) / 7))
    row = mde[(mde.design == "executado")]
    row = row.iloc[(row.test_weeks - weeks_run).abs().argsort()[:1]]
    mde_exec = float(row.mde.iloc[0]) if len(row) else float("nan")

    # ---- readout
    res = readout.read_test(weekly, info, cfg)
    res["series"].to_csv(out / "series.csv", index=False)
    res = {k: v for k, v in res.items() if k != "series"}
    res["mde_executed_design"] = mde_exec
    res["decision"] = decide(res, mde_exec, g["minimum_worthwhile_lift"])
    cal = lift_row(res)
    cal.to_csv(out / "calibration.csv", index=False)
    res["calibration"] = cal.iloc[0].to_dict()
    write_json(out / "readout.json", res)
    # weekly revenue per state for the dashboard map
    weekly.reset_index().to_csv(out / "weekly_by_state.csv", index=False)
    log.info("geo-lift: lost R$ %.0f (95%% %.0f to %.0f), lift %.1f%%, verdict %s",
             res["lost_revenue_mean"], res["lost_revenue_low"], res["lost_revenue_high"],
             100 * res["relative_lift_mean"], res["decision"]["verdict"])
    return res


def calibration_frame(cfg: dict) -> pd.DataFrame | None:
    f = out_dir(cfg, "geolift") / "calibration.csv"
    return pd.read_csv(f) if f.exists() else None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile")
    run(setup(ap.parse_args(argv).profile))


if __name__ == "__main__":
    main()
