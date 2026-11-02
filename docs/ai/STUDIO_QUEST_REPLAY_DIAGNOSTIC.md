# Source-leased quest replay fault localization

Studio A's authored quest replay diagnostic takes a registered original
blueprint, an exact canonical quest-source SHA-256, an initial quest-session
SHA-256, a target authored ending and a bounded proposed action sequence.
It replays each action through the existing quest engine, identifies the
first illegal action without executing later actions, and reports a verified
legal prefix with the next canonical authored choices.

The result distinguishes `invalid_action`, `ending_unmet`,
`final_session_digest_mismatch` and `verified`. Unknown external evidence
never becomes sandbox evidence. A verified receipt may produce a **sandbox**
playable-handoff descriptor only after replaying the exact ending witness.
It is not proof of a native game, real-world observations or release readiness.

Use `python -m scripts.studio_quest_replay_diagnostic_cli --project PROJECT
--expected-source HEX --expected-session HEX --prompt` to inspect the
first ending with an empty replay. For an authored plan, pass `--plan-file`
with strict JSON of exactly these fields:

```json
{
  "actions": [["arrival", "observe"], ["report", "truth"]],
  "target_ending": "honest",
  "expected_final_session_digest": null
}
```

`--handoff` refuses invalid or unmet replay. `--publish DIRECTORY`
creates a private, exclusive, source-replay-verified JSON receipt; `--restore
DIRECTORY` reads it through a descriptor-anchored, no-follow, bounded path.
Neither path silently overwrites an existing file. The static Jeeves
world-tool catalog exposes `studio_original_quest_replay_diagnostic`;
the tool requires out-of-band authorization and exact typed source leases.

Regression: `pytest -q tests/test_studio_quest_replay_diagnostic.py`.
Native gameplay, consumer devices, external evidence and release remain held.

## Offline authoring editor

`--editor-preview` renders a standalone accessible HTML form with a
CSP-hashed static script and no network access. The form exports a typed
JSON plan and a source/session/baseline lease; browser output is never trusted.
Publish a baseline receipt first with `--publish DIRECTORY`, then import
using `--editor-export FILE --baseline DIRECTORY` with the same source and
session leases. The CLI replays the baseline and recompiles the edited plan
before any handoff. The export must be a private regular file, not a symlink,
and must fit the 32 KiB bound. No implicit overwrite or privilege grant.
