# Replay-verified tactical capture contracts

Use the installed command `python -m skeleton arena-control-contracts demo`
to play an original offline beacon bounty. The contract source embeds a
canonical control-point arena, a player team, and up to twelve distinct
objectives. Objective types are `capture-zone`, `reach-score`,
`finish-by`, and `survive`. Rewards are credited only after a verified
terminal victory; unfinished sessions, losses, and draws cannot mint rewards.

The `new`, `play`, `resume`, `verify`, `pack`, and `unpack`
subcommands accept JSON arguments. A package contains the complete
source-bound checkpoint, the canonical action journal, a deterministic
save lineage, and a manifest derived from replay. Digests provide accidental
and adversarial mutation detection on replay, **not authentication** or
provenance. Never treat an untrusted package as signed content.

Use `python -m skeleton arena-control-contracts-author demo` to preview
an atomic reward edit. `edit` requires the normalized source digest as
`--expected-digest`, JSON operations, and a full playable preview action
sequence. Rejected edits do not publish partial source. The edit receipt
does not authenticate historical authorship.

Test with
`python -m pytest skeleton/testing/test_arena_control_contracts.py -q`.
All source, action, and export bounds are enforced by the canonical control
runtime. The source remains editable and portable offline.
