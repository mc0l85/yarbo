# Ticket Lifecycle

> **Stub** — fill in during Step 9 (tickets.py / portal.py).

## States

```
open → waiting_yarbo → waiting_me → closed
```

| State | Meaning |
|-------|---------|
| `open` | New ticket, no response yet |
| `waiting_yarbo` | We replied; awaiting Yarbo response |
| `waiting_me` | Yarbo replied; needs our response |
| `closed` | Resolved or cancelled |

## Sources

| Source | Role |
|--------|------|
| `gws-mse` (email) | **Trigger only** — subject-line parse to enqueue immediate portal sync |
| Playwright portal scrape | **Canonical source** — full message arrays, correct `last_response_from` |

## auto_handled flag

- Set to `1` only on confirmed `gws-mse send-as-MSE` success
- Reset to `0` if new `ticket_messages` row with `sender='me'` not in sent log (split-brain guard)
- `yarbo-reset-handled <id>` CLI escape hatch for manual override

## Bot receipt filter

`bot_receipt_patterns.yaml` checked against email subject before updating `last_response_from`.
Prevents Zoho auto-acknowledgement emails from appearing as real Yarbo responses.

## Daily reconciliation

Full portal scrape once daily catches tickets missed by email filter.
