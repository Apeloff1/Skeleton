# Arena Forge Run — playable salvage and equipment

This Studio B product integrates authored tactical arenas with earned salvage,
bounded equipment crafting, player loadouts, combat, deterministic saves,
portable export and full replay validation.

Commands (from the installed Python application):

    python -m skeleton arena-forge demo
    python -m skeleton arena-forge preview --source-json SOURCE
    python -m skeleton arena-forge simulate --source-json SOURCE --actions-json ACTIONS
    python -m skeleton arena-forge resume --session-json SAVE --actions-json ACTIONS
    python -m skeleton arena-forge verify --session-json SAVE
    python -m skeleton arena-forge export --session-json SAVE
    python -m skeleton arena-forge import --bundle-json BUNDLE

The original Lantern Harbor example plays salvage, crafting, equipping, then
a second tactical encounter. The authored source binds world, hero, stages,
drops and recipes. Materials are awarded only after canonical verified combat
victory. Equipment changes attack and defense in the actual tactical engine;
durability decreases after fights. Movement, collision and line of sight remain
owned by the existing arena runtime.

Every action is replayed from source with an event receipt, state digest and
parent-linked save. Portable import checks the bundle digest and rebuilds the
entire history. Digests detect corruption but are not signatures. No network,
provider calls, executable authored scripts or unbounded filesystem writes.

Limits: six stages, twelve recipes, 96 actions, 64 tactical turns per stage,
128 earned material units, and 2 MiB output. Unknown schemas, source drift,
duplicate IDs, stat overflow, forged materials, and mutated saves fail closed.
The existing expedition schema and save formats remain unchanged.

Focused validation:

    python -m pytest skeleton/testing/test_arena_forge_run.py -q

Source publication is not device qualification or release certification.
