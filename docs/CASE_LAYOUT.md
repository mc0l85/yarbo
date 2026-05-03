# Case Folder Layout

> **Stub** — fill in during Step 8 (cases.py).

## Path convention

```
~/.yarbo/cases-stage/<YYYY-MM-DD>-T<ticket-id>/   ← local staging (fast writes)
<jarvis-mount>/yarbo/CASES/<YYYY-MM-DD>-T<ticket-id>/   ← durable (async rsync from stage)
```

## Write order (atomic, spec §3.7)

1. Write draft files to local stage dir
2. `sent-pending` rename on stage
3. `gws-mse send-as-MSE` outbound
4. On confirmed send: `sent` rename on stage
5. Async rsync flushes stage → Jarvis CASES/
6. Failed sends logged as `failed-portal`, never silently dropped

## Files per case

| File | Contents |
|------|----------|
| `manifest.json` | ticket_id, opened_at, case_folder, status |
| `draft.md` | LLM-generated reply body (pre-send) |
| `sent.md` | confirmed-sent body |
| `bundle.zip` | diagnostics bundle (capture window + screenshots) |
| `bundle/manifest.json` | bundle metadata |

## Retention

- 90 days: full case folder retained on Jarvis
- 1 year: bundle.zip gzipped, text files kept
- After 1 year: archive to `CASES/_archived/<year>/`
- `yarbo-cases-cleanup.timer`: daily sweep
