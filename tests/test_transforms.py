"""Adstock and saturation: the functional forms the optimiser and API rely on."""

import numpy as np
import pytest

from mmm.model.transforms import geometric_adstock, logistic_saturation, marginal_response, steady_state_response


def test_adstock_without_carryover_is_identity():
    x = np.array([100.0, 0, 0, 50])
    np.testing.assert_allclose(geometric_adstock(x, alpha=0.0, l_max=3), x)


def test_adstock_spreads_a_burst_and_decays():
    x = np.zeros(10)
    x[0] = 100
    a = geometric_adstock(x, alpha=0.6, l_max=8)
    assert a[1] > 0 and a[1] > a[2] > a[3]


def test_normalised_adstock_conserves_volume_at_steady_state():
    """Weights sum to one: a constant spend has steady-state adstock equal to itself."""
    a = geometric_adstock(np.full(60, 10.0), alpha=0.7, l_max=14)
    assert a[-1] == pytest.approx(10.0)


def test_saturation_is_increasing_bounded_and_concave():
    x = np.linspace(0, 5, 200)
    y = logistic_saturation(x, 2.0)
    assert y[0] == pytest.approx(0) and y.max() < 1
    assert np.all(np.diff(y) > 0) and np.all(np.diff(y, 2) < 1e-12)


def test_marginal_response_is_the_derivative_of_the_curve():
    s, h = 3000.0, 1e-3
    num = (steady_state_response(s + h, 0.3, 2.0, 6000, 1e5) - steady_state_response(s - h, 0.3, 2.0, 6000, 1e5)) / (2 * h)
    assert marginal_response(s, 0.3, 2.0, 6000, 1e5) == pytest.approx(num, rel=1e-5)


def test_matches_pymc_marketing_saturation():
    from pymc_marketing.mmm.transformers import logistic_saturation as ref_sat
    from pytensor.xtensor import as_xtensor

    x = np.linspace(0, 1, 11)
    ref = ref_sat(as_xtensor(x, dims=("date",)), lam=2.5).eval()
    np.testing.assert_allclose(logistic_saturation(x, 2.5), ref, rtol=1e-6)


def test_matches_pymc_marketing_adstock():
    from pymc_marketing.mmm.transformers import geometric_adstock as ref_ad
    from pytensor.xtensor import as_xtensor

    x = np.array([0, 100.0, 0, 0, 50, 0, 0, 0])
    ref = ref_ad(as_xtensor(x, dims=("date",)), alpha=0.5, l_max=4, normalize=True, dim="date").eval()
    np.testing.assert_allclose(geometric_adstock(x, 0.5, l_max=4), ref, rtol=1e-6)
