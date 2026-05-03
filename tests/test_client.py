"""Tests for client.py — thin python-yarbo wrapper."""
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

from yarbod.client import YarboClient


def _mock_api():
    """Return a MagicMock shaped like YarboLocalClient."""
    mock = MagicMock()
    mock.connect = MagicMock()
    mock.disconnect = MagicMock()
    mock.publish_command = MagicMock()
    mock.watch_telemetry = MagicMock()
    return mock


# --- connect / disconnect ---

def test_connect_calls_underlying_library():
    with patch("yarbod.client.YarboLocalClient") as MockAPI:
        MockAPI.return_value = _mock_api()
        client = YarboClient(host="10.50.0.182", port=1883)
        client.connect()
        MockAPI.return_value.connect.assert_called_once()


def test_disconnect_calls_underlying_library():
    with patch("yarbod.client.YarboLocalClient") as MockAPI:
        MockAPI.return_value = _mock_api()
        client = YarboClient(host="10.50.0.182", port=1883)
        client.connect()
        client.disconnect()
        MockAPI.return_value.disconnect.assert_called_once()


# --- watch_telemetry delegation ---

def test_watch_telemetry_delegates_to_api():
    with patch("yarbod.client.YarboLocalClient") as MockAPI:
        mock_api = _mock_api()
        MockAPI.return_value = mock_api
        sentinel = object()
        mock_api.watch_telemetry.return_value = sentinel
        client = YarboClient(host="10.50.0.182", port=1883)
        result = client.watch_telemetry()
        mock_api.watch_telemetry.assert_called_once()
        assert result is sentinel


# --- send_command ---

def test_send_command_passes_cmd_and_params():
    with patch("yarbod.client.YarboLocalClient") as MockAPI:
        mock_api = _mock_api()
        MockAPI.return_value = mock_api
        client = YarboClient(host="10.50.0.182", port=1883)
        client.connect()
        client.send_command("start_plan", {"plan_id": "front-yard-zone-a"})
        mock_api.publish_command.assert_called_once_with(
            "start_plan", {"plan_id": "front-yard-zone-a"}
        )


def test_send_command_defaults_empty_params():
    with patch("yarbod.client.YarboLocalClient") as MockAPI:
        mock_api = _mock_api()
        MockAPI.return_value = mock_api
        client = YarboClient(host="10.50.0.182", port=1883)
        client.connect()
        client.send_command("stop")
        mock_api.publish_command.assert_called_once_with("stop", {})


# --- connection error propagates ---

def test_connect_propagates_exception():
    with patch("yarbod.client.YarboLocalClient") as MockAPI:
        mock_api = _mock_api()
        mock_api.connect.side_effect = ConnectionError("broker unreachable")
        MockAPI.return_value = mock_api
        client = YarboClient(host="10.50.0.182", port=1883)
        with pytest.raises(ConnectionError, match="broker unreachable"):
            client.connect()


# --- constructor wires host and port ---

def test_constructor_passes_host_and_port_to_library():
    with patch("yarbod.client.YarboLocalClient") as MockAPI:
        YarboClient(host="10.50.0.182", port=1883)
        MockAPI.assert_called_once_with(broker="10.50.0.182", port=1883)
