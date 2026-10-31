# Original offline combat sessions (candidate, not release-qualified)

This gameplay vertical connects the canonical FLGB-13 event/save authority
(`EventBus`, `SaveableGameplayState`) to the existing Combat Design damage and
telegraph rules. It does not invent a second combat damage model, install a new
service, use model-provider credentials, or claim a native engine implementation.

## Player workflow

The original source is `skeleton/testing/fixtures/combat_original_lantern_harbor.json`.
It contains no third-party art, ROM, music, SDK or game-derived IP.

```sh
python -m skeleton.app.combat_cli --source skeleton/testing/fixtures/combat_original_lantern_harbor.json
python -m skeleton.app.combat_cli --source skeleton/testing/fixtures/combat_original_lantern_harbor.json --command '{"action":"attack","attack_id":"lantern-jab"}' --output /tmp/turn1.json
python -m skeleton.app.combat_cli --source skeleton/testing/fixtures/combat_original_lantern_harbor.json --save /tmp/turn1.json --verify
python -m skeleton.app.combat_cli --source skeleton/testing/fixtures/combat_original_lantern_harbor.json --save /tmp/turn1.json --command '{"action":"guard"}' --output /tmp/turn2.json
```

All outputs are exclusive new files, with owner-only permissions. The CLI never
rewrites an existing save. A failed action never advances a persisted state.
The user can choose `attack`, `guard`, `rest`, or `heal` (when carrying
a healing item). The enemy follows a deterministic authored attack priority.
A winning fight yields the authored reward ID, not a minted transferable asset.

## Authoring contract

The `combat_session.v1` schema declares one world, encounter, player, enemy,
bounded attacks and optional original reward. Every attack uses the existing
Combat Design readability gate; illegible telegraphs fail before gameplay.
Physical and elemental damage are resolved by the existing canonical
`resolve_damage` function. Every turn is replayed from source plus command
history, with a source digest, full authoritative state digest, FLGB event bus
digest and FLGB save metadata digest.

Limits: at most 16 attacks, 128 player turns, 48KiB source JSON, 96KiB local
input/output, 100,000 HP, 1,000 stamina, and 20 healing items. Strict JSON
rejects duplicate keys and nonfinite numbers. Unknown source/command fields,
invalid attack IDs, insufficient stamina, invalid replay history, tampered
saves, symlink input and existing output paths are rejected. The CLI does not
load authored Python code, execute scripts, access networks, fetch assets, or
perform provider inference.

## Save, replay, and version migration

The source contract is `skeleton.game.combat_session.v1` and the save
contract is `skeleton.game.combat_save.v1`. The saved command list is the
only state transition authority. A loaded save is accepted only after complete
re-execution of the commands against the supplied exact source and comparison
of every saved field, including event sequence and digest. The input source
cannot silently change without invalidating prior saves.

No implicit migration exists from unknown schema versions. A future migration
must be explicit, source-bound and independently tested; the current reader
fails closed. Existing FLGB saves are not overwritten or reinterpreted.

## Gameplay and accessibility

The CLI reports explicit phase, HP, stamina, consumables, turn count and
verified hashes as machine-readable JSON, suitable for an accessible terminal
reader. The original fixture provides a reachable victory and replayable
failure/guard/heal actions. No visual animation, spatial collision, sound
rendering, Godot build or device gameplay is claimed. The authored attack
telegraph channels are validated source semantics, not evidence that a native
renderer or audio engine emitted them.

## Validation and release boundaries

```sh
python -m pytest -q skeleton/testing/test_combat_session.py
python scripts/check_architecture_map.py
python scripts/check_ai_app_construction.py
python scripts/check_capability_interfaces.py
python scripts/check_provider_bootstrap.py
python scripts/check_enterprise_ai_superiority.py --json
python scripts/check_enterprise_ai_implementation_notes.py --json
```

The focused suite checks a real victory, save reopening, source tamper,
replay forgery, guard, heal, resource limits, CLI permissions, duplicate JSON
properties, symlink rejection and deterministic event identities. Additional
exact-head repository checks and independent review are mandatory before PR
promotion or merge. Source existence is not end-user device qualification.

### Construction implications (L00-L13)

- L00–L02: game plane owns authored encounter source; FLGB and Combat Design
  retain their canonical state and damage responsibilities.
- L03–L04: local operator explicitly selects the source and output; no remote
  authority, tenant data, credentials or unreviewed code is granted.
- L05–L06: finite per-turn resources, bounded histories and no network
  dependency; replay is deterministic across restarts.
- L07–L08: source digests and FLGB event/save receipts preserve provenance.
- L09–L10: CLI exposes explicit errors, and saved outputs are immutable
  new-file snapshots that can be restored after interruption.
- L11–L12: deterministic original fixtures, adversarial tests, required
  architecture and exact-head CI remain the acceptance gates.
- L13: rollback removes the opt-in CLI and new source modules without
  changing existing save stores; versioned saves remain externally owned.

No production release, consumer qualification or cross-platform native
combat parity is asserted by this implementation alone.
