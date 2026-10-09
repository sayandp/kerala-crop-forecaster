"""Database access for the bot. Reads of prices / forecasts use the read-only role; the bot's
own tables are written through `cropcast_bot` (INSERT/UPDATE/DELETE on subscribers,
user_alerts, telegram_updates, bot_events only). The daily pipeline passes its owner engine
for both. Plain SQL, no pandas (the API container stays small).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

from sqlalchemy import Engine, create_engine, text

from cropcast.api.queries import engine as ro_engine
from cropcast.api.queries import sqlalchemy_url
from cropcast.bot.names import Served, markets_of
from cropcast.config import settings

IST = timezone(timedelta(hours=5, minutes=30))  # no DST: a fixed offset needs no tzdata
STALE_DAYS = 3


def today_ist() -> date:
    return datetime.now(UTC).astimezone(IST).date()


@lru_cache(maxsize=1)
def bot_engine() -> Engine:
    if not settings.database_url_bot:
        raise RuntimeError("DATABASE_URL_BOT is not set (bot writes use the cropcast_bot role)")
    timeout = settings.api_db_timeout_s
    return create_engine(
        sqlalchemy_url(settings.database_url_bot),
        pool_pre_ping=True,
        pool_size=2,
        max_overflow=2,
        pool_timeout=timeout,
        connect_args={
            "connect_timeout": max(1, int(timeout)),
            "options": f"-c statement_timeout={int(timeout * 1000)}",
        },
    )


@dataclass(frozen=True)
class PriceRow:
    series: Served
    date: dt.date | None
    price: float | None  # Rs./quintal
    target: dt.date | None = None
    p10: float | None = None
    p90: float | None = None

    def stale_days(self, today: dt.date) -> int | None:
        return None if self.date is None else (today - self.date).days

    def fresh(self, today: dt.date) -> bool:
        d = self.stale_days(today)
        return d is not None and d <= STALE_DAYS


@dataclass(frozen=True)
class Alert:
    id: int
    commodity: str
    market: str
    variety: str
    direction: str
    threshold: float  # Rs./kg
    state: str


class Store:
    def __init__(self, ro: Engine, rw: Engine) -> None:
        self.ro = ro
        self.rw = rw

    @classmethod
    def for_api(cls) -> Store:
        return cls(ro_engine(), bot_engine())

    # --- reads (read-only role) ------------------------------------------------------------

    def prices(self, crop: str) -> list[PriceRow]:
        """Latest observed price and the latest h=7 forecast of every served series of a crop."""
        series = markets_of(crop)
        if not series:
            return []
        commodity = series[0].commodity  # one commodity per product key
        rows = self._all(
            self.ro,
            """SELECT s.m AS market, s.v AS variety, p.date, p.modal_price::float8 AS price,
                      f.target_date AS target, f.p10::float8 AS p10, f.p90::float8 AS p90
               FROM unnest(CAST(:markets AS text[]), CAST(:varieties AS text[])) AS s(m, v)
               LEFT JOIN LATERAL (
                   SELECT date, modal_price FROM prices_clean
                   WHERE commodity = :c AND market = s.m AND variety = s.v
                   ORDER BY date DESC LIMIT 1) p ON TRUE
               LEFT JOIN LATERAL (
                   SELECT target_date, p10, p90 FROM forecasts
                   WHERE commodity = :c AND market = s.m AND variety = s.v AND horizon = 7
                   ORDER BY forecast_date DESC LIMIT 1) f ON TRUE""",
            c=commodity,
            markets=[s.market for s in series],
            varieties=[s.variety for s in series],
        )
        by_market = {s.market: s for s in series}
        return [
            PriceRow(by_market[r["market"]], r["date"], r["price"], r["target"], r["p10"], r["p90"])
            for r in rows
        ]

    def latest_move(self, crop: str) -> dict[str, str]:
        """market -> predicted class of the newest shadow prediction (move alerts only)."""
        rows = self._all(
            self.ro,
            """SELECT DISTINCT ON (market) market, pred_class FROM shadow_predictions
               WHERE commodity = :c ORDER BY market, forecast_date DESC""",
            c=crop,
        )
        return {r["market"]: r["pred_class"] for r in rows}

    def move_verdict(self, crop: str) -> str | None:
        verdict = self._scalar(
            self.ro,
            """SELECT decision FROM promotion_log WHERE model_name = 'cropcast-move-h7'
               AND scope = :c ORDER BY decided_at DESC, id DESC LIMIT 1""",
            c=crop,
        )
        return None if verdict is None else str(verdict)

    # --- users -------------------------------------------------------------------------------

    def touch(self, chat_id: int) -> str:
        """Register / re-activate the chat, bump last_active, return its language."""
        lang = self._scalar(
            self.rw,
            """INSERT INTO subscribers (chat_id) VALUES (:id)
               ON CONFLICT (chat_id) DO UPDATE SET last_active = now(), active = TRUE
               RETURNING lang""",
            write=True,
            id=chat_id,
        )
        return str(lang or "ml")

    def set_lang(self, chat_id: int, lang: str) -> None:
        self._exec("UPDATE subscribers SET lang = :l WHERE chat_id = :id", l=lang, id=chat_id)

    def deactivate(self, chat_id: int) -> None:
        self._exec("UPDATE subscribers SET active = FALSE WHERE chat_id = :id", id=chat_id)

    def delete_user(self, chat_id: int) -> None:
        """/deletedata: every row about this chat (alerts cascade with the subscriber)."""
        with self.rw.begin() as conn:
            conn.execute(text("DELETE FROM bot_events WHERE chat_id = :id"), {"id": chat_id})
            conn.execute(text("DELETE FROM subscribers WHERE chat_id = :id"), {"id": chat_id})

    def digest_crops(self, chat_id: int) -> list[str]:
        crops = self._scalar(
            self.rw, "SELECT digest_crops FROM subscribers WHERE chat_id = :id", id=chat_id
        )
        return list(crops or [])

    def subscribe(self, chat_id: int, crop: str) -> bool:
        n = self._exec(
            """UPDATE subscribers SET digest_crops = array_append(digest_crops, :c)
               WHERE chat_id = :id AND NOT (:c = ANY(digest_crops))""",
            c=crop,
            id=chat_id,
        )
        return n > 0

    def unsubscribe(self, chat_id: int, crop: str) -> bool:
        n = self._exec(
            """UPDATE subscribers SET digest_crops = array_remove(digest_crops, :c)
               WHERE chat_id = :id AND :c = ANY(digest_crops)""",
            c=crop,
            id=chat_id,
        )
        return n > 0

    # --- alerts ------------------------------------------------------------------------------

    def alerts(self, chat_id: int) -> list[Alert]:
        rows = self._all(
            self.rw,
            """SELECT id, commodity, market, variety, direction,
                      threshold_rs_kg::float8 AS threshold, state
               FROM user_alerts WHERE chat_id = :id AND active ORDER BY id""",
            id=chat_id,
        )
        return [Alert(**r) for r in rows]

    def create_alert(
        self,
        chat_id: int,
        s: Served,
        direction: str,
        threshold: float,
        state: str,
        price_date: date | None,
        price_rs_kg: float | None,
    ) -> int:
        new_id = self._scalar(
            self.rw,
            """INSERT INTO user_alerts (chat_id, commodity, market, variety, direction,
                   threshold_rs_kg, state, last_price_date, last_price_rs_kg)
               VALUES (:id, :c, :m, :v, :d, :t, :s, :pd, :pp) RETURNING id""",
            write=True,
            id=chat_id,
            c=s.commodity,
            m=s.market,
            v=s.variety,
            d=direction,
            t=threshold,
            s=state,
            pd=price_date,
            pp=price_rs_kg,
        )
        return int(new_id)

    def stop_alert(self, chat_id: int, alert_id: int) -> bool:
        return (
            self._exec(
                "UPDATE user_alerts SET active = FALSE WHERE id = :a AND chat_id = :id AND active",
                a=alert_id,
                id=chat_id,
            )
            > 0
        )

    def stop_all(self, chat_id: int) -> int:
        return self._exec(
            "UPDATE user_alerts SET active = FALSE WHERE chat_id = :id AND active", id=chat_id
        )

    # --- webhook bookkeeping ---------------------------------------------------------------

    def claim_update(self, update_id: int) -> bool:
        """True the first time an update_id is seen (Telegram retries on slow answers)."""
        got = self._scalar(
            self.rw,
            """INSERT INTO telegram_updates (update_id) VALUES (:u)
               ON CONFLICT (update_id) DO NOTHING RETURNING update_id""",
            write=True,
            u=update_id,
        )
        return got is not None

    def event(self, chat_id: int | None, event: str, detail: str | None = None) -> None:
        self._exec(
            "INSERT INTO bot_events (chat_id, event, detail) VALUES (:id, :e, :d)",
            id=chat_id,
            e=event,
            d=detail,
        )

    # --- helpers -----------------------------------------------------------------------------

    @staticmethod
    def _all(engine: Engine, sql: str, **params: Any) -> list[dict[str, Any]]:
        with engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(text(sql), params)]

    @staticmethod
    def _scalar(engine: Engine, sql: str, write: bool = False, **params: Any) -> Any:
        if write:
            with engine.begin() as conn:
                return conn.execute(text(sql), params).scalar()
        with engine.connect() as conn:
            return conn.execute(text(sql), params).scalar()

    def _exec(self, sql: str, **params: Any) -> int:
        with self.rw.begin() as conn:
            return int(conn.execute(text(sql), params).rowcount)
