# Interactive offline combat campaign

`combat-campaign-play` lets a player control the canonical hero across
multiple authored combat encounters. Enemy turns use the existing deterministic
tactical policy. All attacks, guard effects, rest healing, victories, carried
health, currency and save lineage remain owned by the canonical turn-combat
engine. The player cannot issue commands for enemy actors.

## Play and export

```bash
python -m skeleton combat-campaign-play demo
python -m skeleton combat-campaign-play start --source-json "$CAMPAIGN"
python -m skeleton combat-campaign-play act --session-json "$SAVE" --command-json '{"kind":"attack","target_id":"warden"}'
python -m skeleton combat-campaign-play act --session-json "$SAVE" --command-json '{"kind":"guard"}'
python -m skeleton combat-campaign-play resume --session-json "$SAVE" --commands-json "$PLAYER_CHOICES"
python -m skeleton combat-campaign-play verify --session-json "$SAVE"
python -m skeleton combat-campaign-play pack --session-json "$SAVE"
python -m skeleton combat-campaign-play unpack --package-json "$PORTABLE"
```

Each player action is validated on the actual hero turn, applied by the
canonical engine, then followed by deterministic opponent actions until the
next hero turn or terminal outcome. A victorious encounter carries earned
health and reward to the next authored encounter. Loss or draw ends the
campaign; no reward is granted for failed encounters.

The complete choice journal is replayed from the original normalized source
on every import. The portable manifest binds world, campaign, source, state,
save digest, current encounter, health, earned currency and player choice
count. Editing a turn, enemy action, reward, health, source, or save is
rejected. The source supports up to four encounters, 32 canonical turns per
encounter and 128 player choices. Payloads are bounded to 128 KiB.

The demo uses the deterministic hero policy to exercise a complete playable
route; normal play accepts the user's explicit hero decisions. No scripts,
network calls, providers, or arbitrary file paths are evaluated. Checksums
provide integrity and replay consistency, not distribution signatures.
