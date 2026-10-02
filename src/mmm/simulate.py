"""Generate the dataset from the known process in config.py.

Written so the transformations match the ones the model will fit: geometric
adstock then logistic saturation. If the simulation used a different functional
form, "recovery" would be measuring the wrong thing.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import BASELINE, RANDOM_SEED, START_DATE, TRUTH, WEEKS


def geometric_adstock(spend: np.ndarray, alpha: float, max_lag: int = 8) -> np.ndarray:
    """Carryover: each week keeps a decaying share of previous weeks' spend."""
    weights = alpha ** np.arange(max_lag + 1)
    weights = weights / weights.sum()
    padded = np.concatenate([np.zeros(max_lag), spend])
    return np.array([np.dot(weights[::-1], padded[i:i + max_lag + 1]) for i in range(len(spend))])


def logistic_saturation(x: np.ndarray, lam: float) -> np.ndarray:
    """Diminishing returns, scaled to [0, 1)."""
    return (1 - np.exp(-lam * x)) / (1 + np.exp(-lam * x))


def simulate() -> pd.DataFrame:
    """Weekly spend by channel plus the revenue it produced.

    Also returns the per-channel contribution, which a real dataset never has.
    It is kept so the model's estimate can be scored against the truth.
    """
    rng = np.random.default_rng(RANDOM_SEED)
    dates = pd.date_range(START_DATE, periods=WEEKS, freq="W-SUN")
    frame = pd.DataFrame({"date": dates})
    week_index = np.arange(WEEKS)

    baseline = (
        BASELINE.intercept
        + BASELINE.weekly_trend * week_index
        + BASELINE.yearly_amplitude * np.sin(2 * np.pi * week_index / 52.0)
    )
    frame["baseline_true"] = baseline
    revenue = baseline.copy()

    for channel, truth in TRUTH.items():
        spend = np.clip(
            rng.normal(truth.base_spend, truth.spend_sd, WEEKS)
            # A mild campaign pattern: real plans are not white noise.
            * (1 + 0.25 * np.sin(2 * np.pi * week_index / 26.0 + hash(channel) % 7)),
            0, None,
        )
        frame[channel] = spend

        # Scale before saturation so lambda is interpretable across channels of
        # very different spend levels.
        scaled = spend / spend.max()
        contribution = truth.beta * logistic_saturation(
            geometric_adstock(scaled, truth.adstock_alpha), truth.saturation_lambda
        )
        # Express contribution in revenue units.
        contribution = contribution * truth.base_spend * 2.2
        frame[f"{channel}_contribution_true"] = contribution
        revenue = revenue + contribution

    frame["revenue"] = revenue + rng.normal(0, BASELINE.noise_sd, WEEKS)
    return frame


def true_roi(frame: pd.DataFrame) -> pd.DataFrame:
    """Incremental revenue per unit of spend, from the generating process."""
    rows = []
    for channel in TRUTH:
        contribution = frame[f"{channel}_contribution_true"].sum()
        spend = frame[channel].sum()
        rows.append({"channel": channel, "spend": spend, "contribution": contribution,
                     "roi": contribution / spend})
    return pd.DataFrame(rows).sort_values("roi", ascending=False).reset_index(drop=True)
