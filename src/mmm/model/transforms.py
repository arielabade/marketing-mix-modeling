"""Adstock and saturation in plain numpy.

Role in the pipeline
    The same functional forms PyMC-Marketing uses inside the model, written
    out so the optimiser, the API and the tests can evaluate response curves
    from posterior draws without building a PyMC graph.
Input
    Spend arrays and parameters.
Output
    Transformed arrays.
Dependencies
    numpy.

Conventions (match pymc_marketing.mmm.GeometricAdstock(normalize=True) and
LogisticSaturation):
    adstock(x)_t   = sum_{l=0..L-1} w_l x_{t-l},  w_l = alpha^l / sum_k alpha^k   (L = l_max weights)
    saturation(x)  = (1 - exp(-lam x)) / (1 + exp(-lam x))
    contribution   = beta * saturation(adstock(spend / spend_scale)) * target_scale
Because the adstock weights sum to one, a constant daily spend s has a steady
state adstock equal to s: the response curve of a sustained budget is just
beta * saturation(s / spend_scale), which is what the optimiser uses.
"""

from __future__ import annotations

import numpy as np


def geometric_adstock(x: np.ndarray, alpha: float, l_max: int, normalize: bool = True) -> np.ndarray:
    """Carryover: today's effective spend is a decaying mix of today and the previous ``l_max - 1`` days."""
    x = np.asarray(x, dtype=float)
    w = alpha ** np.arange(l_max)
    if normalize:
        w = w / w.sum()
    out = np.convolve(x, w)[: len(x)]
    return out


def logistic_saturation(x: np.ndarray, lam: float | np.ndarray) -> np.ndarray:
    """Diminishing returns in [0, 1): each extra real buys less than the one before."""
    z = np.exp(-np.asarray(lam) * np.asarray(x, dtype=float))
    return (1 - z) / (1 + z)


def steady_state_response(spend: np.ndarray, beta, lam, spend_scale: float, target_scale: float) -> np.ndarray:
    """Daily incremental revenue (R$) of holding ``spend`` (R$/day) constant.

    Broadcasts: pass posterior draws as arrays to get one curve per draw.
    """
    return np.asarray(beta) * logistic_saturation(np.asarray(spend) / spend_scale, lam) * target_scale


def marginal_response(spend, beta, lam, spend_scale, target_scale):
    """d(revenue)/d(spend) of the steady-state curve: the return of the NEXT real."""
    z = np.exp(-np.asarray(lam) * np.asarray(spend) / spend_scale)
    return np.asarray(beta) * target_scale * (2 * np.asarray(lam) / spend_scale) * z / (1 + z) ** 2
