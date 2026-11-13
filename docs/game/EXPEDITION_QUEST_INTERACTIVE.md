# Playable offline expedition quests

Run `python -m skeleton quest-expedition-play --demo` to play the original
Lantern Harbor quest through NPC schedules, crafting, camp combat and earned
endings. The following commands form a complete original playthrough:

```text
talk guide aid
travel forge
talk smith aid
craft beacon
travel dock
travel camp
fight
buy tide_tonic
use tide_tonic
fight
finish beacon_lit
```

The JSON-line interface emits started, prompt, accepted, invalid, checkpoint
and terminal events. It uses the canonical expedition-quest state machine for
every move; no client can directly award currency, inventory or endings.
Prompts show location-bound travel, scheduled NPCs, available recipes,
shop actions and earned endings. `wait` advances the authored schedule.
A complete JSON quest action is also accepted, including a bounded
`fight_tactical` hero script validated by the canonical combat engine.

Use `--source-json` for an authored quest or `--resume-json` with the
full `session` from a checkpoint. `--source-digest` pins trusted source
identity before play. `--checkpoint-every` is 1..64; `--max-turns` is
1..96 per invocation. EOF, three invalid actions or budget exhaustion
emit a replay-verified checkpoint before failing. On earned terminal
completion, the portable bundle is exported and reimported.

These checksums detect corruption but do not authenticate game authors.
No network, external scripts or arbitrary filesystem access is performed.

Focused tests:
`python -m pytest skeleton/testing/test_expedition_quest_interactive.py skeleton/testing/test_expedition_quest.py -q`.
All required exact-head CI remains a release hold until completed.
