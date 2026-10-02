"""Fit the MMM and score it against the truth.

The model is given exactly what a client's data team can hand over: dates,
weekly spend per channel, and weekly revenue. It is not given the adstock
rates, the saturation curves, the baseline or the per-channel contributions,
all of which config.py knows.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from pymc_marketing.mmm import MMM, GeometricAdstock, LogisticSaturation

from .config import CHANNELS, OPTIMISATION, RANDOM_SEED


def build() -> MMM:
    """Geometric adstock then logistic saturation, plus yearly seasonality.

    Seasonality is in the model because it is in the business: without it, a
    channel that happens to spend during the strong season is credited with the
    season itself. That is the most common way an MMM flatters a channel.
    """
    return MMM(
        date_column="date",
        channel_columns=list(CHANNELS),
        adstock=GeometricAdstock(l_max=8),
        saturation=LogisticSaturation(),
        yearly_seasonality=2,
    )


def fit(frame: pd.DataFrame, draws: int = 1000, chains: int = 4, tune: int = 2000) -> MMM:
    """Sample the posterior.

    target_accept is raised to 0.95: at the default the sampler produced 93
    divergences on this geometry. Divergences mean the chains could not explore
    parts of the posterior, so the resulting intervals are not trustworthy — a
    diagnostic to fix, not a warning to scroll past.
    """
    model = build()
    features = frame[["date", *CHANNELS]]
    target = frame["revenue"]
    model.fit(
        X=features,
        y=target,
        draws=draws,
        chains=chains,
        tune=tune,
        target_accept=0.95,
        random_seed=RANDOM_SEED,
        progressbar=False,
    )
    return model


def estimated_roi(model: MMM, frame: pd.DataFrame) -> pd.DataFrame:
    """Posterior-mean incremental revenue per unit of spend, by channel."""
    contributions = model.compute_channel_contribution_original_scale()
    mean_contribution = contributions.mean(dim=("chain", "draw")).sum(dim="date")

    rows = []
    for channel in CHANNELS:
        spend = float(frame[channel].sum())
        contribution = float(mean_contribution.sel(channel=channel))
        rows.append({"channel": channel, "spend": spend,
                     "estimated_contribution": contribution,
                     "estimated_roi": contribution / spend})
    return pd.DataFrame(rows)


def recovery_report(model: MMM, frame: pd.DataFrame, truth: pd.DataFrame) -> pd.DataFrame:
    """Side-by-side: what the process did, and what the model thinks it did.

    This table is the deliverable. On real data it cannot exist, which is
    exactly why the simulation is worth the honesty cost of not being real.
    """
    estimated = estimated_roi(model, frame)
    merged = truth.merge(estimated, on=["channel", "spend"], suffixes=("_true", "_est"))
    merged = merged.rename(columns={"roi": "true_roi", "contribution": "true_contribution"})
    merged["roi_error"] = merged["estimated_roi"] - merged["true_roi"]
    merged["roi_error_pct"] = merged["roi_error"] / merged["true_roi"]
    merged["true_rank"] = merged["true_roi"].rank(ascending=False).astype(int)
    merged["estimated_rank"] = merged["estimated_roi"].rank(ascending=False).astype(int)
    return merged.sort_values("true_roi", ascending=False).reset_index(drop=True)


def signal_to_noise(frame: pd.DataFrame, noise_sd: float) -> pd.DataFrame:
    """How much of each channel's effect is visible above weekly revenue noise.

    Computed from the SIMULATION's true contributions, which a real project
    cannot do. The real-world equivalent is the ratio of a channel's spend
    variation to unexplained revenue variance, and it answers the question that
    should be asked before fitting anything: is there enough signal here for an
    MMM to say something, or will it return the prior dressed as a finding?
    """
    rows = []
    for channel in CHANNELS:
        contribution = frame[f"{channel}_contribution_true"]
        rows.append(
            {
                "channel": channel,
                "share_of_revenue": contribution.sum() / frame["revenue"].sum(),
                "signal_to_noise": contribution.std() / noise_sd,
            }
        )
    return pd.DataFrame(rows)


def roi_rank_correlation(report: pd.DataFrame) -> float:
    """Spearman between true and estimated ROI.

    More forgiving than exact rank matching, and closer to the decision: what
    matters is whether the ordering of channels survives, not whether each lands
    on its exact position.
    """
    from scipy import stats

    return float(stats.spearmanr(report["true_roi"], report["estimated_roi"]).statistic)


def rank_agreement(report: pd.DataFrame) -> float:
    """Share of channels the model places in the correct ROI position.

    Ranking is the decision the business actually makes: where the next pound
    goes. A model can misstate every ROI level and still be useful if the order
    is right, and can get levels close while inverting the order and be worse
    than useless.
    """
    return float((report["true_rank"] == report["estimated_rank"]).mean())


def optimise_budget(model: MMM, frame: pd.DataFrame, num_periods: int = 13) -> pd.DataFrame:
    """Reallocate a fixed budget across channels using the fitted response curves.

    The total is held at the recent run-rate: this answers "where should the
    money we already spend go", which is the question a team can act on without
    a new budget approval.

    Bounds are applied because an unconstrained optimiser will happily
    recommend moving 90% of spend into one channel. No media team implements
    that, and the saturation curve is least trustworthy exactly where no data
    was observed.
    """
    recent = frame.tail(num_periods)
    current = {channel: float(recent[channel].mean()) for channel in CHANNELS}
    total = sum(current.values())

    bounds = {
        channel: (
            spend * OPTIMISATION.min_share_of_current,
            spend * OPTIMISATION.max_share_of_current,
        )
        for channel, spend in current.items()
    }

    allocation, _ = model.optimize_budget(
        budget=total * OPTIMISATION.budget_multiplier,
        num_periods=num_periods,
        budget_bounds=bounds,
    )
    optimised = {channel: float(allocation.sel(channel=channel)) for channel in CHANNELS}

    rows = []
    for channel in CHANNELS:
        rows.append(
            {
                "channel": channel,
                "current_weekly_spend": round(current[channel], 2),
                "recommended_weekly_spend": round(optimised[channel], 2),
                "change": round(optimised[channel] - current[channel], 2),
                "change_pct": round((optimised[channel] - current[channel]) / current[channel], 4),
                "at_bound": bool(
                    abs(optimised[channel] - bounds[channel][0]) < 1
                    or abs(optimised[channel] - bounds[channel][1]) < 1
                ),
            }
        )
    return pd.DataFrame(rows)
