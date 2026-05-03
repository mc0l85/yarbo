# Limitations

Four gaps in the current `python-yarbo` / MQTT layer. Surfaced here, in `README.md`,
in `yarbo --help` epilog, and in `_YARBO/SKILL.md`.

1. **Schedule editing not supported.** Read-only schedule. Edits require Yarbo phone app.
2. **Zone / plan creation/editing not supported.** Read map and start saved plans only. No zone edits.
3. **Firmware OTA orchestration not in MQTT scope.** Read firmware version only. Update kicked from app.
4. **`python-yarbo` cloud modules are experimental.** This skill uses local-only mode.

Skill commands that land in any gap respond with:
> "phone app required, want me to open it on your phone?"

These limitations are expected to shrink when Yarbo's official Open API ships (announced 2026-04-06,
expected early 2027). At that point, re-evaluate against the official SDK before replacing
`python-yarbo`.
