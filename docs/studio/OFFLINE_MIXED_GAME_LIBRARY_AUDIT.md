# Mixed signed/unsigned original-game library acceptance

The canonical CLI `python -m skeleton app audit-mixed-game-library` checks a
bounded local catalog during the transition from unsigned original games to
detached Ed25519 source-signed archives. It is an **observational, read-only**
cross-custody audit, not a signature conversion or native device test.

Pass at least one `--unsigned-entry` JSON object matching the
`audit-offline-game-library` schema and at least one `--signed-entry` JSON
object matching `audit-signed-game-library`. Each object must contain the
operator's independent archive, manifest, save and (for signed entries) key
and ordered policy SHA-256 pins. Supply `--trusted-local-operator` explicitly.
Maximum total is eight games, of which no more than four may be signed.

The command validates both schemas and budgets before opening sources. It
rejects overlapping path custody between the two classes and shared inode
identities even under different names. Each class independently verifies its
archive, installed source, saved replay, signer and policy history (where
applicable), then the mixed operation checks unique project IDs and repeats
both complete audits. A mutation or same-byte inode replacement between
passes blocks the entire receipt.

Successful output includes a deterministic SHA-256 over the path-free,
project-sorted game inventory. Each game explicitly reports
`source_signed: true/false`; unsigned sources are never upgraded by wording
or by the presence of signed neighbors. No private save bytes or local
filesystem paths appear in the acceptance receipt.

The status remains `mixed_original_game_library_replayed_release_blocked`.
Neither an operator-supplied policy chain nor its epoch number proves
freshness or durable anti-rollback. No native Godot/browser device, Windows
installer, signing authority, rights clearance, publisher identity or
consumer release is certified. All pre-existing security and release holds
remain in force.

## Acceptance

Run `python -m pytest -q skeleton/testing/test_app_offline_mixed_game_library_audit.py`
on a supported POSIX executor. The tests build and install a separate original
unsigned game, reuse the genuine signed game fixture with a two-epoch policy
chain, replay private progress, and exercise path aliasing, inode aliasing,
operator denial, malformed JSON, bad independent pins, oversized catalogs,
same-byte replacement and cross-mode project collision.

The CLI is intentionally strict: a mixed library with no unsigned games or
no signed games must use the existing homogeneous audit commands instead.
