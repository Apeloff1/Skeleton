# Authored scene schedule (Studio A)

The operator supplies an exact source digest, canonical quest actions, and a
bounded schedule JSON object with three fields: `scene_ticks` (one strictly
positive duration per authored scene), `npc_turnaround_ticks` (nonnegative
cooldown between appearances of the same NPC), and `min_start_ticks`
(optional nonnegative earliest scene starts). These ticks are author estimates,
not wall-clock time, animation timing, or evidence that the game engine ran.

The canonical `compile_dialogue_staging` and `replay_quest` owners verify
the exact authored scenes, source identity, NPC identity, quest prerequisite
order, selected alternatives, and session lease. A schedule cannot reorder
quest prerequisites, forge NPC testimony, or claim an ending was delivered.
Each scene carries an independent content digest. The full result binds the
authored timing request, scene source and quest replay to a stable digest.

CLI: `python -m scripts.studio_scene_schedule_cli --project PROJECT
--expected-source DIGEST --schedule '{"scene_ticks":{"origin":4,"contest":6,
"settlement":3},"npc_turnaround_ticks":2,"min_start_ticks":{}}'`

Use `--publish-directory EXISTING_DIR` to create an exclusive private
`scene_schedule.json` without overwriting existing evidence; use
`--verify-directory EXISTING_DIR` with the same source and quest actions to
replay the stored schedule. The implementation walks directory descriptors
without symlinks, writes an fsynced temporary file, then atomically hard-links
the completed receipt into its final name. The final file is mode 0600.
Unsupported secure descriptor environments fail closed.

Jeeves discovers `studio_authored_scene_schedule` through the existing
operator-gated static world-tool allowlist. The typed tool is read-only;
publication is a separate explicit CLI operation. This is an offline editor
and replay handoff, **not** native engine or consumer release certification.
