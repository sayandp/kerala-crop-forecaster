"""Kerala mandi prices from Agmarknet.

Two sources, both returning the same standard frame (see `STANDARD_COLUMNS`):

* **Agmarknet 2.0 public report API** (`api.agmarknet.gov.in/v1`) — the JSON API behind
  the agmarknet.gov.in report pages. Serves any date, so it powers the backfill and the
  daily lookback that catches late market reports.
    - daily state report:  /prices-and-arrivals/commodity-market/daily-report-state
    - monthly per-crop:    /prices-and-arrivals/date-wise/specific-commodity
* **data.gov.in** resource "Current Daily Price of Various Commodities from Various
  Markets (Mandi)" — returns *today only*; fallback for the daily pull.

All prices are Rs./quintal. Raw responses are cached under data/cache/ (never refetched
once a date is final), and every request goes through the polite rate-limited client.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import numpy as np
import pandas as pd

from cropcast.config import settings
from cropcast.ingest.http import get_json, make_client

log = logging.getLogger(__name__)

IST = ZoneInfo("Asia/Kolkata")
QUINTAL_UNITS = {"rs./quintal", "rs/quintal", "rs. / quintal"}
STANDARD_COLUMNS: list[str] = [
    "date",
    "state",
    "district",
    "market",
    "commodity",
    "variety",
    "min_price",
    "max_price",
    "modal_price",
    "arrivals_tonnes",
    "source",
]
SOURCE_DATAGOV = "agmarknet"  # data.gov.in republishes Agmarknet data
SOURCE_PORTAL = "agmarknet_v2"
# A date's data is treated as final (cache never refetched) this many days after it.
FINAL_AFTER_DAYS = 7


def today_ist() -> date:
    return datetime.now(IST).date()


def _empty() -> pd.DataFrame:
    return pd.DataFrame({c: pd.Series(dtype="object") for c in STANDARD_COLUMNS})


def _write_cache(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _read_cache(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_final(day: date) -> bool:
    return (today_ist() - day).days >= FINAL_AFTER_DAYS


def _finish(df: pd.DataFrame, source: str) -> pd.DataFrame:
    if df.empty:
        return _empty()
    df["source"] = source
    if "arrivals_tonnes" not in df.columns:
        df["arrivals_tonnes"] = np.nan  # e.g. data.gov.in publishes no arrivals
    for col in ("min_price", "max_price", "modal_price", "arrivals_tonnes"):
        df[col] = pd.to_numeric(df[col], errors="coerce").astype(float)
    return df.reindex(columns=STANDARD_COLUMNS)


# ---------------------------------------------------------------------------
# Agmarknet 2.0 report API
# ---------------------------------------------------------------------------


def portal_client() -> httpx.Client:
    # The API serves the agmarknet.gov.in SPA; identify ourselves the same way it does.
    return make_client(Origin="https://agmarknet.gov.in", Referer="https://agmarknet.gov.in/")


def _check_portal(payload: Any, what: str) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("success") is not True:
        msg = payload.get("message") if isinstance(payload, dict) else type(payload).__name__
        raise RuntimeError(f"agmarknet portal returned failure for {what}: {msg}")
    return payload


def fetch_portal_daily(
    day: date, client: httpx.Client | None = None, use_cache: bool = True
) -> dict[str, Any]:
    """All Kerala commodities x markets for one arrival date (raw JSON, cached)."""
    cache = settings.cache_dir / "agmarknet_v2" / "daily" / f"{day.isoformat()}.json"
    if use_cache and cache.exists() and _is_final(day):
        cached: dict[str, Any] = _read_cache(cache)
        return cached
    own = client is None
    client = client or portal_client()
    try:
        payload = get_json(
            client,
            f"{settings.agmarknet_api_base}/prices-and-arrivals/commodity-market/daily-report-state",
            params={
                "date": day.isoformat(),
                "state": settings.agmarknet_state_id,
                "includeExcel": "false",
            },
        )
    finally:
        if own:
            client.close()
    payload = _check_portal(payload, f"daily {day}")
    _write_cache(cache, payload)
    return payload


def parse_portal_daily(payload: dict[str, Any], day: date) -> pd.DataFrame:
    """Flatten the daily state report into the standard frame (raw names, pre-normalize)."""
    rows: list[dict[str, Any]] = []
    other_units: Counter[tuple[str, str]] = Counter()
    for group in payload.get("commodityGroups") or []:
        for cmdt in group.get("commodities") or []:
            name = cmdt.get("commodityName")
            for mkt in cmdt.get("markets") or []:
                for rec in mkt.get("data") or []:
                    unit = str(rec.get("unitOfPrice") or "Rs./Quintal")
                    if unit.strip().casefold() not in QUINTAL_UNITS:
                        other_units[(str(name), unit)] += 1
                        continue
                    tonnes = str(rec.get("unitOfArrivals") or "").casefold() == "metric tonnes"
                    rows.append(
                        {
                            "date": day,
                            "state": "Keralam",
                            "district": None,
                            "market": mkt.get("marketCenter"),
                            "commodity": name,
                            "variety": rec.get("variety"),
                            "min_price": rec.get("minimumPrice"),
                            "max_price": rec.get("maximumPrice"),
                            "modal_price": rec.get("modalPrice"),
                            "arrivals_tonnes": rec.get("arrivals") if tonnes else None,
                        }
                    )
    if other_units:
        log.info(
            "skipped non-quintal price rows",
            extra={"units": {f"{c} [{u}]": n for (c, u), n in other_units.items()}},
        )
    return _finish(pd.DataFrame(rows), SOURCE_PORTAL)


def fetch_portal_month(
    year: int,
    month: int,
    commodity_id: int,
    client: httpx.Client | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Date-wise prices for one commodity, one month, all Kerala markets (cached)."""
    cache = (
        settings.cache_dir
        / "agmarknet_v2"
        / "monthly"
        / str(commodity_id)
        / f"{year:04d}-{month:02d}.json"
    )
    month_end = (pd.Timestamp(year=year, month=month, day=1) + pd.offsets.MonthEnd(0)).date()
    if use_cache and cache.exists() and _is_final(month_end):
        cached: dict[str, Any] = _read_cache(cache)
        return cached
    own = client is None
    client = client or portal_client()
    try:
        payload = get_json(
            client,
            f"{settings.agmarknet_api_base}/prices-and-arrivals/date-wise/specific-commodity",
            params={
                "year": year,
                "month": month,
                "includeExcel": "false",
                "stateId": settings.agmarknet_state_id,
                "commodityId": commodity_id,
            },
        )
    finally:
        if own:
            client.close()
    payload = _check_portal(payload, f"month {year}-{month:02d} commodity {commodity_id}")
    _write_cache(cache, payload)
    return payload


def parse_portal_month(payload: dict[str, Any], commodity_name: str) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for mkt in payload.get("markets") or []:
        for day in mkt.get("dates") or []:
            for rec in day.get("data") or []:
                rows.append(
                    {
                        "date": day.get("arrivalDate"),
                        "state": "Keralam",
                        "district": None,
                        "market": mkt.get("marketName"),
                        "commodity": commodity_name,
                        "variety": rec.get("variety"),
                        "min_price": rec.get("minimumPrice"),
                        "max_price": rec.get("maximumPrice"),
                        "modal_price": rec.get("modalPrice"),
                        "arrivals_tonnes": rec.get("arrivals"),  # report is in metric tonnes
                    }
                )
    df = pd.DataFrame(rows)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"], format="%d/%m/%Y", errors="coerce").dt.date
    return _finish(df, SOURCE_PORTAL)


# ---------------------------------------------------------------------------
# data.gov.in
# ---------------------------------------------------------------------------


def norm_key(key: str) -> str:
    # The resource has shipped both "Modal_x0020_Price"/"Arrival_Date" and
    # "modal_price"/"arrival_date" style keys; fold them to one form.
    return key.replace("_x0020_", "_").replace(" ", "_").strip().lower()


def fetch_datagov(
    fetch_day: date | None = None, client: httpx.Client | None = None
) -> list[dict[str, Any]]:
    """All Kerala records currently published (paginated). Cached per fetch day."""
    if settings.datagov_api_key is None:
        raise RuntimeError("DATAGOV_API_KEY is not set")
    fetch_day = fetch_day or today_ist()
    own = client is None
    client = client or make_client()
    url = f"{settings.datagov_base_url}/{settings.datagov_resource_id}"
    records: list[dict[str, Any]] = []
    offset = 0
    try:
        while True:
            page = get_json(
                client,
                url,
                params={
                    "api-key": settings.datagov_api_key.get_secret_value(),
                    "format": "json",
                    "limit": settings.datagov_page_size,
                    "offset": offset,
                    "filters[state.keyword]": settings.state,
                },
                min_interval=1.0,
            )
            batch = page.get("records") or []
            records.extend(batch)
            total = int(page.get("total") or 0)
            offset += len(batch)
            if not batch or offset >= total:
                break
    finally:
        if own:
            client.close()
    _write_cache(
        settings.cache_dir / "agmarknet" / f"{fetch_day.isoformat()}.json",
        {"fetched_at": datetime.now(IST).isoformat(), "records": records},
    )
    return records


def parse_datagov(records: Iterable[dict[str, Any]]) -> pd.DataFrame:
    rows = [{norm_key(k): v for k, v in r.items()} for r in records]
    df = pd.DataFrame(rows)
    if df.empty:
        return _empty()
    df = df.rename(columns={"arrival_date": "date"})
    df["date"] = pd.to_datetime(df["date"], format="%d/%m/%Y", errors="coerce").dt.date
    for col in STANDARD_COLUMNS:
        if col not in df.columns and col != "source":
            df[col] = None
    # Belt and braces: the API filter is not trusted, Kerala is enforced here too.
    is_kerala = df["state"].astype(str).str.strip().str.casefold().isin({"kerala", "keralam"})
    return _finish(df.loc[is_kerala].copy(), SOURCE_DATAGOV)


# ---------------------------------------------------------------------------
# Daily entry point
# ---------------------------------------------------------------------------


def fetch_kerala_prices(run_date: date, lookback_days: int | None = None) -> pd.DataFrame:
    """Raw (un-normalized) Kerala prices for run_date and the lookback window.

    Sources are tried in `settings.ingest_sources` order; the first that yields rows wins.
    """
    lookback = settings.ingest_lookback_days if lookback_days is None else lookback_days
    days = [run_date - timedelta(days=i) for i in range(lookback, -1, -1)]
    errors: list[str] = []
    for source in settings.ingest_sources:
        try:
            if source == "agmarknet":
                with portal_client() as client:
                    frames = [parse_portal_daily(fetch_portal_daily(d, client), d) for d in days]
                df = pd.concat(frames, ignore_index=True)
            else:
                if run_date != today_ist():
                    raise RuntimeError("data.gov.in only serves today's prices")
                df = parse_datagov(fetch_datagov(run_date))
        except Exception as exc:
            log.warning("ingest source failed", extra={"source": source, "error": repr(exc)})
            errors.append(f"{source}: {exc!r}")
            continue
        if df.empty:
            log.warning("ingest source returned no rows", extra={"source": source})
            errors.append(f"{source}: no rows")
            continue
        log.info(
            "fetched prices",
            extra={"source": source, "rows": len(df), "days": [d.isoformat() for d in days]},
        )
        return df
    raise RuntimeError("all ingest sources failed: " + "; ".join(errors))
