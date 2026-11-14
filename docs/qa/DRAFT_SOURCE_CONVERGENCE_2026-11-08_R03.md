# Draft-source reconciliation custody — 2026-11-08

## Status
**REVIEW-ONLY / DRAFT / NO MERGE / NO AUTO-MERGE / NO RELEASE.** Built as an immutable, exact-Git-blob integration child of #5081 at `ce4f067dd0acd5b7b45395b3e68bdfad00140d5d`, inheriting #5074 at `5166439f8f79319efc6099f49b05e28b19abef6c`. Original heads preserved. Neither upstream branch nor this candidate is release qualified; preserve all ancestor merge/security/device holds.

## Source cohorts
- PR #5084: 50 source Git blobs selectively staged from its full 51-path review diff.
- PR #5083: 10 source Git blobs selectively staged from its full 10-path review diff.
- PR #5082: 33 source Git blobs selectively staged from its full 33-path review diff.
- PR #5076: 4 source Git blobs selectively staged from its full 4-path review diff.
- PR #5085: 2 source Git blobs selectively staged from its full 2-path review diff.
- PR #5080: 2 source Git blobs selectively staged from its full 3-path review diff.
- PR #5078: 2 source Git blobs selectively staged from its full 2-path review diff.
- PR #5077: 2 source Git blobs selectively staged from its full 2-path review diff.
- PR #5075: 2 source Git blobs selectively staged from its full 2-path review diff.

Git-reused source files: 107; mirrored Git-blob entries: 38; total staged paths before manifest and ledger: 145; gross donor additions counted from GitHub file stats: 8886. No placeholders or randomly synthesized source files.

## Explicit omissions and merge conflict custody
- PR #5084: `tests/forge_ai_builder/test_model_planner.py` **NOT** copied — declined 43-test deletion.
- PR #5080: `skeleton/testing/test_ai_next_model.py` **NOT** copied — parent #5081 and next-model changes overlap; manual merge.
- #5079 is a sibling of #5081 with divergent `.machine/repository.toml`, `skeleton/app/offline_delivery_archive.py`, `skeleton/testing/test_ai_next_model.py` and shared backend imports. Do not choose one side's file blindly; merge independently after exact-source review.
- #5069 installer custody overlaps the integrated foundation and #5073; it is excluded to prevent double-merging a stale version.
- #5022, #4991, #4990, #4902 remain quarantined historical review heads; only the separately reconstructed source work in selected donor PRs is considered.
- #5084 source changes are mirrored under `skeleton/ai/forge` using identical Git blob SHA, and #5078 sandbox executor change is mirrored under `skeleton/ai/runtime/sandbox`. No source ownership cutover or migration signoff is implied. Two source-tree identity pins must be recalculated from the resultant Git tree.

## Validation and approval conditions
Run exact-head `python scripts/check_ai_file_tree.py`, `python -m compileall -q skeleton`, `python -m pytest -q tests/forge_ai_builder tests/qualification tests/game/test_b025_gameplay_state_migration.py tests/test_game_grid_goal_reachability.py tests/test_sandbox_executor.py`, relevant `skeleton/testing/test_godot_export_*.py` and first-install/flight tests, `cd frontend && yarn typecheck && yarn lint:ci`, canonical source inventory tests, complete Merge Readiness domain shards, Backend Quality, App Foundation E2E, Workflow Input Security, Secret Scanning, Malware Gate, Artifact Policy, Repository Hygiene, Dependency Review, Sealed Context Guard, Windows Installer and independent security review. Current-head GitHub CI must complete and succeed; queued, skipped, failed, ancestor or synthetic-only results DO NOT qualify. Windows 11/WSL2, actual Docker/GGUF/Godot, provenance, rollback and physical-device tests remain independently required before any release claim.

## Source file inventory (Git SHA bound)
- #5084 `skeleton/forge/ai_builder/edit/__init__.py` — `c8587cce504965d72d7c8809c629fc65c05ce323` (added)
- #5084 `skeleton/forge/ai_builder/edit/diff.py` — `4864e117d98debcb1d05ca66606194c1c7b1a359` (added)
- #5084 `skeleton/forge/ai_builder/edit/model_edit.py` — `fb464a7e35ba7429fdaf62d58c8921c6957ce371` (added)
- #5084 `skeleton/forge/ai_builder/edit/protocol.py` — `59a11c5fe7b42e39350beeeea9ec827033e56fe3` (added)
- #5084 `skeleton/forge/ai_builder/edit/rules.py` — `26eb6540ae5fc7e368c21b3db96a568168b40fa1` (added)
- #5084 `skeleton/forge/ai_builder/edit/session.py` — `0c4a025d775b322cb8fdb243da5a24d920f4363f` (added)
- #5084 `skeleton/forge/ai_builder/model_planner.py` — `e3762bc4627581e8640dc3ccdf507e16478564d0` (modified)
- #5084 `skeleton/forge/ai_builder/procgen/__init__.py` — `9a3b39ecb4b3ea5100d5d5fb4837234d97a988cd` (added)
- #5084 `skeleton/forge/ai_builder/procgen/biomes.py` — `c8181040be467dc3be9098d69e696377c69dd13a` (added)
- #5084 `skeleton/forge/ai_builder/procgen/bsp.py` — `b7eef02a1f887643906f5cf7e037a579fe79feec` (added)
- #5084 `skeleton/forge/ai_builder/procgen/canonical.py` — `96106a0bd62b8822496117bddb5ec520433ac1eb` (added)
- #5084 `skeleton/forge/ai_builder/procgen/checks.py` — `cf7b383506b63d3752c4876ff44da73acc2bd184` (added)
- #5084 `skeleton/forge/ai_builder/procgen/completability.py` — `712c56437524634c9205e9369e87b6a0d337ef60` (added)
- #5084 `skeleton/forge/ai_builder/procgen/config.py` — `1b5d26f6f3c83793cfea61cf3d69e99383c3f738` (added)
- #5084 `skeleton/forge/ai_builder/procgen/encounters.py` — `3157b6a4e15711af9ab23458bedafbe70ada7af9` (added)
- #5084 `skeleton/forge/ai_builder/procgen/erosion.py` — `9562f5b5e9a72b1ee0491b4c995dc0fe3ed2e251` (added)
- #5084 `skeleton/forge/ai_builder/procgen/errors.py` — `35762263db7d6478f33bb3d8bc4967992d122b70` (added)
- #5084 `skeleton/forge/ai_builder/procgen/fill.py` — `ec46431c1bbcc97bb08c11bc0106b769f93652d7` (added)
- #5084 `skeleton/forge/ai_builder/procgen/graph_rooms.py` — `c5d62b92a172532e78464ce33141924e8bdc5036` (added)
- #5084 `skeleton/forge/ai_builder/procgen/heightmap.py` — `81f38c24fd9a042a804d99d41a637a745037aba7` (added)
- #5084 `skeleton/forge/ai_builder/procgen/keys.py` — `f07438d8d79fb1e3371ca09ea0561e1166d33e44` (added)
- #5084 `skeleton/forge/ai_builder/procgen/layout.py` — `5a3745ac26af7de5a79095a3a4190b17f1fb4ccf` (added)
- #5084 `skeleton/forge/ai_builder/procgen/loot.py` — `e1fe594c4ff3a5382559ac666f288802b36d7da7` (added)
- #5084 `skeleton/forge/ai_builder/procgen/metrics.py` — `b3c481a2ee9aa632789e3c6913fb9857f12c6ffc` (added)
- #5084 `skeleton/forge/ai_builder/procgen/noise.py` — `87a5eac76d3fbbf9520d7611b05cd2d81b8b7224` (added)
- #5084 `skeleton/forge/ai_builder/procgen/rng.py` — `3f997bee0a411b3bc5225e7721d471cc1ab188ae` (added)
- #5084 `skeleton/forge/ai_builder/procgen/terrain.py` — `0b05118e442cef41ba419e070271cea3b7f2b583` (added)
- #5084 `skeleton/forge/ai_builder/procgen/tiles.py` — `531265218f1c53e38bb127836123d48dfa4c316f` (added)
- #5084 `skeleton/forge/ai_builder/prompt_normalizer.py` — `e30630211052ff997b8eed801128ba262799a595` (modified)
- #5084 `skeleton/forge/ai_builder/validate/__init__.py` — `f896fe89fbd39fa1f3357c093bd21f7ccc534883` (added)
- #5084 `skeleton/forge/ai_builder/validate/_common.py` — `55c4e00f1df9583fd18a63c11445cc41955a186b` (added)
- #5084 `skeleton/forge/ai_builder/validate/engine_ext.py` — `479331ebffd7338563f26db9565679580604949a` (added)
- #5084 `skeleton/forge/ai_builder/validate/playability.py` — `d3d502554e83de70b1b12e3acfd0bda84a1e2401` (added)
- #5084 `skeleton/forge/ai_builder/validate/qa_hook.py` — `891158d4f792b59e90706207ed5f4cfeed4df0b9` (added)
- #5084 `skeleton/forge/ai_builder/validate/references.py` — `e0c59d64cba74a808d1d46b23ec8c9a2842464ea` (added)
- #5084 `skeleton/forge/ai_builder/validate/schema.py` — `28c03cfac3346181ea06bb420307e1f08ac504f2` (added)
- #5084 `skeleton/forge/ai_builder/validate/scoring.py` — `b9a09b0abae763915a02b53ba118afd41b28756b` (added)
- #5084 `tests/forge_ai_builder/history_fake.py` — `35a16c1e7b0796b3e1f4b11a9105bdebb4f5f990` (added)
- #5084 `tests/forge_ai_builder/plan_fixtures.py` — `85ea39fe98e688c84129da2bdb095bbb85e13948` (added)
- #5084 `tests/forge_ai_builder/test_edit_diff_rules.py` — `7bf24f2bdf929730f6ba16b01f790775cb78d395` (added)
- #5084 `tests/forge_ai_builder/test_edit_session.py` — `49cd8b03db172fa61613b6aaaf46a9b8c74afc39` (added)
- #5084 `tests/forge_ai_builder/test_procgen_dungeon.py` — `ae76ac34ff7b8fe366511d124308fb0972270b57` (added)
- #5084 `tests/forge_ai_builder/test_procgen_encounters_loot.py` — `9ee3ac63b08d34eb23b915d1e6cb260c960d0f8d` (added)
- #5084 `tests/forge_ai_builder/test_procgen_fill_checks.py` — `5b7fc982b59a24933164cc31cb29e20866a22fe7` (added)
- #5084 `tests/forge_ai_builder/test_procgen_review.py` — `6061716cd71388f12ef3bd07be9e3d629bd99635` (added)
- #5084 `tests/forge_ai_builder/test_procgen_rng_terrain.py` — `e33d03002f0f6eee984145f4f61ef7a1f5179613` (added)
- #5084 `tests/forge_ai_builder/test_quarantine_fail_closed.py` — `65c7477391f5439246a62aff6d3f155fe3deb850` (added)
- #5084 `tests/forge_ai_builder/test_validate_playability.py` — `0cfd16557b676b247cb5b55939d05891ff09179f` (added)
- #5084 `tests/forge_ai_builder/test_validate_schema_refs.py` — `66935c5df5aeeb15bbc42985dcffb09c2f6c94fe` (added)
- #5084 `tests/forge_ai_builder/test_validate_scoring.py` — `f6fe264f9af2157433c6f36067338e1386380051` (added)
- #5083 `frontend/src/features/CreatorVisualEditor/__tests__/fixtures/pythonParity.json` — `0897debe9a55fb31dc03907af057056441399bf2` (added)
- #5083 `frontend/src/features/CreatorVisualEditor/canonicalJson.ts` — `ce16e2d7edec9c06e838bfed0b2a9a630d8cd800` (added)
- #5083 `frontend/src/features/CreatorVisualEditor/components/VisualSceneEditor.tsx` — `a057271b3abaf3556d05b1e79917b39f280d6ded` (added)
- #5083 `frontend/src/features/CreatorVisualEditor/creatorCommand.ts` — `0854a7306841df75b46f88368b8d834fb46ef163` (added)
- #5083 `frontend/src/features/CreatorVisualEditor/designGraph.ts` — `ccd7e1451ebf23b67e314bc9c5577481d0aad40c` (added)
- #5083 `frontend/src/features/CreatorVisualEditor/graphEdits.ts` — `9c31318ee9a288c7c8be8614e6ab169804f53569` (added)
- #5083 `frontend/src/features/CreatorVisualEditor/index.ts` — `9cdecc48058cc8e0bc74305ca41dc663918a374f` (added)
- #5083 `frontend/src/features/CreatorVisualEditor/semanticDiff.ts` — `22a835a5686be5e4d740d295019cef97a01dacf3` (added)
- #5083 `frontend/src/features/CreatorVisualEditor/sha256.ts` — `e8c1084a960118a4b91d7dffe9b6398320326d06` (added)
- #5083 `frontend/src/features/CreatorVisualEditor/strings.ts` — `34ad4333ca4ba307413578f0c3a99bc7dc9d1c85` (added)
- #5082 `docs/qualification/gf-m-harness.md` — `a7380a61aadbba0edbbc08c570edb17fc7cb25e9` (added)
- #5082 `skeleton/qualification/__init__.py` — `d929b70395a16fe59478eebae052dd134227027b` (added)
- #5082 `skeleton/qualification/__main__.py` — `419f4f1e07303165d96c3b72fb1f17e3d8794b6a` (added)
- #5082 `skeleton/qualification/cases/gfm-fps-01.json` — `bbb25e8c5166cb5e6871cbae39a5abcf8be22dfc` (added)
- #5082 `skeleton/qualification/cases/gfm-fps-02.json` — `bae9299dff7d886c2c7b3cd7e4fb5cc09813b860` (added)
- #5082 `skeleton/qualification/cases/gfm-perf-01.json` — `f51dfe03486f867b522641dadd7ef0721ae9b0ed` (added)
- #5082 `skeleton/qualification/cases/gfm-perf-02.json` — `3bfe33dd4a162b3889e929d62cf7a1c699a159e7` (added)
- #5082 `skeleton/qualification/cases/gfm-prom-01.json` — `31452d39040ddd920916bf45cbc7bfbb284cc46e` (added)
- #5082 `skeleton/qualification/cases/gfm-ret-01.json` — `420cbaf4c583434b2b1854fe3d9930d4d3b384d4` (added)
- #5082 `skeleton/qualification/cases/gfm-rpl-01.json` — `0f171989e7e97375f5ab4127676f0e7c88c51db4` (added)
- #5082 `skeleton/qualification/cases/gfm-soak-01.json` — `a3783e0595bd6a39a92e5994271631fe4c751916` (added)
- #5082 `skeleton/qualification/cases/gfm-soak-02.json` — `8e406e28f08b3c50579e677635e65713e2fc337e` (added)
- #5082 `skeleton/qualification/errors.py` — `06bbdb19fc2499791cf773f73b5a5ff34cdefcb7` (added)
- #5082 `skeleton/qualification/evidence.py` — `9e07ab1141e24c3c4be7e540136f2666ee4d9d03` (added)
- #5082 `skeleton/qualification/gates/__init__.py` — `a73297e67391025a959687122f733f192a429b0d` (added)
- #5082 `skeleton/qualification/gates/_stats.py` — `79c3bb4253a5faac4952cdaf032b8f00ca92be4f` (added)
- #5082 `skeleton/qualification/gates/fps.py` — `b88b4a9cc10d23413f63e5bfbe7c4e982c31bc5b` (added)
- #5082 `skeleton/qualification/gates/perf.py` — `117a5c391748bf6d44e9f946029312bcce8bb1b9` (added)
- #5082 `skeleton/qualification/gates/promotion.py` — `ad09c65cdc7a255330ef1ade77cf702490bcb27c` (added)
- #5082 `skeleton/qualification/gates/replay.py` — `073b7d02749f7d080f3c6ded267b7e5daff89416` (added)
- #5082 `skeleton/qualification/gates/retention.py` — `a1c7af2c1164cabc5da0c7843d9a5c5ea45068e2` (added)
- #5082 `skeleton/qualification/gates/soak.py` — `d11d58efc66bc9c91947f76710fe62cfe1337a25` (added)
- #5082 `skeleton/qualification/report.py` — `7541e448755562734f2011e3310f705fbd1df500` (added)
- #5082 `skeleton/qualification/runner.py` — `753254346d7ee644c3d9ba82fb042a224250048b` (added)
- #5082 `skeleton/qualification/schema.py` — `ab117616debcc3dd02feb23570d0e0fd73cf3ec7` (added)
- #5082 `skeleton/qualification/verdict.py` — `11137f21fa5111467d0e55c263ad6d5df5ed4248` (added)
- #5082 `tests/qualification/__init__.py` — `83836ffe2f4afce066b8484abb7515b5b11c23ec` (added)
- #5082 `tests/qualification/conftest.py` — `9a8a8e97c1fba2fc78b055c6604304e43c2ea698` (added)
- #5082 `tests/qualification/test_evidence.py` — `76c39c9febd82e94008ec72d7038d3163bdf1899` (added)
- #5082 `tests/qualification/test_gates.py` — `eed2ad013f5fba091d7137ee5702ecf9913edd3d` (added)
- #5082 `tests/qualification/test_quarantine_security.py` — `753bdf8dcf0486ee6407337f5cb041448f366d9b` (added)
- #5082 `tests/qualification/test_runner_cli.py` — `da4821d06d5b70fdcbe5885a81a4bb24fd30b0ab` (added)
- #5082 `tests/qualification/test_schema.py` — `c06547a4a6f94ee6cf6a82c9e3b46604c32db2da` (added)
- #5076 `skeleton/godot_export/export_cert.py` — `d603397b6ecfc428f06a0a8b36ad0afd26332d18` (modified)
- #5076 `skeleton/godot_export/provenance.py` — `1e82ee0097ed565fa73a4abc1b4942cbf5ffc0b8` (modified)
- #5076 `skeleton/testing/test_godot_export_provenance.py` — `d828f4d5371228378fcf0c3e56603169e9b77571` (modified)
- #5076 `skeleton/testing/test_godot_export_provenance_negative.py` — `5cf60d9549dee37d4a1540f91a93c21e264d013d` (added)
- #5085 `skeleton/game/gameplay/offline_grid_campaign.py` — `74db142e78d3ff8cb2f24d054722a2705b74da52` (modified)
- #5085 `tests/test_game_grid_goal_reachability.py` — `3e94f02b8c0c0c787fe68bcb72abb79385427a9f` (added)
- #5080 `skeleton/ai/runtime/operational_ai/transport/flight/event_stream/service.py` — `d4dda7ade0d540f29edac3f533e7cb58d9267cef` (modified)
- #5080 `skeleton/testing/test_ai_flight_event_stream.py` — `8826aecf1fdcd6355ebc9f54414d10f522ef68e0` (modified)
- #5078 `skeleton/sandbox/executor.py` — `2f5d5b7e8fd0ca2102b00d9343d8891732349f4a` (modified)
- #5078 `tests/test_sandbox_executor.py` — `b2fa8e045a0bb0c35eb7f6fa34be53c9d219c6e7` (modified)
- #5077 `skeleton/app/first_install.py` — `148e0ee1a727ae4dd58be7e1149cb97e7cc41cc7` (modified)
- #5077 `tests/test_first_install_provider_identity.py` — `b2a9aebf45266a208bb01cbd89f2aad2dfec1375` (added)
- #5075 `skeleton/game/gameplay/state_migration.py` — `11951e0b3a2a4c9b13e126c1fabb0847ad15d849` (modified)
- #5075 `tests/game/test_b025_gameplay_state_migration.py` — `1c2ecb8320e13fc918f33024a133483a2c25c77f` (modified)
