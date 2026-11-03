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
