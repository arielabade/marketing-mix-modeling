"""Decision rule for a geo-lift, ported from ab-testing-toolkit (``abtest.report.decide``).

Role in the pipeline
    Turns the readout into a verdict a media team can act on, and decides
    whether the result is solid enough to calibrate the MMM.
Input
    The readout dict and the power table.
Output
    {"verdict", "reason", "use_for_calibration"}.
Dependencies
    None.

The same three questions as the A/B toolkit: is the effect real, is it big
enough to matter, and was the test able to see it? A test that "found
nothing" without power is INCONCLUSIVE, not negative, and must not be fed to
the MMM as "this channel does nothing".
"""

from __future__ import annotations


def decide(readout: dict, mde_at_design: float | None, minimum_worthwhile_lift: float,
           probability_threshold: float = 0.95) -> dict:
    p = readout["prob_revenue_fell"]
    lift = -readout["relative_lift_mean"]  # positive = revenue fell when the channel went off
    if p >= probability_threshold and lift >= minimum_worthwhile_lift:
        verdict = "channel_is_incremental"
        reason = (f"Revenue in the treated states fell {lift:.1%} with the channel off "
                  f"(P = {p:.1%}), above the {minimum_worthwhile_lift:.0%} bar.")
    elif p >= probability_threshold:
        verdict = "real_but_small"
        reason = f"The drop looks real (P = {p:.1%}) but {lift:.1%} is below the {minimum_worthwhile_lift:.0%} bar."
    elif mde_at_design is None or mde_at_design != mde_at_design or lift < mde_at_design:
        verdict = "inconclusive"
        reason = ("The test was not powered for an effect this size; absence of a result is not "
                  "evidence of no effect.")
    else:
        verdict = "no_effect"
        reason = f"Powered for {mde_at_design:.0%} and the drop did not appear (P = {p:.1%})."
    return {"verdict": verdict, "reason": reason,
            "use_for_calibration": verdict in ("channel_is_incremental", "real_but_small", "no_effect")}
