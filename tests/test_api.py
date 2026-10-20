"""API contract: shapes and status codes of every endpoint, against a throwaway registry."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(registry, monkeypatch):
    monkeypatch.setenv("MMM_REGISTRY_PATH", str(registry.root))
    from mmm.serve import app as appmod

    for f in (appmod._cfg, appmod._registry, appmod._load):
        f.cache_clear()
    return TestClient(appmod.app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["models"]["calibrated"].startswith("mmm_calibrated-")


def test_model_metadata(client):
    r = client.get("/model")
    assert r.status_code == 200 and r.json()["calibrated"] is True


def test_channels(client):
    r = client.get("/channels").json()
    assert {c["channel"] for c in r["channels"]} == {"meta", "tiktok", "google_search"}
    assert all(c["marginal_roi"] > 0 for c in r["channels"])


def test_curve(client):
    r = client.get("/curves/meta", params={"points": 10}).json()
    assert len(r["spend"]) == 10 and r["revenue_mean"][0] == pytest.approx(0)
    assert r["revenue_low"][-1] <= r["revenue_mean"][-1] <= r["revenue_high"][-1]


def test_unknown_channel_is_404(client):
    assert client.get("/curves/radio").status_code == 404


def test_optimize_default_budget(client):
    r = client.post("/optimize", json={"horizon_days": 30})
    assert r.status_code == 200
    body = r.json()
    total = sum(c["recommended_total"] for c in body["channels"])
    assert total == pytest.approx(body["total_budget"], rel=1e-6)
    assert {"gain_mean", "gain_low", "gain_high", "prob_better"} <= body.keys()


def test_optimize_with_bounds(client):
    r = client.post("/optimize", json={"budget": 150000, "horizon_days": 30,
                                       "bounds": {"meta": [2000, 3000], "tiktok": [500, 1000],
                                                  "google_search": [1000, 2000]}})
    assert r.status_code == 200
    for c in r.json()["channels"]:
        assert c["recommended_daily"] >= 0


def test_infeasible_budget_is_422(client):
    assert client.post("/optimize", json={"budget": 10, "horizon_days": 30}).status_code == 422


def test_invalid_payload_is_422(client):
    assert client.post("/optimize", json={"budget": -1}).status_code == 422
