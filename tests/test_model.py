"""Model-side helpers, tested without paying for an MCMC run."""

import pandas as pd

from mmm.config import BASELINE
from mmm.model import build, roi_rank_correlation, signal_to_noise
from mmm.simulate import simulate


def test_model_is_configured_with_adstock_and_saturation():
    model = build()
    assert model.adstock is not None
    assert model.saturation is not None
    # Seasonality must be modelled, or a channel that spends in the strong
    # season is credited with the season.
    assert model.yearly_seasonality == 2


def test_signal_to_noise_flags_the_unidentifiable_channel():
    """The diagnostic that predicts which ROI estimates can be trusted.

    affiliate contributes about 1% of revenue and its weekly variation is a
    few percent of the revenue noise, so an MMM has nothing to learn from.
    """
    table = signal_to_noise(simulate(), BASELINE.noise_sd).set_index("channel")
    assert table.loc["affiliate", "signal_to_noise"] < 0.1
    assert table.loc["tv", "signal_to_noise"] > table.loc["affiliate", "signal_to_noise"] * 10


def test_rank_correlation_is_one_for_a_perfect_estimate():
    report = pd.DataFrame({"true_roi": [0.7, 0.5, 0.3], "estimated_roi": [0.8, 0.6, 0.4]})
    assert roi_rank_correlation(report) == 1.0


def test_rank_correlation_is_negative_when_the_order_inverts():
    report = pd.DataFrame({"true_roi": [0.7, 0.5, 0.3], "estimated_roi": [0.2, 0.5, 0.9]})
    assert roi_rank_correlation(report) == -1.0
