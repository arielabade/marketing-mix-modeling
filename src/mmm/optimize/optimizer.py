"""Where should the next real go?

Role in the pipeline
    Last modelling step: takes the calibrated model's response curves and a
    budget, returns the allocation that maximises expected incremental revenue.
Input
    ``ChannelPosterior`` (draws of each channel's curve), current daily spend
    per channel, total budget, per-channel bounds, horizon in days.
Output
    ``Allocation``: recommended vs current spend per channel, expected
    incremental revenue of each, and the posterior distribution of the gain.
Dependencies
    numpy, scipy (SLSQP).

Decisions
    * Maximise the posterior MEAN of total incremental revenue. Revenue is
      linear in the draws, so this equals optimising the mean curve, and it is
      the risk-neutral choice for a budget that is re-decided every month.
    * Bounds are relative to current spend (default 50%-150%): the curves are
      only trustworthy inside the spend range the data has seen; outside it
      the optimiser would be trading on extrapolation.
    * Uncertainty is reported, not optimised away: the same allocation is
      evaluated on every draw, giving an interval for the gain and the
      probability that the recommendation beats the current split.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from ..model.posterior import ChannelPosterior


@dataclass
class Allocation:
    table: pd.DataFrame                 # per channel: current, recommended, revenue, ROI, marginal ROI
    total_budget: float                 # R$ over the horizon
    horizon_days: int
    gain_mean: float                    # expected extra incremental revenue vs current split (R$, horizon)
    gain_low: float
    gain_high: float
    prob_better: float
    revenue_recommended: dict = field(default_factory=dict)  # mean, low, high (R$, horizon)
    revenue_current: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"total_budget": self.total_budget, "horizon_days": self.horizon_days,
                "gain_mean": self.gain_mean, "gain_low": self.gain_low, "gain_high": self.gain_high,
                "prob_better": self.prob_better, "revenue_recommended": self.revenue_recommended,
                "revenue_current": self.revenue_current, "channels": self.table.to_dict(orient="records")}


def _total(post: ChannelPosterior, channels: list[str], daily: np.ndarray) -> np.ndarray:
    """[draw] total daily incremental revenue of a daily allocation."""
    return sum(post.response(c, [daily[i]])[:, 0] for i, c in enumerate(channels))


def optimize_budget(post: ChannelPosterior, current_daily: dict[str, float], total_budget: float,
                    horizon_days: int, bounds: dict[str, tuple[float, float]] | None = None,
                    min_share: float = 0.5, max_share: float = 1.5) -> Allocation:
    """Optimal split of ``total_budget`` (R$ over ``horizon_days``) across channels.

    ``bounds`` (R$/day per channel) override the default band of
    ``min_share``-``max_share`` x current daily spend. Raises ValueError when
    the bounds cannot add up to the budget: the business constraint is
    infeasible and silently relaxing it would hide that.
    """
    channels = [c for c in post.channels if c in current_daily]
    cur = np.array([current_daily[c] for c in channels], float)
    daily_budget = total_budget / horizon_days
    if bounds is None:
        bounds = {c: (min_share * current_daily[c], max_share * current_daily[c]) for c in channels}
    lo = np.array([bounds[c][0] for c in channels], float)
    hi = np.array([bounds[c][1] for c in channels], float)
    if (lo > hi).any():
        raise ValueError("a channel has min bound above its max bound")
    if lo.sum() > daily_budget + 1e-6 or hi.sum() < daily_budget - 1e-6:
        raise ValueError(f"bounds sum to [{lo.sum() * horizon_days:,.0f}, {hi.sum() * horizon_days:,.0f}] "
                         f"over the horizon and cannot hold a budget of {total_budget:,.0f}")

    # mean curve: beta*sat is not linear in lam, so average the curves, not the parameters
    def neg_expected(x):
        return -float(_total(post, channels, x).mean())

    start = np.clip(cur * daily_budget / max(cur.sum(), 1e-9), lo, hi)
    if abs(start.sum() - daily_budget) > 1e-6:  # project the start onto the budget
        free = (start > lo) & (start < hi)
        start = start + (daily_budget - start.sum()) * (free / max(free.sum(), 1))
        start = np.clip(start, lo, hi)
    scale = max(daily_budget, 1.0)
    res = minimize(lambda z: neg_expected(z * scale) / scale, start / scale, method="SLSQP",
                   bounds=list(zip(lo / scale, hi / scale, strict=False)),
                   constraints=[{"type": "eq", "fun": lambda z: z.sum() - daily_budget / scale}],
                   options={"maxiter": 500, "ftol": 1e-10})
    x = np.clip(res.x * scale, lo, hi)

    rec_draws = _total(post, channels, x) * horizon_days
    cur_scaled = cur * daily_budget / max(cur.sum(), 1e-9)  # current split at the same total budget
    cur_draws = _total(post, channels, cur_scaled) * horizon_days
    gain = rec_draws - cur_draws
    rows = []
    for i, c in enumerate(channels):
        r_rec = post.response(c, [x[i]])[:, 0] * horizon_days
        r_cur = post.response(c, [cur_scaled[i]])[:, 0] * horizon_days
        m_rec = post.marginal(c, [x[i]])[:, 0]
        rows.append({
            "channel": c,
            "current_daily": float(cur[i]), "current_daily_at_budget": float(cur_scaled[i]),
            "recommended_daily": float(x[i]), "change_pct": float(x[i] / cur_scaled[i] - 1) if cur_scaled[i] else np.nan,
            "recommended_total": float(x[i] * horizon_days),
            "revenue_recommended": float(r_rec.mean()), "revenue_recommended_low": float(np.quantile(r_rec, 0.05)),
            "revenue_recommended_high": float(np.quantile(r_rec, 0.95)),
            "revenue_current": float(r_cur.mean()),
            "roi_recommended": float(r_rec.mean() / max(x[i] * horizon_days, 1e-9)),
            "marginal_roi_recommended": float(m_rec.mean()),
            "marginal_roi_current": float(post.marginal(c, [cur_scaled[i]])[:, 0].mean()),
            "at_lower_bound": bool(abs(x[i] - lo[i]) < 1e-3 * max(lo[i], 1)),
            "at_upper_bound": bool(abs(x[i] - hi[i]) < 1e-3 * max(hi[i], 1)),
        })
    q = lambda a, p: float(np.quantile(a, p))  # noqa: E731
    return Allocation(
        table=pd.DataFrame(rows), total_budget=float(total_budget), horizon_days=int(horizon_days),
        gain_mean=float(gain.mean()), gain_low=q(gain, 0.05), gain_high=q(gain, 0.95),
        prob_better=float((gain > 0).mean()),
        revenue_recommended={"mean": float(rec_draws.mean()), "low": q(rec_draws, 0.05), "high": q(rec_draws, 0.95)},
        revenue_current={"mean": float(cur_draws.mean()), "low": q(cur_draws, 0.05), "high": q(cur_draws, 0.95)},
    )
