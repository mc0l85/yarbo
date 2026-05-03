"""Tests for cases.py — folder protocol, atomic writes, repair, retention."""
import gzip
import json
import os
import re
import threading
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from yarbod.cases import CaseManager, Case, FRONTMATTER_STATUS_PENDING, FRONTMATTER_STATUS_SENT, FRONTMATTER_STATUS_FAILED


# --- helpers ---

def make_manager(tmp_path, rsync_target=None):
    return CaseManager(
        stage_dir=tmp_path / "cases-stage",
        rsync_target=rsync_target,
        alerts=MagicMock(),
    )


# --- open_case ---

def test_open_case_creates_folder(tmp_path):
    mgr = make_manager(tmp_path)
    case = mgr.open_case("12345", "Subject: error E07")
    assert case.case_dir.exists()


def test_open_case_folder_name_includes_date_and_ticket_id(tmp_path):
    mgr = make_manager(tmp_path)
    case = mgr.open_case("12345", "Subject: error E07")
    today = date.today().isoformat()
    assert today in case.case_dir.name
    assert "12345" in case.case_dir.name


def test_open_case_creates_manifest_json(tmp_path):
    mgr = make_manager(tmp_path)
    case = mgr.open_case("12345", "Subject: error E07")
    manifest = json.loads((case.case_dir / "manifest.json").read_text())
    assert manifest["ticket_id"] == "12345"
    assert manifest["subject"] == "Subject: error E07"
    assert "opened_at" in manifest
    assert manifest["status"] == "open"


def test_open_case_idempotent_returns_existing(tmp_path):
    mgr = make_manager(tmp_path)
    case1 = mgr.open_case("12345", "Subject")
    case2 = mgr.open_case("12345", "Subject")
    assert case1.case_dir == case2.case_dir


# --- write_draft ---

def test_write_draft_creates_file(tmp_path):
    mgr = make_manager(tmp_path)
    case = mgr.open_case("12345", "S")
    path = case.write_draft("Dear Yarbo, please fix this.")
    assert path.exists()


def test_write_draft_filename_has_correct_format(tmp_path):
    mgr = make_manager(tmp_path)
    case = mgr.open_case("12345", "S")
    path = case.write_draft("body")
    assert re.match(r"^\d{3}-rodney-draft-\d{4}-\d{2}-\d{2}T", path.name)


def test_write_draft_sequence_increments(tmp_path):
    mgr = make_manager(tmp_path)
    case = mgr.open_case("12345", "S")
    p1 = case.write_draft("first draft")
    p2 = case.write_draft("second draft")
    seq1 = int(p1.name[:3])
    seq2 = int(p2.name[:3])
    assert seq2 == seq1 + 1


# --- write_sent_pending / confirm_sent / mark_failed ---

def test_write_sent_pending_has_status_pending(tmp_path):
    mgr = make_manager(tmp_path)
    case = mgr.open_case("12345", "S")
    path = case.write_sent_pending("Reply body here.")
    content = path.read_text()
    assert FRONTMATTER_STATUS_PENDING in content


def test_confirm_sent_updates_status_to_sent(tmp_path):
    mgr = make_manager(tmp_path)
    case = mgr.open_case("12345", "S")
    path = case.write_sent_pending("Reply body.")
    case.confirm_sent(path)
    content = path.read_text()
    assert FRONTMATTER_STATUS_SENT in content
    assert FRONTMATTER_STATUS_PENDING not in content


def test_mark_failed_updates_status_to_failed(tmp_path):
    mgr = make_manager(tmp_path)
    case = mgr.open_case("12345", "S")
    path = case.write_sent_pending("Reply body.")
    case.mark_failed(path)
    content = path.read_text()
    assert FRONTMATTER_STATUS_FAILED in content
    assert FRONTMATTER_STATUS_PENDING not in content


def test_confirm_sent_is_atomic(tmp_path):
    mgr = make_manager(tmp_path)
    case = mgr.open_case("12345", "S")
    path = case.write_sent_pending("body")
    with patch("yarbod.cases.os.replace") as mock_replace:
        case.confirm_sent(path)
    mock_replace.assert_called_once()


# --- repair_partial ---

def test_repair_partial_fixes_pending_files(tmp_path):
    mgr = make_manager(tmp_path)
    case = mgr.open_case("12345", "S")
    path = case.write_sent_pending("Unsent reply.")
    # Simulate crash before confirm_sent — file stays pending
    repaired = mgr.repair_partial()
    assert repaired == 1
    assert FRONTMATTER_STATUS_FAILED in path.read_text()


def test_repair_partial_ignores_already_sent(tmp_path):
    mgr = make_manager(tmp_path)
    case = mgr.open_case("12345", "S")
    path = case.write_sent_pending("body")
    case.confirm_sent(path)
    repaired = mgr.repair_partial()
    assert repaired == 0


def test_repair_partial_returns_count(tmp_path):
    mgr = make_manager(tmp_path)
    for tid in ["111", "222", "333"]:
        c = mgr.open_case(tid, "S")
        c.write_sent_pending(f"body {tid}")
    repaired = mgr.repair_partial()
    assert repaired == 3


# --- sequence counter concurrency ---

def test_sequence_counter_safe_under_concurrent_writes(tmp_path):
    mgr = make_manager(tmp_path)
    case = mgr.open_case("12345", "S")
    errors = []

    def write_draft(n):
        try:
            case.write_draft(f"draft {n}")
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=write_draft, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    md_files = list(case.case_dir.glob("*-rodney-draft-*.md"))
    seqs = sorted(int(f.name[:3]) for f in md_files)
    assert len(seqs) == 10
    assert seqs == list(range(seqs[0], seqs[0] + 10))


# --- retention sweep ---

def test_sweep_gzips_bundles_older_than_90_days(tmp_path):
    mgr = make_manager(tmp_path)
    old_date = (date.today() - timedelta(days=95)).isoformat()
    old_case = tmp_path / "cases-stage" / f"{old_date}-T99999"
    old_case.mkdir(parents=True)
    bundle = old_case / "bundle.zip"
    bundle.write_bytes(b"PK" + b"\x00" * 10)
    (old_case / "manifest.json").write_text(json.dumps({
        "ticket_id": "99999", "status": "closed",
        "closed_at": f"{old_date}T00:00:00+00:00"
    }))

    mgr.sweep_retention()
    assert (old_case / "bundle.zip.gz").exists()
    assert not bundle.exists()


def test_sweep_archives_cases_older_than_1_year(tmp_path):
    mgr = make_manager(tmp_path)
    old_date = (date.today() - timedelta(days=370)).isoformat()
    old_case = tmp_path / "cases-stage" / f"{old_date}-T88888"
    old_case.mkdir(parents=True)
    (old_case / "manifest.json").write_text(json.dumps({
        "ticket_id": "88888", "status": "closed",
        "closed_at": f"{old_date}T00:00:00+00:00"
    }))

    mgr.sweep_retention()
    archived = tmp_path / "cases-stage" / "_archived" / old_date[:4] / f"{old_date}-T88888"
    assert archived.exists()
    assert not old_case.exists()


def test_sweep_leaves_active_cases_alone(tmp_path):
    mgr = make_manager(tmp_path)
    today = date.today().isoformat()
    active = tmp_path / "cases-stage" / f"{today}-T77777"
    active.mkdir(parents=True)
    (active / "manifest.json").write_text(json.dumps({
        "ticket_id": "77777", "status": "open", "closed_at": None
    }))

    mgr.sweep_retention()
    assert active.exists()
