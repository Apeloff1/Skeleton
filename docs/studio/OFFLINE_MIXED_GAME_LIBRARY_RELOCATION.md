# Mixed original-game relocation proof

`python -m skeleton app audit-mixed-library-relocation` checks that an
independently installed original-game catalog retains its **explicit** signed
and unsigned classifications, pinned source archives, private saved progress,
and Ed25519 signer policy history across relocation.

Pass matching `--before-unsigned`, `--after-unsigned`,
`--before-signed` and `--after-signed` strict JSON entries. Each entry is
identical to its corresponding homogeneous library audit input. Supply
`--trusted-local-operator` and independent SHA-256 pins. At least one signed
and one unsigned original game are required, maximum eight total and four
signed. The before and after inventories must have equal counts in each class.

All installed source roots must be distinct across the four lists. The
operation performs both mixed library audits, verifies the before/after
project inventories match, runs the existing signed and unsigned relocation
proofs independently, and then reexecutes the mixed audits while comparing
descriptor identities. No source, private save or signer policy is copied,
deleted, installed, rewritten or upgraded by this command.

The receipt is path-free and explicitly retains `source_signed` per game.
The deterministic digest is derived from the canonical project-sorted
inventory. A signed-to-unsigned downgrade, changed private replay, changed
signer policy history, altered archive, source inode replacement, or alias
between installed roots blocks the whole handoff.

The status is `mixed_game_library_relocated_replay_verified_release_blocked`.
This does not establish atomic migration, package signing, publisher identity,
rights clearance, policy freshness, native device execution, or release
certification. Existing security gates and release holds remain required.

Focused acceptance:
`python -m pytest -q skeleton/testing/test_app_offline_mixed_game_library_audit.py skeleton/testing/test_app_offline_mixed_game_library_relocation.py`

The relocation fixture creates and installs a separate original unsigned
game and an Ed25519 source-signed game with historical policy snapshots,
then reinstalls each into a new source root. It checks replay continuity,
signer downgrade, archive mutation, same-byte inode replacement, root alias,
operator denial and deterministic receipt behavior. POSIX descriptor
custody is required; unsupported platforms must not be reported as verified.
