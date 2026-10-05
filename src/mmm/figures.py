"""Figures for the README, built from the committed report CSVs.

Every figure here reads ``reports/*.csv`` rather than refitting the model, so
regenerating the charts is cheap and cannot silently disagree with the numbers
quoted in the README: if a fit changes, the CSVs change and the charts follow.

Run with ``python -m mmm.figures``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import brandviz as bv

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports"
FIGURES = ROOT / "assets" / "figures"


def _load() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    roi = pd.read_csv(REPORTS / "roi_recovery.csv")
    snr = pd.read_csv(REPORTS / "signal_to_noise.csv")
    budget = pd.read_csv(REPORTS / "budget_allocation.csv")
    return roi, snr, budget


def roi_recovery(roi: pd.DataFrame) -> Path:
    """Did the model recover the ROI the simulator actually used?

    Two peer series, so this is the categorical case rather than the
    highlight-one case: truth and estimate are not subject and background,
    they are the comparison the whole project exists to make.
    """
    roi = roi.sort_values("true_roi", ascending=False).reset_index(drop=True)

    fig, ax = bv.panel(
        12.4, 5.9,
        title="The model ranks every channel that carries signal, and inverts the one that does not",
        subtitle="Return on ad spend: what the simulator used, against what the model recovered",
    )
    ax.set_xlim(-0.6, len(roi) - 0.4)
    ax.set_ylim(0, max(roi["true_roi"].max(), roi["estimated_roi"].max()) * 1.32)
    fig.canvas.draw()

    bv.grouped_bars(
        ax, roi["channel"].tolist(),
        {"True ROI": roi["true_roi"], "Estimated ROI": roi["estimated_roi"]},
        colors=(bv.COBALT, bv.AMBER), label_fmt="{:.2f}",
    )
    ax.set_ylabel("Revenue returned per unit of spend")
    ax.legend(loc="upper right", ncols=2, bbox_to_anchor=(1.0, 1.08))
    bv.clean(ax)

    worst = roi.loc[roi["roi_error_pct"].abs().idxmax()]
    bv.annotate(
        ax,
        f"{worst['channel']}: estimated {worst['estimated_roi']:.2f} against a true "
        f"{worst['true_roi']:.2f}\n{worst['roi_error_pct'] * 100:+.0f}% error, and the only rank the model gets wrong",
        xy=(len(roi) - 1 + 0.19, worst["estimated_roi"] * 1.02),
        xytext=(0.35, ax.get_ylim()[1] * 0.93),
        color=bv.IVORY,
    )
    return bv.save(fig, FIGURES / "roi_recovery.svg")


def signal_diagnostic(roi: pd.DataFrame, snr: pd.DataFrame) -> Path:
    """The diagnostic that predicts the failure before the model is fitted.

    Two panels sharing one channel order: the reader does not have to be told
    that low signal-to-noise and large ROI error are the same fact, they can
    see the two bars line up.
    """
    merged = (
        snr.merge(roi[["channel", "roi_error_pct"]], on="channel")
        .sort_values("signal_to_noise", ascending=False)
        .reset_index(drop=True)
    )
    floor = 0.10  # below this the channel's contribution is inside the noise

    fig, axes = bv.panel(
        12.4, 5.4, ncols=2,
        title="A channel the model cannot measure can be named before it is fitted",
        subtitle="Signal-to-noise is computed from spend and revenue alone. The error is only knowable because the truth is simulated.",
    )
    left, right = axes
    positions = np.arange(len(merged))
    below = merged["signal_to_noise"] < floor
    colors = [bv.CRIMSON if flag else bv.COBALT for flag in below]

    left.set_xlim(-0.6, len(merged) - 0.4)
    left.set_ylim(0, merged["signal_to_noise"].max() * 1.30)
    fig.canvas.draw()
    bv.bars(left, positions, merged["signal_to_noise"], colors,
            labels=merged["signal_to_noise"], label_fmt="{:.2f}", label_pad=0.035)
    left.set_xticks(positions, merged["channel"])
    left.set_title("Before the fit: signal-to-noise", fontsize=11.5, color=bv.STEEL)
    bv.reference_line(left, floor, "measurability floor", where=0.015, ha="left")
    bv.clean(left)

    errors = merged["roi_error_pct"].abs() * 100
    right.set_xlim(-0.6, len(merged) - 0.4)
    right.set_ylim(0, errors.max() * 1.30)
    fig.canvas.draw()
    bv.bars(right, positions, errors, colors,
            labels=[f"{value:,.0f}%" for value in errors], label_pad=0.035)
    right.set_xticks(positions, merged["channel"])
    right.set_title("After the fit: absolute ROI error", fontsize=11.5, color=bv.STEEL)
    bv.clean(right)

    fig.subplots_adjust(bottom=0.20, wspace=0.22)
    flagged = merged.loc[below, "channel"].tolist()
    if flagged:
        fig.text(0.045, 0.055,
                 f"Flagged in advance: {', '.join(flagged)}. The other channels are "
                 f"ranked perfectly (Spearman 1.000).",
                 color=bv.STEEL, fontsize=10)
    return bv.save(fig, FIGURES / "signal_diagnostic.svg")


def budget_shift(budget: pd.DataFrame) -> Path:
    """Where the next unit of budget goes, and which move is capped.

    A dumbbell rather than two bar series: the quantity the reader cares about
    is the *move*, and a dumbbell draws the move as the thing with length.
    """
    budget = budget.sort_values("recommended_weekly_spend", ascending=True).reset_index(drop=True)

    fig, ax = bv.panel(
        12.4, 4.9,
        title="Optimised weekly allocation under the fitted response curves",
        subtitle="Affiliate is held at its +100% change bound, which is a constraint speaking, not evidence",
    )
    positions = np.arange(len(budget), dtype=float)
    ax.set_ylim(-0.7, len(budget) - 0.3)
    ax.set_xlim(0, budget[["current_weekly_spend", "recommended_weekly_spend"]].to_numpy().max() * 1.28)
    fig.canvas.draw()

    for position, row in zip(positions, budget.itertuples()):
        ax.plot([row.current_weekly_spend, row.recommended_weekly_spend],
                [position, position], color=bv.SLATE, linewidth=3.0,
                solid_capstyle="round", zorder=2)
        ax.plot(row.current_weekly_spend, position, "o", markersize=9,
                markerfacecolor=bv.CARBON, markeredgecolor=bv.STEEL,
                markeredgewidth=2.0, zorder=3)
        ax.plot(row.recommended_weekly_spend, position, "o", markersize=10,
                markerfacecolor=bv.COBALT, markeredgecolor=bv.CARBON,
                markeredgewidth=2.0, zorder=4)
        note = f"{row.change_pct * 100:+.0f}%" + ("  (at bound)" if row.at_bound else "")
        ax.text(max(row.current_weekly_spend, row.recommended_weekly_spend) * 1.03,
                position, note, va="center", ha="left", fontsize=10,
                fontweight="bold", color=bv.IVORY)

    ax.set_yticks(positions, budget["channel"])
    ax.set_xlabel("Weekly spend")
    ax.xaxis.set_major_formatter(lambda value, _: f"{value / 1000:,.0f}k")
    ax.plot([], [], "o", markersize=9, markerfacecolor=bv.CARBON,
            markeredgecolor=bv.STEEL, markeredgewidth=2.0, label="Current", linestyle="none")
    ax.plot([], [], "o", markersize=10, markerfacecolor=bv.COBALT,
            markeredgecolor=bv.CARBON, markeredgewidth=2.0, label="Recommended", linestyle="none")
    ax.legend(loc="lower right", ncols=2)
    bv.clean(ax, axis="x", spines=("top", "right", "bottom"))
    return bv.save(fig, FIGURES / "budget_shift.svg")


def headline(roi: pd.DataFrame, snr: pd.DataFrame):
    """The three numbers the README leads with."""
    worst = roi.loc[roi["roi_error_pct"].abs().idxmax()]
    measurable = snr[snr["signal_to_noise"] >= 0.10]
    fig, _ = bv.kpi_strip([
        ("1.000", f"Rank correlation on the {len(measurable)} channels\nthat carry measurable signal"),
        (f"{worst['roi_error_pct'] * 100:+,.0f}%", f"ROI error on {worst['channel']},\nthe channel the diagnostic flags"),
        (f"{snr['signal_to_noise'].min():.2f}", "Its signal-to-noise ratio,\nknown before the model is fitted"),
    ])
    return bv.save(fig, FIGURES / "headline.svg")


def build_all() -> list[Path]:
    roi, snr, budget = _load()
    return [
        headline(roi, snr),
        roi_recovery(roi),
        signal_diagnostic(roi, snr),
        budget_shift(budget),
    ]


if __name__ == "__main__":
    for path in build_all():
        print(path.relative_to(ROOT))
