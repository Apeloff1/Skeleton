# Deterministic scene mission director

The installed `python -m skeleton scene-mission demo` runs an original
Lantern Hollow story with a choice, key collection, scene travel, three
dependency-ordered missions, earned reputation and a verified ending.
The director composes the existing `skeleton.scene_travel.v1` canonical
runtime, not a replacement movement engine.

Authored `skeleton.scene_mission.v1` sources declare a canonical scene
world, location-bound decisions with explicit reputation consequences,
mission triggers (visited scene, collected pickup or selected option), a
dependency DAG and ending requirements. The director uses the canonical
`QuestNode` / `quest_order` contract to reject missing/cyclic dependencies.
Each mission may complete once only, when its prerequisite missions and
replay-derived trigger are satisfied. An ending requires the actual terminal
scene outcome, completed missions and earned reputation.

```sh
python -m skeleton scene-mission demo
python -m skeleton scene-mission simulate --source-json '<JSON>' --actions-json '<JSON>'
python -m skeleton scene-mission resume --session-json '<JSON>' --actions-json '<JSON>'
python -m skeleton scene-mission verify --session-json '<JSON>'
python -m skeleton scene-mission export --session-json '<JSON>'
python -m skeleton scene-mission import --bundle-json '<JSON>'
python -m pytest skeleton/testing/test_scene_mission.py -q
```

All decisions are offline and data-only. The director never executes authored
scripts or trusts client-reported rewards. Source identity, canonical scene
replay, event receipts and save parent digests are reconstructed on import.
Checksum bundles detect corruption but do not establish trusted authorship or
asset license rights. Mission action count is capped at 512, source JSON at
128 KiB and snapshots at 2 MiB. Existing scene saves retain their original
schema and CLI; mission saves use a separate explicit versioned adapter.
