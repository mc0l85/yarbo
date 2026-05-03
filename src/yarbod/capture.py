"""Raw JSONL telemetry capture — O_APPEND writes, atomic rotation, retention sweep."""
from __future__ import annotations

import gzip
import json
import os
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from yarbod.alerts import AlertDispatcher

DISK_LOW_BYTES: int = 1 * 1024 ** 3   # 1 GB
DISK_KEEP_GZ_DAYS: int = 30
DISK_DELETE_DAYS: int = 365


class CaptureWriter:
    def __init__(self, capture_dir: Path, alerts: "AlertDispatcher") -> None:
        self._dir = capture_dir
        self._alerts = alerts
        self._dir.mkdir(parents=True, exist_ok=True)

    def _today_path(self) -> Path:
        return self._dir / f"{date.today().isoformat()}.jsonl"

    def append(self, record: dict[str, Any]) -> None:
        usage = shutil.disk_usage(self._dir)
        if usage.free < DISK_LOW_BYTES:
            self._alerts.dispatch(
                "capture_disk_low",
                cooldown_seconds=3600,
                message=f"Yarbo capture disk low: {usage.free // 1024**3}GB free",
            )
            return

        line = json.dumps(record, separators=(",", ":")) + "\n"
        path = self._today_path()
        # O_APPEND: POSIX guarantees atomicity for writes ≤ PIPE_BUF on local ext4/xfs
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
        try:
            os.write(fd, line.encode())
        finally:
            os.close(fd)

    def rotate(self, target_date: date | None = None) -> None:
        if target_date is None:
            from datetime import timedelta
            target_date = date.today() - timedelta(days=1)

        jsonl_path = self._dir / f"{target_date.isoformat()}.jsonl"
        if not jsonl_path.exists():
            return

        gz_path = self._dir / f"{target_date.isoformat()}.jsonl.gz"
        tmp_path = self._dir / f"{target_date.isoformat()}.jsonl.gz.tmp"

        try:
            with open(jsonl_path, "rb") as f_in:
                with gzip.open(tmp_path, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            os.replace(tmp_path, gz_path)
            jsonl_path.unlink()
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink()
            raise

        usage = shutil.disk_usage(self._dir)
        if usage.free < 5 * 1024 ** 3:
            self.sweep_retention()

    def sweep_retention(self) -> None:
        from datetime import timedelta
        today = date.today()
        for gz in self._dir.glob("*.jsonl.gz"):
            try:
                file_date = date.fromisoformat(gz.stem.removesuffix(".jsonl"))
            except ValueError:
                continue
            age_days = (today - file_date).days
            if age_days > DISK_DELETE_DAYS:
                gz.unlink()
