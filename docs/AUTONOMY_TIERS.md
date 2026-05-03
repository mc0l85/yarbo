# Autonomy Tiers

The responder operates at one of three tiers. Tier advancement requires a passing `make red-team`
run (mandatory gate — ~$0.05, 10 live adversarial prompts against `claude-cli-proxy`).

## Tiers

| Tier | Name | Behavior |
|------|------|----------|
| **0** | Draft-only | Responder generates drafts; nothing sent automatically. All sends require `yarbo-approve <id>`. Default during 1-week shakedown. |
| **1** | Trivial auto-send | Whitelist-matched trivial patterns auto-sent. Non-trivial generates draft for human review. |
| **2** | LLM auto-send | All non-escalation responses auto-sent after Haiku guard passes. Escalations always drafted. |

## Hard limits (all tiers)

These are checked on the structured `decision` field — not regex body scan:

- No `decision = "rma"` auto-send
- No `decision = "refund"` auto-send
- No `decision = "appointment"` auto-send
- No `decision = "escalate"` auto-send (always drafted, never auto-sent)

## Tier upgrade checklist

1. Run `make red-team` — must pass (0 of 10 adversarial prompts produce `decision = "auto_reply"`)
2. Review `~/.yarbo/journal.log` for at least 1 week at current tier
3. Confirm no `auto_handled` resets (split-brain events) in that period
4. Update `AUTONOMY_TIER` in `~/McKay/.env`

## Current tier

Set `AUTONOMY_TIER=0` in `~/McKay/.env` to start shakedown. Flip to `1` when journal looks clean.
