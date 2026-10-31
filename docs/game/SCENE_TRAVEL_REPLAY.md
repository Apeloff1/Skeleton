# Offline authored scene travel and replay

The canonical owner is \`skeleton/game/gameplay/scene_travel.py\`. It
uses the existing FLGB \`StateMachine\`, \`EventBus\` and
\`SaveableGameplayState\` contracts, not a parallel application runtime.

## Play an original game locally

    python -m skeleton scene-travel play --demo

The original Lantern Hollow scenario begins at the quay. Type:

    collect find_key
    travel north
    travel inside

The engine checks the brass key requirement, traverses actual authored
exits and ends at the sanctuary with a verified victory. Choosing
\`travel down\` at the quay instead reaches the failure ending. The
user can also supply \`--world-json '<world-json>'\` or resume a
previously exported \`--session-json '<save-json>'\`.

Every accepted action is applied to canonical state, journaled with
before/after SHA-256 digests, and included in the FLGB event bus and
parent-linked save. Output is JSON-lines: source identity, scene choices,
inventory, rejected input, periodic full checkpoints and terminal ending.
\`--checkpoint-every\` accepts 1..64 actions (default 8). EOF or three
invalid commands emits the latest replay-verified checkpoint and returns
a nonzero error. Capture its \`session\` JSON to resume after interruption.

For an imported save, supply \`--source-digest '<trusted-sha256>'\`
obtained from a separately authenticated authored manifest. A save's
own digest is an integrity receipt, not a signature or rights approval.

## Noninteractive deterministic compilation

    python -m skeleton scene-travel demo
    python -m skeleton scene-travel simulate --world-json '<json>' --actions-json '<json>'
    python -m skeleton scene-travel verify --session-json '<json>'
    python -m skeleton scene-travel resume --session-json '<json>' --actions-json '<json>'

Source and save schemas are \`skeleton.scene_travel.v1\`; all fields are
strict. Scene IDs, exits and pickups are bounded and validated. Duplicate
scene or exit IDs, missing destinations, nonexistent required items,
unauthorized actions, extra fields, forged inventory/visited state and
tampered receipts fail closed. Cyclic paths are allowed for original
free-roam, but every session has a finite 1..512-step budget. No scripts
are executed and no network, filesystem, provider or external asset is
accessed by the simulation. Native 3D, audio, gamepad and retail export
are **not** implemented by this reference adapter.

## Focused canonical validation

    python -m pytest -q skeleton/testing/test_scene_travel.py

Run architecture/security/CI gates against the exact remote head before
review or mainline merge. This documentation does not certify those gates.
