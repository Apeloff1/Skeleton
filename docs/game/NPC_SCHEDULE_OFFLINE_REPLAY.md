# Offline deterministic NPC schedules (FLGB-13 consumer)

This is a canonical gameplay extension under `skeleton/game/gameplay`, not a
second simulation engine, a network provider, or an AI NPC model. The player can
visit original NPCs at deterministic world ticks, make one-time interactions,
unlock facts, advance the world clock, and restore the exact event stream from
a content-bound saved command log. The CLI runs with no network access.

## Original end-to-end Lantern Harbor journey

The lighthouse keeper Mira requests a lens repair. Dockwright Sol repairs the
lens at the workshop, after which Mira lights the beacon at tick 8 and Sol
opens the tide gate at tick 12. These are original authored interactions,
not generated audiovisual assets or third-party character likenesses.

```sh
python -m scripts.npc_schedule_cli \
  --schedule skeleton/testing/fixtures/lantern_harbor_npc_schedule.json \
  --commands skeleton/testing/fixtures/lantern_harbor_npc_commands.json \
  --save /tmp/lantern-harbor-save.json
python -m scripts.npc_schedule_cli \
  --schedule skeleton/testing/fixtures/lantern_harbor_npc_schedule.json \
  --resume /tmp/lantern-harbor-save.json
python -m pytest -q skeleton/testing/test_npc_schedule.py
```

The CLI only creates a new save and refuses to overwrite an existing name.
Save creation uses a same-directory temporary regular file, fsync and an
atomic no-clobber hard link, with cleanup of the temporary name. File input
refuses symlinks and oversized JSON. The CLI never invokes a provider.

## Determinism and authority

Schedule digest commits to world, canon digest, initial facts and every NPC
route. A stop is active in `[start_tick, end_tick)`; stops of the same NPC
cannot overlap, interaction IDs cannot repeat within a route, and world ticks
cannot move backwards. Interactions require matching player, NPC, current
tick, location/interaction ID and previously earned facts. An interaction
can be consumed once only. Canonical `EventBus` commits to every advance
and interaction; `SaveableGameplayState` binds world, canon, tick, replay
state and optional parent save digest. Restoring re-executes all commands
through the actual gameplay module and checks both digests. Unknown fields,
non-integer ticks, forged saves and unbounded commands fail closed.

Limits: 512 NPCs, 256 stops/NPC, 4,096 facts, 8,192 commands, 1,000,000
ticks, and 2 MB per CLI JSON input/save. No claims of real-time NPC pathfinding,
native 3D animation, model inference, or device qualification are made.

## Integration and qualification

Upstream: authored world and canon digest, FLGB-13 gameplay event bus.
Downstream: a CLI-consumable JSON snapshot and an inspectable active-NPC
view suitable for a builder UI adapter. Consumers must validate the original
source digest before replay and must not silently substitute missing canon.

Focused tests exercise the canonical gameplay module, original fixture,
save/restore, no-clobber publication, symlink and oversized input refusal,
replay tampering, prerequisite failure and deterministic event ordering.
Required repository-wide architecture, security, exact-head CI, independent
review, device and release gates remain pending until actually executed.
