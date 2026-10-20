"""Shared fixtures: a synthetic posterior and a throwaway registry, so unit tests never sample MCMC."""

from __future__ import annotations

import numpy as np
import pytest

from mmm.model.posterior import ChannelPosterior

CHANNELS = ["meta", "tiktok", "google_search"]


@pytest.fixture
def posterior() -> ChannelPosterior:
    rng = np.random.default_rng(0)
    n = 200
    beta = np.column_stack([rng.normal(0.30, 0.02, n), rng.normal(0.05, 0.01, n), rng.normal(0.12, 0.01, n)]).clip(0.01)
    lam = np.column_stack([rng.normal(2.0, 0.1, n), rng.normal(2.0, 0.1, n), rng.normal(3.0, 0.1, n)]).clip(0.1)
    alpha = np.full((n, 3), 0.3)
    return ChannelPosterior(CHANNELS, beta, lam, alpha, {"meta": 6000.0, "tiktok": 2000.0, "google_search": 2500.0},
                            100000.0)


@pytest.fixture
def current() -> dict:
    return {"meta": 3000.0, "tiktok": 1000.0, "google_search": 1200.0}


@pytest.fixture
def registry(tmp_path, posterior, current):
    from mmm.registry import Registry

    reg = Registry(tmp_path / "registry")
    meta = {"calibrated": True, "diagnostics": {"converged": True, "rhat_max": 1.0, "divergences": 0},
            "current_daily_spend": current, "window": {"start": "2024-01-01", "end": "2024-12-31", "days": 366},
            "roi": [{"channel": c, "roi_mean": 1.0} for c in CHANNELS]}
    for name in ("mmm_calibrated", "mmm_uncalibrated"):
        v = reg.save(name, None, posterior, meta)
        reg.promote(v)
    return reg
