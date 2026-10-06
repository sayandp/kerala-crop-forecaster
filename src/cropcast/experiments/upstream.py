"""E2 (Phase 2.5): upstream / cross-state markets from the same Agmarknet 2.0 source.

Stored as parquet under data/upstream/ (never in the free-tier DB).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from cropcast.config import settings
from cropcast.ingest.agmarknet import fetch_portal_month, parse_portal_month, portal_client

log = logging.getLogger(__name__)

TAMIL_NADU, KARNATAKA = 31, 16


@dataclass(frozen=True)
class Upstream:
    crop: str  # the Kerala commodity it informs
    state_id: int
    state: str
    commodity_id: int
    commodity_name: str


UPSTREAM = [
    Upstream("banana", TAMIL_NADU, "Tamil Nadu", 19, "Banana"),
    Upstream("banana", KARNATAKA, "Karnataka", 19, "Banana"),
    Upstream("coconut", TAMIL_NADU, "Tamil Nadu", 116, "Coconut"),
    Upstream("coconut", KARNATAKA, "Karnataka", 116, "Coconut"),
    Upstream("coconut", TAMIL_NADU, "Tamil Nadu", 111, "Copra"),
    Upstream("pepper", KARNATAKA, "Karnataka", 34, "Black pepper"),
    Upstream("tapioca", TAMIL_NADU, "Tamil Nadu", 85, "Tapioca"),
]


def upstream_path() -> object:
    return settings.data_dir / "upstream" / "upstream_prices.parquet"


def fetch_upstream(start: str = "2018-01", end: str | None = None) -> pd.DataFrame:
    """All upstream monthly reports (cached per state/commodity/month) -> one parquet."""
    end = end or str(pd.Period(pd.Timestamp.today(), "M"))
    months = pd.period_range(pd.Period(start, "M"), pd.Period(end, "M"), freq="M")
    frames = []
    with portal_client() as client:
        for u in UPSTREAM:
            for m in months:
                try:
                    payload = fetch_portal_month(
                        m.year, m.month, u.commodity_id, client, state_id=u.state_id
                    )
                except Exception as exc:  # keep going; a missing month is just a gap
                    log.warning(
                        "upstream fetch failed",
                        extra={"upstream": u, "month": str(m), "error": repr(exc)},
                    )
                    continue
                df = parse_portal_month(payload, u.commodity_name)
                if df.empty:
                    continue
                frames.append(df.assign(crop=u.crop, state=u.state, state_id=u.state_id))
            log.info(
                "upstream done",
                extra={"crop": u.crop, "state": u.state, "commodity": u.commodity_name},
            )
    out = pd.concat(frames, ignore_index=True)
    path = settings.data_dir / "upstream" / "upstream_prices.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(path, index=False)
    log.info("upstream written", extra={"rows": len(out), "path": str(path)})
    return out
