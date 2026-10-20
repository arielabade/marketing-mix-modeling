"""FastAPI service: answers "where should the next real go?" over HTTP.

Role in the pipeline
    Serving layer. Reads the production model from the registry (posterior
    draws only, no PyMC graph), so a request takes milliseconds.
Input
    MMM_REGISTRY_PATH (or config registry.path), MMM_PROFILE.
Output
    JSON endpoints, documented in docs/API.md:
      GET  /health            liveness + which model versions are loaded
      GET  /model             metadata, diagnostics and ROI of the served model
      GET  /channels          ROI and marginal ROI per channel at current spend
      GET  /curves/{channel}  response curve (mean and 90% band) over a spend grid
      POST /optimize          optimal split of a budget, with uncertainty
Dependencies
    fastapi, pydantic, mmm.registry, mmm.optimize.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from .. import __version__, settings
from ..optimize import optimize_budget
from ..registry import Registry

MODELS = {"calibrated": "mmm_calibrated", "uncalibrated": "mmm_uncalibrated"}

app = FastAPI(title="Tecelã MMM API", version=__version__,
              description="Geo-lift-calibrated MMM: channel returns and budget allocation. Simulated data.")


@lru_cache(maxsize=1)
def _cfg() -> dict:
    return settings.load()


@lru_cache(maxsize=1)
def _registry() -> Registry:
    return Registry(settings.path(_cfg(), "registry.path"))


@lru_cache(maxsize=4)
def _load(model: str):
    if model not in MODELS:
        raise HTTPException(404, f"unknown model {model!r}; use one of {list(MODELS)}")
    reg = _registry()
    try:
        version = reg.production(MODELS[model])
    except FileNotFoundError as e:
        raise HTTPException(503, str(e)) from e
    return version, reg.metadata(version), reg.posterior(version)


class OptimizeRequest(BaseModel):
    budget: float | None = Field(None, gt=0, description="Total R$ over the horizon. Default: current run-rate.")
    horizon_days: int = Field(30, ge=1, le=366)
    model: str = Field("calibrated", description="calibrated | uncalibrated")
    bounds: dict[str, tuple[float, float]] | None = Field(
        None, description="Optional R$/day [min, max] per channel. Default: 50%-150% of current daily spend.")
    min_share: float = Field(0.5, ge=0, le=1)
    max_share: float = Field(1.5, ge=1, le=5)


@app.get("/health")
def health():
    loaded = {}
    for m, name in MODELS.items():
        try:
            loaded[m] = _registry().production(name)
        except FileNotFoundError:
            loaded[m] = None
    return {"status": "ok" if loaded.get("calibrated") else "degraded", "version": __version__, "models": loaded}


@app.get("/model")
def model(model: str = "calibrated"):
    version, meta, _ = _load(model)
    keep = ("version", "created_at", "calibrated", "window", "diagnostics", "roi", "current_daily_spend")
    return {k: meta.get(k) for k in keep}


@app.get("/channels")
def channels(model: str = "calibrated"):
    version, meta, post = _load(model)
    cur = meta["current_daily_spend"]
    roi = {r["channel"]: r for r in meta.get("roi", [])}
    out = []
    for c in post.channels:
        m = post.marginal(c, [cur[c]])[:, 0]
        r = post.response(c, [cur[c]])[:, 0]
        out.append({"channel": c, "current_daily_spend": cur[c],
                    "daily_incremental_revenue": float(r.mean()),
                    "roi_at_current_spend": float(r.mean() / max(cur[c], 1e-9)),
                    "marginal_roi": float(m.mean()), "marginal_roi_low": float(np.quantile(m, 0.05)),
                    "marginal_roi_high": float(np.quantile(m, 0.95)),
                    "historical_roi": roi.get(c, {}).get("roi_mean")})
    return {"model_version": version, "channels": out}


@app.get("/curves/{channel}")
def curves(channel: str, model: str = "calibrated", points: int = 25, max_multiple: float = 2.0):
    version, meta, post = _load(model)
    if channel not in post.channels:
        raise HTTPException(404, f"unknown channel {channel!r}")
    cur = meta["current_daily_spend"][channel]
    grid = np.linspace(0, max_multiple * cur, max(points, 2))
    r = post.response(channel, grid)
    return {"model_version": version, "channel": channel, "current_daily_spend": cur,
            "spend": grid.tolist(), "revenue_mean": r.mean(0).tolist(),
            "revenue_low": np.quantile(r, 0.05, axis=0).tolist(), "revenue_high": np.quantile(r, 0.95, axis=0).tolist()}


@app.post("/optimize")
def optimize(req: OptimizeRequest):
    version, meta, post = _load(req.model)
    cur = meta["current_daily_spend"]
    budget = req.budget if req.budget is not None else sum(cur.values()) * req.horizon_days
    if req.bounds:
        unknown = set(req.bounds) - set(post.channels)
        if unknown:
            raise HTTPException(422, f"unknown channels in bounds: {sorted(unknown)}")
        bounds = {c: req.bounds.get(c, (req.min_share * cur[c], req.max_share * cur[c])) for c in post.channels}
    else:
        bounds = None
    try:
        alloc = optimize_budget(post.thin(300), cur, budget, req.horizon_days, bounds=bounds,
                                min_share=req.min_share, max_share=req.max_share)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return {"model_version": version, **alloc.to_dict()}
