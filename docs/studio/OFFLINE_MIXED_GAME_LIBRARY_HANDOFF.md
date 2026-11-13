# Durable mixed-game handoff

`python -m skeleton app mixed-library-handoff` publishes or rechecks a
bounded, independently pinned catalog containing original unsigned games
and Ed25519 source-signed games. The catalog must include both classes.
Use repeated `--unsigned-entry` and `--signed-entry` strict JSON inputs
matching their homogeneous library audit schemas and supply
`--trusted-local-operator`.

To publish, provide `--output <new-owner-private.json>`. The destination
must not exist and cannot be inside an installed source, archive, private
save, detached signing material or historical policy path. The publisher
checks the complete live replay twice, fsyncs a temporary receipt, links it
without clobbering an existing name, fsyncs the parent and reads back the
canonical receipt against its SHA-256. It replays the catalog again after
publication. Any uncertain post-publication result fails closed and leaves
the new receipt for operator-controlled quarantine; it does not blindly
delete an inode that another process may have replaced.

For inspection, provide `--inspect-receipt <existing.json>` and the
independently retained `--expected-receipt-sha256 <64 lowercase hex>`.
The inspector checks the owner-private inode, canonical JSON and independent
hash, reruns both signed and unsigned game catalogs, compares every receipt
field, and rejects same-byte inode substitutions between reads. The inspector
never writes to the receipt, game, private saves or signer policies.

The publication receipt is **not** an Ed25519 signature, release approval,
license, publisher identity, Windows installer, native Godot device test or
proof of policy freshness. An unsigned game stays explicitly unsigned even
when it shares a catalog with signed games. All security and release holds
remain active.

Focused regression:
`python -m pytest -q skeleton/testing/test_app_offline_mixed_game_library_handoff.py`
The test generates a real original unsigned game, uses a signed game with a
two-epoch policy chain, performs replay and no-clobber receipt publication,
then tests independent readback, bad pins, root aliasing, signer downgrade,
inode replacement, mutation during publication and operator denial.
