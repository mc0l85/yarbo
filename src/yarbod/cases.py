"""Per-case audit trail: folder protocol, atomic frontmatter writes, repair, retention."""
from __future__ import annotations

import fcntl
import gzip
import json
import os
import shutil
import tempfile
import threading
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from yarbod.alerts import AlertDispatcher

FRONTMATTER_STATUS_PENDING = "status: pending"
FRONTMATTER_STATUS_SENT = "status: sent"
FRONTMATTER_STATUS_FAILED = "status: failed-send"

_BUNDLE_GZIP_DAYS = 90
_ARCHIVE_DAYS = 365


def _utc_iso_filename() -> str:
    return datetime.now(timezone.utc).isoformat().replace(":", "-")


class Case:
    def __init__(self, case_dir: Path) -> None:
        self.case_dir = case_dir
        self._seq_lock = threading.Lock()
        self._seq_file = case_dir / ".seq"

    def _next_seq(self) -> int:
        with self._seq_lock:
            fd = os.open(self._seq_file, os.O_RDWR | os.O_CREAT, 0o644)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX)
                raw = os.read(fd, 32).decode().strip()
                seq = int(raw) + 1 if raw else 1
                os.lseek(fd, 0, os.SEEK_SET)
                os.ftruncate(fd, 0)
                os.write(fd, str(seq).encode())
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
                os.close(fd)
        return seq

    def _write_md(self, source: str, frontmatter: dict, body: str) -> Path:
        seq = self._next_seq()
        ts = _utc_iso_filename()
        filename = f"{seq:03d}-{source}-{ts}.md"
        path = self.case_dir / filename
        fm_lines = "\n".join(f"{k}: {v}" for k, v in frontmatter.items())
        content = f"---\n{fm_lines}\n---\n\n{body}\n"
        path.write_text(content)
        return path

    def write_draft(self, body: str) -> Path:
        return self._write_md(
            "rodney-draft",
            {"status": "draft", "created_at": datetime.now(timezone.utc).isoformat()},
            body,
        )

    def write_sent_pending(self, body: str) -> Path:
        return self._write_md(
            "rodney-sent",
            {"status": "pending", "created_at": datetime.now(timezone.utc).isoformat()},
            body,
        )

    def _rewrite_status(self, path: Path, new_status: str) -> None:
        content = path.read_text()
        updated = content.replace(FRONTMATTER_STATUS_PENDING, f"status: {new_status}", 1)
        tmp_fd, tmp_path_str = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        tmp_path = Path(tmp_path_str)
        try:
            with os.fdopen(tmp_fd, "w") as f:
                f.write(updated)
            os.replace(tmp_path, path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

    def confirm_sent(self, path: Path) -> None:
        self._rewrite_status(path, "sent")

    def mark_failed(self, path: Path) -> None:
        self._rewrite_status(path, "failed-send")

    def freeze(
        self,
        closed_at: datetime,
        resolution: str,
        total_messages: int,
        time_to_close_hr: float,
    ) -> None:
        summary = self.case_dir / "summary.md"
        section = (
            f"\n## Close-out\n\n"
            f"- closed_at: {closed_at.isoformat()}\n"
            f"- resolution: {resolution}\n"
            f"- total_messages: {total_messages}\n"
            f"- time_to_close_hr: {time_to_close_hr:.1f}\n"
        )
        with open(summary, "a") as f:
            f.write(section)
        manifest_path = self.case_dir / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text())
            manifest["status"] = "closed"
            manifest["closed_at"] = closed_at.isoformat()
            manifest_path.write_text(json.dumps(manifest, indent=2))


class CaseManager:
    def __init__(
        self,
        stage_dir: Path,
        rsync_target: str | None,
        alerts: "AlertDispatcher",
    ) -> None:
        self._stage = stage_dir
        self._rsync_target = rsync_target
        self._alerts = alerts
        self._stage.mkdir(parents=True, exist_ok=True)

    def open_case(self, ticket_id: str, subject: str) -> Case:
        today = date.today().isoformat()
        folder_name = f"{today}-T{ticket_id}"

        # Idempotent: return existing case if folder already exists
        for existing in self._stage.iterdir():
            if existing.is_dir() and f"-T{ticket_id}" in existing.name:
                return Case(existing)

        case_dir = self._stage / folder_name
        case_dir.mkdir(parents=True, exist_ok=True)

        manifest = {
            "ticket_id": ticket_id,
            "subject": subject,
            "opened_at": datetime.now(timezone.utc).isoformat(),
            "status": "open",
            "closed_at": None,
        }
        (case_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        return Case(case_dir)

    def repair_partial(self) -> int:
        repaired = 0
        for case_dir in self._stage.iterdir():
            if not case_dir.is_dir() or case_dir.name.startswith("_"):
                continue
            for md_file in case_dir.glob("*-rodney-sent-*.md"):
                content = md_file.read_text()
                if FRONTMATTER_STATUS_PENDING in content:
                    Case(case_dir).mark_failed(md_file)
                    repaired += 1
        return repaired

    def sweep_retention(self) -> None:
        today = date.today()
        for case_dir in list(self._stage.iterdir()):
            if not case_dir.is_dir() or case_dir.name.startswith("_"):
                continue
            manifest_path = case_dir / "manifest.json"
            if not manifest_path.exists():
                continue
            manifest = json.loads(manifest_path.read_text())
            if manifest.get("status") != "closed" or not manifest.get("closed_at"):
                continue

            try:
                closed_date = datetime.fromisoformat(manifest["closed_at"]).date()
            except (ValueError, TypeError):
                continue

            age_days = (today - closed_date).days

            if age_days > _ARCHIVE_DAYS:
                year = str(closed_date.year)
                archive_parent = self._stage / "_archived" / year
                archive_parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(case_dir), archive_parent / case_dir.name)
                continue

            if age_days > _BUNDLE_GZIP_DAYS:
                for bundle in case_dir.glob("bundle.zip"):
                    gz_path = bundle.with_suffix(".zip.gz")
                    tmp_path = bundle.with_suffix(".zip.gz.tmp")
                    try:
                        with open(bundle, "rb") as f_in, gzip.open(tmp_path, "wb") as f_out:
                            shutil.copyfileobj(f_in, f_out)
                        os.replace(tmp_path, gz_path)
                        bundle.unlink()
                    except Exception:
                        tmp_path.unlink(missing_ok=True)
