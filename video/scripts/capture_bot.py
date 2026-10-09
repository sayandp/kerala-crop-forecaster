"""Capture REAL bot replies for the demo video (no faked text).

Runs the bot's own handler / rendering code against live Neon (read-only role for prices,
cropcast_bot for its own rows) with Telegram sending stubbed and a fake chat id, then deletes
every row it created. Also renders today's real channel post (notify's own gather/render, no
send). Output: video/capture/bot/conversation.json

    uv run python video/scripts/capture_bot.py
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from sqlalchemy import create_engine, text

from cropcast.alerts.channel import gather, postable, render_post
from cropcast.api.queries import sqlalchemy_url
from cropcast.bot import render
from cropcast.bot.handlers import Bot
from cropcast.bot.names import crop_name, market_name, markets_of
from cropcast.bot.store import Store, today_ist
from cropcast.config import PROJECT_ROOT, settings

OUT = PROJECT_ROOT / "video" / "capture" / "bot"
CHAT = 990_000_000_001  # fake private chat
UPDATE0 = 9_900_000_000_000


def env_url(key: str) -> str:
    env = (PROJECT_ROOT / ".env").read_text(encoding="utf-8")
    m = re.search(rf"^{key}=(.*)$", env, re.M)
    assert m, f"{key} missing in .env"
    return sqlalchemy_url(m.group(1))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ro, rw = create_engine(env_url("DATABASE_URL_RO")), create_engine(env_url("DATABASE_URL_BOT"))
    store = Store(ro, rw)
    log: list[dict[str, Any]] = []
    sent: list[tuple[str, Any]] = []

    def send(chat_id: int, body: str, keyboard: Any = None) -> None:
        sent.append((body, keyboard))

    bot = Bot(store, send=send)
    uid = [UPDATE0]

    def step(user: str, update: dict[str, Any], tapped: str | None = None) -> None:
        uid[0] += 1
        n = len(sent)
        bot.handle({"update_id": uid[0], **update})
        log.append({"from": "user", "text": user, "tap": tapped})
        for body, kb in sent[n:]:
            buttons = [[b["text"] for b in row] for row in kb] if kb else None
            log.append({"from": "bot", "text": body, "buttons": buttons})

    def msg(t: str) -> None:
        step(t, {"message": {"chat": {"id": CHAT, "type": "private"}, "text": t}})

    def tap(label: str, data: str) -> None:
        step(
            label,
            {
                "callback_query": {
                    "id": "demo",
                    "data": data,
                    "message": {"chat": {"id": CHAT, "type": "private"}},
                }
            },
            tapped=label,
        )

    try:
        msg("/start")
        msg("/price നേന്ത്രൻ")
        msg("/alert നേന്ത്രൻ")
        idx = [s.market for s in markets_of("banana")].index("Kayamkulam")
        tap(market_name("Kayamkulam", "ml"), f"am:banana:{idx}")
        msg("/lang en")
        msg("/price tomato")
        msg("/alert banana kayamkulam above 55")
        msg("/alerts")

        # Alert message FORMAT with the real latest price: a level the real price is above.
        row = next(r for r in store.prices("banana") if r.series.market == "Kayamkulam")
        assert row.price is not None and row.date is not None
        level = int(row.price // 100) - 1
        alert_text = render.with_footer(
            "en",
            "\n".join(
                [
                    render.t(
                        "en",
                        "alert_fired_above",
                        crop=crop_name("banana", "en"),
                        market=market_name("Kayamkulam", "en"),
                        price=render.kg(row.price),
                        date=render.day(row.date, "en"),
                        amount=level,
                    ),
                    render.t("en", "alert_fired_tail", id=1),
                ]
            ),
        )

        # Today's channel post, rendered by notify's own code (not sent).
        run_date = today_ist()
        rows = postable(gather(ro, run_date), run_date)
        asof = max(rows["as_of"]) if len(rows) else run_date
        post = render_post(rows, asof if isinstance(asof, date) else run_date)

        out = {
            "captured_at": str(today_ist()),
            "bot": "@keralacropprices_bot",
            "conversation": log,
            "alert_example": {
                "text": alert_text,
                "note": f"format of a fired alert, real latest price ({row.date}); level {level}",
            },
            "channel_post": post,
        }
        (OUT / "conversation.json").write_text(
            json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps({k: (len(v) if isinstance(v, list) else "ok") for k, v in out.items()}))
    finally:
        # Remove every trace of the fake chat.
        owner = create_engine(settings.database_url)
        with owner.begin() as conn:
            conn.execute(text("DELETE FROM bot_events WHERE chat_id = :c"), {"c": CHAT})
            conn.execute(text("DELETE FROM subscribers WHERE chat_id = :c"), {"c": CHAT})
            conn.execute(text("DELETE FROM telegram_updates WHERE update_id > :u"), {"u": UPDATE0})
            left = conn.execute(
                text(
                    "SELECT (SELECT count(*) FROM subscribers WHERE chat_id = :c) + "
                    "(SELECT count(*) FROM user_alerts WHERE chat_id = :c) + "
                    "(SELECT count(*) FROM bot_events WHERE chat_id = :c)"
                ),
                {"c": CHAT},
            ).scalar_one()
        print("cleanup: rows left for the fake chat =", left)


if __name__ == "__main__":
    main()
