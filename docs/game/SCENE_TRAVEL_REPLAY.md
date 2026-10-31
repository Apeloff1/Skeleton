# Offline authored scene travel and replay

The canonical owner is `skeleton/game/gameplay/scene_travel.py`. It
uses the existing FLGB `StateMachine`, `EventBus` and
`SaveableGameplayState` contracts, not a parallel application runtime.

## Play an original game locally

    python -m skeleton scene-travel play --demo

The original Lantern Hollow scenario begins at the quay. Type:

    collect find_key
    travel north
    travel inside

The engine checks the brass key requirement, traverses actual authored
exits and ends at the sanctuary with a verified victory. Choosing
`travel down` at the quay instead reaches the failure ending. The
user can also supply `--world-json '<world-json>'` or resume a
previously exported `--session-json '<save-json>'`.

Every accepted action is applied to canonical state, journaled with
before/after SHA-256 digests, and included in the FLGB event bus and
parent-linked save. Output is JSON-lines: source identity, scene choices,
inventory, rejected input, periodic full checkpoints and terminal ending.
`--checkpoint-every` accepts 1..64 actions (default 8). EOF or three
invalid commands emits the latest replay-verified checkpoint and returns
a nonzero error. Capture its `session` JSON to resume after interruption.

For an imported save, supply `--source-digest '<trusted-sha256>'`
obtained from a separately authenticated authored manifest. A save's
own digest is an integrity receipt, not a signature or rights approval.

## Noninteractive deterministic compilation

    python -m skeleton scene-travel demo
    python -m skeleton scene-travel simulate --world-json '<json>' --actions-json '<json>'
    python -m skeleton scene-travel verify --session-json '<json>'
    python -m skeleton scene-travel resume --session-json '<json>' --actions-json '<json>'

Source and save schemas are `skeleton.scene_travel.v1`; all fields are
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


## Bounded victory route hints

    python -m skeleton scene-travel hint --demo
    python -m skeleton scene-travel hint --session-json '<saved-json>'

The hint solver runs the real scene transition rules, not an unverified
graph-only guess. It searches in deterministic shortest-action order and
returns a winning command sequence with exact starting source/state and
replayed final state hashes. A completed victory save returns an empty
winning route; terminal failure is unreachable. The search distinguishes
exhaustively unreachable from inconclusive when bounded resource limits
are exhausted. Operators can constrain --max-states (1..4096) and
--max-depth (1..512). No AI provider, network, learned model, untrusted
script execution or remote asset fetch is involved.

Focused tests also include:

    python -m pytest -q skeleton/testing/test_scene_route_solver.py

## Replay-proven alternate-ending and scene coverage audit

\`python -m skeleton scene-travel audit --demo\` traverses actual
source-authorized gameplay transitions, reporting shortest replayable
witnesses for victory, failure and draw, along with visited scene
coverage and unobserved authored scenes. Imported checkpoints can be
audited with \`--session-json\` after complete journal verification.
Every witness includes the initial source/state digest and final state
digest, and can be replayed through the canonical scene engine.

The audit preserves a strict distinction between **not reached** and
**inconclusive**: if \`--max-states\` or \`--max-depth\` truncates the
search, missing endings are not falsely declared impossible. Unlike
the victory-only route solver, the state key includes the tick so
turn-budget-dependent draw outcomes remain observable. Exploration
is bounded to at most 4096 states and 512 steps; no scripts or provider
calls execute.

Focused regression: \`python -m pytest
skeleton/testing/test_scene_ending_audit.py -q\`.
