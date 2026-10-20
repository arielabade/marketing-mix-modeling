"""Build and fit the MMM.

Role in the pipeline
    Creates the PyMC-Marketing model (geometric adstock -> logistic saturation,
    yearly Fourier seasonality, linear controls), sets the priors, optionally
    attaches the geo-lift as a calibration likelihood, and samples.
Input
    The national daily frame from ``mmm.data.features.model_frame`` and settings.
Output
    A fitted ``pymc_marketing.mmm.MMM``.
Dependencies
    pymc-marketing 0.19 (the classic national MMM class; pinned because 0.20
    removes it in favour of the multidimensional class, see docs/DECISIONS.md).

Priors, and why
    * saturation_beta ~ HalfNormal(sd = k x spend share x mean scaled revenue).
      Every channel starts with the same expected return per real. That is the
      honest prior when nothing else is known, and it is exactly what makes two
      channels whose budgets move together end up with similar ROI: the data
      cannot tell them apart, so the prior's "same return" survives.
    * adstock_alpha ~ Beta(1, 3): most daily carryover is short (mean 0.25), but
      the prior still allows video-style decays of 0.6-0.7.
    * saturation_lam ~ Gamma(3, 1): curves that bend inside the observed spend
      range (spend is scaled by its maximum, so x in [0, 1]).
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

from ..data.features import CONTROL_COLUMNS


def _priors(frame: pd.DataFrame, cfg: dict):
    from pymc_extras.prior import Prior

    ch = cfg["channels"]
    spend = frame[ch].sum()
    share = (spend / spend.sum()).values
    mean_scaled_y = float(frame["y"].mean() / frame["y"].abs().max())
    m = cfg["model"]
    beta_sd = np.maximum(m["beta_prior_scale"] * share * mean_scaled_y, 1e-3)
    return {
        "beta": Prior("HalfNormal", sigma=beta_sd, dims="channel"),
        "lam": Prior("Gamma", alpha=m["lam_prior"]["alpha"], beta=m["lam_prior"]["beta"], dims="channel"),
        "alpha": Prior("Beta", alpha=m["alpha_prior"]["alpha"], beta=m["alpha_prior"]["beta"], dims="channel"),
    }


def build_mmm(frame: pd.DataFrame, cfg: dict):
    """Configure (but do not fit) the model for this frame."""
    from pymc_marketing.mmm import MMM, GeometricAdstock, LogisticSaturation

    p = _priors(frame, cfg)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        return MMM(
            date_column="date",
            channel_columns=list(cfg["channels"]),
            control_columns=list(CONTROL_COLUMNS),
            adstock=GeometricAdstock(l_max=cfg["model"]["adstock_l_max"], priors={"alpha": p["alpha"]}),
            saturation=LogisticSaturation(priors={"lam": p["lam"], "beta": p["beta"]}),
            yearly_seasonality=cfg["model"]["yearly_seasonality"],
        )


def split_xy(frame: pd.DataFrame, cfg: dict) -> tuple[pd.DataFrame, pd.Series]:
    X = frame[["date", *cfg["channels"], *CONTROL_COLUMNS]].reset_index(drop=True)
    return X, frame["y"].reset_index(drop=True)


def fit_mmm(frame: pd.DataFrame, cfg: dict, lift_tests: pd.DataFrame | None = None):
    """Fit the model; with ``lift_tests`` the geo-lift enters as a second likelihood.

    Calibration does not overwrite the model's estimate with the experiment.
    It adds the experiment as one more observation of the Meta response curve,
    weighted by its own uncertainty (``sigma``): a precise test moves the
    posterior a lot, a noisy one barely.
    """
    mmm = build_mmm(frame, cfg)
    X, y = split_xy(frame, cfg)
    s = cfg["model"]["sampler"]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        mmm.build_model(X, y)
        if lift_tests is not None and len(lift_tests):
            mmm.add_lift_test_measurements(lift_tests)
        mmm.fit(X, y, draws=s["draws"], tune=s["tune"], chains=s["chains"], cores=min(s["chains"], 4),
                target_accept=s["target_accept"], nuts_sampler=s.get("nuts_sampler", "pymc"),
                random_seed=s["random_seed"], progressbar=False)
    return mmm


def scales(frame: pd.DataFrame, cfg: dict) -> dict:
    """Max-abs scales PyMC-Marketing applies to spend and revenue (needed to read the curves)."""
    return {"target": float(frame["y"].abs().max()),
            "channels": {c: float(frame[c].abs().max()) for c in cfg["channels"]}}
