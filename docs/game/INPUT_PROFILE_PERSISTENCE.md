# Offline input profile persistence and replay continuation

The canonical presentation input router can now publish revised profiles
and resumable input sessions without overwriting existing files:

```sh
python -m scripts.game.route_inputs --profile controls.json \
  --rebind keyboard-east --control ArrowRight --revision 0 \
  --out-profile revised-controls.json
python -m scripts.game.route_inputs --profile revised-controls.json \
  --events new-events.json --out-session first-session.json
python -m scripts.game.route_inputs --profile revised-controls.json \
  --resume first-session.json --events later-events.json \
  --out-session second-session.json
```

Each output uses atomic no-clobber publication and file synchronization.
Resumed sessions are verified by the canonical `InputSession.restore` path
before new events are admitted. Changing a profile digest invalidates an
old replay rather than silently remapping historical player actions.
Input JSON rejects duplicate keys, non-finite constants and oversized
regular files. This is an offline captured-input adapter, not an OS driver.
