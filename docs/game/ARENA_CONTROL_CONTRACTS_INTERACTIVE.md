# Player-controlled tactical capture bounties

`python -m skeleton arena-control-contracts-play demo` opens a JSON-line
player session. The control-point arena renders the board and legal actions,
the player controls only the authored team, and the canonical deterministic
opponent policy plays the other team. Every accepted action is recorded by
the control-point engine. The contract overlay then replays that complete
journal before settling any objective rewards.

Use `play --source-json JSON --team TEAM` for an authored source. Use
`resume --session-json JSON --team TEAM` with the verified contract
checkpoint returned after EOF or input-budget exhaustion. Invalid commands
return a rejected checkpoint with no speculative actions or rewards.
`verify --receipt-json JSON` validates the nested canonical journal,
contract save lineage, terminal status and integrity receipt.

The JSON-line stream contains player turns, legal moves, opponent actions,
and a final `contract_result`. This receipt is an offline replay-integrity
witness, **not** an authenticated identity or input provenance record.

Focused tests:
`python -m pytest skeleton/testing/test_arena_control_contracts_interactive.py -q`
