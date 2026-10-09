"""Canonical names for commodities, varieties, markets, districts and states.

One canonical name per entity. Every ingest source goes through `normalize()` so that a
market or commodity never appears under two spellings (which would split a series).
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

import pandas as pd
import yaml

log = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent


class CommodityMap(NamedTuple):
    canonical: str
    # Prepended to the variety so distinct products that share a canonical commodity
    # (e.g. ripe vs green banana) never collide on the (date, market, commodity, variety) key.
    variety_prefix: str = ""


# Keys are casefolded raw commodity names as published by Agmarknet / data.gov.in.
# Only target crops are mapped; anything else is logged (with counts) and dropped.
COMMODITY_MAP: dict[str, CommodityMap] = {
    "banana": CommodityMap("banana"),
    "banana - ripe": CommodityMap("banana"),
    "banana - green": CommodityMap("banana", "Green "),
    "banana-green": CommodityMap("banana", "Green "),
    "coconut": CommodityMap("coconut"),
    "rubber": CommodityMap("rubber"),
    "black pepper": CommodityMap("pepper"),
    "pepper garbled": CommodityMap("pepper", "Garbled "),
    "pepper ungarbled": CommodityMap("pepper", "Ungarbled "),
    "tapioca": CommodityMap("tapioca"),
    # Phase 6b crops: only the markets listed in config/series.yaml are kept (see below).
    "arecanut(betelnut/supari)": CommodityMap("arecanut"),
    "arecanut": CommodityMap("arecanut"),
    "coffee": CommodityMap("coffee"),
    "ginger(green)": CommodityMap("ginger"),
    "tomato": CommodityMap("tomato"),
    "onion": CommodityMap("onion"),
    "green chilli": CommodityMap("green_chilli"),
    "bitter gourd": CommodityMap("bitter_gourd"),
    "drumstick": CommodityMap("drumstick"),
    "cucumbar(kheera)": CommodityMap("cucumber"),
    "cucumber": CommodityMap("cucumber"),
}

# The original five crops are stored for every Kerala market. For the Phase 6b crops only the
# selected series' markets are stored (Neon free tier: +5 MB instead of +155 MB).
ALL_MARKET_COMMODITIES = frozenset({"banana", "coconut", "pepper", "rubber", "tapioca"})


@lru_cache(maxsize=1)
def selected_markets() -> frozenset[tuple[str, str]]:
    """(commodity, market) pairs of config/series.yaml for the selected-markets-only crops."""
    from cropcast.config import settings

    data = yaml.safe_load((settings.config_dir / "series.yaml").read_text(encoding="utf-8"))
    return frozenset(
        (str(s["commodity"]), str(s["market"]))
        for s in data["series"]
        if str(s["commodity"]) not in ALL_MARKET_COMMODITIES
    )


# Casefolded raw variety -> canonical variety.
VARIETY_MAP: dict[str, str] = {
    "nendra bale": "Nendran",
    "nendran": "Nendran",
    "nendra": "Nendran",
    "ungrabled": "Ungarbled",
    "ungarbled": "Ungarbled",
    "garbled": "Garbled",
    "rss-4": "RSS-4",
    "rss4": "RSS-4",
    "rss 4": "RSS-4",
    "banana - ripe": "Ripe",
    # Generic variety labels that just repeat the commodity name.
    "banana - green": "",
    "banana": "",
    "other": "Other",
    "": "Other",
}

# Raw district spellings -> canonical (Kerala's 14 districts).
DISTRICT_MAP: dict[str, str] = {
    "alleppey": "Alappuzha",
    "alappuzha": "Alappuzha",
    "calicut": "Kozhikode",
    "kozhikode": "Kozhikode",
    "kozhikode(calicut)": "Kozhikode",
    "thirssur": "Thrissur",
    "thrissur": "Thrissur",
    "trichur": "Thrissur",
    "palakad": "Palakkad",
    "palakkad": "Palakkad",
    "palghat": "Palakkad",
    "kasargod": "Kasaragod",
    "kasaragod": "Kasaragod",
    "trivandrum": "Thiruvananthapuram",
    "thiruvananthapuram": "Thiruvananthapuram",
    "quilon": "Kollam",
    "kollam": "Kollam",
    "ernakulam": "Ernakulam",
    "idukki": "Idukki",
    "kannur": "Kannur",
    "kottayam": "Kottayam",
    "malappuram": "Malappuram",
    "pathanamthitta": "Pathanamthitta",
    "wayanad": "Wayanad",
}

STATE_MAP: dict[str, str] = {"keralam": "Kerala", "kerala": "Kerala"}

# Explicit market aliases (applied after whitespace cleanup, before suffix rules).
# Add entries here when two sources spell the same market differently.
MARKET_ALIASES: dict[str, str] = {
    "Broadway market Market": "Broadway",
}

_WS = re.compile(r"\s+")
_VFPCK = re.compile(r"\(?\s*vfpck\s*\)?", re.IGNORECASE)
_MARKET_SUFFIX = re.compile(r"\s+market$", re.IGNORECASE)


def _clean(s: object) -> str:
    if s is None or (isinstance(s, float) and math.isnan(s)):
        return ""
    return _WS.sub(" ", str(s)).strip()


def canonical_market(raw: object) -> str:
    """'Adimali  VFPCK Market' -> 'Adimali VFPCK'; 'Ernakulam Market' -> 'Ernakulam'."""
    name = _clean(raw)
    name = MARKET_ALIASES.get(name, name)
    is_vfpck = bool(_VFPCK.search(name))
    name = _VFPCK.sub(" ", name)
    name = _MARKET_SUFFIX.sub("", _clean(name))
    name = _clean(name)
    if name and name.islower():
        name = name.title()
    return f"{name} VFPCK" if is_vfpck else name


def canonical_variety(raw: object) -> str:
    v = _clean(raw)
    return VARIETY_MAP.get(v.casefold(), v)


def canonical_district(raw: object) -> str | None:
    d = _clean(raw)
    if not d:
        return None
    return DISTRICT_MAP.get(d.casefold(), d.title())


def canonical_state(raw: object) -> str:
    s = _clean(raw)
    return STATE_MAP.get(s.casefold(), s)


@lru_cache(maxsize=1)
def market_districts() -> dict[str, str]:
    """Canonical market -> canonical district, from the Agmarknet masters snapshot."""
    raw: dict[str, str | None] = yaml.safe_load(
        (_HERE / "kerala_markets.yaml").read_text(encoding="utf-8")
    )
    out: dict[str, str] = {}
    for market, district in raw.items():
        d = canonical_district(district)
        if d:
            out[canonical_market(market)] = d
    return out


def apply_price_conventions(df: pd.DataFrame) -> pd.DataFrame:
    """min = max = 0 with a positive modal means "only the modal was reported" -> NULL bounds."""
    out = df.copy()
    lo = pd.to_numeric(out["min_price"], errors="coerce")
    hi = pd.to_numeric(out["max_price"], errors="coerce")
    modal_only = (lo == 0) & (hi == 0)
    out["min_price"] = lo.mask(modal_only)
    out["max_price"] = hi.mask(modal_only)
    return out


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Map raw source rows onto canonical names.

    Expects columns: state, district, market, commodity, variety (+ prices, date, source).
    Rows whose commodity is not in COMMODITY_MAP are dropped *with a log line* listing
    every unmapped name and its row count.
    """
    if df.empty:
        return df.copy()
    out = df.copy()
    raw_commodity = out["commodity"].map(_clean)
    mapped = raw_commodity.str.casefold().map(COMMODITY_MAP)

    unmapped = Counter(raw_commodity[mapped.isna()])
    if unmapped:
        log.info(
            "dropping unmapped commodities",
            extra={"unmapped": dict(unmapped.most_common()), "rows": sum(unmapped.values())},
        )
    keep = mapped.notna()
    out = out.loc[keep].copy()
    mapped = mapped.loc[keep]

    out["commodity"] = [m.canonical for m in mapped]
    prefixes = [m.variety_prefix for m in mapped]
    out["variety"] = [
        (p + canonical_variety(v)).strip() or "Other"
        for p, v in zip(prefixes, out["variety"], strict=True)
    ]
    out["market"] = out["market"].map(canonical_market)
    out["state"] = out["state"].map(canonical_state)

    # Phase 6b crops: keep only the selected markets (all their varieties, so a relabel at the
    # portal can still be aliased in the clean layer).
    selected = out["commodity"].isin(ALL_MARKET_COMMODITIES) | pd.Series(
        list(zip(out["commodity"], out["market"], strict=True)), index=out.index
    ).isin(selected_markets())
    if (~selected).any():
        log.info(
            "dropping unselected markets of selected-only crops",
            extra={"rows": int((~selected).sum())},
        )
    out = out.loc[selected].copy()

    districts = out["district"].map(canonical_district) if "district" in out else None
    lookup = out["market"].map(market_districts())
    out["district"] = lookup if districts is None else districts.fillna(lookup)
    missing = out.loc[out["district"].isna(), "market"].unique().tolist()
    if missing:
        log.warning("markets with unknown district", extra={"markets": missing})
    return apply_price_conventions(out).reset_index(drop=True)
