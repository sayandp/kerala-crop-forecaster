"""Telegram update handling: commands, inline keyboards, per-chat rate limit.

`Bot.handle(update)` runs after the webhook has already answered 200 (FastAPI background task).
Each update is processed at most once (update_id claimed in telegram_updates). Private chats
only. Logged: command / callback names, never message text, names or usernames.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from collections.abc import Callable
from datetime import date
from typing import Any

from cropcast.bot import names, render, telegram
from cropcast.bot.names import CROPS, Served, crop_name, market_name, markets_of
from cropcast.bot.render import kg, t
from cropcast.bot.store import Store, today_ist
from cropcast.config import settings

log = logging.getLogger(__name__)

Keyboard = list[list[dict[str, str]]]
Sender = Callable[[int, str, Keyboard | None], Any]
LANG_KEYBOARD: Keyboard = [
    [{"text": "മലയാളം", "callback_data": "lang:ml"}, {"text": "English", "callback_data": "lang:en"}]
]


class RateLimiter:
    """At most `limit` commands per chat per `window` seconds (in memory: one Render worker)."""

    def __init__(
        self, limit: int, window: float = 60.0, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.limit, self.window, self.clock = limit, window, clock
        self.hits: dict[int, deque[float]] = defaultdict(deque)
        self.warned: dict[int, float] = {}

    def allow(self, chat_id: int) -> tuple[bool, bool]:
        """(allowed, warn): warn once per window when the limit is first exceeded."""
        now = self.clock()
        q = self.hits[chat_id]
        while q and now - q[0] >= self.window:
            q.popleft()
        if len(q) < self.limit:
            q.append(now)
            return True, False
        warn = now - self.warned.get(chat_id, -1e9) >= self.window
        if warn:
            self.warned[chat_id] = now
        return False, warn


def crop_keyboard(lang: str, prefix: str, crops: tuple[str, ...] | list[str] = CROPS) -> Keyboard:
    buttons = [{"text": crop_name(c, lang), "callback_data": f"{prefix}:{c}"} for c in crops]
    return [buttons[i : i + 2] for i in range(0, len(buttons), 2)]


def market_keyboard(lang: str, crop: str, prefix: str) -> Keyboard:
    buttons = [
        {"text": market_name(s.market, lang), "callback_data": f"{prefix}:{crop}:{i}"}
        for i, s in enumerate(markets_of(crop))
    ]
    return [buttons[i : i + 2] for i in range(0, len(buttons), 2)]


def threshold_steps(price_kg: float) -> list[tuple[str, float]]:
    """Suggested alert levels: +/-5 % and +/-10 % of the current price (rounded)."""

    def r(x: float) -> float:
        return float(round(x)) if price_kg >= 20 else round(x * 2) / 2

    return [
        ("a", r(price_kg * 1.05)),
        ("a", r(price_kg * 1.10)),
        ("b", r(price_kg * 0.95)),
        ("b", r(price_kg * 0.90)),
    ]


def initial_state(direction: str, threshold: float, price_kg: float) -> str:
    """A new alert whose condition already holds waits for a crossing back (no instant fire)."""
    holds = price_kg >= threshold if direction == "above" else price_kg <= threshold
    return "triggered" if holds else "armed"


class Bot:
    def __init__(
        self,
        store: Store,
        send: Sender | None = None,
        today: Callable[[], date] = today_ist,
        limiter: RateLimiter | None = None,
    ) -> None:
        self.store = store
        self._send_raw: Sender = send or (lambda c, txt, kb: telegram.send_message(c, txt, kb))
        self.today = today
        self.limiter = limiter or RateLimiter(settings.bot_rate_limit_per_min)

    # --- entry point -------------------------------------------------------------------------

    def handle(self, update: dict[str, Any]) -> None:
        update_id = update.get("update_id")
        if isinstance(update_id, int) and not self.store.claim_update(update_id):
            log.info("duplicate update ignored", extra={"update_id": update_id})
            return
        if "my_chat_member" in update:
            self._chat_member(update["my_chat_member"])
        elif "callback_query" in update:
            self._callback(update["callback_query"])
        elif "message" in update:
            self._message(update["message"])

    def send(self, chat_id: int, text: str, keyboard: Keyboard | None = None) -> None:
        try:
            self._send_raw(chat_id, text, keyboard)
        except telegram.Blocked:
            self.store.deactivate(chat_id)
            self.store.event(chat_id, "blocked")

    # --- update kinds ------------------------------------------------------------------------

    def _chat_member(self, m: dict[str, Any]) -> None:
        chat = m.get("chat", {})
        if chat.get("type") != "private":
            return
        if m.get("new_chat_member", {}).get("status") == "kicked":  # user blocked the bot
            self.store.deactivate(int(chat["id"]))
            self.store.event(int(chat["id"]), "blocked")

    def _gate(self, chat_id: int, lang: str) -> bool:
        ok, warn = self.limiter.allow(chat_id)
        if not ok:
            if warn:
                self.store.event(chat_id, "rate_limited")
                self.send(chat_id, t(lang, "rate_limited"))
            return False
        return True

    def _message(self, msg: dict[str, Any]) -> None:
        chat = msg.get("chat", {})
        text = msg.get("text")
        if chat.get("type") != "private" or not isinstance(text, str) or not text.strip():
            return
        chat_id = int(chat["id"])
        lang = self.store.touch(chat_id)
        if not self._gate(chat_id, lang):
            return
        words = text.strip().split()
        if words[0].startswith("/"):
            cmd = words[0][1:].split("@", 1)[0].lower()
            args = words[1:]
        else:  # plain text: "nendran", "കപ്പ പെരുമ്പാവൂർ" -> price
            cmd, args = "price", words
            if names.split_crop(args)[0] is None:
                cmd = "unknown"
        handler = COMMANDS.get(cmd)
        self.store.event(chat_id, "command", cmd if handler else "unknown")
        if handler is None:
            self.send(chat_id, t(lang, "unknown_command"))
            return
        handler(self, chat_id, lang, args)

    def _callback(self, cq: dict[str, Any]) -> None:
        telegram.answer_callback(str(cq.get("id", ""))) if telegram.configured() else None
        msg = cq.get("message") or {}
        chat = msg.get("chat", {})
        data = str(cq.get("data", ""))
        if chat.get("type") != "private" or not data:
            return
        chat_id = int(chat["id"])
        lang = self.store.touch(chat_id)
        if not self._gate(chat_id, lang):
            return
        parts = data.split(":")
        self.store.event(chat_id, "callback", parts[0])
        kind, rest = parts[0], parts[1:]
        if kind == "lang" and rest and rest[0] in ("ml", "en"):
            self.store.set_lang(chat_id, rest[0])
            self.send(chat_id, t(rest[0], "lang_set") + "\n\n" + t(rest[0], "help"))
            return
        crop = rest[0] if rest and rest[0] in CROPS else None
        if crop is None:
            return
        series = markets_of(crop)
        idx = int(rest[1]) if len(rest) > 1 and rest[1].isdigit() else None
        s = series[idx] if idx is not None and idx < len(series) else None
        if kind == "p":
            self._price(chat_id, lang, crop, None)
        elif kind == "m":
            self._markets(chat_id, lang, crop)
        elif kind == "a":
            self.send(
                chat_id,
                t(lang, "pick_market", crop=crop_name(crop, lang)),
                market_keyboard(lang, crop, "am"),
            )
        elif kind == "am" and s:
            self._threshold_menu(chat_id, lang, s)
        elif kind == "at" and s and len(rest) == 4 and rest[2] in ("a", "b"):
            amount = names.parse_amount(rest[3])
            if amount:
                self._create_alert(chat_id, lang, s, "above" if rest[2] == "a" else "below", amount)
        elif kind == "s":
            self._subscribe(chat_id, lang, crop)
        elif kind == "u":
            self._unsubscribe(chat_id, lang, crop)

    # --- commands ----------------------------------------------------------------------------

    def cmd_start(self, chat_id: int, lang: str, args: list[str]) -> None:
        self.send(chat_id, t(lang, "start"), LANG_KEYBOARD)

    def cmd_help(self, chat_id: int, lang: str, args: list[str]) -> None:
        self.send(chat_id, t(lang, "help"))

    def cmd_about(self, chat_id: int, lang: str, args: list[str]) -> None:
        self.send(chat_id, t(lang, "about"))

    def cmd_lang(self, chat_id: int, lang: str, args: list[str]) -> None:
        choice = args[0].lower() if args else ""
        choice = {"മലയാളം": "ml", "malayalam": "ml", "english": "en"}.get(choice, choice)
        if choice in ("ml", "en"):
            self.store.set_lang(chat_id, choice)
            self.send(chat_id, t(choice, "lang_set"))
        else:
            self.send(chat_id, "Language / ഭാഷ:", LANG_KEYBOARD)

    def _crop_or_ask(
        self, chat_id: int, lang: str, args: list[str], prefix: str
    ) -> tuple[str | None, list[str]]:
        if not args:
            self.send(chat_id, t(lang, "pick_crop"), crop_keyboard(lang, prefix))
            return None, []
        crop, rest = names.split_crop(args)
        if crop is None:
            self.send(
                chat_id, t(lang, "unknown_crop", text=" ".join(args)), crop_keyboard(lang, prefix)
            )
        return crop, rest

    def _market_or_explain(
        self, chat_id: int, lang: str, crop: str, words: list[str]
    ) -> Served | None:
        s = names.match_market(crop, " ".join(words))
        if s is None:
            available = ", ".join(market_name(x.market, lang) for x in markets_of(crop))
            self.send(
                chat_id,
                t(
                    lang,
                    "unknown_market",
                    crop=crop_name(crop, lang),
                    text=" ".join(words),
                    markets=available,
                ),
            )
        return s

    def cmd_price(self, chat_id: int, lang: str, args: list[str]) -> None:
        crop, rest = self._crop_or_ask(chat_id, lang, args, "p")
        if crop is None:
            return
        if not rest:
            self._price(chat_id, lang, crop, None)
            return
        s = self._market_or_explain(chat_id, lang, crop, rest)
        if s is not None:
            self._price(chat_id, lang, crop, s)

    def _price(self, chat_id: int, lang: str, crop: str, s: Served | None) -> None:
        rows = self.store.prices(crop)
        today = self.today()
        if s is None:
            self.send(chat_id, render.price_list(lang, crop, rows, today))
            return
        row = next(r for r in rows if r.series == s)
        self.send(chat_id, render.price_detail(lang, row, today))

    def cmd_markets(self, chat_id: int, lang: str, args: list[str]) -> None:
        crop, _ = self._crop_or_ask(chat_id, lang, args, "m")
        if crop is not None:
            self._markets(chat_id, lang, crop)

    def _markets(self, chat_id: int, lang: str, crop: str) -> None:
        self.send(chat_id, render.markets_text(lang, crop, self.store.prices(crop), self.today()))

    def cmd_alert(self, chat_id: int, lang: str, args: list[str]) -> None:
        crop, rest = self._crop_or_ask(chat_id, lang, args, "a")
        if crop is None:
            return
        if not rest:
            self.send(
                chat_id,
                t(lang, "pick_market", crop=crop_name(crop, lang)),
                market_keyboard(lang, crop, "am"),
            )
            return
        # <market words> <direction> <amount>; ">60" / "<60" also accepted
        direction, amount, market_words = None, None, rest
        for i, w in enumerate(rest):
            d = names.match_direction(w) or {">": "above", "<": "below"}.get(w[:1])
            if d:
                direction, market_words = d, rest[:i]
                amount = names.parse_amount(" ".join(rest[i:]))
                break
        s = self._market_or_explain(chat_id, lang, crop, market_words) if market_words else None
        if s is None:
            if not market_words:
                self.send(chat_id, t(lang, "alert_usage"))
            return
        if direction is None or amount is None:
            self._threshold_menu(chat_id, lang, s)
            return
        self._create_alert(chat_id, lang, s, direction, amount)

    def _threshold_menu(self, chat_id: int, lang: str, s: Served) -> None:
        row = next((r for r in self.store.prices(s.commodity) if r.series == s), None)
        if row is None or row.price is None or row.date is None:
            self.send(
                chat_id,
                t(
                    lang,
                    "no_price",
                    crop=crop_name(s.commodity, lang),
                    market=market_name(s.market, lang),
                ),
            )
            return
        idx = markets_of(s.commodity).index(s)
        price_kg = row.price / 100
        buttons = [
            {
                "text": t(lang, "btn_above" if d == "a" else "btn_below", amount=render.amount(v)),
                "callback_data": f"at:{s.commodity}:{idx}:{d}:{render.amount(v)}",
            }
            for d, v in threshold_steps(price_kg)
        ]
        self.send(
            chat_id,
            t(
                lang,
                "pick_threshold",
                crop=crop_name(s.commodity, lang),
                market=market_name(s.market, lang),
                price=kg(row.price),
                date=render.day(row.date, lang),
            ),
            [buttons[:2], buttons[2:]],
        )

    def _create_alert(
        self, chat_id: int, lang: str, s: Served, direction: str, amount: float
    ) -> None:
        if len(self.store.alerts(chat_id)) >= settings.bot_max_alerts:
            self.send(chat_id, t(lang, "alert_limit"))
            return
        crop, market = crop_name(s.commodity, lang), market_name(s.market, lang)
        row = next((r for r in self.store.prices(s.commodity) if r.series == s), None)
        if row is None or row.price is None:
            self.send(chat_id, t(lang, "no_price", crop=crop, market=market))
            return
        price_kg = row.price / 100
        state = initial_state(direction, amount, price_kg)
        alert_id = self.store.create_alert(chat_id, s, direction, amount, state, row.date, price_kg)
        self.store.event(chat_id, "alert_created", s.commodity)
        condition = t(lang, f"condition_{direction}", amount=render.amount(amount))
        key = "alert_created" if state == "armed" else "alert_created_already"
        self.send(
            chat_id,
            t(
                lang,
                key,
                id=alert_id,
                crop=crop,
                market=market,
                condition=condition,
                price=kg(row.price),
            ),
        )

    def cmd_alerts(self, chat_id: int, lang: str, args: list[str]) -> None:
        alerts = self.store.alerts(chat_id)
        if not alerts:
            self.send(chat_id, t(lang, "alerts_none"))
            return
        lines = [t(lang, "alerts_title")]
        for a in alerts:
            short = ("▲ ₹" if a.direction == "above" else "▼ ₹") + render.amount(a.threshold)
            state = t(lang, "alerts_state_triggered") if a.state == "triggered" else ""
            lines.append(
                t(
                    lang,
                    "alerts_line",
                    id=a.id,
                    crop=crop_name(a.commodity, lang),
                    market=market_name(a.market, lang),
                    short=short,
                    state=state,
                )
            )
        self.send(chat_id, "\n".join(lines))

    def cmd_stop(self, chat_id: int, lang: str, args: list[str]) -> None:
        raw = args[0].lstrip("#") if args else ""
        if not raw.isdigit():
            self.send(chat_id, t(lang, "stop_usage"))
            return
        key = "alert_stopped" if self.store.stop_alert(chat_id, int(raw)) else "alert_not_found"
        self.send(chat_id, t(lang, key, id=int(raw)))

    def cmd_stopall(self, chat_id: int, lang: str, args: list[str]) -> None:
        self.send(chat_id, t(lang, "alerts_all_stopped", n=self.store.stop_all(chat_id)))

    def cmd_subscribe(self, chat_id: int, lang: str, args: list[str]) -> None:
        crop, _ = self._crop_or_ask(chat_id, lang, args, "s")
        if crop is not None:
            self._subscribe(chat_id, lang, crop)

    def _subscribe(self, chat_id: int, lang: str, crop: str) -> None:
        key = "subscribed" if self.store.subscribe(chat_id, crop) else "already_subscribed"
        self.send(chat_id, t(lang, key, crop=crop_name(crop, lang), crop_key=crop))

    def cmd_unsubscribe(self, chat_id: int, lang: str, args: list[str]) -> None:
        if not args:
            subscribed = self.store.digest_crops(chat_id)
            if not subscribed:
                self.send(chat_id, t(lang, "not_subscribed", crop="—"))
            else:
                self.send(chat_id, t(lang, "pick_crop"), crop_keyboard(lang, "u", subscribed))
            return
        crop, _ = self._crop_or_ask(chat_id, lang, args, "u")
        if crop is not None:
            self._unsubscribe(chat_id, lang, crop)

    def _unsubscribe(self, chat_id: int, lang: str, crop: str) -> None:
        key = "unsubscribed" if self.store.unsubscribe(chat_id, crop) else "not_subscribed"
        self.send(chat_id, t(lang, key, crop=crop_name(crop, lang)))

    def cmd_deletedata(self, chat_id: int, lang: str, args: list[str]) -> None:
        self.store.delete_user(chat_id)
        self.send(chat_id, t(lang, "deleted"))


COMMANDS: dict[str, Callable[[Bot, int, str, list[str]], None]] = {
    "start": Bot.cmd_start,
    "help": Bot.cmd_help,
    "about": Bot.cmd_about,
    "lang": Bot.cmd_lang,
    "price": Bot.cmd_price,
    "markets": Bot.cmd_markets,
    "alert": Bot.cmd_alert,
    "alerts": Bot.cmd_alerts,
    "stop": Bot.cmd_stop,
    "stopall": Bot.cmd_stopall,
    "subscribe": Bot.cmd_subscribe,
    "unsubscribe": Bot.cmd_unsubscribe,
    "deletedata": Bot.cmd_deletedata,
}
