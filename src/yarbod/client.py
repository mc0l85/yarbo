"""Thin wrapper around python-yarbo's YarboLocalClient."""
from __future__ import annotations

from typing import Any, AsyncIterator

from yarbo import YarboLocalClient, YarboTelemetry


class YarboClient:
    """Stable interface over YarboLocalClient for monitor.py."""

    def __init__(self, host: str, port: int = 1883) -> None:
        self._api: YarboLocalClient = YarboLocalClient(broker=host, port=port)

    def connect(self) -> None:
        self._api.connect()

    def disconnect(self) -> None:
        self._api.disconnect()

    def watch_telemetry(self) -> AsyncIterator[YarboTelemetry]:
        return self._api.watch_telemetry()

    def send_command(self, cmd: str, params: dict[str, Any] | None = None) -> None:
        self._api.publish_command(cmd, params or {})
