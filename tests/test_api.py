"""FastAPI tests with TestClient against a seeded test database."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from cropcast.api import main as api
from cropcast.api import queries as q
from cropcast.config import settings

pytestmark = pytest.mark.db
D = date(2026, 10, 7)


def _seed(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE prices_clean, model_metrics, promotion_log, channel_stats"))
        banana = [{"d": D - timedelta(days=i), "p": 5000 + i} for i in range(120)]
        pepper = [{"d": D - timedelta(days=i)} for i in range(5, 120)]  # last obs 5 days ago
        conn.execute(
            text(
                "INSERT INTO prices_clean (commodity, market, variety, date, modal_price, "
                "min_price, max_price, n_reports, sources) "
                "VALUES ('banana', 'Kayamkulam', 'Nendran', :d, :p, :p, :p, 1, 't')"
            ),
            banana,
        )
        conn.execute(
            text(
                "INSERT INTO prices_clean (commodity, market, variety, date, modal_price, "
                "n_reports, sources) VALUES ('pepper', 'Kannur', 'Other', :d, 68000, 1, 't')"
            ),
            pepper,
        )
        run_id = conn.execute(
            text(
                "INSERT INTO pipeline_runs (run_date, steps, status, finished_at) "
                "VALUES (:d, 'all', 'success', now()) RETURNING run_id"
            ),
            {"d": D},
        ).scalar_one()
        for crop, market, var, last in (
            ("banana", "Kayamkulam", "Nendran", 5000),
            ("pepper", "Kannur", "Other", 68000),
        ):
            for h in (1, 7, 14):
                conn.execute(
                    text(
                        "INSERT INTO forecasts (run_id, forecast_date, target_date, horizon, "
                        "market, commodity, variety, p10, p50, p90, last_value, model_name, "
                        "model_version) "
                        "VALUES (:r, :d, :t, :h, :m, :c, :v, :lo, :mid, :hi, :mid, :n, '3')"
                    ),
                    {
                        "r": run_id,
                        "d": D,
                        "t": D + timedelta(days=h),
                        "h": h,
                        "m": market,
                        "c": crop,
                        "v": var,
                        "lo": last * 0.9,
                        "mid": last,
                        "hi": last * 1.1,
                        "n": f"cropcast-price-h{h}",
                    },
                )
        for crop in ("all", "banana"):
            for metric, val, naive in (
                ("mape_28d", 4.9, 5.0),
                ("coverage_80_28d", 81.0, None),
                ("n_28d", 50, None),
            ):
                conn.execute(
                    text(
                        "INSERT INTO model_metrics (model_name, split, commodity, horizon, metric, "
                        "value, naive_value) VALUES ('champion', 'live', :c, 7, :m, :v, :n)"
                    ),
                    {"c": crop, "m": metric, "v": val, "n": naive},
                )
        for metric, val in (("n", 40), ("n_moves", 9), ("days_covered", 20)):
            conn.execute(
                text(
                    "INSERT INTO model_metrics (model_name, split, commodity, horizon, metric, "
                    "value) VALUES ('move-h7-shadow', 'live', 'coconut', 7, :m, :v)"
                ),
                {"m": metric, "v": val},
            )
        conn.execute(
            text("INSERT INTO channel_stats (date, member_count) VALUES (:d, 42)"), {"d": D}
        )


@pytest.fixture
def client(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    _seed(engine)
    monkeypatch.setattr(settings, "database_url_ro", str(engine.url.render_as_string(False)))
    q.engine.cache_clear()
    q.clear_cache()
    api.limiter.reset()
    yield TestClient(api.app)
    q.engine.cache_clear()
    q.clear_cache()


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["db_ok"] and body["status"] == "ok" and body["db_size_mb"] > 0
    assert body["last_successful_run"] is not None


def test_health_reports_db_down(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "database_url_ro", "postgresql+psycopg://x@127.0.0.1:1/none")
    q.engine.cache_clear()
    r = client.get("/health")
    assert r.status_code == 503 and r.json()["db_ok"] is False


def test_crops_and_markets(client: TestClient) -> None:
    assert {c["crop"] for c in client.get("/crops").json()} == {"banana", "pepper"}
    m = client.get("/markets", params={"crop": "banana"}).json()
    assert m[0]["market"] == "Kayamkulam" and m[0]["variety"] == "Nendran"
    assert client.get("/markets", params={"crop": "mango"}).status_code == 404
    assert client.get("/markets", params={"crop": "BAD;drop"}).status_code == 422


def test_forecast_and_staleness(client: TestClient) -> None:
    r = client.get("/forecast", params={"crop": "banana", "market": "Kayamkulam", "horizon": 7})
    body = r.json()
    assert r.status_code == 200
    assert body["p10"] <= body["p50"] <= body["p90"]
    assert body["as_of"] == str(D) and body["target_date"] == str(D + timedelta(days=7))
    assert body["model_name"] == "cropcast-price-h7" and body["model_version"] == "3"
    assert body["stale"] is False
    pep = client.get("/forecast", params={"crop": "pepper", "market": "Kannur"}).json()
    assert pep["stale"] is True  # last observation 5 days before as_of
    assert (
        client.get(
            "/forecast", params={"crop": "banana", "market": "Kayamkulam", "horizon": 3}
        ).status_code
        == 422
    )
    assert (
        client.get("/forecast", params={"crop": "banana", "market": "Nowhere"}).status_code == 404
    )


def test_history_window(client: TestClient) -> None:
    body = client.get(
        "/history", params={"crop": "banana", "market": "Kayamkulam", "days": 90}
    ).json()
    assert len(body["points"]) == 90 and body["points"][-1]["date"] == str(D)


def test_metrics_and_badges(client: TestClient) -> None:
    m = client.get("/metrics").json()
    allh7 = next(r for r in m["champion"] if r["crop"] == "all" and r["horizon"] == 7)
    assert allh7["mape_28d"] == 4.9 and allh7["naive_mape_28d"] == 5.0
    coconut = next(s for s in m["shadow"] if s["crop"] == "coconut")
    assert coconut["n_moves"] == 9 and coconut["verdict"] == "insufficient data"
    assert {s["crop"] for s in m["shadow"]} == {"coconut", "pepper", "rubber", "tapioca"}
    cov = client.get("/badge/coverage.json").json()
    assert cov["schemaVersion"] == 1 and cov["message"].startswith("81%")
    assert client.get("/badge/subscribers.json").json()["message"] == "42"


def test_responses_are_cached(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    client.get("/crops")
    monkeypatch.setattr(q, "_rows", lambda *a, **k: pytest.fail("cache miss"))
    assert client.get("/crops").status_code == 200


def test_rate_limit(client: TestClient) -> None:
    codes = [client.get("/crops").status_code for _ in range(61)]
    assert codes[:60] == [200] * 60 and codes[60] == 429


def test_cors_allows_dashboard_origin(client: TestClient) -> None:
    origin = settings.cors_origins[0]
    r = client.get("/crops", headers={"Origin": origin})
    assert r.headers.get("access-control-allow-origin") == origin
    assert (
        "access-control-allow-origin"
        not in client.get("/crops", headers={"Origin": "https://evil.example"}).headers
    )


def test_openapi_docs_available(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    assert {"/health", "/forecast", "/history", "/metrics"} <= set(spec["paths"])
    assert json.dumps(spec)  # serialisable
