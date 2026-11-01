# Source-bound original quest accessibility hints

This Studio A vertical produces spoiler-bounded accessibility hints from the
canonical quest DAG and an exact replayed quest session. Only stages currently
**available** or already **completed** may appear. The deterministic prompt
creates generic available-stage hints; authored text must remain bound to a
stage that the session has actually unlocked. Exact hidden stage and ending identifiers are blocked in visible hint text;
freeform prose is not semantically spoiler-certified and requires editorial
review. It cannot create choices,
unlock stages, mint evidence, reveal locked ending predicates, or certify
native gameplay.

Use `scripts/studio_quest_hint_cli.py --project <id> --expected-source
<source-sha256> --actions '[]' --prompt` to generate a typed deck. Use
`--authoring '<JSON>'` for source-leased edits. The shape is
`{"hints":[{"stage_id":"...","text":"...","audience":"available"}]}`.
`--editor-directory` writes a private CSP-hashed HTML editor that exports
typed JSON; `--import-authoring` and `--baseline-deck` enforce exact
source/session/baseline digest leases before recompilation. `--publish`
and `--restore` provide exclusive, descriptor-anchored private custody.

The static Jeeves router exposes `studio_original_quest_hints`. Optional
`--playable-manifest` verifies the existing original offline 2D game
compiler and reports a separate companion hint HTML digest. The companion
is not claimed to be embedded in a native runtime; consumer/device/release
qualification remains held.

Focused regression contract:
`pytest -q tests/test_studio_quest_hint_deck.py`.
