"""End to end on the small profile: mart -> geo-lift -> MMM (both) -> optimiser -> API -> dashboard.

Samples real (short) MCMC chains, so it is marked ``e2e`` and runs in its own CI job.
"""

import json
import os

import pytest

pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("e2e")
    os.environ.update({"MMM_PROFILE": "small", "MMM_DATA_SOURCE": "parquet",
                       "MMM_REGISTRY_PATH": str(tmp / "registry"), "MMM_REPORTS_PATH": str(tmp / "reports"),
                       "MMM_DASHBOARD_PATH": str(tmp / "dashboard"),
                       "MMM_GROUND_TRUTH_DIR": str(tmp / "no_ground_truth_in_ci")})
    from mmm.jobs import evaluate, geolift, optimize, report, train
    from mmm.jobs.common import setup

    cfg = setup("small")
    res = {"geolift": geolift.run(cfg), "train": train.run(cfg)}
    res["evaluate"] = evaluate.run(cfg)
    res["optimize"] = optimize.run(cfg)
    report.run(cfg)
    return tmp, res


def test_geolift_produces_a_calibration_row(run):
    tmp, res = run
    g = res["geolift"]
    assert g["calibration"]["delta_x"] < 0 and g["calibration"]["sigma"] > 0
    assert 0 < g["treated_spend_share"] < 1


def test_both_models_are_trained_and_registered(run):
    tmp, res = run
    models = res["train"]["models"]
    assert set(models) == {"uncalibrated", "calibrated"}
    assert (tmp / "registry").exists()


def test_backtest_is_time_ordered(run):
    tmp, res = run
    for fold in res["evaluate"]["backtest"]:
        assert fold["train_end"] < fold["test_start"]


def test_optimizer_spends_the_budget(run):
    tmp, res = run
    rec = res["optimize"].get("calibrated") or res["optimize"].get("uncalibrated")
    total = sum(c["recommended_total"] for c in rec["channels"])
    assert total == pytest.approx(rec["total_budget"], rel=1e-6)


def test_dashboard_is_written(run):
    tmp, _ = run
    html = (tmp / "dashboard" / "index.html").read_text()
    assert "dados simulados" in html.lower()
    data = json.loads((tmp / "dashboard" / "data.json").read_text())
    assert "geolift" in data and "allocation" in data


def test_api_serves_the_trained_model(run):
    from fastapi.testclient import TestClient

    from mmm.serve import app as appmod

    for f in (appmod._cfg, appmod._registry, appmod._load):
        f.cache_clear()
    c = TestClient(appmod.app)
    h = c.get("/health").json()
    assert any(h["models"].values())
    model = "calibrated" if h["models"]["calibrated"] else "uncalibrated"
    assert c.post("/optimize", json={"model": model}).status_code == 200
