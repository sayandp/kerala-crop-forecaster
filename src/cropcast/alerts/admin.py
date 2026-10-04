"""Best-effort admin pings via the Telegram Bot API (plain HTTP; no bot framework)."""

from __future__ import annotations

import logging

import httpx

from cropcast.config import settings

log = logging.getLogger(__name__)

TELEGRAM_MAX_LEN = 4000


def send_admin_message(text: str) -> bool:
    """Send `text` to TELEGRAM_ADMIN_CHAT_ID. Never raises; returns True if delivered."""
    token = settings.telegram_bot_token
    chat_id = settings.telegram_admin_chat_id
    if token is None or not chat_id:
        log.info("telegram not configured; admin message not sent")
        return False
    url = f"https://api.telegram.org/bot{token.get_secret_value()}/sendMessage"
    try:
        resp = httpx.post(
            url,
            json={
                "chat_id": chat_id,
                "text": text[:TELEGRAM_MAX_LEN],
                "disable_web_page_preview": True,
            },
            timeout=15.0,
        )
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        # Do not log the URL: it contains the bot token.
        log.error("telegram admin message failed", extra={"error": type(exc).__name__})
        return False
    return True
