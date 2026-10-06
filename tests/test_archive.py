"""Archive of old prices_raw rows: verify-before-delete, archive_log, read-back, enrichment."""

from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import Engine, text

from cropcast import archive, db
from tests.conftest import price_row


@pytest.fixture
def fake_gh(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Replace GitHub Releases with a local folder: <tmp>/releases/<tag>/*.parquet."""
    store = tmp_path / "releases"
    monkeypatch.setattr(archive.settings, "data_dir", tmp_path / "data")

    def upload(tag: str, files: list[Path], cutoff: date, rows: int) -> None:
        (store / tag).mkdir(parents=True)
        for f in files:
            shutil.copy(f, store / tag / f.name)

    def download(tag: str, dest: Path) -> list[Path]:
        dest.mkdir(parents=True, exist_ok=True)
        for f in (store / tag).glob(archive.FILE_GLOB):
            shutil.copy(f, dest / f.name)
        return sorted(dest.glob(archive.FILE_GLOB))

    monkeypatch.setattr(archive, "upload_release", upload)
    monkeypatch.setattr(archive, "download_release", download)
    return store


def _seed(engine: Engine) -> None:
    rows = [
        price_row(date=date(2025, 12, 30)),
        price_row(date=date(2026, 1, 2)),
        price_row(date=date(2026, 6, 1)),
        price_row(date=date(2026, 9, 30)),  # recent: stays
    ]
    db.upsert_prices(pd.DataFrame(rows), engine)


def _count(engine: Engine, sql: str) -> int:
    with engine.connect() as conn:
        return int(conn.execute(text(sql)).scalar_one())


@pytest.mark.db
def test_archive_verifies_then_deletes_and_reads_back(engine: Engine, fake_gh: Path) -> None:
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE archive_log"))
    _seed(engine)
    res = archive.archive_prices_raw(engine, date(2026, 7, 1), "data-archive-test")
    assert res.rows == 3
    assert sorted(f.name for f in res.files) == [
        "prices_raw_2025.parquet",
        "prices_raw_2026.parquet",
    ]
    assert _count(engine, "SELECT count(*) FROM prices_raw") == 1  # only the recent row left
    assert _count(engine, "SELECT rows FROM archive_log WHERE release_tag='data-archive-test'") == 3
    shutil.rmtree(archive.archive_root())  # force a download, like a fresh CI checkout
    back = archive.load_archive(engine)
    assert len(back) == 3 and pd.to_datetime(back["date"]).max() < pd.Timestamp("2026-07-01")
    # Idempotent: nothing left to archive.
    assert archive.archive_prices_raw(engine, date(2026, 7, 1), "data-archive-test2").rows == 0


@pytest.mark.db
def test_failed_verification_deletes_nothing(
    engine: Engine, fake_gh: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(engine)
    real_upload = archive.upload_release

    def lossy_upload(tag: str, files: list[Path], cutoff: date, rows: int) -> None:
        real_upload(tag, files, cutoff, rows)
        f = sorted((fake_gh / tag).glob("*.parquet"))[0]
        pd.read_parquet(f).iloc[:0].to_parquet(f)  # an asset arrives empty

    monkeypatch.setattr(archive, "upload_release", lossy_upload)
    with pytest.raises(RuntimeError, match="verification failed"):
        archive.archive_prices_raw(engine, date(2026, 7, 1), "data-archive-bad")
    assert _count(engine, "SELECT count(*) FROM prices_raw") == 4


def test_fill_arrivals_matches_the_kept_report_exactly() -> None:
    rows = pd.DataFrame([price_row(arrivals_tonnes=None), price_row(variety="Poovan")])
    arrivals = pd.DataFrame(
        [
            {**price_row(), "arrivals_tonnes": 2.5},
            {**price_row(modal_price=5400.0), "arrivals_tonnes": 9.0},  # other grade: no match
        ]
    )
    out = archive.fill_arrivals(rows, arrivals).set_index("variety")
    assert out.loc["Nendran", "arrivals_tonnes"] == 2.5
    assert pd.isna(out.loc["Poovan", "arrivals_tonnes"])
