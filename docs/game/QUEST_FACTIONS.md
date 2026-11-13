# Quest faction consequences: offline playable contract

`python -m skeleton quest-factions demo` plays the original Lantern Harbor
beacon expedition, including authored NPC decisions, earned ingredients,
workshop crafting, tactical fights, shop purchases and a faction-gated ending.

The `skeleton.quest_factions.v1` source wraps a canonical
`skeleton.expedition_quest.v1` quest with a bounded list of factions. Each
faction declares its NPC members and signed aid/decline standing deltas. Each
ending may require minimum standings. The base quest remains authoritative
for travel, NPC presence, crafting, combat and earned ending requirements;
the faction policy adds a second fail-closed consequence gate.

## CLI

- `demo`: original offline campaign and its complete save.
- `simulate --source-json JSON --actions-json JSON`: authored play.
- `resume --session-json JSON --actions-json JSON`: replay then continue.
- `verify --session-json JSON`: reconstruct all nested quest and faction events.
- `export --session-json JSON`: bounded portable checksum bundle.
- `import --bundle-json JSON`: check the bundle and replay its contents.
- `compare --left-json JSON --right-json JSON`: compare two replayed branches.

All commands return canonical JSON on stdout or a structured error on stderr
with exit status 2. The source and every save use schema versions, source
digests and deterministic event receipts. Replay rejects fabricated standing,
inventory, purchases, checkpoints and endings. Digests detect corruption,
not authorship or access rights. This subsystem is local and requires no
network or hosted model.

## Authoring contract

```json
{
  "schema_version": "skeleton.quest_factions.v1",
  "campaign_id": "lantern_accord",
  "quest": {"schema_version": "skeleton.expedition_quest.v1"},
  "factions": [
    {"id": "harbor_wardens", "members": ["guide", "smith"],
     "aid_delta": 2, "decline_delta": -1}
  ],
  "ending_requirements": [
    {"ending_id": "beacon_lit",
     "minimum_standing": [{"faction_id": "harbor_wardens", "minimum": 4}]}
  ]
}
```

The abbreviated quest above is illustrative: supply a fully valid authored
quest or start from `original_factions()`. References must point to real NPCs,
factions and endings. No arbitrary state injection is accepted. Saves from
a changed source digest must restart; they are never silently transplanted.

## Acceptance and release hold

Focused contract: `python -m pytest skeleton/testing/test_quest_factions.py -q`.
Full integration and required exact-head CI must pass before promotion.
The demo is not evidence of device qualification, consumer installation,
cryptographic authenticity or complete game-release readiness.
