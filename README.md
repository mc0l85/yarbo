# yarbo

Rodney-facing skill and daemon suite for Myron's Yarbo robot system — MQTT telemetry capture,
alerts, support-ticket lifecycle, and overnight LLM responder.

---

> **LIMITATIONS — read before using**
>
> Four gaps exist in the current `python-yarbo` / MQTT layer. Commands that land in a gap
> refuse with "phone app required, want me to open it on your phone?" rather than silently failing.
>
> 1. **Schedule editing not supported.** Read-only schedule. Edits require Yarbo phone app.
> 2. **Zone / plan creation/editing not supported.** Read map and start saved plans only. No zone edits.
> 3. **Firmware OTA orchestration not in MQTT scope.** Read firmware version only. Update kicked from app.
> 4. **`python-yarbo` cloud modules are experimental.** This skill uses local-only mode.
>
> See [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) for full detail.

---

## Architecture

Single-machine deploy on x404 (`10.0.17.249`):

- **`yarbo-monitor.service`** — long-running daemon; MQTT subscribe via `python-yarbo`; writes
  `/dev/shm/yarbo/state.json` (ramdisk) and `~/.yarbo/capture/<date>.jsonl`.
- **Four systemd timers** — tickets (15m), portal (daily), forum (daily, Phase 2), responder (hourly 03–11 UTC).
- **`_YARBO/SKILL.md`** in `ecc/.claude/skills/_YARBO/` — read-only interface for Rodney CLI.

See [`docs/CASE_LAYOUT.md`](docs/CASE_LAYOUT.md), [`docs/TICKET_LIFECYCLE.md`](docs/TICKET_LIFECYCLE.md),
[`docs/AUTONOMY_TIERS.md`](docs/AUTONOMY_TIERS.md), [`docs/MQTT_TOPICS.md`](docs/MQTT_TOPICS.md).

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium

cp .env.example ~/McKay/.env   # fill in values; mode 600
# Run initial portal cookie export (one-time, interactive):
# python -m yarbo.portal --init-session
```

## Tests

```bash
pytest                   # unit + integration; fails below 80% coverage
make adversarial         # adversarial responder tests (separate target)
make red-team            # live claude-cli-proxy red-team (mandatory before each Tier upgrade)
make smoke-live          # 60s real MQTT + 1 portal read + 1 screenshot (run by hand on x404)
```

## `python-yarbo` pin policy

Pinned to commit SHA in `pyproject.toml`. Pre-1.0; ships from `main`. Bump via PR + smoke
test against captured JSONL fixtures. Daily `yarbo-upstream-check.timer` alerts on non-trivial
upstream commits since the pin (path-filtered — excludes docs/CI churn).

## Repo layout

```
src/yarbo/          daemon + cron modules
tests/              unit, integration, adversarial, smoke
deploy/             systemd units
docs/               LIMITATIONS, MQTT_TOPICS, CASE_LAYOUT, TICKET_LIFECYCLE, AUTONOMY_TIERS, SCREEN_REGISTRY
```

Skill lives separately in `ecc/.claude/skills/_YARBO/SKILL.md`.
