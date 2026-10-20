"""Job: build the client dashboard (docs/dashboard) from the other jobs' outputs.

Role in the pipeline
    Last step. Reads reports/{geolift,train,evaluate,optimize}, the registry
    and (for the regional map) the mart, and writes a static site:
        docs/dashboard/index.html   the page (Plotly, no server)
        docs/dashboard/data.json    every number the page shows
        docs/dashboard/br_ufs.geojson  state outlines for the map
Input
    Settings; the reports and registry written by geolift/train/evaluate/optimize.
Output
    The files above. GitHub Pages serves docs/ as is.
Dependencies
    pandas, numpy, mmm.registry, mmm.optimize, mmm.validation (only to show the
    simulator's true ROI next to the estimates, clearly labelled as such).
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from .. import settings
from ..data import load_mart
from ..registry import Registry
from .common import log, read_json, setup, write_json
from .train import NAMES

ASSETS = Path(__file__).resolve().parents[1] / "report" / "assets"
LABELS = {"meta": "Meta Ads", "tiktok": "TikTok Ads", "google_search": "Google Search",
          "google_shopping": "Google Shopping/PMax", "youtube": "YouTube", "afiliados": "Afiliados"}


def _optional(path: Path):
    return read_json(path) if path.exists() else None


def _gain_draws(cfg: dict, reg: Registry, alloc: dict, name: str) -> list[float]:
    """Posterior draws of the extra revenue of the recommended split over the current one."""
    post = reg.posterior(reg.production(name)).thin(cfg["optimizer"]["posterior_draws"])
    h = alloc["horizon_days"]
    rec = sum(post.response(c["channel"], [c["recommended_daily"]])[:, 0] for c in alloc["channels"]) * h
    cur = sum(post.response(c["channel"], [c["current_daily_at_budget"]])[:, 0] for c in alloc["channels"]) * h
    return [round(float(x), 2) for x in rec - cur]


def _curves(cfg: dict, reg: Registry, name: str) -> dict:
    version = reg.production(name)
    post = reg.posterior(version).thin(cfg["optimizer"]["posterior_draws"])
    cur = reg.metadata(version)["current_daily_spend"]
    out = {}
    for c in post.channels:
        grid = np.linspace(0, 2 * cur[c], 41)
        r = post.response(c, grid)
        m = post.marginal(c, grid)
        out[c] = {"spend": grid.round(2).tolist(), "mean": r.mean(0).round(2).tolist(),
                  "low": np.quantile(r, 0.05, 0).round(2).tolist(), "high": np.quantile(r, 0.95, 0).round(2).tolist(),
                  "marginal": m.mean(0).round(4).tolist(), "current": cur[c]}
    return out


def _spend_story(cfg: dict) -> dict:
    """Weekly spend per channel and the daily Meta x TikTok correlation (the "problem" chart)."""
    from ..data.features import spend_wide

    mart = load_mart(cfg)
    daily = spend_wide(mart.media, cfg["channels"], mart.dates)
    weekly = daily.resample("W-MON", label="left", closed="left").sum()
    weekly = weekly[daily.resample("W-MON", label="left", closed="left").size().values == 7]
    corr = {}
    for a in cfg["channels"]:
        for b in cfg["channels"]:
            if a < b and daily[a].std() > 0 and daily[b].std() > 0:
                corr[f"{a}|{b}"] = round(float(daily[a].corr(daily[b])), 3)
    return {"week": weekly.index.strftime("%Y-%m-%d").tolist(),
            **{c: weekly[c].round(0).tolist() for c in cfg["channels"]}, "corr": corr}


def _regional(cfg: dict, geolift: dict | None) -> list[dict]:
    """Per-state figures for the map: test group, revenue, media spend, revenue change in the test."""
    mart = load_mart(cfg)
    end = mart.dates.max()
    last12 = mart.sales[mart.sales.data > end - pd.Timedelta(days=365)]
    rev = last12.groupby("uf").receita.sum()
    spend = mart.media[(mart.media.data > end - pd.Timedelta(days=365)) & (mart.media.tipo_investimento == "pago")] \
        .groupby("uf").investimento.sum()
    g = mart.geo_tests[mart.geo_tests.teste_id == cfg["geolift"]["test_id"]].set_index("uf")
    change = {}
    if geolift:
        t = g.iloc[0]
        s = mart.sales.pivot_table(index="data", columns="uf", values="receita", aggfunc="sum").fillna(0)
        pre = s[(s.index >= t.pre_inicio) & (s.index < t.inicio)].mean()
        post = s[(s.index >= t.inicio) & (s.index <= t.resfriamento_fim)].mean()
        ctrl = g[g.grupo == "controle"].index
        base = post[ctrl].sum() / pre[ctrl].sum()  # what the season did to the control states
        change = ((post / pre) / base - 1).to_dict()  # each state's change beyond the control trend
    rows = []
    for uf in sorted(rev.index.union(spend.index)):
        rows.append({"uf": uf, "grupo": g.grupo.get(uf, "fora do teste"), "receita_12m": float(rev.get(uf, 0)),
                     "midia_12m": float(spend.get(uf, 0)), "variacao_teste": float(change.get(uf, np.nan))})
    return rows


def build_data(cfg: dict) -> dict:
    rep = settings.path(cfg, "reports.path")
    reg = Registry(settings.path(cfg, "registry.path"))
    geo = _optional(rep / "geolift" / "readout.json")
    diag = _optional(rep / "train" / "diagnostics.json")
    ev = _optional(rep / "evaluate" / "summary.json")
    alloc = {k: _optional(rep / "optimize" / f"allocation_{k}.json") for k in NAMES}
    data: dict = {"labels": LABELS, "simulated": True, "profile": cfg["profile"]}
    if geo:
        series = pd.read_csv(rep / "geolift" / "series.csv")
        power = pd.read_csv(rep / "geolift" / "power.csv")
        data["geolift"] = {**{k: v for k, v in geo.items() if k != "donor_weights"},
                           "donor_weights": geo.get("donor_weights", {}),
                           "series": series.to_dict(orient="list"), "power": power.to_dict(orient="records")}
    if diag:
        data["diagnostics"] = diag
        data["roi"] = {k: pd.read_csv(rep / "train" / f"roi_{k}.csv").to_dict(orient="records") for k in NAMES
                       if (rep / "train" / f"roi_{k}.csv").exists()}
        best = "calibrated" if "calibrated" in data["roi"] else "uncalibrated"
        data["main_model"] = best
        contrib = pd.read_csv(rep / "train" / f"contributions_{best}.csv", parse_dates=["date"])
        monthly = contrib.set_index("date").resample("MS").sum()
        data["contributions_monthly"] = {"month": monthly.index.strftime("%Y-%m").tolist(),
                                         **{c: monthly[c].round(0).tolist() for c in monthly.columns}}
        fitted = pd.read_csv(rep / "train" / f"fitted_{best}.csv", parse_dates=["date"]).set_index("date")
        wk = fitted.resample("W-MON").sum()
        data["fit_weekly"] = {"week": wk.index.strftime("%Y-%m-%d").tolist(), "y": wk.y.round(0).tolist(),
                              "pred": wk.pred.round(0).tolist()}
    if ev:
        data["evaluation"] = ev
        f = rep / "evaluate" / "roi_vs_truth.csv"
        if f.exists():
            data["roi_vs_truth"] = pd.read_csv(f).to_dict(orient="records")
    for k, a in alloc.items():
        if a:
            data.setdefault("allocation", {})[k] = a
            data.setdefault("gain_draws", {})[k] = _gain_draws(cfg, reg, a, NAMES[k])
            data.setdefault("curves", {})[k] = _curves(cfg, reg, NAMES[k])
    data["regional"] = _regional(cfg, geo)
    data["spend"] = _spend_story(cfg)
    return data


def run(cfg: dict) -> Path:
    data = build_data(cfg)
    out = settings.path(cfg, "reports.dashboard")
    out.mkdir(parents=True, exist_ok=True)
    write_json(out / "data.json", data)
    shutil.copy(ASSETS / "br_ufs.geojson", out / "br_ufs.geojson")
    html = (ASSETS / "dashboard.html").read_text(encoding="utf-8")
    geo = (ASSETS / "br_ufs.geojson").read_text(encoding="utf-8")
    # inline data and outlines too, so the page also works opened from disk (file://)
    payload = json.dumps(json.loads((out / "data.json").read_text()), ensure_ascii=False, separators=(",", ":"))
    html = html.replace("/*__DATA__*/null", payload).replace("/*__GEO__*/null", geo)
    (out / "index.html").write_text(html, encoding="utf-8")
    if cfg["profile"] == "default":  # README figures reflect the full run only
        from .. import figures

        for f in figures.main(cfg):
            log.info("figure %s", f)
    log.info("dashboard written to %s", out / "index.html")
    return out / "index.html"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--profile")
    run(setup(ap.parse_args(argv).profile))


if __name__ == "__main__":
    main()
