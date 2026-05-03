"""Tests for alerts.py — cooldown DB, dispatch, transition rate-limit."""
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, settings, strategies as st

from yarbod.alerts import AlertDispatcher, COOLDOWN_PRESETS


# --- helpers ---

def make_dispatcher(tmp_path, egress=None):
    egress = egress or MagicMock()
    return AlertDispatcher(db_path=tmp_path / "cooldown.db", egress_fn=egress), egress


# --- basic dispatch ---

def test_dispatch_fires_first_time(tmp_path):
    d, egress = make_dispatcher(tmp_path)
    fired = d.dispatch("stuck:YA-001", cooldown_seconds=900, message="Robot stuck")
    assert fired is True
    egress.assert_called_once_with("Robot stuck")


def test_dispatch_suppressed_within_cooldown(tmp_path):
    d, egress = make_dispatcher(tmp_path)
    d.dispatch("stuck:YA-001", cooldown_seconds=900, message="Robot stuck")
    fired = d.dispatch("stuck:YA-001", cooldown_seconds=900, message="Robot stuck again")
    assert fired is False
    assert egress.call_count == 1


def test_dispatch_fires_again_after_cooldown_expires(tmp_path):
    d, egress = make_dispatcher(tmp_path)
    d.dispatch("stuck:YA-001", cooldown_seconds=1, message="first")
    time.sleep(1.1)
    fired = d.dispatch("stuck:YA-001", cooldown_seconds=1, message="second")
    assert fired is True
    assert egress.call_count == 2


def test_different_keys_fire_independently(tmp_path):
    d, egress = make_dispatcher(tmp_path)
    d.dispatch("stuck:YA-001", cooldown_seconds=9000, message="stuck")
    d.dispatch("error_code:YA-001:7", cooldown_seconds=9000, message="error")
    assert egress.call_count == 2


def test_dispatch_persists_across_dispatcher_instances(tmp_path):
    db_path = tmp_path / "cooldown.db"
    egress1 = MagicMock()
    d1 = AlertDispatcher(db_path=db_path, egress_fn=egress1)
    d1.dispatch("stuck:YA-001", cooldown_seconds=9000, message="first instance")

    egress2 = MagicMock()
    d2 = AlertDispatcher(db_path=db_path, egress_fn=egress2)
    fired = d2.dispatch("stuck:YA-001", cooldown_seconds=9000, message="second instance")
    assert fired is False
    egress2.assert_not_called()


# --- cooldown presets ---

def test_cooldown_presets_include_required_keys():
    required = {"stuck", "error_code", "low_batt_off_dock", "rain_pause", "broker_offline"}
    assert required.issubset(set(COOLDOWN_PRESETS.keys()))


# --- transition rate-limit (MQTT spoofing defense) ---

def test_transition_rate_limit_allows_infrequent_transitions(tmp_path):
    d, _ = make_dispatcher(tmp_path)
    for _ in range(2):
        assert d.check_transition_rate_limit("YA-001", "working", "stuck") is True


def test_transition_rate_limit_blocks_excessive_transitions(tmp_path):
    d, _ = make_dispatcher(tmp_path)
    for _ in range(3):
        d.check_transition_rate_limit("YA-001", "working", "stuck")
    # 4th within same hour window → blocked
    result = d.check_transition_rate_limit("YA-001", "working", "stuck")
    assert result is False


# --- hypothesis property: cooldown is never breached ---

@given(
    n_calls=st.integers(min_value=2, max_value=20),
    cooldown=st.integers(min_value=60, max_value=3600),
)
@settings(max_examples=50, deadline=5000)
def test_property_cooldown_never_breached(tmp_path_factory, n_calls, cooldown):
    tmp_path = tmp_path_factory.mktemp("hyp")
    egress = MagicMock()
    d = AlertDispatcher(db_path=tmp_path / "cooldown.db", egress_fn=egress)
    for _ in range(n_calls):
        d.dispatch("test:key", cooldown_seconds=cooldown, message="msg")
    assert egress.call_count == 1
