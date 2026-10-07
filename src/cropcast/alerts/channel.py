"""Telegram Stage 1: one daily broadcast post to a public channel (no webhook, no server).

The post shows, per crop, 1-3 main markets: the latest modal price (dated when it is not
today's) and the champion's p10-p90 range for the price 7 days ahead, Malayalam line first and
English line second. No up/down move
alerts (the move classifier is shadow-only until promoted AND `move_alerts_enabled`).

Idempotent: a date is posted at most once (channel_posts). Skipped when nothing new was
ingested today. Dry-run prints the post instead of sending it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import yaml
from sqlalchemy import Engine, text

from cropcast.config import PROJECT_ROOT, settings
from cropcast.validate.units import implausible

log = logging.getLogger(__name__)

TEMPLATES = Path(__file__).resolve().parent / "templates"
CHANNEL_CONFIG = PROJECT_ROOT / "config" / "channel.yaml"
LANGS = ("ml", "en")
API = "https://api.telegram.org/bot{token}/{method}"
MAX_PRICE_AGE_DAYS = 3  # a market whose latest price is older is left out of the post


@lru_cache(maxsize=4)
def template(lang: str) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((TEMPLATES / f"{lang}.yaml").read_text(encoding="utf-8"))
    return data


@lru_cache(maxsize=1)
def channel_config() -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load(CHANNEL_CONFIG.read_text(encoding="utf-8"))
    return data


def _kg(rs_per_quintal: float) -> str:
    return f"{rs_per_quintal / 100:,.0f}"


def gather(engine: Engine, run_date: date) -> pd.DataFrame:
    """Configured markets: last observed price + its date, 7-day p10/p90 for run_date."""
    sql = """
        SELECT f.commodity, f.market, f.variety, f.p10::float8 AS p10, f.p90::float8 AS p90,
               f.last_value::float8 AS last_value,
               (SELECT max(c.date) FROM prices_clean c
                 WHERE c.commodity = f.commodity AND c.market = f.market
                   AND c.variety = f.variety AND c.date <= f.forecast_date) AS obs_date
        FROM forecasts f
        WHERE f.forecast_date = :d AND f.horizon = 7
    """
    with engine.connect() as conn:
        return pd.read_sql(text(sql), conn, params={"d": run_date})


def postable(rows: pd.DataFrame, run_date: date) -> pd.DataFrame:
    """Markets fresh enough (latest price <= 3 days old) and in a plausible Rs./kg band."""
    if rows.empty:
        return rows
    obs = pd.to_datetime(rows["obs_date"])
    fresh = obs >= pd.Timestamp(run_date) - pd.Timedelta(days=MAX_PRICE_AGE_DAYS)
    ok = fresh & ~implausible(rows["commodity"], rows["last_value"])
    dropped = rows.loc[~ok, ["commodity", "market"]].astype(str)
    if len(dropped):
        log.info(
            "markets left out of the post",
            extra={"markets": [f"{c}/{m}" for c, m in dropped.itertuples(index=False)]},
        )
    return rows[ok]


def render_post(rows: pd.DataFrame, run_date: date) -> str:
    cfg = channel_config()
    t = {lang: template(lang) for lang in LANGS}
    lines = [
        t["ml"]["header"].format(date=f"{run_date:%d-%m-%Y}"),
        t["en"]["header"].format(date=f"{run_date:%d %b %Y}"),
        "",
    ]
    for crop, markets in cfg["crops"].items():
        items = []
        for mk in markets:
            r = rows[
                (rows["commodity"] == crop)
                & (rows["market"] == mk["market"])
                & (rows["variety"] == mk["variety"])
            ]
            if r.empty:
                continue
            r0 = r.iloc[0]
            obs = pd.Timestamp(r0["obs_date"]).date() if pd.notna(r0["obs_date"]) else None
            for lang in LANGS:
                tl = t[lang]
                stale = obs is not None and obs != run_date
                line = tl["line_stale" if stale else "line"].format(
                    market=mk["market"],
                    price=_kg(r0["last_value"]),
                    lo=_kg(r0["p10"]),
                    hi=_kg(r0["p90"]),
                    obs_date=f"{obs:%d-%m}" if obs is not None else "",
                )
                items.append(("• " if lang == "ml" else "  ") + line)
        if items:
            lines.append(f"{t['ml']['crops'][crop]} · {t['en']['crops'][crop]}")
            lines.extend(items)
            lines.append("")
    lines.append(t["ml"]["footer"])
    lines.append(t["en"]["footer"].format(repo=cfg["repo_url"]))
    return "\n".join(lines)


@dataclass(frozen=True)
class NotifyResult:
    status: str  # posted | dry_run | skipped
    reason: str
    message_id: int | None = None
    text: str = ""


def _api(method: str, payload: dict[str, Any]) -> dict[str, Any]:
    assert settings.telegram_bot_token is not None
    url = API.format(token=settings.telegram_bot_token.get_secret_value(), method=method)
    resp = httpx.post(url, json=payload, timeout=20.0)
    resp.raise_for_status()
    body: dict[str, Any] = resp.json()
    if not body.get("ok"):
        raise RuntimeError(f"telegram {method} failed: {body.get('description')}")
    return body


def already_posted(engine: Engine, run_date: date) -> bool:
    with engine.connect() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM channel_posts WHERE post_date = :d"), {"d": run_date}
        ).scalar_one()
    return int(n) > 0


def new_data_today(engine: Engine, run_date: date) -> bool:
    with engine.connect() as conn:
        n = conn.execute(
            text(
                "SELECT count(*) FROM prices_raw "
                "WHERE (ingested_at AT TIME ZONE 'Asia/Kolkata')::date >= :d"
            ),  # run dates are IST
            {"d": run_date},
        ).scalar_one()
    return int(n) > 0


def notify(engine: Engine, run_date: date, dry_run: bool = False) -> NotifyResult:
    if already_posted(engine, run_date):
        return NotifyResult("skipped", "already posted for this date")
    if not new_data_today(engine, run_date):
        return NotifyResult("skipped", "no new data ingested today")
    rows = gather(engine, run_date)
    if rows.empty:
        return NotifyResult("skipped", "no forecasts for this date")
    rows = postable(rows, run_date)
    if rows.empty:
        return NotifyResult("skipped", f"no market price fresher than {MAX_PRICE_AGE_DAYS} days")
    post = render_post(rows, run_date)
    if dry_run or not (settings.telegram_bot_token and settings.telegram_channel_id):
        reason = "dry-run" if dry_run else "TELEGRAM_BOT_TOKEN / TELEGRAM_CHANNEL_ID not set"
        log.info("channel post (not sent)", extra={"reason": reason, "chars": len(post)})
        return NotifyResult("dry_run", reason, text=post)
    body = _api(
        "sendMessage",
        {"chat_id": settings.telegram_channel_id, "text": post, "disable_web_page_preview": True},
    )
    message_id = int(body["result"]["message_id"])
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO channel_posts (post_date, chat_id, message_id, text) "
                "VALUES (:d, :c, :m, :t) ON CONFLICT (post_date) DO NOTHING"
            ),
            {"d": run_date, "c": settings.telegram_channel_id, "m": message_id, "t": post},
        )
    return NotifyResult("posted", "sent", message_id, post)


def record_member_count(engine: Engine, run_date: date) -> int | None:
    if not (settings.telegram_bot_token and settings.telegram_channel_id):
        return None
    count = int(_api("getChatMemberCount", {"chat_id": settings.telegram_channel_id})["result"])
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO channel_stats (date, member_count) VALUES (:d, :n) "
                "ON CONFLICT (date) DO UPDATE SET member_count = EXCLUDED.member_count, "
                "recorded_at = now()"
            ),
            {"d": run_date, "n": count},
        )
    return count
