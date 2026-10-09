"""Morning schedule: quiet hours, once-per-day scheduled runs."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, text

from cropcast import db, pipeline
from cropcast.bot import alerts as bot_alerts
from cropcast.bot import telegram


@pytest.mark.parametrize(
    ("utc", "quiet"),
    [
        ("2026-10-09T15:29:00", False),  # 20:59 IST
        ("2026-10-09T15:30:00", True),  # 21:00 IST
        ("2026-10-09T23:30:00", True),  # 05:00 IST (morning run start)
        ("2026-10-10T00:29:00", True),  # 05:59 IST
        ("2026-10-10T00:30:00", False),  # 06:00 IST
    ],
)
def test_quiet_hours_21_to_06_ist(utc: str, quiet: bool) -> None:
    assert telegram.quiet_hours(datetime.fromisoformat(utc).replace(tzinfo=UTC)) is quiet


def test_digests_and_alerts_are_silent_in_quiet_hours(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        telegram,
        "send_message",
        lambda chat_id, body, silent=False: calls.append({"silent": silent}),
    )
    send = bot_alerts.broadcast_sender()
    monkeypatch.setattr(telegram, "quiet_hours", lambda now=None: True)
    send(1, "x")
    monkeypatch.setattr(telegram, "quiet_hours", lambda now=None: False)
    send(1, "y")
    assert [c["silent"] for c in calls] == [True, False]


def test_send_message_sets_disable_notification(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[dict[str, Any]] = []
    monkeypatch.setattr(telegram, "call", lambda method, payload, **k: seen.append(payload) or {})
    telegram.send_message(1, "a", silent=True)
    telegram.send_message(1, "b")
    assert seen[0]["disable_notification"] is True and "disable_notification" not in seen[1]


@pytest.mark.db
def test_second_scheduled_run_same_day_writes_and_posts_nothing(
    engine: Engine, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    d = date(2026, 10, 10)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE pipeline_runs CASCADE"))
    assert db.daily_run_done(d, engine) is False

    # A failed first attempt does not count; a manual partial run (no notify) does not count.
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO pipeline_runs (run_date, steps, status, dry_run) VALUES "
                "(:d, 'ingest,validate,notify', 'failed', FALSE), "
                "(:d, 'user_alerts', 'success', FALSE), "
                "(:d, 'ingest,notify', 'success', TRUE)"
            ),
            {"d": d},
        )
    assert db.daily_run_done(d, engine) is False

    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO pipeline_runs (run_date, steps, status, dry_run) VALUES "
                "(:d, 'ingest,validate,weather,clean,predict,notify,revalidate', 'success', FALSE)"
            ),
            {"d": d},
        )
    assert db.daily_run_done(d, engine) is True

    def must_not_run(*a: Any, **k: Any) -> Any:
        raise AssertionError("the pipeline must not run twice on the same day")

    monkeypatch.setattr(pipeline, "run_pipeline", must_not_run)
    status = tmp_path / "last_run.json"
    rc = pipeline.main(
        ["--steps", "all", "--date", d.isoformat(), "--once-per-day", "--status-file", str(status)]
    )
    assert rc == 0 and json.loads(status.read_text(encoding="utf-8"))["status"] == "skipped"
    with engine.connect() as conn:
        n = conn.execute(text("SELECT count(*) FROM pipeline_runs")).scalar_one()
    assert n == 4  # no new run row
