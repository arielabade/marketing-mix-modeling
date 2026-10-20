"""Geo-lift readout: how much revenue did switching the channel off cost?

Role in the pipeline
    Reads the executed test from the mart and estimates the incremental revenue
    of the tested channel in the treated states, with a credible interval.
    Its output is the calibration input of the MMM.
Input
    Weekly revenue per UF, the test metadata, daily spend per UF of the channel.
Output
    A dict with the lost revenue (mean, sd, 95% interval), relative lift,
    implied ROI of the switched-off spend, the DiD check, and the series for
    the dashboard.
Dependencies
    CausalPy (Bayesian synthetic control, WeightedSumFitter), statsmodels (DiD).

Window
    Pre-period: ``pre_start`` to the day before the test. Post-period: the test
    plus the cool-down weeks, because revenue keeps falling for a few days after
    the spend stops (adstock); stopping at the last test day would understate
    the effect.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd


def _windows(weekly: pd.DataFrame, info: dict) -> tuple[pd.DataFrame, pd.Timestamp]:
    w = weekly[(weekly.index >= info["pre_start"]) & (weekly.index <= info["cooldown_end"])]
    return w, info["start"]


def synthetic_control(weekly: pd.DataFrame, info: dict, cfg: dict) -> dict:
    """Bayesian synthetic control on relative revenue (each series / its pre-period mean)."""
    import causalpy as cp

    w, start = _windows(weekly, info)
    pre = w[w.index < start]
    controls = [c for c in info["control"] if pre[c].sum() > 0]
    treated_level = pre[info["treated"]].sum(1).mean()
    df = pd.DataFrame({"tratamento": w[info["treated"]].sum(1) / treated_level})
    for c in controls:
        df[c] = w[c] / pre[c].mean()
    df = df.reset_index(drop=True)
    t0 = int((w.index < start).sum())
    g = cfg["geolift"]
    model = cp.pymc_models.WeightedSumFitter(sample_kwargs={
        "draws": g["draws"], "tune": g["tune"], "chains": g["chains"], "progressbar": False,
        "random_seed": cfg["model"]["sampler"]["random_seed"], "target_accept": 0.95})
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = cp.SyntheticControl(df, treatment_time=t0, control_units=controls, treated_units=["tratamento"],
                                  model=model)
    # posterior of the counterfactual mean (mu), relative units -> R$; shape [weeks, samples]
    def _mu(da):
        return np.asarray(da.stack(sample=("chain", "draw")).transpose("obs_ind", "treated_units", "sample").values)[:, 0, :]

    arr = _mu(res.post_pred) * treated_level
    obs = df["tratamento"].values[t0:] * treated_level
    lost = arr.sum(0) - obs.sum()                    # R$ lost over the post window, per draw
    cf_total = arr.sum(0)
    pre_arr = _mu(res.pre_pred)
    pre_fit = pre_arr.mean(1)
    pre_obs = df["tratamento"].values[:t0]
    weights = res.model.idata.posterior["beta"].mean(("chain", "draw")).values.ravel()
    coeffs = list(res.model.idata.posterior["beta"].coords["coeffs"].values)
    return {
        "method": "synthetic_control",
        "lost_revenue_draws": lost,
        "lost_revenue_mean": float(lost.mean()), "lost_revenue_sd": float(lost.std()),
        "lost_revenue_low": float(np.quantile(lost, 0.025)), "lost_revenue_high": float(np.quantile(lost, 0.975)),
        "relative_lift_mean": float((-lost / cf_total).mean()),
        "relative_lift_low": float(np.quantile(-lost / cf_total, 0.025)),
        "relative_lift_high": float(np.quantile(-lost / cf_total, 0.975)),
        "prob_revenue_fell": float((lost > 0).mean()),
        "pre_mape": float(np.mean(np.abs(pre_fit - pre_obs) / pre_obs)),
        "donor_weights": dict(zip(coeffs, map(float, weights), strict=False)),
        "series": pd.DataFrame({
            "week": w.index, "observed": df["tratamento"].values * treated_level,
            "synthetic": np.concatenate([pre_fit * treated_level, arr.mean(1)]),
            "synthetic_low": np.concatenate([np.quantile(pre_arr, 0.025, 1), np.quantile(arr / treated_level, 0.025, 1)]) * treated_level,
            "synthetic_high": np.concatenate([np.quantile(pre_arr, 0.975, 1), np.quantile(arr / treated_level, 0.975, 1)]) * treated_level,
            "post": np.arange(len(df)) >= t0}),
    }


def difference_in_differences(weekly: pd.DataFrame, info: dict) -> dict:
    """Check with a different identifying assumption: parallel trends in log revenue.

    d_t = log(treated_t) - log(controls_t); effect = mean(d | post) - mean(d | pre),
    with Newey-West standard errors (weekly gaps are autocorrelated).
    """
    import statsmodels.api as sm

    w, start = _windows(weekly, info)
    d = np.log(w[info["treated"]].sum(1)) - np.log(w[info["control"]].sum(1))
    post = (w.index >= start).astype(float)
    X = sm.add_constant(post)
    fit = sm.OLS(d.values, X).fit(cov_type="HAC", cov_kwds={"maxlags": 2})
    delta, se = float(fit.params[1]), float(fit.bse[1])
    treated_post = w.loc[w.index >= start, info["treated"]].sum(1).sum()
    rel = np.exp(delta) - 1
    return {"method": "difference_in_differences", "relative_lift_mean": float(rel),
            "relative_lift_low": float(np.exp(delta - 1.96 * se) - 1),
            "relative_lift_high": float(np.exp(delta + 1.96 * se) - 1),
            "lost_revenue_mean": float(treated_post / (1 + rel) - treated_post), "p_value": float(fit.pvalues[1])}


def spend_context(info: dict) -> dict:
    """Spend the test removed, and the treated states' share of the channel's spend.

    The share is measured in the pre-period: during the test it is zero by design.
    """
    s = info["spend_daily"]
    pre = s[(s.index >= info["pre_start"]) & (s.index < info["start"])]
    test = s[(s.index >= info["start"]) & (s.index <= info["end"])]
    treated, control = info["treated"], [c for c in s.columns if c not in info["treated"]]
    share = float(pre[treated].sum().sum() / pre.sum().sum())
    days = int((info["end"] - info["start"]).days + 1)
    # spend the treated states would have received = control spend during the test x share / (1 - share)
    ctrl_test = float(test[control].sum().sum())
    removed = ctrl_test * share / (1 - share) - float(test[treated].sum().sum())
    national_planned = (ctrl_test / (1 - share)) / days
    return {"treated_spend_share": share, "test_days": days, "spend_removed": removed,
            "national_daily_spend_planned": national_planned}


def read_test(weekly: pd.DataFrame, info: dict, cfg: dict) -> dict:
    sc = synthetic_control(weekly, info, cfg)
    did = difference_in_differences(weekly, info)
    ctx = spend_context(info)
    roi_draws = sc["lost_revenue_draws"] / ctx["spend_removed"]
    out = {"test_id": info["test_id"], "channel": info["channel"], "treated": info["treated"],
           "start": str(info["start"].date()), "end": str(info["end"].date()),
           "cooldown_end": str(info["cooldown_end"].date()), **ctx,
           **{k: v for k, v in sc.items() if k not in ("series", "lost_revenue_draws")},
           "roi_mean": float(roi_draws.mean()), "roi_low": float(np.quantile(roi_draws, 0.025)),
           "roi_high": float(np.quantile(roi_draws, 0.975)), "did": did}
    out["series"] = sc["series"]
    return out
