# Bounded NPC encounter solver

The solver finds an actual playable route through the canonical scene graph,
including pickup gates, NPC dialogue decisions, authored NPC schedules,
reputation and ending requirements. Search never grants an item, teleports
an actor, executes authored code or accepts a synthetic ending.

    python -m skeleton scene-npc-solve demo
    python -m skeleton scene-npc-solve solve --source-json '...' --ending-id rescued
    python -m skeleton scene-npc-solve verify --receipt-json '...'

The breadth-first traversal is deterministic and uses only actions accepted
by the existing NPC encounter and scene travel runtimes. It deduplicates
equivalent semantic positions with the current encounter tick preserved, so
time-dependent NPC availability is not conflated with static topology.

The solver has explicit maximum node and depth budgets (1024 and 64 hard
ceilings). It returns a complete replay-verified save, exact action sequence,
source digest, search bounds, explored-node count and integrity receipt.
Verification reruns the bounded search to establish the deterministic witness.

Unknown targets, unearned dialogue consequences, exhausted search budgets,
invalid source, altered actions and forged receipts fail closed. Checksums
detect corruption, not author identity. Consumer/device qualification is
separate from this offline runtime.
