"""Drift: windows, Evidently result parsing, MAPE-ratio streak, escalation rule."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
from sqlalchemy import Engine, text

from cropcast.features.series import Series
from cropcast.features.snapshot import Snapshot
from cropcast.monitor import drift
from tests.conftest import FIXTURES


def test_windows_are_90_then_14_days_and_disjoint() -> None:
    rs, re_, cs, ce = drift.windows(date(2026, 10, 6))
    assert (ce - cs).days == 13 and (re_ - rs).days == 89 and re_ < cs and ce == date(2026, 10, 6)


def test_calendar_features_are_not_counted_as_drift() -> None:
    assert not set(drift.CALENDAR_FEATURES) & set(drift.DRIFT_FEATURES)
    assert "rain_7d" in drift.DRIFT_FEATURES and "roll_cv_7" in drift.DRIFT_FEATURES


def test_parse_evidently_result() -> None:
    d = {
        "metrics": [
            {
                "config": {"type": "evidently:metric_v2:DriftedColumnsCount"},
                "value": {"count": 1.0, "share": 0.5},
            },
            {
                "config": {
                    "type": "evidently:metric_v2:ValueDrift",
                    "column": "a",
                    "method": "K-S p_value",
                    "threshold": 0.05,
                },
                "value": 0.001,
            },
            {
                "config": {
                    "type": "evidently:metric_v2:ValueDrift",
                    "column": "b",
                    "method": "Wasserstein distance (normed)",
                    "threshold": 0.1,
                },
                "value": 0.05,
            },
        ]
    }
    count, share, drifted, per_col = drift._parse(d)
    assert (count, share, drifted) == (1, 0.5, ["a"])
    assert per_col["b"]["drift"] is False


def test_compute_on_real_fixture(tmp_path: Path) -> None:
    prices = pd.read_parquet(FIXTURES / "sample_prices.parquet").assign(n_reports=1)
    keys = prices[["commodity", "market", "variety"]].drop_duplicates()
    series = [Series(*map(str, k)) for k in keys.itertuples(index=False)]
    snap = Snapshot(prices, pd.DataFrame(), tmp_path / "p", tmp_path / "w")
    result, details = drift.compute(snap, series, tmp_path)
    assert 0 <= result.drift_share <= 1 and result.n_features > 5
    assert result.html_path is not None and result.html_path.exists()
    assert details["ref_rows"] > details["cur_rows"] > 0


@pytest.mark.db
def test_mape_ratio_streak_counts_consecutive_recent_days(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE model_metrics"))
        conn.execute(
            text(
                "INSERT INTO model_metrics (model_name, split, commodity, horizon, "
                "metric, value) VALUES ('naive', 'backtest', 'all', 7, 'mape', 4.0)"
            )
        )
        # 8 most recent days above 1.5 x 4 = 6, an older day below
        for i, v in enumerate([7.0] * 8 + [5.0]):
            conn.execute(
                text(
                    "INSERT INTO model_metrics (model_name, split, commodity, horizon, "
                    "metric, value, computed_at) VALUES ('champion', 'live', 'all', 7, "
                    "'mape_28d', :v, now() - make_interval(days => :i))"
                ),
                {"v": v, "i": i},
            )
    streak, backtest = drift.mape_ratio_streak(engine)
    assert streak == 8 and backtest == 4.0


def test_escalation_rule(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = drift.DriftResult(
        date(2026, 10, 6),
        date(2026, 7, 1),
        date(2026, 9, 22),
        date(2026, 9, 23),
        date(2026, 10, 6),
        10,
        4,
        0.4,
        False,
        0.5,
    )
    sent: list[str] = []
    issues: list[str] = []
    monkeypatch.setattr(drift, "compute", lambda *a: (fake, {}))
    monkeypatch.setattr(drift, "mape_ratio_streak", lambda e: (2, 4.0))
    monkeypatch.setattr(drift, "upload_html", lambda r, f: "https://x/report.html")
    monkeypatch.setattr(drift, "store", lambda *a: None)
    monkeypatch.setattr(drift, "open_issue", lambda t, b: issues.append(t))
    out: dict[str, Any] = drift.run_weekly(None, None, [], False, sent.append)  # type: ignore[arg-type]
    assert out["escalated"] and "40%" in sent[0] and issues
    fake.drift_share = 0.2
    sent.clear()
    out = drift.run_weekly(None, None, [], False, sent.append)  # type: ignore[arg-type]
    assert not out["escalated"] and not sent
