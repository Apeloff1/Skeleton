# Scene Circuit — switch puzzles and conditional gates

This playable Studio B vertical extends canonical offline scene travel with
reversible, source-authored switches and conditional exit gates. The underlying
engine still owns scene movement, pickup inventory, keyed exits, endings and
deterministic replay.

Installed CLI commands:

    python -m skeleton scene-circuit demo
    python -m skeleton scene-circuit preview --source-json SOURCE
    python -m skeleton scene-circuit simulate --source-json SOURCE --actions-json ACTIONS
    python -m skeleton scene-circuit resume --session-json SAVE --actions-json ACTIONS
    python -m skeleton scene-circuit verify --session-json SAVE
    python -m skeleton scene-circuit export --session-json SAVE
    python -m skeleton scene-circuit import --bundle-json BUNDLE

Original Lantern Harbor puzzle: turn on the quay lantern, collect the brass
key, traverse the unlocked north gate, and reach the sanctuary. A gate may
require multiple switches on or off. Toggles are permitted only when the
player is in the switch's authored playable scene. Invalid references fail
before simulation.

Every legal action advances a replay-derived state digest, event receipt and
parent-linked save. Portable import validates a bundle digest and rebuilds
the entire nested canonical scene session. Digests are corruption detectors,
not signatures. There are no scripts, network calls or filesystem writes.

Limits: 16 switches, 32 gates, 96 actions and 2 MiB CLI output. Existing
scene-travel saves and sources are not modified.

Focused validation:

    python -m pytest skeleton/testing/test_scene_circuit.py -q

Source delivery does not establish device or release qualification.
