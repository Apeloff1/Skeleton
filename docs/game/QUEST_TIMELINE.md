# Replay-verified quest reward timeline and save branch comparison

The installed offline quest runner now supports `timeline` and
`compare` on canonical saved games. It reconstructs each completed
quest by executing the original source-bound trigger through
`QuestEngine`; no client-provided reward amount is accepted.

```sh
python -m skeleton.game.gameplay.quest_cli timeline \
  --plan docs/game/fixtures/lantern_harbor_quests.json --save SAVE.json
python -m skeleton.game.gameplay.quest_cli compare \
  --plan docs/game/fixtures/lantern_harbor_quests.json \
  --left-save LEFT.json --right-save RIGHT.json
python -m pytest skeleton/testing/test_quest_timeline.py
```

The timeline exposes per-event before/after state digests, exact currency
and item changes, completed quests, terminal ending, save digest and
receipt. Comparison distinguishes identical, prefix and divergent
replay histories, and reports the first divergence and final inventory
and currency for each branch.

Every input save is restored and replayed by the canonical quest engine
before analysis. All reports carry the exact authored plan digest.
Verification functions recompute every field and checksum; they reject
altered reward amounts, forged receipts and source mismatch.
Checksums provide integrity checks, not source authentication or a
payment authorization mechanism.

The command reads bounded, regular JSON files through the existing
quest CLI safe input path. No network, script execution or provider
is required. It is an offline game replay/debugging and acceptance
feature, not a consumer/device release certification.
