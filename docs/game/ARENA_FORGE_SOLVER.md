# Arena Forge Solver — deterministic equipment and combat planning

This source-bound solver searches actual forge actions: fights, earned-salvage
crafting, equipping and unequipping. Each candidate is executed by the real
tactical arena runtime, including movement, combat, durability and rewards.

CLI:

    python -m skeleton arena-forge-solve demo
    python -m skeleton arena-forge-solve plan --source-json SOURCE
    python -m skeleton arena-forge-solve resume --session-json SAVE
    python -m skeleton arena-forge-solve verify --source-json SOURCE --plan-json PLAN

The original Lantern Harbor tutorial includes a tough tide-guard encounter
which needs equipment earned from the first stage. Results are shortest
routes within the bounded deterministic search. A budget-exhausted search
is inconclusive rather than proof of unwinnability. No untrusted checkpoint
can create gear or rewards; all receipts are replay-checked.

Caps: 512 search states and 24 actions. No network or provider calls.

    python -m pytest skeleton/testing/test_arena_forge_solver.py -q

A plan receipt is integrity evidence, not an authorization signature.
