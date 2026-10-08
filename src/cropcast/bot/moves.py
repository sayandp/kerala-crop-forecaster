"""Guard for model move alerts ("likely to rise > 3 % this week").

A crop's move alerts are on only if BOTH:
  1. `move_alerts_enabled.<crop>: true` in config/channel.yaml (a human flips it; default off), and
  2. the newest live verdict for that crop in promotion_log (model cropcast-move-h7, written by the
     pre-registered weekly `promotion_check`) is "pass".
A flag set for a crop without a "pass" verdict is refused (and logged), never honoured.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol

import yaml

from cropcast.config import settings

log = logging.getLogger(__name__)

CHANNEL_CONFIG = settings.config_dir / "channel.yaml"


class VerdictSource(Protocol):
    def move_verdict(self, crop: str) -> str | None: ...


def move_flags(path: Path = CHANNEL_CONFIG) -> dict[str, bool]:
    raw = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("move_alerts_enabled", {})
    if not isinstance(raw, dict):  # a bare boolean is ambiguous: treat as all off
        return {}
    return {str(k): v is True for k, v in raw.items()}


def move_alerts_allowed(
    source: VerdictSource, crop: str, flags: dict[str, bool] | None = None
) -> bool:
    flags = move_flags() if flags is None else flags
    if not flags.get(crop, False):
        return False
    verdict = source.move_verdict(crop)
    if verdict != "pass":
        log.warning(
            "move alerts flag ignored: no live 'pass' verdict",
            extra={"crop": crop, "verdict": verdict},
        )
        return False
    return True
