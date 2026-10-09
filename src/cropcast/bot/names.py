"""Crop / market / direction names as people type them (config/aliases.yaml), both languages.

Matching order: exact (after normalisation) -> unique prefix (>= 3 chars) -> fuzzy (difflib,
stdlib). Pure functions; the served series come from config/series.yaml (no DB, no pandas).
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from cropcast.config import settings

ALIASES_PATH = settings.config_dir / "aliases.yaml"
SERIES_PATH = settings.config_dir / "series.yaml"
FUZZY_CUTOFF = 0.85  # lower let "kannur" match "mookannur"; real typos score > 0.9

# Old-style chillu encodings (consonant + virama + ZWJ) -> atomic chillu letters.
_CHILLU = {
    "ണ്‍": "ൺ",  # ൺ
    "ന്‍": "ൻ",  # ൻ
    "ര്‍": "ർ",  # ർ
    "ല്‍": "ൽ",  # ൽ
    "ള്‍": "ൾ",  # ൾ
}
_DROP = re.compile(r"[\s​-‍\-_.,'\"/()]+")


def norm(text: str) -> str:
    """Comparable key: NFC, lower-case, chillus unified, spaces / ZWJ / punctuation removed."""
    s = unicodedata.normalize("NFC", text).lower()
    for old, new in _CHILLU.items():
        s = s.replace(old, new)
    return _DROP.sub("", s)


@dataclass(frozen=True)
class Served:
    commodity: str
    market: str
    variety: str
    crop: str = ""  # product key (config/series.yaml `crop:`), e.g. small_onion

    @property
    def key(self) -> str:
        return self.crop or self.commodity


@lru_cache(maxsize=1)
def aliases(path: Path = ALIASES_PATH) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data


@lru_cache(maxsize=1)
def served(path: Path = SERIES_PATH) -> tuple[Served, ...]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return tuple(
        Served(
            str(s["commodity"]),
            str(s["market"]),
            str(s["variety"]),
            str(s.get("crop") or s["commodity"]),
        )
        for s in data["series"]
    )


# Product keys in button / display order (config/aliases.yaml `crops:`).
CROPS: tuple[str, ...] = tuple(str(k) for k in aliases()["crops"])


def markets_of(crop: str) -> list[Served]:
    """Served series of a crop, sorted by market (the index is used in inline keyboards)."""
    return sorted((s for s in served() if s.key == crop), key=lambda s: s.market)


def crop_of(commodity: str, market: str, variety: str) -> str:
    """Product key of a stored series (alerts store commodity / market / variety)."""
    for s in served():
        if (s.commodity, s.market, s.variety) == (commodity, market, variety):
            return s.key
    return commodity


def crop_name(crop: str, lang: str) -> str:
    entry = aliases()["crops"].get(crop, {})
    if lang == "en":
        return str(entry.get("name_en") or crop.replace("_", " ").capitalize())
    names = entry.get("ml") or []
    return str(names[0]) if names else crop


def market_name(market: str, lang: str) -> str:
    if lang == "ml":
        names = aliases()["markets"].get(market, {}).get("ml") or []
        if names:
            return str(names[0])
    return market


def _table(kind: str, keys: list[str] | None = None) -> dict[str, str]:
    """normalised alias -> canonical key (also the canonical key itself)."""
    out: dict[str, str] = {}
    for key, entry in aliases()[kind].items():
        if keys is not None and key not in keys:
            continue
        names = (
            [key, *entry]
            if isinstance(entry, list)
            else [key, *(n for ns in entry.values() if isinstance(ns, list) for n in ns)]
        )
        for name in names:
            out.setdefault(norm(str(name)), str(key))
    return out


def _match(text: str, table: dict[str, str]) -> str | None:
    k = norm(text)
    if not k:
        return None
    if k in table:
        return table[k]
    if len(k) >= 3:
        hits = {v for a, v in table.items() if a.startswith(k)}
        if len(hits) == 1:
            return hits.pop()
    close = difflib.get_close_matches(k, list(table), n=1, cutoff=FUZZY_CUTOFF)
    return table[close[0]] if close else None


def match_crop(text: str) -> str | None:
    return _match(text, _table("crops"))


def match_market(crop: str, text: str) -> Served | None:
    series = {s.market: s for s in markets_of(crop)}
    key = _match(text, _table("markets", list(series)))
    return series.get(key) if key else None


def match_direction(text: str) -> str | None:
    k = norm(text)
    for direction, names in aliases()["directions"].items():
        if k in {norm(str(n)) for n in names}:
            return str(direction)
    return None


def split_crop(args: list[str]) -> tuple[str | None, list[str]]:
    """Longest leading words naming a crop: "black pepper kannur" -> (pepper, [kannur])."""
    for i in range(min(3, len(args)), 0, -1):
        crop = match_crop(" ".join(args[:i]))
        if crop:
            return crop, args[i:]
    return None, args


def market_slug(market: str) -> str:
    """Deep-link slug, same rule as web/lib/crops.ts: "Chenkal VFPCK" -> "chenkal-vfpck"."""
    return re.sub(r"[^a-z0-9]+", "-", market.lower()).strip("-")


def parse_start_payload(payload: str) -> tuple[str, str | None, Served | None] | None:
    """`/start alert_<crop>[_<market-slug>]` or `price_<crop>` (website buttons) -> parts.

    Crop keys may contain underscores (small_onion), so the longest matching key wins."""
    kind, _, rest = payload.partition("_")
    if kind not in ("alert", "price") or not rest:
        return None
    crop = max((k for k in CROPS if rest == k or rest.startswith(k + "_")), key=len, default=None)
    if crop is None:
        return None
    slug = rest[len(crop) + 1 :]
    market = None
    if slug:
        market = next((s for s in markets_of(crop) if market_slug(s.market) == slug), None)
    return kind, crop, market


_NUMBER = re.compile(r"(\d+(?:[.,]\d+)?)")


def parse_amount(text: str) -> float | None:
    """'₹62.5', 'rs62', '62/kg' -> 62.5 (Rs./kg)."""
    m = _NUMBER.search(text.replace(",", "."))
    if not m:
        return None
    value = float(m.group(1))
    return value if 0 < value < 100_000 else None
