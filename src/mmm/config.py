"""The known data-generating process.

================================ READ THIS =================================
The data in this project is SIMULATED, and that is the point.

A marketing mix model estimates how much of a business's revenue each channel
caused. On real data that quantity is never observed, so a model's output can
be inspected but not scored: there is nothing to compare it against.

Simulating from a process whose parameters are written down here is the only
way to ask the question that matters — "does this model recover the truth?" —
and answer it with a number instead of a plot.

Everything below is the truth the model is NOT told and has to find.
============================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field

RANDOM_SEED = 20261002

# Two years of weekly data: long enough for seasonality to be identifiable,
# short enough to be a realistic ask from a client's data team.
WEEKS = 104
START_DATE = "2024-01-07"


@dataclass(frozen=True)
class ChannelTruth:
    """What each channel really does.

    adstock_alpha
        Carryover. 0.0 means a week's spend works only that week; 0.7 means 70%
        of its effect survives into the next week. Brand-style channels carry
        over, performance channels mostly do not.
    saturation_lambda
        Steepness of diminishing returns in the logistic saturation curve.
        Higher means the channel saturates sooner.
    beta
        Peak contribution to weekly revenue once saturated.
    base_spend / spend_sd
        The weekly media plan the business actually ran.
    """

    adstock_alpha: float
    saturation_lambda: float
    beta: float
    base_spend: float
    spend_sd: float


# Deliberately varied so recovery is a real test: a channel with heavy carryover
# and one with none, an efficient channel and a wasteful one.
TRUTH: dict[str, ChannelTruth] = {
    "tv": ChannelTruth(adstock_alpha=0.70, saturation_lambda=2.5, beta=0.55,
                       base_spend=28_000, spend_sd=6_000),
    "search": ChannelTruth(adstock_alpha=0.15, saturation_lambda=4.0, beta=0.40,
                           base_spend=18_000, spend_sd=4_000),
    "social": ChannelTruth(adstock_alpha=0.35, saturation_lambda=3.0, beta=0.28,
                           base_spend=14_000, spend_sd=3_500),
    "affiliate": ChannelTruth(adstock_alpha=0.05, saturation_lambda=6.0, beta=0.09,
                              base_spend=6_000, spend_sd=1_500),
}

CHANNELS = tuple(TRUTH)


@dataclass(frozen=True)
class BaselineTruth:
    """Revenue that happens without media.

    A model that attributes the baseline to channels will report wonderful ROI
    for whichever channel happens to spend when the business is seasonally
    strong. Including a real trend and seasonality is what makes the simulation
    a fair test rather than a softball.
    """

    intercept: float = 42_000.0
    weekly_trend: float = 110.0
    yearly_amplitude: float = 7_500.0
    noise_sd: float = 3_200.0


BASELINE = BaselineTruth()


@dataclass(frozen=True)
class OptimisationSettings:
    """Budget reallocation.

    The optimiser moves money between channels under a fixed total, subject to
    bounds: no real media plan can send 100% of budget to one channel, and a
    recommendation that does is a recommendation nobody implements.
    """

    min_share_of_current: float = 0.4
    max_share_of_current: float = 2.0
    budget_multiplier: float = 1.0


OPTIMISATION = OptimisationSettings()
