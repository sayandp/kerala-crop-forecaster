"""Bot texts and price formatting (Rs./quintal in the DB -> Rs./kg for people)."""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from cropcast.bot.names import crop_name, market_name
from cropcast.bot.store import PriceRow
from cropcast.config import settings

TEXTS = Path(__file__).resolve().parent / "texts"
ML_MONTHS = ["ജനു", "ഫെബ്രു", "മാർ", "ഏപ്രി", "മേയ്", "ജൂൺ", "ജൂലൈ", "ഓഗ", "സെപ്", "ഒക്ടോ", "നവം", "ഡിസം"]
EN_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
REPO = "https://github.com/sayandp/kerala-crop-forecaster"


@lru_cache(maxsize=2)
def texts(lang: str) -> dict[str, str]:
    data: dict[str, str] = yaml.safe_load((TEXTS / f"{lang}.yaml").read_text(encoding="utf-8"))
    return data


def t(lang: str, key: str, **values: Any) -> str:
    template = texts(lang if lang in ("ml", "en") else "ml")[key]
    defaults = {
        "channel": settings.telegram_channel_url,
        "dashboard": settings.dashboard_url,
        "repo": REPO,
        "max": settings.bot_max_alerts,
    }
    return template.format(**{**defaults, **values})


def kg(rs_per_quintal: float) -> str:
    v = rs_per_quintal / 100
    return f"{v:.0f}" if v >= 20 else f"{v:.1f}"


def amount(rs_per_kg: float) -> str:
    return f"{rs_per_kg:g}"


def day(d: date, lang: str) -> str:
    months = ML_MONTHS if lang == "ml" else EN_MONTHS
    return f"{d.day} {months[d.month - 1]}"


def with_footer(lang: str, body: str) -> str:
    return f"{body}\n\n{t(lang, 'footer')}"


def price_list(lang: str, crop: str, rows: list[PriceRow], today: date) -> str:
    """All served markets of a crop: latest price, date, 7-day range; stale ones marked."""
    lines = [t(lang, "price_title", crop=crop_name(crop, lang))]
    any_stale = False
    for r in sorted(rows, key=lambda r: (not r.fresh(today), r.series.market)):
        if r.price is None or r.date is None:
            continue
        values = {
            "market": market_name(r.series.market, lang),
            "price": kg(r.price),
            "date": day(r.date, lang),
        }
        if r.p10 is not None and r.p90 is not None:
            line = t(lang, "price_line", lo=kg(r.p10), hi=kg(r.p90), **values)
        else:
            line = t(lang, "price_line_noforecast", **values)
        if not r.fresh(today):
            line += t(lang, "stale_mark")
            any_stale = True
        lines.append(line)
    if any_stale:
        lines.append(t(lang, "stale_note"))
    return with_footer(lang, "\n".join(lines))


def price_detail(lang: str, r: PriceRow, today: date) -> str:
    crop = crop_name(r.series.commodity, lang)
    market = market_name(r.series.market, lang)
    if r.price is None or r.date is None:
        return t(lang, "no_price", crop=crop, market=market)
    values = {"crop": crop, "market": market, "price": kg(r.price), "date": day(r.date, lang)}
    if r.p10 is not None and r.p90 is not None and r.target is not None:
        body = t(
            lang, "price_detail", target=day(r.target, lang), lo=kg(r.p10), hi=kg(r.p90), **values
        )
    else:
        body = t(lang, "price_detail_noforecast", **values)
    if not r.fresh(today):
        body += "\n" + t(lang, "stale_warning", days=r.stale_days(today))
    return with_footer(lang, body)


def markets_text(lang: str, crop: str, rows: list[PriceRow], today: date) -> str:
    fresh = [r for r in rows if r.fresh(today) and r.price is not None and r.date is not None]
    name = crop_name(crop, lang)
    if not fresh:
        return t(lang, "markets_none", crop=name)
    lines = [t(lang, "markets_title", crop=name)]
    for r in sorted(fresh, key=lambda r: r.series.market):
        assert r.price is not None and r.date is not None
        lines.append(
            t(
                lang,
                "markets_line",
                market=market_name(r.series.market, lang),
                price=kg(r.price),
                date=day(r.date, lang),
            )
        )
    return with_footer(lang, "\n".join(lines))


def move_lines(lang: str, moves: dict[str, str]) -> list[str]:
    out = []
    for market, cls in sorted(moves.items()):
        if cls in ("up", "down"):
            out.append(
                t(lang, "move_up" if cls == "up" else "move_down", market=market_name(market, lang))
            )
    return out
