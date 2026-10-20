"""Report page: every slot is filled, and every action title is true for the numbers it states.

The storytelling rule (arielabade/prompts): a title that states a conclusion is
computed from the data and falls back to a neutral title when the condition
does not hold. These tests pin both branches.
"""

import copy
import re

import numpy as np
import pytest

from mmm.report import page


def _alloc(gain=12000.0, prob=0.97):
    ch = []
    for c, cur, rec in [("meta", 3000, 4200), ("tiktok", 1000, 500), ("google_search", 1200, 1300),
                        ("google_shopping", 1500, 1600), ("youtube", 400, 300), ("afiliados", 600, 300)]:
        ch.append({"channel": c, "current_daily": cur, "current_daily_at_budget": cur, "recommended_daily": rec,
                   "change_pct": rec / cur - 1, "recommended_total": rec * 30, "revenue_recommended": rec * 30 * 1.5,
                   "revenue_recommended_low": 1, "revenue_recommended_high": 2, "revenue_current": cur * 30 * 1.4,
                   "roi_recommended": 1.5, "marginal_roi_recommended": 0.9, "marginal_roi_current": 0.9,
                   "at_lower_bound": rec == cur * 0.5, "at_upper_bound": False})
    return {"total_budget": 7700 * 30, "horizon_days": 30, "gain_mean": gain, "gain_low": gain * 0.4,
            "gain_high": gain * 1.6, "prob_better": prob, "revenue_recommended": {"mean": 3e5, "low": 2e5, "high": 4e5},
            "revenue_current": {"mean": 2.9e5, "low": 2e5, "high": 4e5}, "channels": ch}


def _roi(meta, tiktok):
    vals = {"meta": meta, "tiktok": tiktok, "google_search": 1.6, "google_shopping": 1.8, "youtube": 1.0, "afiliados": 0.6}
    return [{"channel": c, "spend": 1e5, "contribution": v * 1e5, "roi_mean": v, "roi_low": v * 0.8,
             "roi_high": v * (1.6 if c == "youtube" else 1.2), "roi_sd": 0.1} for c, v in vals.items()]


@pytest.fixture
def data():
    weeks = [f"2025-{m:02d}-{d:02d}" for m in range(6, 11) for d in (2, 9, 16, 23)]
    post = [w >= "2025-08-04" for w in weeks]
    obs = [100000.0 * (0.88 if p else 1.0) for p in post]
    grid = np.linspace(0, 6000, 41)
    curve = {"spend": grid.tolist(), "mean": (grid * 0.5).tolist(), "low": (grid * 0.4).tolist(),
             "high": (grid * 0.6).tolist(), "marginal": np.linspace(2, 0.5, 41).tolist(), "current": 3000.0}
    return {
        "labels": page.LABELS, "profile": "test",
        "facts": {"start": "2023-10-01", "end": "2026-10-13", "months": 36, "revenue": 3.88e7, "spend": 6.0e6, "orders": 133000},
        "geolift": {"channel": "meta", "treated": ["BA", "CE", "ES", "GO", "MT", "PE", "PR"], "start": "2025-08-04",
                    "end": "2025-09-14", "test_days": 42, "relative_lift_mean": -0.12, "lost_revenue_mean": 48000,
                    "lost_revenue_low": 30000, "lost_revenue_high": 66000, "roi_mean": 2.2, "treated_spend_share": 0.25,
                    "spend_removed": 21600, "did": {"relative_lift_mean": -0.11},
                    "decision": {"verdict": "channel_is_incremental"},
                    "series": {"week": weeks, "observed": obs, "synthetic": [100000.0] * len(weeks),
                               "synthetic_low": [95000.0] * len(weeks), "synthetic_high": [105000.0] * len(weeks), "post": post},
                    "power": []},
        "roi": {"uncalibrated": _roi(1.4, 1.3), "calibrated": _roi(2.0, 0.55)},
        "roi_vs_truth": [{"channel": r["channel"], "roi_true": r["roi_mean"] * 0.95} for r in _roi(2.0, 0.55)],
        "evaluation": {"roi_recovery": {"uncalibrated": {"mean_abs_roi_error": 0.45}, "calibrated": {"mean_abs_roi_error": 0.12}}},
        "allocation": {"calibrated": _alloc()},
        "gain_draws": {"calibrated": list(np.linspace(-2000, 25000, 200))},
        "curves": {"calibrated": {c: copy.deepcopy(curve) for c in page.LABELS}},
        "spend": {"week": weeks, "meta": [21000.0] * len(weeks), "tiktok": [6700.0] * len(weeks), "corr": {"meta|tiktok": 0.93}},
        "regional": [{"uf": "BA", "grupo": "tratamento", "receita_12m": 1e6, "midia_12m": 1e5, "variacao_teste": -0.1}],
    }


def test_every_slot_is_filled(data):
    html = page.render(data)
    assert not re.search(r"\[\[\w+\]\]", html)
    assert "dados simulados" in html.lower()


def test_hero_states_the_gain_when_it_is_likely(data):
    s = page.story(data)
    assert "a mais por mês" in s["h1"] and "Meta" in s["h1"] and "TikTok" in s["h1"]


def test_hero_falls_back_when_the_gain_is_uncertain(data):
    data["allocation"]["calibrated"] = _alloc(gain=500.0, prob=0.55)
    s = page.story(data)
    assert s["h1"] == "A divisão atual da verba está perto do ponto ótimo"
    assert "Manter" in s["h_reco"]


def test_problem_title_needs_a_high_correlation(data):
    assert "0,93" in page.story(data)["h_problema"]
    data["spend"]["corr"]["meta|tiktok"] = 0.2
    assert "independente" in page.story(data)["h_problema"]


def test_test_title_follows_the_verdict(data):
    assert "12%" in page.story(data)["h_teste"]
    data["geolift"]["decision"]["verdict"] = "inconclusive"
    assert "inconclusivo" in page.story(data)["h_teste"]


def test_calibration_title_names_the_channels_that_moved_most(data):
    title = page.story(data)["h_calib"]
    assert title.startswith("Com o teste, TikTok Ads") or title.startswith("Com o teste, Meta Ads")
    assert "Meta Ads" in title and "TikTok Ads" in title


def test_next_test_is_the_most_uncertain_untested_channel(data):
    assert "Rodar o próximo teste geográfico em YouTube" in page.story(data)["reco_items"]


def test_money_is_formatted_for_brazil():
    assert page.brl_short(48000) == "R$ 48 mil"
    assert page.brl_short(3.88e7) == "R$ 38,80 mi"
    assert page.pct(-0.12, 1) == "−12%"
    assert page.per_real(1.97) == "R$ 1,97"


def test_page_is_deterministic(data):
    assert page.render(data) == page.render(copy.deepcopy(data))


def test_no_hardcoded_conclusion_numbers_in_template():
    """Numbers in the template would go stale when the data changes."""
    text = (page.ASSETS / "index.html").read_text(encoding="utf-8")
    body = re.sub(r"<script.*?</script>|<style.*?</style>", "", text, flags=re.S)
    body = re.sub(r"R\$ 1(?![\d,.]\d)", "", body)  # "para cada R$ 1": a definition, not a result
    assert not re.search(r"R\$\s?\d", body)
