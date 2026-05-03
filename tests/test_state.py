"""Tests for state.py — YarboState schema, load paths, stale detection."""
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from yarbod.state import YarboState, load_state, STALE_THRESHOLD_SECONDS


# --- fixtures ---

VALID_STATE = {
    "schema_version": 1,
    "last_updated": "2026-04-30T22:14:03+00:00",
    "robot": {
        "serial": "YA-TEST-001",
        "model": "lawn-mower-20",
        "firmware": "1.2.3",
        "head_attached": "mower",
    },
    "activity": {
        "state": "working",
        "battery_pct": 67,
        "charging": False,
        "current_plan": "front-yard-zone-a",
        "progress_pct": 42,
    },
    "location": {"lat": 41.1, "lon": -96.1, "rtk": "fix", "satellites": 23},
    "errors": {"active": None, "history": []},
    "rain_sensor": False,
    "broker_health": {
        "connected": True,
        "last_msg_at": "2026-04-30T22:14:03+00:00",
        "reconnects_today": 0,
    },
}


# --- schema round-trip ---

def test_yarbostate_roundtrip():
    state = YarboState.from_dict(VALID_STATE)
    assert state.schema_version == 1
    assert state.robot["serial"] == "YA-TEST-001"
    assert state.activity["battery_pct"] == 67
    assert state.location["rtk"] == "fix"
    assert state.errors["active"] is None
    assert state.rain_sensor is False
    assert state.broker_health["connected"] is True


def test_yarbostate_to_dict_roundtrip():
    state = YarboState.from_dict(VALID_STATE)
    d = state.to_dict()
    assert d["schema_version"] == 1
    assert d["robot"]["model"] == "lawn-mower-20"
    assert d["activity"]["state"] == "working"


# --- load paths ---

def test_load_state_reads_live_path(tmp_path):
    live = tmp_path / "state.json"
    live.write_text(json.dumps(VALID_STATE))
    state = load_state(live_path=live, fallback_path=tmp_path / "nonexistent.json")
    assert state is not None
    assert state.robot["serial"] == "YA-TEST-001"


def test_load_state_falls_back_when_live_missing(tmp_path):
    fallback = tmp_path / "state.json.last"
    fallback.write_text(json.dumps(VALID_STATE))
    state = load_state(
        live_path=tmp_path / "nonexistent.json",
        fallback_path=fallback,
    )
    assert state is not None
    assert state.robot["firmware"] == "1.2.3"


def test_load_state_returns_none_when_both_missing(tmp_path):
    state = load_state(
        live_path=tmp_path / "no_live.json",
        fallback_path=tmp_path / "no_fallback.json",
    )
    assert state is None


def test_load_state_prefers_live_over_fallback(tmp_path):
    live_data = {**VALID_STATE, "robot": {**VALID_STATE["robot"], "serial": "LIVE-001"}}
    fallback_data = {**VALID_STATE, "robot": {**VALID_STATE["robot"], "serial": "FALLBACK-001"}}
    live = tmp_path / "state.json"
    fallback = tmp_path / "state.json.last"
    live.write_text(json.dumps(live_data))
    fallback.write_text(json.dumps(fallback_data))
    state = load_state(live_path=live, fallback_path=fallback)
    assert state.robot["serial"] == "LIVE-001"


# --- stale detection ---

def test_stale_prefix_when_older_than_threshold(tmp_path):
    stale_ts = (datetime.now(timezone.utc) - timedelta(seconds=STALE_THRESHOLD_SECONDS + 60)).isoformat()
    stale_data = {**VALID_STATE, "last_updated": stale_ts}
    live = tmp_path / "state.json"
    live.write_text(json.dumps(stale_data))
    state = load_state(live_path=live, fallback_path=tmp_path / "nope.json")
    assert state.is_stale() is True
    assert state.stale_prefix().startswith("[stale ")
    assert "ago]" in state.stale_prefix()


def test_no_stale_prefix_when_fresh(tmp_path):
    fresh_ts = datetime.now(timezone.utc).isoformat()
    fresh_data = {**VALID_STATE, "last_updated": fresh_ts}
    live = tmp_path / "state.json"
    live.write_text(json.dumps(fresh_data))
    state = load_state(live_path=live, fallback_path=tmp_path / "nope.json")
    assert state.is_stale() is False
    assert state.stale_prefix() == ""


def test_stale_threshold_is_300_seconds():
    assert STALE_THRESHOLD_SECONDS == 300


# --- malformed JSON ---

def test_load_state_returns_none_on_invalid_json(tmp_path):
    live = tmp_path / "state.json"
    live.write_text("{not valid json")
    state = load_state(live_path=live, fallback_path=tmp_path / "nope.json")
    assert state is None
