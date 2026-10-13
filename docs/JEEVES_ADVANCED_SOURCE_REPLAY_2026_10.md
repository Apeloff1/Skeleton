# Advanced original game scene reference replay — October 2026

**DX-102–DX-108.** Jeeves now links actually saved original scenes to
the installed 29 advanced reference-gameplay families. This closes a
functional gap between source-only scene generation and concrete gameplay.

- \`studio.advanced.replay.plan\`: read an **existing human-committed**
  editor system and original authored scene; execute 0–128 typed real game
  commands using the correct editor, scene seed and current configuration.
  Verify the complete canonical action hash-chain and return exact source
  fingerprints, turn count, terminal status and actual resulting game state.
- \`studio.advanced.replay.stage\`: regenerate a reviewed exact plan and
  stage the **full actual session** as a content-addressed real source file
  \`game/replays/<editor>_<scene_id>.json\`.
- \`studio.advanced.replay.verify\`: load the **actual committed** replay
  from GameWorkspace; replay its command sequence from the previously
  saved scene and system, and compare the exact resulting session.
- Added GameWorkspace validator that **reruns real reference-gameplay** on
  both original-source proposal and eventual human commit. Source digest,
  game editor, scene seed, underlying system SHA, scene SHA, every action
  token, replay final state, trace hash chain and immutable source path are
  enforced. There is no trust in caller-supplied victory or fabricated
  session receipts.

This uses the current installed game engines and their actual deterministic
reference simulators. It does not execute target-hardware native binaries
or prove consumer release quality. An empty 0-turn session is a genuine
baseline simulation but **not** a claim of a completed game.

**Tests:** none executed during this user-requested build-only pass.
