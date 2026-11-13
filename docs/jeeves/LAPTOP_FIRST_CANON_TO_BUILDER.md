# Laptop-first Jeeves canonical world handoff

This path exercises one original game from an authored prompt to typed canon,
explicit operator-reviewed edit, deterministic proof, HTML5 playable, typed
builder recipe, persisted player choice, export and source-bound restoration.
It does not generate a model, a Godot executable or Windows installer.

## Original lighthouse sample

Use a private directory as STORE. Run each command from the repository root
with Python and the package installed:

1. python -m skeleton world-laptop --store STORE propose --brief-file examples/jeeves/lighthouse_brief.json
2. python -m skeleton world-laptop --store STORE inspect --world-id lighthouse
3. python -m skeleton world-laptop --store STORE review --world-id lighthouse --expected-digest DIGEST_FROM_PROPOSE --operation-file examples/jeeves/lighthouse_review.json --review-note "I reviewed the rescue route and its consequences."
4. python -m skeleton world-laptop --store STORE compile --world-id lighthouse --expected-digest DIGEST_FROM_REVIEW
5. python -m skeleton world-laptop --store STORE verify --world-id lighthouse
6. python -m skeleton world-laptop --store STORE session-create --world-id lighthouse --slot player
7. python -m skeleton world-laptop --store STORE session-choose --world-id lighthouse --slot player --choice-id rescue --expected-session-digest DIGEST_FROM_CREATE
8. python -m skeleton world-laptop --store STORE session-export --world-id lighthouse --slot player
9. Save the returned result object as a JSON file and run world-laptop session-restore --world-id lighthouse --slot restored --export-file FILE.

The compile receipt identifies a CSP-protected offline HTML player and
lighthouse.laptop.builder.json. The builder JSON contains canonical scene nodes,
choice edges, ending witnesses, source/review digests, and the player-session
contract. It is an engine-facing source recipe, not a compiled engine binary.

The review operation is an explicit, typed, graph-verified transaction. A stale
source digest, missing review, unearned choice, stale session digest, forged
session export, altered builder file or changed HTML causes a typed failure.
Publication is fail-closed if interrupted; the receipt is written last and
verify recomputes both artifacts from the reviewed source. A later source edit
invalidates the review lease and prevents session continuation until reviewed
again. Existing multi-plane Studio Engine compilation remains a separate,
stricter nine-source approval process; this path does not bypass it.

Canonical regression:
python -m pytest skeleton/testing/test_jeeves_world_laptop_flow.py -q

Platform limits: source custody requires POSIX descriptor-relative open and
O_NOFOLLOW; unsupported Windows environments fail closed. The flow makes no
device, consumer installation, model inference, or release qualification claim.

Jeeves read-only tool names: world.laptop_preview and world.laptop_handoff_preview.
They inspect the reviewed canonical source and verified handoff without changing
custody, granting approval or invoking model inference.

## Existing Studio Engine owner integration

A minimal world compiles its typed builder recipe without manufacturing the
other reviewed planes. For an existing fully authored nine-plane world, run
world-laptop approve-current --world-id ID --expected-digest DIGEST
--review-note "I reviewed this already authored canon." followed by
world-laptop compile, then world-laptop engine-inspect --world-id ID
--era eight_bit_tile_1983. Supply the exact engine.source_digests object as
JSON to world-laptop engine-compile --expected-digests-file FILE; finally run
world-laptop engine-verify. The adapter invokes StudioEngineStore directly,
preserving its nine-plane review, temporal and original asset requirements.
A minimal world without those planes fails closed with not_found.

Before persistence, the read-only Jeeves world.laptop_propose_preview tool
accepts a typed prompt brief and returns canonical source plus ending proof
without writing or implicitly approving any file. The operator then uses
world-laptop propose to persist the same deterministic original source.

## Read-only laptop acceptance rehearsal

After compile and verify, run `python -m skeleton world-laptop --store STORE
acceptance --world-id lighthouse`. To check a previously persisted slot and its
portable save without overwriting it, add `--slot player`. This operation
verifies the exact canonical review and both published artifacts, replays each
proved ending witness, validates a portable session export/import roundtrip,
and optionally checks the existing slot's restore preflight. It writes no
worlds, approvals, artifacts or player slots. A changed source, missing slot,
corrupted HTML/builder or forged session fails closed with a typed error.

Run `python -m pytest skeleton/testing/test_jeeves_world_laptop_acceptance.py
skeleton/testing/test_jeeves_world_laptop_flow.py -q` on the exact branch
before promotion. Acceptance is offline source evidence only; it does not
certify native engines, model inference, Windows installation or consumers.

The read-only `diagnose` command now checks ending replay and portable
roundtrip acceptance before reporting a builder handoff as ready for engine
validation. A passing source-level rehearsal is not proof that a native game
runs on a laptop. Portable save checksums detect accidental corruption but
are not cryptographic authentication of an external player history; replay
validation prevents impossible transitions, not a valid alternative history
whose checksum was recomputed by its author.

## Atomic player custody

All laptop session create, choose, inspect, export and restore-check operations
now verify the exact approved source, review digest, playable HTML, builder
recipe and receipt under the **same world lease** as the player session access.
The previous separate verification and session lock could accept an approval
or artifact change without a world digest change. The new guard rejects such
changes before any session publication. Other SessionStore owners retain their
original direct API and acceptance's already-locked read path remains safe.

Focused tests: `python -m pytest skeleton/testing/test_jeeves_world_laptop_atomic_session.py skeleton/testing/test_jeeves_world_laptop_acceptance.py skeleton/testing/test_jeeves_world_laptop_flow.py -q`.
This is source custody only, not a model, Windows or consumer qualification.
