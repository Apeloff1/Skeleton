# Original-game multi-generation relocation assurance

Use `python -m skeleton app audit-mixed-library-epoch-relocation` with
matching two to six `--before-unsigned-generation`,
`--before-signed-generation`, `--after-unsigned-generation`, and
`--after-signed-generation` bounded JSON arrays plus
`--trusted-local-operator`. Each generation contains the independently
pinned source/archive/private-save and signed key/policy history.

The verifier independently reexecutes every original and relocated game at
every generation, proves every private replay prefix, verifies detached
signatures and complete policy histories, and rejects reused installation
inodes, altered games, rollback, forks, and mismatched generation counts.
It reexecutes the complete source and relocation proof twice and emits a
deterministic read-only evidence digest without changing either installation.

This is point-in-time, source-level relocation evidence only. It does not
copy games, migrate private saves, certify rights, verify consumer hardware,
sign packages, prove persistent anti-rollback state, or authorize release.
