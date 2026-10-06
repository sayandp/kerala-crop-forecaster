"""DB tests (need TEST_DATABASE_URL): idempotent upserts and the pipeline run log."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import Engine, text

from cropcast import db, pipeline
from cropcast.validate.schemas import validate
from tests.conftest import price_row

pytestmark = pytest.mark.db


def _count(engine: Engine, table: str = "prices_raw") -> int:
    with engine.connect() as conn:
        return int(conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())


def test_upsert_same_day_twice_is_idempotent(engine: Engine, good_prices: pd.DataFrame) -> None:
    good, _ = validate(good_prices, today=date(2026, 10, 3))
    db.upsert_prices(good, engine)
    first = _count(engine)
    db.upsert_prices(good, engine)
    assert _count(engine) == first == len(good)


def test_upsert_updates_changed_prices(engine: Engine) -> None:
    db.upsert_prices(pd.DataFrame([price_row()]), engine)
    db.upsert_prices(pd.DataFrame([price_row(modal_price=5800.0)]), engine)
    with engine.connect() as conn:
        modal = conn.execute(text("SELECT modal_price FROM prices_raw")).scalar_one()
    assert float(modal) == 5800.0
    assert _count(engine) == 1


def test_weather_upsert_idempotent(engine: Engine) -> None:
    w = pd.DataFrame(
        [
            {
                "date": date(2026, 10, 1),
                "district": "Kollam",
                "rainfall_mm": 1.0,
                "temp_max_c": 31.0,
                "temp_min_c": 24.0,
                "temp_mean_c": 27.0,
                "source": "open-meteo",
            }
        ]
    )
    db.upsert_weather(w, engine)
    db.upsert_weather(w, engine)
    assert _count(engine, "weather_daily") == 1


def test_pipeline_twice_same_date_no_duplicates(
    engine: Engine, good_prices: pd.DataFrame, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dup = pd.concat([good_prices, good_prices.iloc[[0]]], ignore_index=True)  # 1 bad row
    monkeypatch.setattr(pipeline, "fetch_kerala_prices", lambda *a, **k: dup.copy())
    monkeypatch.setattr(pipeline, "normalize", lambda df: df)
    monkeypatch.setattr(pipeline.settings, "data_dir", tmp_path)  # raw snapshots

    for _ in range(2):
        ctx = pipeline.RunContext(run_date=date(2026, 10, 3), engine=engine)
        results = pipeline.run_pipeline(["ingest", "validate"], ctx)
    assert _count(engine) == len(good_prices)
    assert results[-1].metrics["new_rows"] == 0
    assert _count(engine, "prices_rejected") == 2  # quarantined once per run
    with engine.connect() as conn:
        statuses = conn.execute(text("SELECT status FROM pipeline_runs ORDER BY run_id")).scalars()
        assert list(statuses) == ["success", "success"]


def test_failed_run_is_logged_and_admin_pinged(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: object, **_k: object) -> pd.DataFrame:
        raise RuntimeError("all ingest sources failed")

    sent: list[str] = []
    monkeypatch.setattr(pipeline, "fetch_kerala_prices", boom)
    monkeypatch.setattr(pipeline, "send_admin_message", lambda msg: sent.append(msg) or True)
    ctx = pipeline.RunContext(run_date=date(2026, 10, 3), engine=engine)
    with pytest.raises(RuntimeError):
        pipeline.run_pipeline(["ingest", "validate"], ctx)
    with engine.connect() as conn:
        status, error = conn.execute(text("SELECT status, error FROM pipeline_runs")).one()
    assert status == "failed" and "all ingest sources failed" in error
    assert len(sent) == 1 and "step=ingest" in sent[0]


def test_run_records_db_size_mb(engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    sent: list[str] = []
    monkeypatch.setattr(pipeline, "send_admin_message", lambda msg: sent.append(msg) or True)
    monkeypatch.setattr(pipeline.settings, "db_warn_mb", 0.0)  # force the budget warning
    ctx = pipeline.RunContext(run_date=date(2026, 10, 3), engine=engine)
    pipeline.run_pipeline([], ctx)
    with engine.connect() as conn:
        details = conn.execute(text("SELECT details FROM pipeline_runs")).scalar_one()
    assert details["db_size_mb"] > 0
    assert len(sent) == 1 and "MB" in sent[0]


def test_null_bounds_round_trip_and_insert_if_absent(engine: Engine) -> None:
    row = pd.DataFrame([price_row(min_price=None, max_price=None)])
    assert db.insert_prices_if_absent(row, engine) == 1
    # Never overwrites an existing key.
    assert db.insert_prices_if_absent(pd.DataFrame([price_row(modal_price=5800.0)]), engine) == 0
    with engine.connect() as conn:
        lo, hi, modal = conn.execute(
            text("SELECT min_price, max_price, modal_price FROM prices_raw")
        ).one()
    assert lo is None and hi is None and float(modal) == 5500.0
