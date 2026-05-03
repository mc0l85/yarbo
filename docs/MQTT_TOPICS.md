# MQTT Topics

> **Stub** — populate during Step 2 (client.py) once live MQTT traffic is observed on
> `10.50.0.182:1883`.

## Source of truth

`python-yarbo` source at `markus-lassfolk/python-yarbo` (pinned SHA in `pyproject.toml`).
Protocol shape documented in upstream `docs/index.md`.

## Fallback

If `python-yarbo` is unavailable, raw subscribe via:
```bash
mosquitto_sub -h 10.50.0.182 -p 1883 -t '#' -v
```

## Topics to document

- State topics (battery, mode, head type, errors, GPS, RTK, rain sensor)
- Command topics (start_plan, stop, pause, resume, RTH, beep, lights, snow chute, blower, roller)
- Base station heartbeat / device presence topics
- Error / fault code topic and known codes

## Two-layer spoofing defense

1. UniFi rule: `1883/tcp` restricted to base station MAC only (static DHCP + MAC verified during commissioning)
2. `alerts.py` transition rate-limit: suspicious transitions (e.g. `working→stuck` 3+/hr) discarded with journal entry
