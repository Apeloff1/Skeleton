# Offline source-bound quest transactions

Owner: canonical FLGB-13 gameplay plane, under skeleton/game/gameplay.
Entry point: python -m scripts.game.quest_journal.

The authored plan declares a world ID, DAG of quest IDs, deterministic event
identities and bounded item/currency rewards. An event completes one quest only
when its exact event type, source identity and payload digest match the plan
and all prerequisite quests are complete. The completion is an authored game
rule, **not** cryptographic proof that a real-world action happened.

Use the canonical Python API QuestEngine(QuestPlan(...)).replay(triggers) to
obtain deterministic ending, inventory, currency and SaveableGameplayState
metadata. QuestEngine.restore(saved) reconstructs every event from genesis,
then compares the entire canonical state, source digest and save digest. A
changed source, event order, forged reward or edited ending is rejected.

CLI:
  python -m scripts.game.quest_journal inspect --plan plan.json
  python -m scripts.game.quest_journal run --plan plan.json --events events.json --save new-save.json
  python -m scripts.game.quest_journal verify --plan plan.json --save new-save.json

The CLI does not contact any provider or network. Inputs must be bounded
regular UTF-8 JSON files; duplicate object keys, non-finite values, unknown
schema fields and symlinks are rejected. Saves use private same-directory
temporary files, fsync and atomic no-clobber publication. Existing saves
cannot be overwritten. Only a caller-owned path should be supplied; this is
not a privileged filesystem service or a sandbox for hostile users.

Canonical focused tests:
  python -m pytest -q skeleton/testing/test_quest_session.py

Architecture/security holds: no native renderer, AI authoring, installer,
player authentication or release qualification is claimed. Completion trigger
digests are authored game event identities, not user authorization tokens.
This source branch remains WIP until actual exact-head CI and admission.
