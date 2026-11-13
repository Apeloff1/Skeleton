# Mixed original-game library replay continuity

Use `python -m skeleton app audit-mixed-library-continuity` to verify a staged
save upgrade for an already installed mixed catalog of original games. Provide
`--before-unsigned-entry`, `--after-unsigned-entry`, `--before-signed-entry`
and `--after-signed-entry` as repeated strict JSON entries in matching
order, followed by `--trusted-local-operator`. Each entry is the
same independently pinned descriptor used by the corresponding signed or
unsigned library audit. Both signed and unsigned groups must be present.

The operation re-audits each complete library, reexecutes both saves against
the independently pinned installed original world, and requires the new replay
to preserve every previous action receipt. A strict prefix is accepted; an
equal-length fork, replay rollback, swapped game identity, cross-project save
alias, source change, signer-policy change or mutation during final recheck
fails the entire batch. At least one game must advance. No save is written.

This is **read-only, point-in-time continuity evidence**. It is not a
persistent anti-rollback counter or a trusted current-policy revocation feed.
An old signed policy history is not made fresh by matching the previous
snapshot. No native Godot/browser device, executable package signature,
original-content rights, publisher identity or consumer release is certified.

Run the focused acceptance after remote publication:

`pytest -q skeleton/testing/test_app_offline_mixed_game_library_continuity.py`

Preserve all malware, secret, workflow-input, CodeQL, dependency, and release
holds until required exact-head checks succeed.
