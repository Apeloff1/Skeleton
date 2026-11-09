# Salon chat UX

Conversation choreography for Skeleton AI chat. October 2026 surface.
The turn runtime still journals. This organ decides how a turn is felt.

## Implement

1. Place `salon.py` at `skeleton/ai/assistant/salon.py`.
2. Place `test_ai_chat_salon.py` at `skeleton/testing/test_ai_chat_salon.py`.
3. Export the salon symbols from `skeleton/ai/assistant/__init__.py`.
4. Serve `salon_surface.html` as the reference client. It is a mirror of the beat protocol, not the authority. The authority is `SalonSession.compose`.
5. Do not replace `turn_runtime`, `streaming`, or `response_acceptance`.
6. Keep `stored_prose = 0`. Never copy user text into the salon ledger.

## Compile check

```bash
python -m unittest skeleton.testing.test_ai_chat_salon
```

## Protocol

Each turn emits beats: presence, ingress, stance, body, optional adage, optional callback, optional open hand, seal.
Cadence is milliseconds. Reduced motion forces 0.
Interrupt drops the tail after an interruptible beat. Presence and seal cannot be cut.
Reactions: quieter, more_play, pin, fork, hold.
Citation chips ride on the body beat.
`production_authority` is always false. Salon does not commit the transcript.

## Other agents

Import `SalonSession`. Pass the model answer as `body`. Render `plan.beats` in order, waiting `cadence_ms` unless the client prefers reduced motion. On interrupt, call `session.interrupt(seq)` and stop playback. On seal, return focus to the composer.