# Studio A — readiness-gated real HTML5 playable

This end-user vertical extends the joint authored quest readiness proof into
an **actual deterministic original offline HTML5 game bundle** compiled by the
registered studio catalog. It does not accept user-supplied HTML, fabricated
gameplay receipts, or a partial/unknown quest safety proof.

The flow is prompt or bounded typed budget → canonical quest source and initial
session lease → independent ending coverage and exhaustive terminal-softlock
proofs → catalog HTML5 compiler and gameplay receipt → replay-verified ZIP
with `index.html`, `quest_readiness.json`,
`quest_readiness_handoff.json`, and `manifest.json`.

## Operator use

`python -m scripts.studio_quest_readiness_playable_cli --project PROJECT
--expected-source QUEST_SOURCE_SHA256 --expected-session EMPTY_SESSION_SHA256
--prompt --publish EXISTING_PRIVATE_DIRECTORY`

For a bounded explicit budget, use `--budget-file PRIVATE_JSON` containing
`{"max_states":512,"max_depth":12}`. To reuse a privately persisted joint
readiness receipt, use `--restore-proof DIRECTORY`. Verify a previously
published ZIP with `--verify DIRECTORY`; the complete bundle is rebuilt and
byte-compared, not merely checked against a caller-supplied hash.

Publication is exclusive, private (0600), descriptor-relative, nofollow and
fsynced. Verification refuses symlinks, hardlinks, nonregular/public files,
oversized reads, in-place replacement, source drift and forged proof digests.
Archive member names and metadata are fixed, sorted and reproducible.

The manifest intentionally keeps native gameplay, hardware qualification,
rights and release **false**. It proves only the canonical sandbox quest and
the registered HTML5 preview compiler. Neither the bundle hash nor source
hash is an authenticated developer signature.

Focused fixtures: `tests/test_studio_quest_readiness_playable.py`.
