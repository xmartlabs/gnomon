"""Clock and period defaults shared by fixture-based tests."""

from datetime import datetime
from typing import ContextManager
from unittest import mock


FIXTURE_NOW = "2026-06-30"


def pinned_now(iso_date: str = FIXTURE_NOW) -> ContextManager:
    value = datetime.fromisoformat(iso_date + "T12:00:00").astimezone()
    return mock.patch("gnomon.cli.period.now_local", return_value=value)


def legacy_all_history() -> ContextManager:
    return mock.patch("gnomon.cli.period.DEFAULT_PERIOD", "all_history")
