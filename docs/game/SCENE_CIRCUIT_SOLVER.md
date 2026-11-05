# Scene Circuit Solver — bounded playable victory routing

This extension searches real circuit switch, pickup and travel actions using
the canonical scene-circuit runtime. It returns a deterministic shortest
route and source/initial/final state digests. A saved checkpoint can be
continued without redoing previous actions. All candidate actions pass the
same gate conditions as end-user play.

CLI:

    python -m skeleton scene-circuit-solve demo
    python -m skeleton scene-circuit-solve plan --source-json SOURCE
    python -m skeleton scene-circuit-solve resume --session-json SAVE
    python -m skeleton scene-circuit-solve verify --source-json SOURCE --plan-json PLAN

A budget-exhausted search returns inconclusive, not unreachable. The state
key includes scene position, inventory, collected pickups and switch states.
Search caps: 4096 states and 96 actions. No external scripts, network,
provider calls, arbitrary filesystem writes or untrusted reward grants.

Validation:

    python -m pytest skeleton/testing/test_scene_circuit_solver.py -q

Solver receipts are replay evidence, not cryptographic authorization.
