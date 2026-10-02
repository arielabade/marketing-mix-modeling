"""The simulation is the ground truth, so it is tested before the model is."""

import numpy as np
import pytest

from mmm.config import BASELINE, TRUTH, WEEKS
from mmm.simulate import geometric_adstock, logistic_saturation, simulate, true_roi


def test_adstock_with_no_carryover_leaves_spend_untouched():
    spend = np.array([100.0, 0.0, 0.0, 0.0])
    np.testing.assert_allclose(geometric_adstock(spend, alpha=0.0), spend)


def test_adstock_spreads_a_single_burst_into_later_weeks():
    spend = np.zeros(6)
    spend[0] = 100.0
    carried = geometric_adstock(spend, alpha=0.7)
    assert carried[1] > 0
    assert carried[1] > carried[2] > carried[3]


def test_adstock_conserves_total_effect():
    """Weights are normalised, so carryover moves effect in time, not volume."""
    spend = np.full(40, 10.0)
    carried = geometric_adstock(spend, alpha=0.6)
    # Away from the padded start, the steady state equals the input.
    assert carried[20] == pytest.approx(10.0, rel=1e-6)


def test_saturation_is_increasing_and_bounded():
    x = np.linspace(0, 10, 50)
    y = logistic_saturation(x, lam=3.0)
    assert np.all(np.diff(y) > 0)
    assert y.max() < 1.0
    assert y[0] == pytest.approx(0.0)


def test_saturation_shows_diminishing_returns():
    """The second unit of spend must buy less than the first."""
    y = logistic_saturation(np.array([0.2, 0.4, 0.6]), lam=4.0)
    assert (y[1] - y[0]) > (y[2] - y[1])


def test_simulation_is_reproducible():
    first, second = simulate(), simulate()
    np.testing.assert_allclose(first["revenue"], second["revenue"])


def test_simulation_has_the_declared_shape():
    frame = simulate()
    assert len(frame) == WEEKS
    for channel in TRUTH:
        assert (frame[channel] >= 0).all()
        assert f"{channel}_contribution_true" in frame.columns


def test_media_does_not_explain_all_revenue():
    """A baseline that media cannot claim is what makes the test fair."""
    frame = simulate()
    media = sum(frame[f"{c}_contribution_true"].sum() for c in TRUTH)
    assert 0.2 < media / frame["revenue"].sum() < 0.7


def test_true_roi_orders_channels_as_configured():
    ordering = list(true_roi(simulate())["channel"])
    assert ordering[0] == "tv"
    assert ordering[-1] == "affiliate"
