# Deterministic accessible input profiles

The canonical game presentation plane now translates already-captured keyboard,
controller and touch input chords into deterministic semantic gameplay commands.
This is **not** a native device driver, controller pairing layer, OS keyboard
hook, touch gesture detector, or screen-reader qualification.

```sh
python -m scripts.game.route_inputs --profile skeleton/game/presentation/fixtures/original_campaign_controls.json --events events.json
python -m scripts.game.route_inputs --profile skeleton/game/presentation/fixtures/original_campaign_controls.json --rebind keyboard-east --control ArrowRight --revision 0
python -m unittest skeleton.testing.test_input_router -v
```

An event is a versioned JSON record with unique `event_id`, contiguous
`sequence`, `device_class`, `control_path`, sorted `modifiers` and boolean
`pressed`. The source-bound receipt includes semantic `{"kind":"move",
"target":"east"}` or null on release, binding identity, profile digest and
hash-chained event history. Unknown chords, duplicate identities, sequence
gaps, ambiguous bindings, stale remaps and tampered replay fail closed.
Remapping is immutable and optimistic-revision-fenced; an in-progress input
session cannot silently switch to a new profile.

The original profile includes WASD keyboard, controller D-pad right and
touch SwipeRight event names. The caller must obtain genuine OS/device events,
authorize input sources, and connect semantic actions to a gameplay session;
these responsibilities are not simulated by this mapper. Input profiles are
bounded to 128 bindings and replay to 4096 events, with read-only CLI file
ingress and no external network or model access.
