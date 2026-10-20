"""Geo-lift design: which states, how many weeks, and could the test detect anything?

Role in the pipeline
    Runs on PRE-period data only, before (or, here, as an audit of) the test.
Input
    Weekly revenue per UF (``mmm.data.features.geo_panel``) and the test metadata.
Output
    Control ranking by pre-period similarity, and a power table: for each test
    length and treated-set size, the probability of detecting a given lift.
Dependencies
    numpy, pandas, scipy.

Method
    Power is estimated by simulation on history, not by a formula, because the
    noise that matters is how well a synthetic control tracks the treated
    states, and that only shows up in the data:
      1. pick a pseudo test start inside the pre-period;
      2. fit synthetic-control weights on the weeks before it;
      3. measure the relative gap between treated and synthetic over the next
         ``weeks`` (a placebo: no treatment happened);
      4. repeat over many starts -> null distribution of the gap;
      5. inject a known effect into the treated series and count how often the
         gap clears the null's critical value -> power.
    Reused from ab-testing-toolkit: "absence of a result is not evidence of no
    effect" is only true if the test was powered, so power is computed first.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import nnls


def synthetic_weights(y: np.ndarray, X: np.ndarray, penalty: float = 1e3) -> np.ndarray:
    """Non-negative weights summing to one (classic synthetic control), via NNLS.

    Series are expected in relative units (divided by their own pre-period
    mean), so a convex combination of donors can match the treated level.
    The sum-to-one constraint enters as a heavily weighted extra row.
    """
    A = np.vstack([X, penalty * np.ones(X.shape[1])])
    b = np.concatenate([y, [penalty]])
    w, _ = nnls(A, b)
    return w / max(w.sum(), 1e-12)


def _relative(df: pd.DataFrame, base_rows: slice) -> pd.DataFrame:
    return df / df.iloc[base_rows].mean().replace(0, np.nan)


def rank_controls(weekly: pd.DataFrame, treated: list[str], controls: list[str], pre_end: pd.Timestamp) -> pd.DataFrame:
    """Controls ordered by correlation with the treated aggregate in the pre-period."""
    pre = weekly[weekly.index < pre_end]
    t = pre[treated].sum(1)
    rows = []
    for c in controls:
        if pre[c].sum() <= 0:
            continue
        rows.append({"uf": c, "corr_pre": float(np.corrcoef(t, pre[c])[0, 1]),
                     "revenue_share_pre": float(pre[c].sum() / pre.sum().sum())})
    return pd.DataFrame(rows).sort_values("corr_pre", ascending=False).reset_index(drop=True)


def placebo_gaps(weekly: pd.DataFrame, treated: list[str], controls: list[str], pre_end: pd.Timestamp,
                 weeks: int, min_fit_weeks: int, effect: float = 0.0, rng=None, n: int | None = None) -> np.ndarray:
    """Relative gap (treated / synthetic - 1) over ``weeks`` weeks, for pseudo-starts in the pre-period."""
    pre = weekly[weekly.index < pre_end]
    T = pre[treated].sum(1).values
    C = pre[controls].values
    starts = np.arange(min_fit_weeks, len(pre) - weeks + 1)
    if rng is not None and n is not None and len(starts) > n:
        starts = rng.choice(starts, n, replace=False)
    gaps = []
    for s in starts:
        tm, cm = T[:s].mean(), C[:s].mean(0)
        ok = cm > 0
        w = synthetic_weights(T[:s] / tm, (C[:s, ok] / cm[ok]))
        synth = (C[s:s + weeks, ok] / cm[ok]) @ w * tm
        obs = T[s:s + weeks] * (1 - effect)
        gaps.append(obs.sum() / synth.sum() - 1)
    return np.array(gaps)


def power_table(weekly: pd.DataFrame, treated_sets: dict[str, list[str]], controls: list[str],
                pre_end: pd.Timestamp, effect_sizes: list[float], test_weeks: list[int],
                n_simulations: int, alpha: float, min_fit_weeks: int = 12, seed: int = 0) -> pd.DataFrame:
    """Power by (treated set, test length, effect size), with a one-sided test for a DROP.

    The tested change switches a channel off, so the hypothesis is directional:
    revenue in the treated states falls. One-sided at ``alpha``.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for name, treated in treated_sets.items():
        ctrl = [c for c in controls if c not in treated]
        share = float(weekly[weekly.index < pre_end][treated].sum().sum() / weekly[weekly.index < pre_end].sum().sum())
        for wk in test_weeks:
            null = placebo_gaps(weekly, treated, ctrl, pre_end, wk, min_fit_weeks, 0.0, rng, n_simulations)
            if len(null) < 5:
                continue
            crit = np.quantile(null, alpha)  # a drop must be more negative than this
            for eff in effect_sizes:
                alt = placebo_gaps(weekly, treated, ctrl, pre_end, wk, min_fit_weeks, eff, rng, n_simulations)
                rows.append({"design": name, "n_treated": len(treated), "treated_revenue_share": share,
                             "test_weeks": wk, "effect": eff, "power": float(np.mean(alt < crit)),
                             "null_sd": float(null.std()), "n_placebos": len(null)})
    return pd.DataFrame(rows)


def minimum_detectable_effect(power: pd.DataFrame, target: float = 0.8) -> pd.DataFrame:
    """Smallest simulated effect reaching ``target`` power, per design and length (NaN if none)."""
    out = []
    for (d, w), g in power.groupby(["design", "test_weeks"]):
        ok = g[g.power >= target].sort_values("effect")
        out.append({"design": d, "test_weeks": w, "n_treated": int(g.n_treated.iloc[0]),
                    "mde": float(ok.effect.iloc[0]) if len(ok) else np.nan})
    return pd.DataFrame(out)


def candidate_designs(weekly: pd.DataFrame, actual: list[str], pre_end: pd.Timestamp,
                      exclude: tuple[str, ...] = ("SP", "RJ", "MG"), sizes=(3, 5, 7, 9)) -> dict[str, list[str]]:
    """Treated sets of increasing size, built the way the real one was: mid-sized
    states, largest first, the three biggest markets kept as controls (holding
    them out would cost too much revenue). The actual design is always included.
    """
    pre = weekly[weekly.index < pre_end].sum().sort_values(ascending=False)
    pool = [u for u in pre.index if u not in exclude]
    designs = {f"{k} UFs": pool[:k] for k in sizes if k <= len(pool)}
    designs["executado"] = list(actual)
    return designs
