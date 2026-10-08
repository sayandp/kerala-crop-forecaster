"""Minimal Telegram Bot API client (plain httpx; no bot framework).

* 429 Too Many Requests -> sleep `retry_after` (capped) and retry, up to 3 times.
* 403 Forbidden (the user blocked the bot / chat gone) -> `Blocked`, so callers deactivate.
* The URL contains the bot token: it is never logged.
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

from cropcast.config import settings

log = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/{method}"
MAX_RETRY_AFTER_S = 30.0
MAX_LEN = 4000


class Blocked(Exception):
    """The chat can no longer be messaged (403: blocked by user, deactivated, kicked)."""


class TelegramError(Exception):
    pass


def webhook_path_token() -> str | None:
    """URL path segment of the webhook: a hash of TELEGRAM_WEBHOOK_SECRET (not the secret)."""
    secret = settings.telegram_webhook_secret
    if secret is None:
        return None
    return hashlib.sha256(secret.get_secret_value().encode()).hexdigest()[:32]


def configured() -> bool:
    return settings.telegram_bot_token is not None


def call(
    method: str,
    payload: dict[str, Any],
    *,
    retries: int = 3,
    sleep: Callable[[float], None] = time.sleep,
    timeout: float = 15.0,
) -> dict[str, Any]:
    if settings.telegram_bot_token is None:
        raise TelegramError("TELEGRAM_BOT_TOKEN not set")
    url = API.format(token=settings.telegram_bot_token.get_secret_value(), method=method)
    for attempt in range(retries + 1):
        try:
            resp = httpx.post(url, json=payload, timeout=timeout)
        except httpx.HTTPError as exc:  # network: retry with backoff
            if attempt == retries:
                raise TelegramError(f"{method}: {type(exc).__name__}") from None
            sleep(2.0**attempt)
            continue
        body: dict[str, Any] = resp.json() if resp.content else {}
        if resp.status_code == 429 and attempt < retries:
            wait = float(body.get("parameters", {}).get("retry_after", 1))
            log.warning("telegram 429", extra={"method": method, "retry_after": wait})
            sleep(min(wait, MAX_RETRY_AFTER_S))
            continue
        if resp.status_code == 403:
            raise Blocked(str(body.get("description", "forbidden")))
        if resp.status_code >= 400 or not body.get("ok", False):
            raise TelegramError(f"{method}: {resp.status_code} {body.get('description', '')}")
        return body
    raise TelegramError(f"{method}: retries exhausted")


def send_message(
    chat_id: int | str, text: str, keyboard: list[list[dict[str, str]]] | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text[:MAX_LEN],
        "disable_web_page_preview": True,
    }
    if keyboard:
        payload["reply_markup"] = {"inline_keyboard": keyboard}
    return call("sendMessage", payload)


def answer_callback(callback_id: str) -> None:
    # cosmetic (stops the button spinner); never fatal
    with contextlib.suppress(TelegramError, Blocked):
        call("answerCallbackQuery", {"callback_query_id": callback_id}, retries=0, timeout=5.0)


class Pacer:
    """Keep broadcasts under `per_s` messages per second."""

    def __init__(self, per_s: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.gap = 1.0 / per_s
        self.clock = clock
        self.next_at = 0.0

    def wait(self, sleep: Callable[[float], None] = time.sleep) -> None:
        now = self.clock()
        if now < self.next_at:
            sleep(self.next_at - now)
            now = self.next_at
        self.next_at = now + self.gap
