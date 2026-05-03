"""Tests for capture.py — JSONL append, rotation, retention, disk-low."""
import gzip
import json
import os
import shutil
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from yarbod.capture import CaptureWriter, DISK_LOW_BYTES, DISK_KEEP_GZ_DAYS, DISK_DELETE_DAYS


# --- basic append ---

def test_append_creates_file_on_first_write(tmp_path):
    w = CaptureWriter(capture_dir=tmp_path, alerts=MagicMock())
    w.append({"ts": "2026-04-30T22:00:00Z", "topic": "t/status", "payload": {"battery": 67}})
    files = list(tmp_path.glob("*.jsonl"))
    assert len(files) == 1


def test_append_writes_valid_jsonl(tmp_path):
    w = CaptureWriter(capture_dir=tmp_path, alerts=MagicMock())
    payload = {"ts": "2026-04-30T22:00:00Z", "topic": "t/status", "payload": {"battery": 67}}
    w.append(payload)
    line = list(tmp_path.glob("*.jsonl"))[0].read_text().strip()
    parsed = json.loads(line)
    assert parsed["payload"]["battery"] == 67


def test_append_multiple_lines_each_valid_json(tmp_path):
    w = CaptureWriter(capture_dir=tmp_path, alerts=MagicMock())
    for i in range(5):
        w.append({"ts": f"2026-04-30T22:0{i}:00Z", "topic": "t", "payload": {"i": i}})
    lines = list(tmp_path.glob("*.jsonl"))[0].read_text().strip().splitlines()
    assert len(lines) == 5
    for i, line in enumerate(lines):
        assert json.loads(line)["payload"]["i"] == i


# --- rotation ---

def test_rotate_produces_gz_and_removes_jsonl(tmp_path):
    w = CaptureWriter(capture_dir=tmp_path, alerts=MagicMock())
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    jsonl_path = tmp_path / f"{yesterday}.jsonl"
    jsonl_path.write_text('{"ts":"2026-04-29T01:00:00Z","topic":"t","payload":{}}\n')

    w.rotate(target_date=date.fromisoformat(yesterday))

    gz_path = tmp_path / f"{yesterday}.jsonl.gz"
    assert gz_path.exists()
    assert not jsonl_path.exists()


def test_rotate_gz_is_readable_and_correct(tmp_path):
    w = CaptureWriter(capture_dir=tmp_path, alerts=MagicMock())
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    original = '{"ts":"2026-04-29T01:00:00Z","topic":"t","payload":{"x":1}}\n'
    (tmp_path / f"{yesterday}.jsonl").write_text(original)

    w.rotate(target_date=date.fromisoformat(yesterday))

    gz_path = tmp_path / f"{yesterday}.jsonl.gz"
    with gzip.open(gz_path, "rt") as f:
        content = f.read()
    assert json.loads(content.strip())["payload"]["x"] == 1


def test_rotate_is_atomic_no_partial_gz_on_failure(tmp_path):
    w = CaptureWriter(capture_dir=tmp_path, alerts=MagicMock())
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    (tmp_path / f"{yesterday}.jsonl").write_text("line\n")

    with patch("yarbod.capture.os.replace", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            w.rotate(target_date=date.fromisoformat(yesterday))

    tmp_files = list(tmp_path.glob("*.tmp"))
    assert len(tmp_files) == 0  # tmp cleaned up on failure


# --- retention sweep ---

def test_retention_keeps_recent_gz(tmp_path):
    w = CaptureWriter(capture_dir=tmp_path, alerts=MagicMock())
    recent = (date.today() - timedelta(days=10)).isoformat()
    gz = tmp_path / f"{recent}.jsonl.gz"
    gz.write_bytes(b"fake")

    w.sweep_retention()
    assert gz.exists()


def test_retention_deletes_old_gz_beyond_keep_days(tmp_path):
    w = CaptureWriter(capture_dir=tmp_path, alerts=MagicMock())
    old = (date.today() - timedelta(days=DISK_DELETE_DAYS + 5)).isoformat()
    gz = tmp_path / f"{old}.jsonl.gz"
    gz.write_bytes(b"fake")

    w.sweep_retention()
    assert not gz.exists()


def test_retention_keeps_gz_within_keep_days(tmp_path):
    w = CaptureWriter(capture_dir=tmp_path, alerts=MagicMock())
    edge = (date.today() - timedelta(days=DISK_KEEP_GZ_DAYS - 1)).isoformat()
    gz = tmp_path / f"{edge}.jsonl.gz"
    gz.write_bytes(b"fake")

    w.sweep_retention()
    assert gz.exists()


# --- disk-low guard ---

def test_disk_low_fires_alert_and_skips_write(tmp_path):
    alerts = MagicMock()
    w = CaptureWriter(capture_dir=tmp_path, alerts=alerts)

    with patch("yarbod.capture.shutil.disk_usage") as mock_du:
        mock_du.return_value = MagicMock(free=DISK_LOW_BYTES - 1)
        w.append({"ts": "2026-04-30T22:00:00Z", "topic": "t", "payload": {}})

    alerts.dispatch.assert_called_once()
    assert not any(tmp_path.glob("*.jsonl"))


def test_disk_low_constants():
    assert DISK_LOW_BYTES == 1 * 1024 ** 3   # 1 GB
    assert DISK_KEEP_GZ_DAYS == 30
    assert DISK_DELETE_DAYS == 365
