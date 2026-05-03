"""MQTT subscribe loop — in-memory state, atomic write, alert dispatch."""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from yarbo import YarboTelemetry

from yarbod.state import YarboState, STALE_THRESHOLD_SECONDS

if TYPE_CHECKING:
    from yarbod.alerts import AlertDispatcher
    from yarbod.client import YarboClient


def telemetry_to_state(t: YarboTelemetry) -> YarboState:
    now = datetime.now(timezone.utc)
    return YarboState(
        schema_version=1,
        last_updated=now,
        robot={
            "serial": t.sn or "",
            "model": "",
            "firmware": "",
            "head_attached": str(t.head_type) if t.head_type is not None else None,
        },
        activity={
            "state": t.state or "unknown",
            "battery_pct": t.battery,
            "charging": bool(t.charging_status) if t.charging_status is not None else False,
            "current_plan": t.plan_id,
            "progress_pct": None,
        },
        location={
            "lat": t.latitude,
            "lon": t.longitude,
            "rtk": t.rtk_status,
            "satellites": None,
        },
        errors={
            "active": t.error_code if t.error_code else None,
            "history": [],
        },
        rain_sensor=bool(t.rain_sensor_data) if t.rain_sensor_data else False,
        broker_health={
            "connected": True,
            "last_msg_at": now.isoformat(),
            "reconnects_today": 0,
        },
    )


class YarboMonitor:
    def __init__(
        self,
        client: "YarboClient",
        state_path: Path,
        state_last_path: Path,
        alerts: "AlertDispatcher",
    ) -> None:
        self._client = client
        self._state_path = state_path
        self._state_last_path = state_last_path
        self._alerts = alerts
        self._current_state: YarboState | None = None
        self._prev_activity_state: str | None = None

    def _update_and_write(self, t: YarboTelemetry) -> None:
        new_state = telemetry_to_state(t)
        self._check_transition_alerts(new_state)
        self._current_state = new_state
        self._write_state_atomic()

    def _write_state_atomic(self) -> None:
        if self._current_state is None:
            return
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=self._state_path.parent, suffix=".tmp"
        )
        try:
            with open(tmp_fd, "w") as f:
                json.dump(self._current_state.to_dict(), f, indent=2)
            os.replace(tmp_path, self._state_path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def snapshot_to_disk(self) -> None:
        if self._current_state is None:
            return
        self._state_last_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_last_path.write_text(
            json.dumps(self._current_state.to_dict(), indent=2)
        )

    def _check_transition_alerts(self, new_state: YarboState) -> None:
        new_activity = new_state.activity.get("state")
        serial = new_state.robot.get("serial", "unknown")

        if self._prev_activity_state is not None and new_activity != self._prev_activity_state:
            if new_activity == "stuck":
                self._alerts.dispatch(
                    f"stuck:{serial}",
                    cooldown_seconds=900,
                    message=f"Yarbo {serial} is stuck (was {self._prev_activity_state})",
                )
            if new_state.errors.get("active") is not None:
                code = new_state.errors["active"]
                self._alerts.dispatch(
                    f"error_code:{serial}:{code}",
                    cooldown_seconds=3600,
                    message=f"Yarbo {serial} error code {code}",
                )

        self._prev_activity_state = new_activity

    async def run(self) -> None:
        async for telemetry in self._client.watch_telemetry():
            self._update_and_write(telemetry)
