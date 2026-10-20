"""Turn a geo-lift readout into a calibration row for the MMM.

Role in the pipeline
    Bridges mmm.geolift (regional experiment) and mmm.model (national model).
Input
    The geo-lift readout (lost revenue in the treated states, with its
    posterior sd) and the spend of the tested channel.
Output
    A one-row DataFrame in the format of
    ``MMM.add_lift_test_measurements``: channel, x, delta_x, delta_y, sigma.
Dependencies
    pandas.

From regional test to national curve
    The experiment switched the channel OFF in states that receive a share
    ``pi`` of its spend. If the channel's effect in a state scales with the
    spend that state receives (the national model's own assumption), the
    revenue lost there is ``pi`` times what the whole country would lose with
    the channel off. So the national-equivalent measurement is:

        x       = national daily spend the channel would have had (R$/day)
        delta_x = -x                          (switched off)
        delta_y = -(lost revenue per test day) / pi
        sigma   = sd(lost revenue per test day) / pi

    "Lost revenue per test day" includes the cool-down window: revenue keeps
    falling for a few days after spend stops (adstock), so dividing the whole
    loss by the days the channel was off gives the steady-state daily effect,
    which is what the model's saturation curve describes.
"""

from __future__ import annotations

import pandas as pd


def lift_row(readout: dict) -> pd.DataFrame:
    """Calibration row from a geo-lift readout produced by ``mmm.geolift.readout``."""
    pi = readout["treated_spend_share"]
    days = readout["test_days"]
    x = readout["national_daily_spend_planned"]
    lost_per_day = readout["lost_revenue_mean"] / days
    sd_per_day = readout["lost_revenue_sd"] / days
    return pd.DataFrame([{
        "channel": readout["channel"],
        "x": x,
        "delta_x": -x,
        "delta_y": -lost_per_day / pi,
        "sigma": max(sd_per_day / pi, 1.0),
    }])
