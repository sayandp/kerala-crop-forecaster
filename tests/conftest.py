from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import OperationalError

from cropcast import db
from cropcast.config import settings

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _never_touch_real_databases(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Tests must never reach the production DB (.env's DATABASE_URL may be Neon).

    Point settings.database_url at the throwaway test DB (or an unreachable dummy) and
    reset the cached engine, so any code path that forgets to pass an engine is safe.
    """
    safe = settings.test_database_url or "postgresql+psycopg://nobody@127.0.0.1:1/none"
    monkeypatch.setattr(settings, "database_url", safe)
    monkeypatch.setattr(settings, "mlflow_tracking_uri", None)  # never log tests to DagsHub
    db.get_engine.cache_clear()
    yield
    db.get_engine.cache_clear()


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def price_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "date": date(2026, 10, 1),
        "state": "Kerala",
        "district": "Ernakulam",
        "market": "Aluva",
        "commodity": "banana",
        "variety": "Nendran",
        "min_price": 5000.0,
        "max_price": 6000.0,
        "modal_price": 5500.0,
        "source": "test",
    }
    row.update(overrides)
    return row


@pytest.fixture
def good_prices() -> pd.DataFrame:
    return pd.DataFrame(
        [
            price_row(),
            price_row(variety="Poovan", modal_price=5200.0),
            price_row(
                market="Kottayam",
                district="Kottayam",
                commodity="rubber",
                variety="RSS-4",
                min_price=18000.0,
                max_price=18500.0,
                modal_price=18200.0,
            ),
            price_row(date=date(2026, 10, 2)),
        ]
    )


@pytest.fixture
def engine() -> Iterator[Engine]:
    """A clean test database. Skips when TEST_DATABASE_URL is unset or unreachable."""
    url = settings.test_database_url
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    eng = create_engine(url, future=True)
    try:
        with eng.connect():
            pass
    except OperationalError:
        pytest.skip("test database unreachable")
    db.init_db(eng)
    with eng.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE prices_raw, prices_rejected, weather_daily, pipeline_runs, forecasts, "
                "shadow_predictions, channel_posts, archive_log CASCADE"
            )
        )
    yield eng
    eng.dispose()
