"""Dashboard revalidation is best effort: skipped when unconfigured, a warning on failure."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from cropcast.alerts import revalidate
from cropcast.config import settings


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "vercel_revalidate_url", "https://example.test/api/revalidate")
    monkeypatch.setattr(settings, "revalidate_secret", SecretStr("s3cret"))
    monkeypatch.setattr(revalidate._post.retry, "sleep", lambda _: None)  # type: ignore[attr-defined]


def test_skipped_without_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "vercel_revalidate_url", None)
    assert revalidate.revalidate_dashboard() == (
        "skipped",
        "VERCEL_REVALIDATE_URL / REVALIDATE_SECRET not set",
    )


def test_ok_sends_secret_header(configured: None, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_post(url: str, headers: dict[str, str], timeout: float) -> httpx.Response:
        seen.update(url=url, headers=headers)
        return httpx.Response(200, request=httpx.Request("POST", url))

    monkeypatch.setattr(revalidate.httpx, "post", fake_post)
    assert revalidate.revalidate_dashboard() == ("ok", None)
    assert seen["headers"] == {"x-revalidate-secret": "s3cret"}


def test_failure_is_a_warning_after_retries(
    configured: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    def fake_post(url: str, headers: dict[str, str], timeout: float) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401, request=httpx.Request("POST", url))

    monkeypatch.setattr(revalidate.httpx, "post", fake_post)
    assert revalidate.revalidate_dashboard() == ("warning", "HTTPStatusError")
    assert calls == 3


def test_dry_run_does_not_call(configured: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(revalidate.httpx, "post", lambda *a, **k: pytest.fail("called"))
    assert revalidate.revalidate_dashboard(dry_run=True) == ("skipped", "dry run")
