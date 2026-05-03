"""Tests for monitor.py — state update, atomic write, alert dispatch."""
import asyncio
import json
import os
from datetime import timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from yarbo import YarboTelemetry
from yarbod.monitor import YarboMonitor, telemetry_to_state


# --- telemetry_to_state mapping ---

def test_telemetry_to_state_maps_basic_fields():
    t = YarboTelemetry(
        sn="YA-001",
        battery=67,
        state="working",
        charging_status=0,
        plan_id="front-yard",
        latitude=41.1,
        longitude=-96.1,
        rtk_status="fix",
        error_code=None,
        rain_sensor_data=0,
    )
    state = telemetry_to_state(t)
    assert state.robot["serial"] == "YA-001"
    assert state.activity["battery_pct"] == 67
    assert state.activity["state"] == "working"
    assert state.activity["charging"] is False
    assert state.activity["current_plan"] == "front-yard"
    assert state.location["lat"] == 41.1
    assert state.location["rtk"] == "fix"
    assert state.errors["active"] is None
    assert state.rain_sensor is False


def test_telemetry_to_state_charging_when_status_nonzero():
    t = YarboTelemetry(sn="YA-001", charging_status=1)
    state = telemetry_to_state(t)
    assert state.activity["charging"] is True


def test_telemetry_to_state_error_code_present():
    t = YarboTelemetry(sn="YA-001", error_code=7)
    state = telemetry_to_state(t)
    assert state.errors["active"] == 7


def test_telemetry_to_state_rain_sensor_nonzero():
    t = YarboTelemetry(sn="YA-001", rain_sensor_data=42)
    state = telemetry_to_state(t)
    assert state.rain_sensor is True


# --- atomic write ---

def test_atomic_write_creates_state_json(tmp_path):
    state_path = tmp_path / "state.json"
    monitor = YarboMonitor(
        client=MagicMock(),
        state_path=state_path,
        state_last_path=tmp_path / "state.json.last",
        alerts=MagicMock(),
    )
    t = YarboTelemetry(sn="YA-001", battery=50, state="idle")
    monitor._update_and_write(t)
    assert state_path.exists()
    data = json.loads(state_path.read_text())
    assert data["robot"]["serial"] == "YA-001"


def test_atomic_write_uses_temp_rename(tmp_path):
    state_path = tmp_path / "state.json"
    monitor = YarboMonitor(
        client=MagicMock(),
        state_path=state_path,
        state_last_path=tmp_path / "state.json.last",
        alerts=MagicMock(),
    )
    monitor._update_and_write(YarboTelemetry(sn="YA-001", battery=50, state="idle"))
    with patch("yarbod.monitor.os.replace") as mock_replace:
        monitor._write_state_atomic()
    mock_replace.assert_called_once()


# --- snapshot_to_disk ---

def test_snapshot_to_disk_writes_last_file(tmp_path):
    state_path = tmp_path / "state.json"
    last_path = tmp_path / "state.json.last"
    monitor = YarboMonitor(
        client=MagicMock(),
        state_path=state_path,
        state_last_path=last_path,
        alerts=MagicMock(),
    )
    t = YarboTelemetry(sn="YA-001", battery=80, state="working")
    monitor._update_and_write(t)
    monitor.snapshot_to_disk()
    assert last_path.exists()
    data = json.loads(last_path.read_text())
    assert data["robot"]["serial"] == "YA-001"


# --- alert dispatch on state transitions ---

def test_stuck_transition_dispatches_alert(tmp_path):
    alerts = MagicMock()
    monitor = YarboMonitor(
        client=MagicMock(),
        state_path=tmp_path / "state.json",
        state_last_path=tmp_path / "state.json.last",
        alerts=alerts,
    )
    # Establish initial state: working
    monitor._update_and_write(YarboTelemetry(sn="YA-001", state="working"))
    alerts.reset_mock()
    # Transition to stuck
    monitor._update_and_write(YarboTelemetry(sn="YA-001", state="stuck"))
    alerts.dispatch.assert_called_once()
    key = alerts.dispatch.call_args[0][0]
    assert key.startswith("stuck:")


def test_no_alert_when_state_unchanged(tmp_path):
    alerts = MagicMock()
    monitor = YarboMonitor(
        client=MagicMock(),
        state_path=tmp_path / "state.json",
        state_last_path=tmp_path / "state.json.last",
        alerts=alerts,
    )
    monitor._update_and_write(YarboTelemetry(sn="YA-001", state="working"))
    alerts.reset_mock()
    monitor._update_and_write(YarboTelemetry(sn="YA-001", state="working"))
    alerts.dispatch.assert_not_called()


# --- async run loop ---

@pytest.mark.asyncio
async def test_run_processes_telemetry_stream(tmp_path):
    telemetry_items = [
        YarboTelemetry(sn="YA-001", battery=80, state="working"),
        YarboTelemetry(sn="YA-001", battery=70, state="working"),
    ]

    async def fake_watch():
        for t in telemetry_items:
            yield t

    mock_client = MagicMock()
    mock_client.watch_telemetry.return_value = fake_watch()

    monitor = YarboMonitor(
        client=mock_client,
        state_path=tmp_path / "state.json",
        state_last_path=tmp_path / "state.json.last",
        alerts=MagicMock(),
    )
    await monitor.run()
    data = json.loads((tmp_path / "state.json").read_text())
    assert data["activity"]["battery_pct"] == 70
