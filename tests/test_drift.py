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


def test_only_stationary_features_are_drift_checked() -> None:
    feats = set(drift.DRIFT_FEATURES)
    assert {"lag_7_rel", "roll_cv_7", "pct_change_7", "spread"} <= feats
    # price level, calendar, weather and coverage inputs drift by construction
    assert not feats & {"log_last", "month", "fest_onam", "rain_7d", "n_reports", "horizon"}
    assert drift.is_stationary("arrivals_ratio_7")


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


def _fake(share: float = 0.9, target_p: float | None = 0.5) -> drift.DriftResult:
    return drift.DriftResult(
        date(2026, 10, 6),
        date(2026, 7, 1),
        date(2026, 9, 22),
        date(2026, 9, 23),
        date(2026, 10, 6),
        10,
        int(share * 10),
        share,
        target_p is not None and target_p < 0.05,
        target_p,
    )


def test_feature_drift_alone_never_escalates() -> None:
    assert drift.escalation_reasons(_fake(share=1.0), 0, 4.0, 80.0, True) == []


@pytest.mark.parametrize(
    ("kwargs", "fires"),
    [
        ({"streak": 7}, True),
        ({"streak": 6}, False),
        ({"coverage": 65.0}, True),
        ({"coverage": 93.0}, True),
        ({"coverage": 70.0}, False),
        ({"coverage": 50.0, "full": False}, False),  # < 28 days of matured forecasts
        ({"target_p": 0.005}, True),
        ({"target_p": 0.03}, False),  # Evidently "drift" at 0.05, but not an escalation
    ],
)
def test_performance_escalation_rules(kwargs: dict[str, Any], fires: bool) -> None:
    r = _fake(target_p=kwargs.get("target_p", 0.5))
    reasons = drift.escalation_reasons(
        r,
        kwargs.get("streak", 0),
        4.0,
        kwargs.get("coverage", 80.0),
        kwargs.get("full", True),
    )
    assert bool(reasons) is fires


@pytest.mark.db
def test_live_coverage_needs_a_full_window(engine: Engine) -> None:
    def add(value: float, days_ago: int) -> None:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO model_metrics (model_name, split, commodity, horizon, metric, "
                    "value, computed_at) VALUES ('champion', 'live', 'all', 7, "
                    "'coverage_80_28d', :v, now() - make_interval(days => :d))"
                ),
                {"v": value, "d": days_ago},
            )

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE model_metrics"))
    assert drift.live_coverage(engine) == (None, False)
    add(60.0, 5)
    add(55.0, 0)
    assert drift.live_coverage(engine) == (55.0, False)
    add(90.0, 30)
    assert drift.live_coverage(engine) == (55.0, True)


def test_run_weekly_escalates_on_performance_not_feature_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = _fake(share=0.9)
    sent: list[str] = []
    issues: list[str] = []
    monkeypatch.setattr(drift, "compute", lambda *a: (fake, {}))
    monkeypatch.setattr(drift, "mape_ratio_streak", lambda e: (2, 4.0))
    monkeypatch.setattr(drift, "live_coverage", lambda e: (80.0, True))
    monkeypatch.setattr(drift, "upload_html", lambda r, f: "https://x/report.html")
    monkeypatch.setattr(drift, "store", lambda *a: None)
    monkeypatch.setattr(drift, "open_issue", lambda t, b: issues.append(t))
    out: dict[str, Any] = drift.run_weekly(None, None, [], False, sent.append)  # type: ignore[arg-type]
    assert out["feature_drift_flag"] and not out["escalated"] and not sent and not issues
    monkeypatch.setattr(drift, "live_coverage", lambda e: (62.0, True))
    out = drift.run_weekly(None, None, [], False, sent.append)  # type: ignore[arg-type]
    assert out["escalated"] and "coverage 62.0 %" in sent[0] and issues
