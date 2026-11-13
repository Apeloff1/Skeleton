# Source-bound timed market commissions

The offline Scene Market Contract vertical is built on the canonical market
runtime. It never duplicates or bypasses movement, collision, pickup custody,
spendable balances, crafting, finite stock or one-time delivery rules.

Run a complete original playable commission:

    python -m skeleton scene-market-contract demo

Use the returned session with the same CLI's verify, board, export and import
subcommands. To resume a partial game, supply --session-json and --actions-json.
The original demo earns the sanctuary seal, makes the one-time delivery,
collects five reputation and awards twenty-five nonspendable campaign points.

Authoring is transactional and source-digest-fenced:

    python -m skeleton scene-market-contract-author demo

The authoring receipt includes before/after sources, canonical operations,
digests and a checksum. Verification replays the exact edits. Changes to
deadlines, minimum reputation, rewards and required commissions never alter
canonical market item or credit custody.

The route tool uses only canonical legal candidate actions:

    python -m skeleton scene-market-contract-route demo

Search is bounded by --max-nodes and --max-depth. A found route is a
replayable witness of an actual win; an exhausted search is inconclusive, not
proof of an impossible game. No network, provider key or device qualification
is required for offline source/replay/export.

Safety: strict schema and unique IDs; source-bound saves; full replay from
the original market; one-time rewards; terminal deadline failure; bounded
actions and JSON; checksum tamper detection; optimistic authoring; no false
currency minting. Checksums are not cryptographic signatures. This proves
single-source deterministic gameplay only, not consumer release readiness.

Focused regression suites:
    python -m pytest skeleton/testing/test_scene_market_contract.py
    python -m pytest skeleton/testing/test_scene_market_contract_author.py
    python -m pytest skeleton/testing/test_scene_market_contract_route.py
