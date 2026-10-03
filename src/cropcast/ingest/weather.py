"""District daily rainfall + temperature from Open-Meteo (free, no key).

History comes from the ERA5-backed archive API; the most recent days (which the archive
does not yet cover) from the forecast API. One request covers all 14 districts.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import yaml

from cropcast.config import settings
from cropcast.ingest.agmarknet import today_ist
from cropcast.ingest.http import get_json, make_client

log = logging.getLogger(__name__)

DAILY_VARS = "precipitation_sum,temperature_2m_max,temperature_2m_min,temperature_2m_mean"
# The archive API lags real time by a few days; anything newer goes to the forecast API.
ARCHIVE_LAG_DAYS = 5
COLUMN_MAP = {
    "time": "date",
    "precipitation_sum": "rainfall_mm",
    "temperature_2m_max": "temp_max_c",
    "temperature_2m_min": "temp_min_c",
    "temperature_2m_mean": "temp_mean_c",
}


@lru_cache(maxsize=1)
def districts() -> dict[str, dict[str, float]]:
    path = Path(__file__).resolve().parent / "districts.yaml"
    data: dict[str, dict[str, float]] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data


def parse_openmeteo(payload: Any, names: list[str]) -> pd.DataFrame:
    """Open-Meteo returns one object per location (a bare object for a single location)."""
    items = payload if isinstance(payload, list) else [payload]
    if len(items) != len(names):
        raise ValueError(f"expected {len(names)} locations, got {len(items)}")
    frames = []
    for name, item in zip(names, items, strict=True):
        df = pd.DataFrame(item["daily"]).rename(columns=COLUMN_MAP)
        df["district"] = name
        frames.append(df)
    out = pd.concat(frames, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"]).dt.date
    out["source"] = "open-meteo"
    return out[
        ["date", "district", "rainfall_mm", "temp_max_c", "temp_min_c", "temp_mean_c", "source"]
    ]


def _fetch(client: httpx.Client, url: str, start: date, end: date) -> pd.DataFrame:
    d = districts()
    names = list(d)
    payload = get_json(
        client,
        url,
        params={
            "latitude": ",".join(str(d[n]["lat"]) for n in names),
            "longitude": ",".join(str(d[n]["lon"]) for n in names),
            "daily": DAILY_VARS,
            "timezone": "Asia/Kolkata",
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        },
        min_interval=1.0,
    )
    return parse_openmeteo(payload, names)


def fetch_weather(start: date, end: date) -> pd.DataFrame:
    """Daily weather for every Kerala district between start and end (inclusive)."""
    if end < start:
        raise ValueError("end before start")
    split = today_ist() - timedelta(days=ARCHIVE_LAG_DAYS)
    frames: list[pd.DataFrame] = []
    with make_client() as client:
        # Archive in yearly chunks to keep responses small.
        cur = start
        while cur <= min(end, split):
            chunk_end = min(date(cur.year, 12, 31), end, split)
            frames.append(_fetch(client, settings.openmeteo_archive_url, cur, chunk_end))
            cur = chunk_end + timedelta(days=1)
        if end > split:
            frames.append(
                _fetch(
                    client,
                    settings.openmeteo_forecast_url,
                    max(start, split + timedelta(days=1)),
                    end,
                )
            )
    df = pd.concat(frames, ignore_index=True)
    # Forecast-API rows for future dates are forecasts, not observations: never store them.
    df = df.loc[pd.to_datetime(df["date"]) <= pd.Timestamp(today_ist())]
    log.info("fetched weather", extra={"rows": len(df), "start": str(start), "end": str(end)})
    return df.reset_index(drop=True)
