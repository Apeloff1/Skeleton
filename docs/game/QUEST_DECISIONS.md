# Quest decisions: preview, play and replay-verify

`python -m skeleton quest-decisions preview --demo` lists the currently
legal original quest moves. Each candidate is executed by the **canonical**
quest engine on an isolated verified session. The result shows actual NPC
choices, earned crafting inventory, combat health/currency, ending and a
portable export checksum. It is not an imagined LLM outcome.

For an existing save use `preview --session-json JSON --limit 12`. The
default preview limit is 12 and the hard maximum is 24. If legal actions
exceed that limit, `truncated=true` is returned; absence from a truncated
preview is never proof of impossibility. The source remains immutable.

To play one choice use `apply --session-json JSON --action-json JSON
--expected-state-digest SHA256`. The exact expected digest acts as a
compare-and-swap lease; stale saves, unavailable actions, terminal sessions
and forged rewards fail closed. The result includes the original verified
save, action and a portable replay-verifiable successor bundle. Verify with
`verify --receipt-json JSON`. Checksums detect tampering but do not
authenticate the game author or authorize any external operation.

Focused validation:

```sh
python -m pytest skeleton/testing/test_expedition_quest_decisions.py -q
python -m skeleton quest-decisions preview --demo
```

The preview is bounded, offline and user-reachable via the canonical CLI.
No hidden game state is mutated. Mandatory exact-head CI, device testing and
release qualification are separate requirements.
