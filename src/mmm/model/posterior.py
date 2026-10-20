"""Read what the fitted model believes: parameters, contributions, ROI, curves.

Role in the pipeline
    Extracts plain arrays from a fitted MMM so that everything downstream
    (optimiser, API, dashboard, validation) works without PyMC.
Input
    A fitted ``MMM``, the frame it was fitted on, settings.
Output
    ``ChannelPosterior`` (draws of beta, lam, alpha per channel plus scales),
    contribution and ROI tables.
Dependencies
    numpy, pandas, arviz (via the model's InferenceData).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .transforms import marginal_response, steady_state_response


@dataclass
class ChannelPosterior:
    channels: list[str]
    beta: np.ndarray        # [draw, channel]
    lam: np.ndarray         # [draw, channel]
    alpha: np.ndarray       # [draw, channel]
    spend_scale: dict
    target_scale: float

    def response(self, channel: str, spend: np.ndarray) -> np.ndarray:
        """[draw, len(spend)] daily incremental revenue for a sustained daily spend."""
        i = self.channels.index(channel)
        s = np.atleast_1d(np.asarray(spend, float))
        return steady_state_response(s[None, :], self.beta[:, i, None], self.lam[:, i, None],
                                     self.spend_scale[channel], self.target_scale)

    def marginal(self, channel: str, spend: np.ndarray) -> np.ndarray:
        i = self.channels.index(channel)
        s = np.atleast_1d(np.asarray(spend, float))
        return marginal_response(s[None, :], self.beta[:, i, None], self.lam[:, i, None],
                                 self.spend_scale[channel], self.target_scale)

    def thin(self, n: int, seed: int = 0) -> ChannelPosterior:
        rng = np.random.default_rng(seed)
        idx = rng.choice(self.beta.shape[0], size=min(n, self.beta.shape[0]), replace=False)
        return ChannelPosterior(self.channels, self.beta[idx], self.lam[idx], self.alpha[idx],
                                self.spend_scale, self.target_scale)

    def to_frame(self) -> pd.DataFrame:
        rows = []
        for i, c in enumerate(self.channels):
            rows.append(pd.DataFrame({"draw": np.arange(self.beta.shape[0]), "channel": c, "beta": self.beta[:, i],
                                      "lam": self.lam[:, i], "alpha": self.alpha[:, i]}))
        return pd.concat(rows, ignore_index=True)

    @classmethod
    def from_frame(cls, df: pd.DataFrame, spend_scale: dict, target_scale: float) -> ChannelPosterior:
        channels = list(dict.fromkeys(df["channel"]))
        piv = {k: df.pivot(index="draw", columns="channel", values=k)[channels].values for k in ("beta", "lam", "alpha")}
        return cls(channels, piv["beta"], piv["lam"], piv["alpha"], spend_scale, target_scale)


def channel_posterior(mmm, scales: dict) -> ChannelPosterior:
    post = mmm.idata.posterior
    ch = list(post.coords["channel"].values)

    def stack(name):
        return post[name].stack(sample=("chain", "draw")).transpose("sample", "channel").values

    return ChannelPosterior(ch, stack("saturation_beta"), stack("saturation_lam"), stack("adstock_alpha"),
                            scales["channels"], scales["target"])


def contributions(mmm, frame: pd.DataFrame) -> pd.DataFrame:
    """Posterior mean and 94% interval of each channel's daily contribution (R$)."""
    c = mmm.compute_channel_contribution_original_scale()  # chain, draw, date, channel
    c = c.stack(sample=("chain", "draw"))
    mean = c.mean("sample").to_pandas()
    mean.index = pd.to_datetime(frame["date"].values)
    return mean


def roi_table(mmm, frame: pd.DataFrame, cfg: dict, start=None, end=None) -> pd.DataFrame:
    """Incremental revenue / spend per channel over a window, with 94% interval.

    ROI here is the AVERAGE return of every real spent in the window (what the
    channel delivered). The optimiser uses the MARGINAL return (what the next
    real buys), which is lower wherever the curve has started to flatten.
    """
    c = mmm.compute_channel_contribution_original_scale().stack(sample=("chain", "draw"))
    dates = pd.to_datetime(frame["date"].values)
    mask = np.ones(len(dates), bool)
    if start is not None:
        mask &= dates >= pd.Timestamp(start)
    if end is not None:
        mask &= dates <= pd.Timestamp(end)
    tot = c.isel(date=np.where(mask)[0]).sum("date")  # channel x sample
    rows = []
    for ch in cfg["channels"]:
        spend = float(frame.loc[mask, ch].sum())
        draws = tot.sel(channel=ch).values / max(spend, 1e-9)
        rows.append({"channel": ch, "spend": spend, "contribution": float(tot.sel(channel=ch).mean()) ,
                     "roi_mean": float(draws.mean()), "roi_low": float(np.quantile(draws, 0.03)),
                     "roi_high": float(np.quantile(draws, 0.97)), "roi_sd": float(draws.std())})
    return pd.DataFrame(rows)
