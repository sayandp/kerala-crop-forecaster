"""Register / show / remove the Telegram webhook of the bot (Render API) and its command menu.

    uv run python scripts/set_webhook.py --generate-secret   # once: TELEGRAM_WEBHOOK_SECRET -> .env
    uv run python scripts/set_webhook.py --set --commands    # point Telegram at the Render API
    uv run python scripts/set_webhook.py --info              # webhook status (pending, last error)
    uv run python scripts/set_webhook.py --delete

The secret travels only in .env / Render env / Telegram's secret_token; it is never printed.
"""

from __future__ import annotations

import argparse
import re
import secrets
import sys

from cropcast.bot.telegram import call, webhook_path_token
from cropcast.config import settings
from cropcast.roles import ENV_PATH

ALLOWED_UPDATES = ["message", "callback_query", "my_chat_member"]
COMMANDS = {
    "en": [
        ("price", "Latest price + 7-day range: /price banana kayamkulam"),
        ("markets", "Markets with fresh prices: /markets pepper"),
        ("alert", "Alert when a price crosses a level"),
        ("alerts", "Your alerts"),
        ("stop", "Stop an alert: /stop 3"),
        ("stopall", "Stop all alerts"),
        ("subscribe", "Daily price message for a crop"),
        ("unsubscribe", "Stop the daily message"),
        ("lang", "Language: /lang en or /lang ml"),
        ("help", "All commands"),
        ("about", "How it works, honest limits"),
        ("deletedata", "Delete all your data"),
        ("start", "Start"),
    ],
    "ml": [
        ("price", "വിലയും 7 ദിവസത്തെ പരിധിയും: /price നേന്ത്രൻ"),
        ("markets", "പുതിയ വിലയുള്ള വിപണികൾ"),
        ("alert", "വില ഒരു തുക കടന്നാൽ അറിയിപ്പ്"),
        ("alerts", "നിങ്ങളുടെ അറിയിപ്പുകൾ"),
        ("stop", "ഒരു അറിയിപ്പ് നിർത്താൻ: /stop 3"),
        ("stopall", "എല്ലാ അറിയിപ്പുകളും നിർത്താൻ"),
        ("subscribe", "ദിവസേന വില സന്ദേശം"),
        ("unsubscribe", "ദിവസേന സന്ദേശം നിർത്താൻ"),
        ("lang", "ഭാഷ: /lang ml അല്ലെങ്കിൽ /lang en"),
        ("help", "എല്ലാ കമാൻഡുകളും"),
        ("about", "ഇത് എങ്ങനെ പ്രവർത്തിക്കുന്നു"),
        ("deletedata", "നിങ്ങളുടെ വിവരങ്ങൾ മായ്ക്കാൻ"),
        ("start", "തുടങ്ങാൻ"),
    ],
}


def generate_secret() -> None:
    env = ENV_PATH.read_text(encoding="utf-8") if ENV_PATH.exists() else ""
    if re.search(r"^TELEGRAM_WEBHOOK_SECRET=\S+", env, re.M):
        print("TELEGRAM_WEBHOOK_SECRET already in .env (unchanged)")
        return
    ENV_PATH.write_text(
        env.rstrip() + f"\nTELEGRAM_WEBHOOK_SECRET={secrets.token_urlsafe(32)}\n", encoding="utf-8"
    )
    print("TELEGRAM_WEBHOOK_SECRET written to .env (copy it to Render; it is not printed)")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--generate-secret", action="store_true")
    g.add_argument("--set", action="store_true")
    g.add_argument("--info", action="store_true")
    g.add_argument("--delete", action="store_true")
    p.add_argument("--commands", action="store_true", help="also publish the command menu")
    p.add_argument("--drop-pending", action="store_true")
    args = p.parse_args(argv)

    if args.generate_secret:
        generate_secret()
        return 0
    if args.set:
        token = webhook_path_token()
        if token is None or settings.telegram_webhook_secret is None:
            sys.exit("TELEGRAM_WEBHOOK_SECRET not set: run --generate-secret first")
        url = f"{settings.api_base_url.rstrip('/')}/telegram/webhook/{token}"
        call(
            "setWebhook",
            {
                "url": url,
                "secret_token": settings.telegram_webhook_secret.get_secret_value(),
                "allowed_updates": ALLOWED_UPDATES,
                "drop_pending_updates": args.drop_pending,
                "max_connections": 10,
            },
        )
        print(f"webhook set: {settings.api_base_url}/telegram/webhook/<hash of secret>")
    if args.delete:
        call("deleteWebhook", {"drop_pending_updates": args.drop_pending})
        print("webhook deleted")
    if args.commands:
        for lang, cmds in COMMANDS.items():
            payload: dict[str, object] = {
                "commands": [{"command": c, "description": d} for c, d in cmds]
            }
            if lang != "en":
                payload["language_code"] = lang
            call("setMyCommands", payload)
        print("command menu set (en default, ml for Malayalam clients)")
    if args.info or args.set:
        info = call("getWebhookInfo", {})["result"]
        url = str(info.get("url", ""))
        print(
            {
                "url": re.sub(r"/telegram/webhook/\w+", "/telegram/webhook/<hash>", url),
                "pending_update_count": info.get("pending_update_count"),
                "last_error_date": info.get("last_error_date"),
                "last_error_message": info.get("last_error_message"),
                "allowed_updates": info.get("allowed_updates"),
            }
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
