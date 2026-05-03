# Screen Registry

> **Stub** — populated during Step 5 (AVD bootstrap, Myron interactive MBP session).

## Purpose

Maps Yarbo app screen names to tap-path sequences and post-tap UI-tree hashes.
Used by `app.py` for navigation and drift detection.

## Format (`screen_registry.yaml`)

```yaml
screens:
  home:
    description: Main dashboard
    tap_path: []        # already on home after launch
    ui_hash: null       # populated during AVD bootstrap
  info_page:
    description: Device info / serial / firmware
    tap_path:
      - {type: text, label: "Device"}
    ui_hash: null
  diagnosis_page:
    description: Error log / diagnostics
    tap_path:
      - {type: text, label: "Device"}
      - {type: text, label: "Diagnosis"}
    ui_hash: null
```

## Drift detection

After each navigation, `app.py` computes UI-tree hash and compares to `ui_hash` in registry.
Mismatch fires `app_screen_drift` alert. Registry updated by re-running AVD bootstrap script.

## Bootstrap

See `deploy/yarbo_avd_bootstrap.md` — requires Myron interactive session on MBP Bridge
(`myrons-mbp.local:5055`). Blocked until Step 5.
