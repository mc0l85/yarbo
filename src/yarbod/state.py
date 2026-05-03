"""YarboState dataclass and load helpers."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STALE_THRESHOLD_SECONDS = 300  # 5 minutes


@dataclass
class YarboState:
    schema_version: int
    last_updated: datetime
    robot: dict[str, Any]
    activity: dict[str, Any]
    location: dict[str, Any]
    errors: dict[str, Any]
    rain_sensor: bool
    broker_health: dict[str, Any]

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "YarboState":
        return cls(
            schema_version=d["schema_version"],
            last_updated=datetime.fromisoformat(d["last_updated"]),
            robot=d["robot"],
            activity=d["activity"],
            location=d["location"],
            errors=d["errors"],
            rain_sensor=d["rain_sensor"],
            broker_health=d["broker_health"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "last_updated": self.last_updated.isoformat(),
            "robot": self.robot,
            "activity": self.activity,
            "location": self.location,
            "errors": self.errors,
            "rain_sensor": self.rain_sensor,
            "broker_health": self.broker_health,
        }

    def is_stale(self) -> bool:
        now = datetime.now(timezone.utc)
        ts = self.last_updated
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return (now - ts).total_seconds() > STALE_THRESHOLD_SECONDS

    def stale_prefix(self) -> str:
        if not self.is_stale():
            return ""
        now = datetime.now(timezone.utc)
        ts = self.last_updated
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        delta_m = int((now - ts).total_seconds() // 60)
        return f"[stale {delta_m}m ago]"


def load_state(
    live_path: Path,
    fallback_path: Path,
) -> YarboState | None:
    for path in (live_path, fallback_path):
        if path.exists():
            try:
                data = json.loads(path.read_text())
                return YarboState.from_dict(data)
            except (json.JSONDecodeError, KeyError, ValueError):
                continue
    return None
