"""Pipeline orchestration without a database (dry-run) and without network."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from cropcast import pipeline
from cropcast.validate.schemas import RejectRateExceeded
from tests.conftest import price_row


def test_dry_run_ingest_validate(
    monkeypatch: pytest.MonkeyPatch, good_prices: pd.DataFrame
) -> None:
    monkeypatch.setattr(pipeline, "fetch_kerala_prices", lambda *a, **k: good_prices.copy())
    monkeypatch.setattr(pipeline, "normalize", lambda df: df)
    ctx = pipeline.RunContext(run_date=date(2026, 10, 3), dry_run=True)
    results = pipeline.run_pipeline(["ingest", "validate"], ctx)
    assert [r.step for r in results] == ["ingest", "validate"]
    assert results[1].metrics["good"] == len(good_prices)
    assert ctx.run_id is None  # dry run never touches the DB


def test_too_many_rejects_fails_the_run(monkeypatch: pytest.MonkeyPatch) -> None:
    bad = pd.DataFrame(
        [price_row(variety=str(i), modal_price=0.0, min_price=0.0) for i in range(3)]
    )
    batch = pd.concat([bad, pd.DataFrame([price_row()])], ignore_index=True)
    sent: list[str] = []
    monkeypatch.setattr(pipeline, "fetch_kerala_prices", lambda *a, **k: batch)
    monkeypatch.setattr(pipeline, "normalize", lambda df: df)
    monkeypatch.setattr(pipeline, "send_admin_message", lambda msg: sent.append(msg) or True)
    ctx = pipeline.RunContext(run_date=date(2026, 10, 3), dry_run=True)
    with pytest.raises(RejectRateExceeded):
        pipeline.run_pipeline(["ingest", "validate"], ctx)
    assert sent and "step=validate" in sent[0]


def test_unknown_step_rejected() -> None:
    with pytest.raises(ValueError, match="unknown steps"):
        pipeline.run_pipeline(
            ["train"], pipeline.RunContext(run_date=date(2026, 10, 3), dry_run=True)
        )


def test_cli_parses_steps_and_date() -> None:
    args = pipeline.parse_args(["--steps", "ingest,validate", "--date", "2026-10-01", "--dry-run"])
    assert args.steps == "ingest,validate"
    assert args.date == date(2026, 10, 1)
    assert args.dry_run is True


def test_status_file_written_on_success_and_failure(
    monkeypatch: pytest.MonkeyPatch, good_prices: pd.DataFrame, tmp_path: Path
) -> None:
    import json

    monkeypatch.setattr(pipeline, "normalize", lambda df: df)
    monkeypatch.setattr(pipeline, "fetch_kerala_prices", lambda *a, **k: good_prices.copy())
    status = tmp_path / "status" / "last_run.json"
    argv = ["--steps", "ingest,validate", "--date", "2026-10-03", "--dry-run"]
    assert pipeline.main([*argv, "--status-file", str(status)]) == 0
    ok = json.loads(status.read_text(encoding="utf-8"))
    assert ok["status"] == "success" and ok["run_date"] == "2026-10-03"

    def boom(*_a: object, **_k: object) -> pd.DataFrame:
        raise RuntimeError("source down")

    monkeypatch.setattr(pipeline, "fetch_kerala_prices", boom)
    monkeypatch.setattr(pipeline, "send_admin_message", lambda msg: True)
    assert pipeline.main([*argv, "--status-file", str(status)]) == 1
    assert json.loads(status.read_text(encoding="utf-8"))["status"] == "failed"
