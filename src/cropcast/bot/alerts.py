"""Daily delivery (pipeline step `user_alerts`): price-threshold alerts and personal digests.

Alerts use REAL prices (prices_clean), never model output, and fire once per crossing:

    armed --(price crosses the level)--> triggered  [message]
    triggered --(price crosses back)--> armed        [silent]

Each alert remembers the last observation it evaluated (last_price_date), so re-running a day
never repeats a message. Sending is paced (<= telegram_send_per_s), 429s are retried with
retry_after, and 403 (user blocked the bot) deactivates the user.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from sqlalchemy import Engine, text

from cropcast.bot import render, telegram
from cropcast.bot.moves import move_alerts_allowed, move_flags
from cropcast.bot.names import crop_name, market_name
from cropcast.bot.render import kg, t
from cropcast.bot.store import Store
from cropcast.config import settings

log = logging.getLogger(__name__)

Send = Callable[[int, str], Any]


def step(state: str, direction: str, threshold: float, price: float) -> tuple[str, bool]:
    """Next state and whether to notify, for one new observation (Rs./kg)."""
    beyond = price >= threshold if direction == "above" else price <= threshold
    if state == "armed" and beyond:
        return "triggered", True
    if state == "triggered" and not beyond:
        return "armed", False
    return state, False


@dataclass
class DeliveryResult:
    evaluated: int = 0
    triggered: int = 0
    rearmed: int = 0
    sent: int = 0
    blocked: int = 0
    failed: int = 0
    digests: int = 0
    pruned_updates: int = 0
    skipped: list[str] = field(default_factory=list)

    def as_metrics(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


class Delivery:
    def __init__(self, engine: Engine, send: Send | None, dry_run: bool) -> None:
        self.engine = engine
        self.store = Store(engine, engine)
        self.dry_run = dry_run
        self.pacer = telegram.Pacer(settings.telegram_send_per_s)
        self.res = DeliveryResult()
        self._send: Send | None = send

    def deliver(self, chat_id: int, text_: str) -> bool:
        """True if delivered (or dry-run). Blocked -> deactivate; other errors -> retry next run."""
        if self.dry_run or self._send is None:
            log.info("bot message (not sent)", extra={"chars": len(text_)})
            return True
        self.pacer.wait()
        try:
            self._send(chat_id, text_)
        except telegram.Blocked:
            self.res.blocked += 1
            self.store.deactivate(chat_id)
            self.store.event(chat_id, "blocked")
            return False
        except telegram.TelegramError as exc:
            self.res.failed += 1
            log.warning("bot send failed", extra={"error": str(exc)[:200]})
            return False
        self.res.sent += 1
        return True

    # --- price alerts ------------------------------------------------------------------------

    def alerts(self) -> None:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text("""
                SELECT a.id, a.chat_id, a.commodity, a.market, a.variety, a.direction,
                       a.threshold_rs_kg::float8 AS threshold, a.state, a.last_price_date,
                       s.lang, p.date AS obs_date, p.modal_price::float8 AS obs_price
                FROM user_alerts a
                JOIN subscribers s ON s.chat_id = a.chat_id AND s.active
                JOIN LATERAL (
                    SELECT date, modal_price FROM prices_clean c
                    WHERE c.commodity = a.commodity AND c.market = a.market
                      AND c.variety = a.variety
                    ORDER BY date DESC LIMIT 1) p ON TRUE
                WHERE a.active
                  AND (a.last_price_date IS NULL OR p.date > a.last_price_date)
                ORDER BY a.id""")
            ).all()
        for r in rows:
            self.res.evaluated += 1
            price_kg = r.obs_price / 100
            new_state, fire = step(r.state, r.direction, r.threshold, price_kg)
            if fire:
                body = "\n".join(
                    [
                        t(
                            r.lang,
                            f"alert_fired_{r.direction}",
                            crop=crop_name(r.commodity, r.lang),
                            market=market_name(r.market, r.lang),
                            price=kg(r.obs_price),
                            date=render.day(r.obs_date, r.lang),
                            amount=render.amount(r.threshold),
                        ),
                        t(r.lang, "alert_fired_tail", id=r.id),
                    ]
                )
                if not self.deliver(r.chat_id, render.with_footer(r.lang, body)):
                    continue  # not delivered: evaluate this observation again next run
                self.res.triggered += 1
                if not self.dry_run:
                    self.store.event(r.chat_id, "alert_triggered", r.commodity)
            elif new_state != r.state:
                self.res.rearmed += 1
            if self.dry_run:
                continue
            with self.engine.begin() as conn:
                conn.execute(
                    text("""
                    UPDATE user_alerts SET state = :s, last_price_date = :d,
                        last_price_rs_kg = :p,
                        n_triggered = n_triggered + CASE WHEN :fire THEN 1 ELSE 0 END,
                        triggered_at = CASE WHEN :fire THEN now() ELSE triggered_at END
                    WHERE id = :id"""),
                    {"s": new_state, "d": r.obs_date, "p": price_kg, "fire": fire, "id": r.id},
                )

    # --- personal digests --------------------------------------------------------------------

    def digests(self, run_date: date) -> None:
        with self.engine.connect() as conn:
            users = conn.execute(
                text("""
                SELECT chat_id, lang, digest_crops FROM subscribers
                WHERE active AND cardinality(digest_crops) > 0
                  AND (last_digest_date IS NULL OR last_digest_date < :d)
                ORDER BY chat_id"""),
                {"d": run_date},
            ).all()
        if not users:
            return
        flags = move_flags()
        crops = sorted({c for u in users for c in u.digest_crops})
        prices = {c: self.store.prices(c) for c in crops}
        moves = {
            c: self.store.latest_move(c) for c in crops if move_alerts_allowed(self.store, c, flags)
        }
        for u in users:
            parts = [t(u.lang, "digest_title", date=render.day(run_date, u.lang))]
            for crop in u.digest_crops:
                if crop not in prices:
                    continue
                block = render.price_list(u.lang, crop, prices[crop], run_date)
                block = block.rsplit("\n\n", 1)[0]  # one footer for the whole digest
                parts.append(block)
                parts += render.move_lines(u.lang, moves.get(crop, {}))
            if self.deliver(u.chat_id, render.with_footer(u.lang, "\n\n".join(parts))):
                self.res.digests += 1
                if not self.dry_run:
                    with self.engine.begin() as conn:
                        conn.execute(
                            text(
                                "UPDATE subscribers SET last_digest_date = :d WHERE chat_id = :id"
                            ),
                            {"d": run_date, "id": u.chat_id},
                        )
                    self.store.event(u.chat_id, "digest_sent")

    def prune(self) -> None:
        if self.dry_run:
            return
        with self.engine.begin() as conn:
            self.res.pruned_updates = int(
                conn.execute(
                    text(
                        "DELETE FROM telegram_updates WHERE received_at < now() - interval '7 days'"
                    )
                ).rowcount
            )


def run_user_alerts(
    engine: Engine,
    run_date: date,
    dry_run: bool,
    send: Send | None = None,
    with_digests: bool = True,
) -> DeliveryResult:
    if send is None and telegram.configured():
        send = lambda chat_id, body: telegram.send_message(chat_id, body)  # noqa: E731
    d = Delivery(engine, send, dry_run)
    if send is None and not dry_run:
        d.res.skipped.append("TELEGRAM_BOT_TOKEN not set: messages logged, not sent")
    d.alerts()
    if with_digests:
        d.digests(run_date)
    else:
        d.res.skipped.append("digests: no new prices ingested today")
    d.prune()
    return d.res


def weekly_summary(engine: Engine) -> str:
    """Sunday admin summary: channel, bot, alerts, pipeline health, Neon size."""
    with engine.connect() as conn:
        members = conn.execute(
            text("SELECT member_count FROM channel_stats ORDER BY date DESC LIMIT 1")
        ).scalar()
        usage = conn.execute(text("SELECT * FROM bot_usage")).mappings().one()
        triggered_7d = conn.execute(
            text(
                "SELECT count(*) FROM bot_events WHERE event = 'alert_triggered' "
                "AND at > now() - interval '7 days'"
            )
        ).scalar_one()
        runs = conn.execute(
            text(
                "SELECT status, count(*) FROM pipeline_runs "
                "WHERE started_at > now() - interval '7 days' GROUP BY status"
            )
        ).all()
        size = conn.execute(text("SELECT pg_database_size(current_database())")).scalar_one()
    by_status = {s: n for s, n in runs}
    return "\n".join(
        [
            "cropcast weekly summary",
            f"Channel members: {members if members is not None else '-'}",
            f"Bot users: {usage['users_active']} active · {usage['active_7d']} used in 7 d · "
            f"{usage['active_30d']} in 30 d · {usage['digest_users']} with a daily digest",
            f"Alerts: {usage['alerts_active']} active · {triggered_7d} triggered in 7 d · "
            f"{usage['alerts_created_30d']} created in 30 d",
            f"Pipeline (7 d): {by_status.get('success', 0)} ok · "
            f"{by_status.get('failed', 0)} failed",
            f"Neon: {int(size) / 1048576:.1f} MB of 512 MB",
        ]
    )
