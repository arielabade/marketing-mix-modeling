"""Optimiser: honours the budget and the bounds, and moves money towards the better curve."""

import numpy as np
import pytest

from mmm.optimize import optimize_budget


def test_spends_exactly_the_budget(posterior, current):
    a = optimize_budget(posterior, current, total_budget=sum(current.values()) * 30, horizon_days=30)
    assert a.table.recommended_total.sum() == pytest.approx(sum(current.values()) * 30, rel=1e-6)


def test_respects_default_bounds(posterior, current):
    a = optimize_budget(posterior, current, sum(current.values()) * 30, 30, min_share=0.5, max_share=1.5)
    for r in a.table.itertuples():
        assert 0.5 * current[r.channel] - 1e-6 <= r.recommended_daily <= 1.5 * current[r.channel] + 1e-6


def test_respects_explicit_bounds(posterior, current):
    b = {"meta": (2000, 2500), "tiktok": (900, 1100), "google_search": (1000, 2000)}
    a = optimize_budget(posterior, current, 4500 * 30, 30, bounds=b)
    for r in a.table.itertuples():
        lo, hi = b[r.channel]
        assert lo - 1e-6 <= r.recommended_daily <= hi + 1e-6


def test_infeasible_bounds_raise(posterior, current):
    with pytest.raises(ValueError):
        optimize_budget(posterior, current, 100 * 30, 30)  # below the sum of minimums


def test_moves_budget_away_from_the_weak_channel(posterior, current):
    """tiktok's curve is flat (low beta): it should lose budget to meta."""
    a = optimize_budget(posterior, current, sum(current.values()) * 30, 30).table.set_index("channel")
    assert a.loc["tiktok", "change_pct"] < 0
    assert a.loc["meta", "change_pct"] > 0


def test_marginal_returns_equalise_at_an_interior_optimum(posterior, current):
    a = optimize_budget(posterior, current, sum(current.values()) * 30, 30, min_share=0.0, max_share=10).table
    inner = a[~a.at_lower_bound & ~a.at_upper_bound]
    if len(inner) >= 2:
        assert np.ptp(inner.marginal_roi_recommended) < 0.05 * inner.marginal_roi_recommended.mean()


def test_recommendation_is_not_worse_than_current(posterior, current):
    a = optimize_budget(posterior, current, sum(current.values()) * 30, 30)
    assert a.gain_mean >= -1e-6 and 0 <= a.prob_better <= 1
