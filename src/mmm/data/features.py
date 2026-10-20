"""Model-ready frames built from the mart.

Role in the pipeline
    Turns the long mart tables into (a) the national daily frame the MMM fits
    and (b) the UF x week panel the geo-lift reads.
Input
    ``MartData`` and settings (channel list, owned channels).
Output
    ``model_frame``: one row per day with revenue, spend per channel and the
    control variables. ``geo_panel``: weekly revenue (and spend of the tested
    channel) per UF.
Dependencies
    pandas, numpy.

Why national and daily
    The budget decision is national (one Meta account, one Google account), so
    the MMM is national. Daily, because the adstock of performance channels
    decays within days: weekly data would fold most of the carryover into a
    single period and leave the decay rate unidentified.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .loader import MartData

CONTROL_COLUMNS = [
    "trend",
    "email_entregues",
    "preco",
    "promocao_loja",
    "feriado",
    "black_friday",
    "natal",
    "fim_de_ano",
    "dia_das_maes",
    "outros_eventos",
    "dow_ter", "dow_qua", "dow_qui", "dow_sex", "dow_sab", "dow_dom",
]


def spend_wide(media: pd.DataFrame, channels: list[str], dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Daily national spend per MMM channel (columns), zero-filled."""
    w = media[media.canal_mmm.isin(channels)].pivot_table(index="data", columns="canal_mmm",
                                                          values="investimento", aggfunc="sum")
    return w.reindex(index=dates, columns=channels).fillna(0.0)


def model_frame(mart: MartData, cfg: dict) -> pd.DataFrame:
    """National daily frame: ``date``, ``y`` (paid revenue), one column per channel, controls.

    Controls are scaled to roughly [0, 1] so the default control priors of
    PyMC-Marketing (Normal on the scaled target) are weakly informative:
      * trend: days since start / length (the store grows ~30% a year)
      * email_entregues: e-mails delivered / max (owned channel, not optimised)
      * preco: (1 - price index) x 10, i.e. 1.0 = 10% average discount vs list price
      * calendar dummies from the marketing calendar, plus the year-end slump
        (22/12-06/01), which any retailer knows and the calendar table encodes
        only implicitly
    """
    dates = mart.dates
    channels = cfg["channels"]
    rev = mart.sales.groupby("data")["receita"].sum().reindex(dates).fillna(0.0)
    spend = spend_wide(mart.media, channels, dates)

    c = mart.controls.set_index("data").reindex(dates)
    email = mart.media[mart.media.canal_mmm.isin(cfg.get("owned_channels", []))] \
        .groupby("data")["impressoes"].sum().reindex(dates).fillna(0.0)
    md = dates.strftime("%m-%d")
    fim_ano = (md >= "12-22") | (md <= "01-06")
    out = pd.DataFrame({"date": dates, "y": rev.values})
    for ch in channels:
        out[ch] = spend[ch].values
    out["trend"] = np.arange(len(dates)) / max(len(dates) - 1, 1)
    out["email_entregues"] = (email / max(email.max(), 1.0)).values
    out["preco"] = ((1 - c["indice_preco"]) * 10).values
    out["promocao_loja"] = c["promocao_loja"].astype(int).values
    out["feriado"] = c["feriado_nacional"].astype(int).values
    out["black_friday"] = c["evento_black_friday"].astype(int).values
    out["natal"] = c["evento_natal"].astype(int).values
    out["fim_de_ano"] = fim_ano.astype(int)
    out["dia_das_maes"] = c["evento_dia_das_maes"].astype(int).values
    out["outros_eventos"] = (c["evento_qualquer"] & ~c["evento_black_friday"] & ~c["evento_natal"]
                             & ~c["evento_dia_das_maes"]).astype(int).values
    for i, name in enumerate(["ter", "qua", "qui", "sex", "sab", "dom"], start=2):
        out[f"dow_{name}"] = (c["dia_semana"] == i).astype(int).values
    return out


def geo_panel(mart: MartData, test_id: int, frequency: str = "W-MON") -> tuple[pd.DataFrame, dict]:
    """Weekly paid revenue per UF (columns) and the test's metadata.

    Weeks start on the test's start weekday so that the first treated week is
    entirely treated (a week that mixes pre and test days biases the effect
    towards zero).
    """
    g = mart.geo_tests[mart.geo_tests.teste_id == test_id]
    if g.empty:
        raise ValueError(f"geo test {test_id} not found in the mart")
    meta = g.iloc[0]
    info = {
        "test_id": int(test_id), "channel": meta.canal_mmm,
        "pre_start": meta.pre_inicio, "start": meta.inicio, "end": meta.fim, "cooldown_end": meta.resfriamento_fim,
        "multiplier": float(meta.multiplicador_investimento),
        "treated": sorted(g[g.grupo == "tratamento"].uf), "control": sorted(g[g.grupo == "controle"].uf),
    }
    s = mart.sales.pivot_table(index="data", columns="uf", values="receita", aggfunc="sum").fillna(0.0)
    # 7-day blocks counted from the test start, labelled by their first day
    block = (s.index - info["start"]).days // 7
    week_start = info["start"] + pd.to_timedelta(block * 7, unit="D")
    weekly = s.groupby(week_start).sum()
    weekly = weekly[s.groupby(week_start).size().values == 7]  # complete weeks only
    weekly.index.name = "semana"
    spend = mart.media[mart.media.canal_mmm == info["channel"]] \
        .pivot_table(index="data", columns="uf", values="investimento", aggfunc="sum").fillna(0.0)
    info["spend_daily"] = spend
    return weekly, info
