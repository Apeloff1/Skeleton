# Interactive market commissions and acceptance

Commands:

    python -m skeleton scene-market-contract-play demo
    python -m skeleton scene-market-contract-accept demo

The interactive interface consumes one canonical market action per line:
move north, collect find_key, travel gate, buy copper_badge, craft seal_press,
deliver sanctuary_seal, or a strict JSON action. JSON-line responses include
a contract board, accepted/rejected action receipts, bounded retry counts,
source and state digests, interval checkpoints, and a terminal checkpoint.
EOF and repeated invalid input emit a verified resumable checkpoint before
a nonzero exit. The reducer is shared with non-interactive simulation.

Acceptance independently reconciles the same source and action journal across
canonical simulation, split-save replay, portable export/import, interactive
streaming, terminal checkpoint, nonspendable score, earned market inventory,
tamper rejection, and transactional authoring receipts. It fails closed if
any evidence differs. It does not certify Windows/WSL2 hardware, signatures,
consumer installation, marketplace delivery, CI or release readiness.

Focused suites:
    python -m pytest skeleton/testing/test_scene_market_contract_interactive.py
    python -m pytest skeleton/testing/test_scene_market_contract_acceptance.py
