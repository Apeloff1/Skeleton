# Studio A — reviewed faction reputation

The `world-factions` vertical connects original-author intent to typed
faction rules, explicit review, optimistic-CAS private persistence, canonical
player replay, and a source-verified browser playable handoff.

1. Create a world using `python -m skeleton world-canon --store PRIVATE propose
   --id ferry --premise "Cross the river" --protagonist Iris --region River
   --goal "Reach the far shore"`.
2. Propose a faction using `python -m skeleton world-factions --store PRIVATE
   propose --world-id ferry --prompt "Earn trust" --faction-id ferrymen
   --name Ferrymen --description "River pilots" --choice-id pursue_goal
   --delta 12 --reason "Chose to cross"`.
3. Inspect the returned digest; use `edit --operation-json JSON
   --expected-digest DIGEST` for typed, atomic reviewable edits.
4. `approve --note "Original author reviewed" --expected-digest DIGEST`
   is an explicit operator action. Every edit revokes approval.
5. `compile --expected-digest DIGEST` publishes a playable HTML, source-bound
   faction handoff, and receipt; `verify` replays the compilation and checks
   all bytes against canonical source. `player --slot SLOT` derives reputation
   from a real saved session, not an editable score claim.

The ending witness is the shortest deterministic canonical world path.
It does not prove every possible ending trace has identical reputation.
Reputation saturates at [-100, 100]; only legal choice events change it.
A checksum detects corruption, not author identity or rights ownership.
This feature does not grant release, device, multiplayer, or authenticity
certification. Source and replay leases fail closed on revision changes.

Source: `skeleton/jeeves/worlds/factions.py`. Focused regression fixtures:
`skeleton/testing/test_jeeves_world_factions.py`.
