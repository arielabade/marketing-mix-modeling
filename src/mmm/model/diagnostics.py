"""Is the fitted model trustworthy enough to act on?

Role in the pipeline
    Runs after every fit. A model that fails here is registered but never
    promoted to production (see mmm.registry).
Input
    A fitted MMM and its frame.
Output
    A dict: r-hat, ESS, divergences, prior/posterior predictive checks,
    in-sample fit; plus ``backtest`` for out-of-sample error.
Dependencies
    arviz, numpy, pandas.

Why the backtest cuts in time
    Each fold trains on everything before a cut date and forecasts the next
    ``horizon_days``. A random split would leak: adstock carries yesterday's
    spend into today's revenue, and seasonality repeats, so a model that saw
    the neighbouring days scores far better than it will on the next month.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

KEY_VARS = ["saturation_beta", "saturation_lam", "adstock_alpha", "intercept", "gamma_control", "y_sigma"]


def sampler_health(mmm) -> dict:
    import arviz as az

    idata = mmm.idata
    names = [v for v in KEY_VARS if v in idata.posterior]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        summ = az.summary(idata, var_names=names, kind="diagnostics")
    div = int(idata.sample_stats["diverging"].sum())
    return {
        "rhat_max": float(summ["r_hat"].max()),
        "ess_bulk_min": float(summ["ess_bulk"].min()),
        "ess_tail_min": float(summ["ess_tail"].min()),
        "divergences": div,
        "n_draws": int(idata.posterior.sizes["chain"] * idata.posterior.sizes["draw"]),
        "converged": bool(summ["r_hat"].max() < 1.01 and div == 0),
    }


def _fit_metrics(y: np.ndarray, pred: np.ndarray, low: np.ndarray | None = None, high: np.ndarray | None = None) -> dict:
    err = y - pred
    out = {
        "mape": float(np.mean(np.abs(err) / np.maximum(np.abs(y), 1e-9))),
        "wape": float(np.abs(err).sum() / np.abs(y).sum()),
        "r2": float(1 - (err ** 2).sum() / ((y - y.mean()) ** 2).sum()),
        "bias": float(err.sum() / y.sum()),
    }
    if low is not None:
        out["coverage_94"] = float(np.mean((y >= low) & (y <= high)))
    return out


def predictive_checks(mmm, frame: pd.DataFrame, cfg: dict) -> dict:
    """Prior predictive (are the priors on the right scale?) and posterior predictive (does it fit?)."""
    from .build import split_xy

    X, y = split_xy(frame, cfg)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        prior = mmm.sample_prior_predictive(X, y, samples=300)
        ppc = mmm.sample_posterior_predictive(X, extend_idata=False, combined=True)
    # prior predictive lives in scaled units: compare the implied daily revenue level
    prior_y = np.asarray(prior["y"]).reshape(-1, len(y)) * float(y.abs().max()) if "y" in prior else None
    post = np.asarray(ppc["y"]).reshape(len(y), -1) if np.asarray(ppc["y"]).shape[0] == len(y) else \
        np.asarray(ppc["y"]).reshape(-1, len(y)).T
    pred, low, high = post.mean(1), np.quantile(post, 0.03, axis=1), np.quantile(post, 0.97, axis=1)
    out = {"posterior_predictive": _fit_metrics(y.values, pred, low, high)}
    if prior_y is not None:
        lvl = prior_y.mean(1)
        out["prior_predictive"] = {
            "mean_daily_revenue_p05": float(np.quantile(lvl, 0.05)),
            "mean_daily_revenue_p95": float(np.quantile(lvl, 0.95)),
            "observed_mean_daily_revenue": float(y.mean()),
            "observed_inside_prior_90": bool(np.quantile(lvl, 0.05) <= y.mean() <= np.quantile(lvl, 0.95)),
        }
    out["fitted"] = pd.DataFrame({"date": frame["date"].values, "y": y.values, "pred": pred, "low": low, "high": high})
    return out


def backtest(frame: pd.DataFrame, cfg: dict, lift_tests: pd.DataFrame | None = None) -> pd.DataFrame:
    """Time-ordered folds: fit before the cut, forecast ``horizon_days`` after it."""
    from .build import fit_mmm, split_xy

    h = cfg["backtest"]["horizon_days"]
    rows, preds = [], []
    n = len(frame)
    for k in range(cfg["backtest"]["folds"], 0, -1):
        cut = n - k * h
        train, test = frame.iloc[:cut], frame.iloc[cut:cut + h]
        mmm = fit_mmm(train, cfg, lift_tests)
        Xt, yt = split_xy(test, cfg)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            pp = mmm.sample_posterior_predictive(Xt, extend_idata=False, combined=True,
                                                 include_last_observations=True)
        arr = np.asarray(pp["y"])
        arr = arr if arr.shape[0] == len(yt) else arr.T
        pred, low, high = arr.mean(1), np.quantile(arr, 0.03, axis=1), np.quantile(arr, 0.97, axis=1)
        m = _fit_metrics(yt.values, pred, low, high)
        m.update({"fold": cfg["backtest"]["folds"] - k + 1, "train_end": str(train["date"].iloc[-1].date()),
                  "test_start": str(test["date"].iloc[0].date()), "test_end": str(test["date"].iloc[-1].date()),
                  "revenue_total_error_pct": float(pred.sum() / yt.sum() - 1)})
        rows.append(m)
        preds.append(pd.DataFrame({"fold": m["fold"], "date": test["date"].values, "y": yt.values, "pred": pred,
                                   "low": low, "high": high}))
    out = pd.DataFrame(rows)
    out.attrs["predictions"] = pd.concat(preds, ignore_index=True)
    return out
