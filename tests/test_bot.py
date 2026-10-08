"""Telegram bot (Phase 5): names, webhook auth + dedupe, commands, alert state machine,
blocked users, move-alert guard, /deletedata, rate limit, digests."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import Engine, text

from cropcast.api import main as api
from cropcast.bot import alerts as bot_alerts
from cropcast.bot import names, telegram
from cropcast.bot.handlers import Bot, RateLimiter, initial_state, threshold_steps
from cropcast.bot.moves import move_alerts_allowed
from cropcast.bot.names import markets_of
from cropcast.bot.store import Store
from cropcast.config import settings

TODAY = date(2026, 10, 8)
CHAT = 1001


# --- pure: names, thresholds, state machine, guard, rate limit ---------------------------------


@pytest.mark.parametrize(
    ("typed", "crop"),
    [
        ("banana", "banana"),
        ("Nendran", "banana"),
        ("നേന്ത്രൻ", "banana"),
        ("നേന്ത്രന്‍", "banana"),  # old chillu
        ("ഏത്തക്ക", "banana"),
        ("bananna", "banana"),  # typo -> fuzzy
        ("കപ്പ", "tapioca"),
        ("kappa", "tapioca"),
        ("Black Pepper", "pepper"),
        ("കുരുമുളക്", "pepper"),
        ("thenga", "coconut"),
        ("റബ്ബർ", "rubber"),
        ("rice", None),
    ],
)
def test_crop_aliases_both_languages(typed: str, crop: str | None) -> None:
    assert names.match_crop(typed) == crop


def test_market_aliases_and_split() -> None:
    s = names.match_market("banana", "കായംകുളം")
    assert s is not None and (s.market, s.variety) == ("Kayamkulam", "Nendran")
    assert names.match_market("tapioca", "perumbavur") is not None  # spelling variant
    assert names.match_market("banana", "Kannur") is None  # not a banana market
    assert names.split_crop(["black", "pepper", "kannur"]) == ("pepper", ["kannur"])
    assert names.match_direction("കൂടിയാൽ") == "above" and names.match_direction("below") == "below"
    assert names.parse_amount("₹62.5/kg") == 62.5


def test_every_alias_market_is_served() -> None:
    served = {s.market for s in names.served()}
    assert set(names.aliases()["markets"]) == served


def test_threshold_steps_and_initial_state() -> None:
    assert threshold_steps(60.0) == [("a", 63.0), ("a", 66.0), ("b", 57.0), ("b", 54.0)]
    assert initial_state("above", 60, 65) == "triggered"  # already above: wait for a crossing
    assert initial_state("above", 70, 65) == "armed"
    assert initial_state("below", 60, 55) == "triggered"


def test_crossing_state_machine_fires_once_per_crossing() -> None:
    state, fired = "armed", []
    for price in [58, 61, 63, 62, 59, 58, 61, 70]:  # above 60: crosses at 61 and again at 61
        state, fire = bot_alerts.step(state, "above", 60, price)
        fired.append(fire)
    assert fired == [False, True, False, False, False, False, True, False]
    state, fired = "armed", []
    for price in [50, 39, 38, 41, 40]:  # below 40: fires at 39, re-arms at 41, fires at 40
        state, fire = bot_alerts.step(state, "below", 40, price)
        fired.append(fire)
    assert fired == [False, True, False, False, True]


class _Verdicts:
    def __init__(self, verdict: str | None) -> None:
        self.verdict = verdict

    def move_verdict(self, crop: str) -> str | None:
        return self.verdict


def test_move_alerts_guard() -> None:
    assert not move_alerts_allowed(_Verdicts("pass"), "coconut", {"coconut": False})
    assert not move_alerts_allowed(_Verdicts("fail"), "coconut", {"coconut": True})
    assert not move_alerts_allowed(_Verdicts(None), "coconut", {"coconut": True})
    assert not move_alerts_allowed(_Verdicts("insufficient data"), "coconut", {"coconut": True})
    assert move_alerts_allowed(_Verdicts("pass"), "coconut", {"coconut": True})


def test_shipped_config_has_move_alerts_off() -> None:
    from cropcast.bot.moves import move_flags

    assert move_flags() and not any(move_flags().values())


def test_rate_limiter_warns_once_per_window() -> None:
    now = [0.0]
    rl = RateLimiter(3, clock=lambda: now[0])
    assert [rl.allow(1) for _ in range(5)] == [
        (True, False),
        (True, False),
        (True, False),
        (False, True),
        (False, False),
    ]
    assert rl.allow(2) == (True, False)  # per chat
    now[0] = 61.0
    assert rl.allow(1) == (True, False)


def test_telegram_client_retries_429_and_flags_403(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    monkeypatch.setattr(settings, "telegram_bot_token", SecretStr("t"))
    replies = iter(
        [
            httpx.Response(429, json={"ok": False, "parameters": {"retry_after": 2}}),
            httpx.Response(200, json={"ok": True, "result": {}}),
        ]
    )
    monkeypatch.setattr(telegram.httpx, "post", lambda *a, **k: next(replies))
    slept: list[float] = []
    assert telegram.call("sendMessage", {}, sleep=slept.append)["ok"] and slept == [2.0]
    monkeypatch.setattr(
        telegram.httpx, "post", lambda *a, **k: httpx.Response(403, json={"ok": False})
    )
    with pytest.raises(telegram.Blocked):
        telegram.call("sendMessage", {})


# --- DB-backed ---------------------------------------------------------------------------------


class Outbox:
    def __init__(self) -> None:
        self.messages: list[tuple[int, str, Any]] = []
        self.blocked: set[int] = set()

    def __call__(self, chat_id: int, text_: str, keyboard: Any = None) -> None:
        if chat_id in self.blocked:
            raise telegram.Blocked("blocked")
        self.messages.append((chat_id, text_, keyboard))

    @property
    def texts(self) -> list[str]:
        return [m[1] for m in self.messages]


def _seed(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE prices_clean, forecasts, promotion_log, shadow_predictions, "
                "subscribers, user_alerts, telegram_updates, bot_events CASCADE"
            )
        )
        conn.execute(
            text(
                "INSERT INTO prices_clean (commodity, market, variety, date, modal_price, "
                "n_reports, sources) VALUES ('banana', 'Kayamkulam', 'Nendran', :d, :p, 1, 't')"
            ),
            [{"d": TODAY - timedelta(days=i), "p": 6000 + 10 * i} for i in range(10)],
        )
        conn.execute(  # a stale market: last price 6 days ago
            text(
                "INSERT INTO prices_clean (commodity, market, variety, date, modal_price, "
                "n_reports, sources) VALUES ('banana', 'Parassala', 'Nendran', :d, 5500, 1, 't')"
            ),
            {"d": TODAY - timedelta(days=6)},
        )
        conn.execute(
            text(
                "INSERT INTO forecasts (forecast_date, target_date, horizon, market, commodity, "
                "variety, p10, p50, p90, last_value, model_version) VALUES "
                "(:d, :t, 7, 'Kayamkulam', 'banana', 'Nendran', 5600, 6000, 6500, 6000, '1')"
            ),
            {"d": TODAY, "t": TODAY + timedelta(days=7)},
        )


@pytest.fixture
def bot(engine: Engine) -> Iterator[tuple[Bot, Outbox, Store]]:
    _seed(engine)
    out = Outbox()
    store = Store(engine, engine)
    yield Bot(store, send=out, today=lambda: TODAY, limiter=RateLimiter(20)), out, store


def _msg(text_: str, update_id: int, chat_id: int = CHAT) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "message": {"chat": {"id": chat_id, "type": "private"}, "text": text_},
    }


def _cb(data: str, update_id: int, chat_id: int = CHAT) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": "x",
            "data": data,
            "message": {"chat": {"id": chat_id, "type": "private"}},
        },
    }


@pytest.mark.db
def test_start_defaults_to_malayalam_and_lang_switch(bot: tuple[Bot, Outbox, Store]) -> None:
    b, out, _ = bot
    b.handle(_msg("/start", 1))
    assert "നമസ്കാരം" in out.texts[-1] and out.messages[-1][2]  # language keyboard
    b.handle(_cb("lang:en", 2))
    assert out.texts[-1].startswith("Language: English")
    b.handle(_msg("/help", 3))
    assert out.texts[-1].startswith("Commands:")


@pytest.mark.db
def test_price_ml_and_en_with_footer_and_staleness(bot: tuple[Bot, Outbox, Store]) -> None:
    b, out, _ = bot
    b.handle(_msg("/price നേന്ത്രൻ കായംകുളം", 1))
    reply = out.texts[-1]
    assert "₹60/കിലോ" in reply and f"₹56{chr(0x2013)}65" in reply
    assert reply.endswith("ഉറവിടം: Agmarknet · ഉറപ്പല്ല / not a guarantee")
    b.handle(_msg("/lang en", 2))
    b.handle(_msg("/price banana parassala", 3))
    assert "No new price in this market for 6 days" in out.texts[-1]
    b.handle(_msg("nendran", 4))  # plain text works too
    assert "Kayamkulam: ₹60" in out.texts[-1] and "old price" in out.texts[-1]
    b.handle(_msg("/price rice", 5))
    assert 'I don\'t know "rice"' in out.texts[-1] and out.messages[-1][2]


@pytest.mark.db
def test_markets_lists_only_fresh(bot: tuple[Bot, Outbox, Store]) -> None:
    b, out, _ = bot
    b.handle(_msg("/lang en", 1))
    b.handle(_msg("/markets banana", 2))
    assert "Kayamkulam" in out.texts[-1] and "Parassala" not in out.texts[-1]


@pytest.mark.db
def test_update_id_dedupe(bot: tuple[Bot, Outbox, Store]) -> None:
    b, out, _ = bot
    b.handle(_msg("/help", 77))
    b.handle(_msg("/help", 77))  # Telegram retry of the same update
    assert len(out.messages) == 1


@pytest.mark.db
def test_alert_command_keyboard_flow_and_limit(bot: tuple[Bot, Outbox, Store]) -> None:
    b, out, store = bot
    b.handle(_msg("/lang en", 1))
    b.handle(_msg("/alert nendran kayamkulam above 65", 2))
    assert "Alert #" in out.texts[-1] and "above ₹65/kg" in out.texts[-1]
    b.handle(_msg("/alert banana kayamkulam below 70", 3))  # already below: waits
    assert "already at ₹60/kg" in out.texts[-1]
    # keyboard flow: crop -> market -> threshold buttons -> alert
    idx = [s.market for s in markets_of("banana")].index("Kayamkulam")
    b.handle(_cb(f"am:banana:{idx}", 4))
    buttons = [btn["callback_data"] for row in out.messages[-1][2] for btn in row]
    assert buttons[0] == f"at:banana:{idx}:a:63"
    for i, data in enumerate(buttons):
        b.handle(_cb(data, 10 + i))
    assert len(store.alerts(CHAT)) == 5
    assert "Maximum 5 alerts" in out.texts[-1]
    b.handle(_msg("/alerts", 20))
    assert out.texts[-1].count("#") == 5
    first = store.alerts(CHAT)[0].id
    b.handle(_msg(f"/stop {first}", 21))
    assert len(store.alerts(CHAT)) == 4
    b.handle(_msg("/stopall", 22))
    assert store.alerts(CHAT) == [] and "(4)" in out.texts[-1]


@pytest.mark.db
def test_daily_delivery_fires_once_rearms_and_never_repeats(
    bot: tuple[Bot, Outbox, Store], engine: Engine
) -> None:
    b, _, _ = bot
    b.handle(_msg("/alert banana kayamkulam above 62", 1))  # now 60 -> armed
    sent = Outbox()

    def add_price(d: date, rs_q: float) -> None:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO prices_clean (commodity, market, variety, date, modal_price, "
                    "n_reports, sources) VALUES ('banana','Kayamkulam','Nendran',:d,:p,1,'t')"
                ),
                {"d": d, "p": rs_q},
            )

    def run(d: date) -> bot_alerts.DeliveryResult:
        return bot_alerts.run_user_alerts(engine, d, dry_run=False, send=sent, with_digests=False)

    assert run(TODAY).triggered == 0  # no new observation since the alert was created
    add_price(TODAY + timedelta(days=1), 6300)
    assert run(TODAY + timedelta(days=1)).triggered == 1
    assert "₹63/kg" in sent.texts[-1] or "₹63/കിലോ" in sent.texts[-1]
    assert run(TODAY + timedelta(days=1)).triggered == 0  # re-run: same observation, no repeat
    add_price(TODAY + timedelta(days=2), 6400)
    assert run(TODAY + timedelta(days=2)).triggered == 0  # still above: no repeat
    add_price(TODAY + timedelta(days=3), 6000)
    assert run(TODAY + timedelta(days=3)).rearmed == 1
    add_price(TODAY + timedelta(days=4), 6250)
    assert run(TODAY + timedelta(days=4)).triggered == 1
    assert len(sent.messages) == 2


@pytest.mark.db
def test_blocked_user_is_deactivated(bot: tuple[Bot, Outbox, Store], engine: Engine) -> None:
    b, _, _ = bot
    b.handle(_msg("/subscribe banana", 1))
    sent = Outbox()
    sent.blocked.add(CHAT)
    res = bot_alerts.run_user_alerts(engine, TODAY, dry_run=False, send=sent)
    assert res.blocked == 1 and res.digests == 0
    with engine.connect() as conn:
        assert conn.execute(text("SELECT active FROM subscribers")).scalar() is False
    # coming back re-activates; a 'kicked' my_chat_member update deactivates again
    b.handle(_msg("/help", 2))
    b.handle(
        {
            "update_id": 3,
            "my_chat_member": {
                "chat": {"id": CHAT, "type": "private"},
                "new_chat_member": {"status": "kicked"},
            },
        }
    )
    with engine.connect() as conn:
        assert conn.execute(text("SELECT active FROM subscribers")).scalar() is False


@pytest.mark.db
def test_digest_once_per_day_with_footer(bot: tuple[Bot, Outbox, Store], engine: Engine) -> None:
    b, out, _ = bot
    b.handle(_msg("/subscribe കപ്പ", 1))
    b.handle(_msg("/subscribe നേന്ത്രൻ", 2))
    assert "✅" in out.texts[-1]
    sent = Outbox()
    assert bot_alerts.run_user_alerts(engine, TODAY, False, send=sent).digests == 1
    assert bot_alerts.run_user_alerts(engine, TODAY, False, send=sent).digests == 0
    digest = sent.texts[0]
    assert "കായംകുളം: ₹60" in digest and digest.count("ഉറവിടം: Agmarknet") == 1
    b.handle(_msg("/unsubscribe banana", 3))
    b.handle(_msg("/unsubscribe tapioca", 4))
    nxt = TODAY + timedelta(days=1)
    assert bot_alerts.run_user_alerts(engine, nxt, False, send=sent).digests == 0


@pytest.mark.db
def test_deletedata_wipes_everything(bot: tuple[Bot, Outbox, Store], engine: Engine) -> None:
    b, _, _ = bot
    b.handle(_msg("/subscribe banana", 1))
    b.handle(_msg("/alert banana kayamkulam above 70", 2))
    b.handle(_msg("/deletedata", 3))
    with engine.connect() as conn:
        for table in ("subscribers", "user_alerts", "bot_events"):
            n = conn.execute(text(f"SELECT count(*) FROM {table} WHERE chat_id = {CHAT}")).scalar()
            assert n == 0, table


@pytest.mark.db
def test_rate_limit_20_per_minute(bot: tuple[Bot, Outbox, Store]) -> None:
    b, out, _ = bot
    for i in range(22):
        b.handle(_msg("/help", 100 + i))
    assert len(out.messages) == 21  # 20 answers + one "too many" warning
    assert "ഒരു മിനിറ്റ്" in out.texts[-1]


@pytest.mark.db
def test_bot_usage_view_and_weekly_summary(bot: tuple[Bot, Outbox, Store], engine: Engine) -> None:
    b, _, _ = bot
    b.handle(_msg("/price banana", 1))
    b.handle(_msg("/alert banana kayamkulam above 70", 2))
    b.handle(_msg("/help", 3, chat_id=2002))
    with engine.connect() as conn:
        u = conn.execute(text("SELECT * FROM bot_usage")).mappings().one()
    assert (u["users_active"], u["active_7d"], u["alerts_active"]) == (2, 2, 1)
    summary = bot_alerts.weekly_summary(engine)
    assert "Bot users: 2 active" in summary and "Neon:" in summary


# --- webhook -----------------------------------------------------------------------------------


@pytest.fixture
def hook(
    bot: tuple[Bot, Outbox, Store], monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, Outbox, str]]:
    b, out, _ = bot
    monkeypatch.setattr(settings, "telegram_webhook_secret", SecretStr("s3cret-token"))
    monkeypatch.setattr(api, "_bot", b)
    api.limiter.reset()
    path = telegram.webhook_path_token()
    assert path is not None
    yield TestClient(api.app), out, path
    monkeypatch.setattr(api, "_bot", None)


@pytest.mark.db
def test_webhook_auth(hook: tuple[TestClient, Outbox, str]) -> None:
    client, out, path = hook
    body = _msg("/help", 500)
    assert client.post("/telegram/webhook/wrong", json=body).status_code == 404
    r = client.post(
        f"/telegram/webhook/{path}", json=body, headers={"X-Telegram-Bot-Api-Secret-Token": "x"}
    )
    assert r.status_code == 403 and not out.messages
    assert client.post(f"/telegram/webhook/{path}", json=body).status_code == 403
    ok = {"X-Telegram-Bot-Api-Secret-Token": "s3cret-token"}
    r = client.post(f"/telegram/webhook/{path}", json=body, headers=ok)
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert len(out.messages) == 1  # processed after the response (background task)
    client.post(f"/telegram/webhook/{path}", json=body, headers=ok)  # retry: deduped
    assert len(out.messages) == 1


@pytest.mark.db
def test_webhook_is_not_ip_rate_limited(hook: tuple[TestClient, Outbox, str]) -> None:
    client, _, path = hook
    ok = {"X-Telegram-Bot-Api-Secret-Token": "s3cret-token"}
    codes = {
        client.post(
            f"/telegram/webhook/{path}", json=_msg("/help", 1000 + i, chat_id=3000 + i), headers=ok
        ).status_code
        for i in range(70)  # > the API's 60/min/IP
    }
    assert codes == {200}
