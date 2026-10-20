"""README figures, built from reports/ (never from a refit).

Role in the pipeline
    Part of ``make report``. Reads the outputs of the geolift, train, evaluate
    and optimize jobs and draws the ABADE-themed SVGs the README embeds, so the
    charts cannot disagree with the numbers quoted next to them.
Input
    reports/geolift/{readout.json,series.csv}, reports/evaluate/roi_vs_truth.csv,
    reports/optimize/allocation_calibrated.json.
Output
    assets/figures/{headline,geolift,roi_recovery,budget_shift}.svg
Dependencies
    matplotlib via mmm.brandviz.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import brandviz as bv
from . import settings

LABELS = {"meta": "Meta", "tiktok": "TikTok", "google_search": "Search", "google_shopping": "Shopping/PMax",
          "youtube": "YouTube", "afiliados": "Affiliates"}


def _brl(v: float) -> str:
    return f"R$ {v / 1e3:,.0f}k" if abs(v) < 1e6 else f"R$ {v / 1e6:,.2f}M"


def headline(reports: Path, out: Path) -> Path | None:
    alloc = reports / "optimize" / "allocation_calibrated.json"
    cmp_f = reports / "evaluate" / "roi_vs_truth.csv"
    geo = reports / "geolift" / "readout.json"
    if not (alloc.exists() and cmp_f.exists() and geo.exists()):
        return None
    a, g = json.loads(alloc.read_text()), json.loads(geo.read_text())
    cmp = pd.read_csv(cmp_f)
    err_u, err_c = cmp.abs_error_uncalibrated.mean(), cmp.abs_error_calibrated.mean()
    fig = bv.kpi_strip([
        (f"+{_brl(a['gain_mean'])}", "incremental revenue per month\nsame budget, new split"),
        (f"{-g['relative_lift_mean']:.1%}", "revenue drop in the 7 states\nwhere Meta was switched off"),
        (f"{err_u:.2f} → {err_c:.2f}", "mean ROI error vs truth\nwithout → with the geo-lift"),
    ])
    return bv.save(fig, out / "headline.svg")


def geolift(reports: Path, out: Path) -> Path | None:
    f = reports / "geolift" / "series.csv"
    if not f.exists():
        return None
    s = pd.read_csv(f, parse_dates=["week"])
    g = json.loads((reports / "geolift" / "readout.json").read_text())
    fig, ax = bv.panel(title="Switching Meta off in 7 states: observed vs synthetic control",
                       subtitle=f"Weekly paid revenue, treated states. Shaded: test + cool-down. "
                                f"Lost {_brl(g['lost_revenue_mean'])} ({-g['relative_lift_mean']:.1%}).")
    ax.fill_between(s.week, s.synthetic_low, s.synthetic_high, color=bv.COBALT, alpha=0.18, linewidth=0)
    ax.plot(s.week, s.synthetic, color=bv.COBALT, linestyle=(0, (4, 3)), linewidth=1.8, label="synthetic control")
    ax.plot(s.week, s.observed, color=bv.IVORY, linewidth=2.0, label="observed")
    post = s[s.post]
    if len(post):
        ax.axvspan(post.week.iloc[0], post.week.iloc[-1], color=bv.AMBER, alpha=0.12, linewidth=0)
    ax.yaxis.set_major_formatter(lambda v, _: f"R$ {v / 1e3:,.0f}k")
    ax.legend(frameon=False, loc="upper left", labelcolor=bv.IVORY)
    bv.clean(ax)
    return bv.save(fig, out / "geolift.svg")


def roi_recovery(reports: Path, out: Path) -> Path | None:
    f = reports / "evaluate" / "roi_vs_truth.csv"
    if not f.exists():
        return None
    c = pd.read_csv(f).sort_values("roi_true", ascending=False).reset_index(drop=True)
    fig, ax = bv.panel(title="ROI per channel: truth, MMM alone, MMM + geo-lift",
                       subtitle="Incremental revenue per R$ spent over the training window. Truth = the simulator's planted effect.")
    cats = [LABELS.get(ch, ch) for ch in c.channel]
    bv.grouped_bars(ax, cats, {"truth": c.roi_true.values, "MMM alone": c.roi_uncalibrated.values,
                               "MMM + geo-lift": c.roi_calibrated.values},
                    colors=(bv.AMBER, bv.SLATE, bv.COBALT))
    ax.legend(frameon=False, loc="upper right", labelcolor=bv.IVORY)
    bv.clean(ax)
    return bv.save(fig, out / "roi_recovery.svg")


def budget_shift(reports: Path, out: Path) -> Path | None:
    f = reports / "optimize" / "allocation_calibrated.json"
    if not f.exists():
        return None
    a = json.loads(f.read_text())
    t = pd.DataFrame(a["channels"]).sort_values("change_pct")
    fig, ax = bv.panel(title="Next month's budget: change per channel (same total)",
                       subtitle=f"Optimised on the calibrated model, bounds 50%–150% of current spend. "
                                f"Expected gain {_brl(a['gain_mean'])}, P(better) {a['prob_better']:.0%}.")
    pos = np.arange(len(t))
    colors = [bv.COBALT if v > 0 else bv.CRIMSON for v in t.change_pct]
    bv.bars(ax, pos, t.change_pct.values * 100, colors, horizontal=True, labels=[f"{v:+.0%}" for v in t.change_pct])
    ax.set_yticks(pos, [LABELS.get(ch, ch) for ch in t.channel])
    ax.axvline(0, color=bv.STEEL, linewidth=0.8)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:+.0f}%")
    bv.clean(ax, axis="x", spines=("top", "right", "left"))
    return bv.save(fig, out / "budget_shift.svg")


def main(cfg: dict | None = None) -> list[Path]:
    cfg = cfg or settings.load()
    reports = settings.path(cfg, "reports.path")
    out = settings.ROOT / "assets" / "figures"
    out.mkdir(parents=True, exist_ok=True)
    made = [f(reports, out) for f in (headline, geolift, roi_recovery, budget_shift)]
    return [m for m in made if m]


if __name__ == "__main__":
    for p in main():
        print(p)
