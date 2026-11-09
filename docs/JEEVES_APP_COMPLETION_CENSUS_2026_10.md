# Skeleton full-app deathmarch ledger (2026-10-13)

This is a **source-grounded completion register**, not a claim of a finished app. A file, signed volume, planned capability, PR, or deployed service name is not proof of a working user-visible feature. All release claims require exact-head CI and real installed-product acceptance.

## Machine authority baseline

| Register | Source-declared count | Qualification limitation |
| --- | --- | --- |
| AI masterplan | 421 volumes: 414 verified, 7 hardened implementation states | Labels are not product/runtime acceptance |
| Enterprise AI | 421 designed; 0 enterprise-qualified | Independent benchmark/golden-journey gates required |
| Product AI | 9 capabilities; 5 partial, 3 transport-partial, 1 planned | 0 marked complete |
| App construction | 27 planes, 17 declared closed gaps | P0 evidence ledger is a narrower subset than P0+P1 construction |
| App services | 5, including optional Chroma | Installed startup not established |
| Enterprise system | 11 domains, 16 workstreams, 12 required journeys | implementation_state is not_claimed |
| App contract | 75 required paths | Presence does not certify operation |
| AI file tree | 179 mapped and 24 native owners | Migration is not function |
| Prior Jeeves inventory | 58,884 tracked regular files at a prior exact Git SHA | Historical source count; not today's operational tool count |

The `ai.completion` Jeeves operation reads 8 allowlisted manifest authorities through the existing protected appwide source reader, with source and Git blob receipts; reports the P0 evidence/overall construction distinction, missing paths and owners, enterprise grade, nine AI capability states, and outstanding release gates. It never silently derives a full-app completion score.

## Full application feature-family register

| Group | Feature families | State from available authority |
| --- | --- | --- |
| Product | Desktop/web shell, navigation, workspaces, editors, sessions | Source present; full release unqualified |
| APIs | Application API, engine API, route identity, auth, tenants | Declared; full runtime acceptance open |
| Infrastructure | Mongo, Chroma, persistence, outbox, storage, crash recovery | Declared; installed recovery unqualified |
| AI assistant | Text, context, multi-turn chat, local GGUF, retrieval-grounded answers | Partial in product capability registry |
| AI actions | Safe read/write tools, approvals, workflow orchestration, Supervisor/Secretary/Worker | Partial; privilege and recovery acceptance open |
| AI cognition | Planning, inference, routing, model quality, verification, memory, training | Code/plan exists; model quality not certified |
| Knowledge | Search, source indexing, provenance, citation, almanacs, RSS | Integration/factual evaluation open |
| Crawler | Web/media research, source safety, timed recrawl, glean, distillation | Modules present; live full-flow unqualified |
| Dragon | Mother dragon, idle hatchlings, tamagotchi UI, consent and evolution | Modules/PR work; integrated release unqualified |
| Jeeves | Agent runtime, whole-app inventory, registered adapters, source analysis, self-improvement proposals | Draft PRs #3718, #3729; not mainline release |
| AI chat | Conversation replay, witnessed dialogue, spoiler safety, game handoff | Draft PR series #3714, #3717, #3719, #3727 |
| Game authoring | System editor families, game maker, story studio, original forge | Implemented pieces and drafts; end-to-end acceptance open |
| Worlds | Eras, themes, procedural map, non-solvable worlds, paths, replay | Engine work present; playtest qualifications open |
| NPC/gameplay | Witnessed choice, quests, societies, events, navigation, AI simulation | Draft PR series #3699–#3716; integration open |
| Narrative | 100 chapters, 1,000 acts, 9,999 scenes, branch/ending quality | Draft PR #3720; no full produced game certified |
| Game systems | Maze, RPG, platformers, puzzles, fighting, rhythm, survival, racing, factory, colony, sports and other genre families | Engine implementations; complete acceptance not proven |
| Platforms | Original homebrew ROM/native exporters, modern engine packaging, console/PC era profiles | Source present; per-target emulator/hardware evidence open |
| Visual/media | 2D/3D/voxel animation, assets, art, sound, video and speech | Components and partial provider transports; final media quality open |
| Legal | Asset rights, originality, plagiarism, licenses and homebrew boundaries | Modules present; content-specific release review needed |
| Quality | Replay, adversarial mirrors, independent scoring, feedback promotion | Code/plan exists; independent comparator certification open |
| Tooling | Repository organization, machine indexes, duplicate handling, file tree migration | Multiple unmerged indexing PRs #3722–#3728 |
| Delivery | App assembly, installer, native portability, CI, supply chain, rollback | Release evidence not established |
| Enterprise | Privacy, resilience, SLO, incident recovery, quotas, observability, 12 journeys | Designed; production implementation not claimed |

Each group contains many distinct features and variants. They are not binary counts or a substitute for an exhaustive, automatically refreshed per-feature acceptance graph.

## Major deathmarch milestones, ordered by dependency

1. **DM01–DM04: Trustworthy census and graph.** Source-pinned whole-app readiness, appwide UI-to-API-to-runtime action bindings, missing owner/feature inventory, canonical consolidation of overlapping indexing PRs.
2. **DM05–DM08: Working AI.** Real trained local model, grounded claim verification and refusal, safe tool effects, recovery-safe chat and model routes.
3. **DM09–DM12: Working Jeeves.** Explicit adapters across editors/forges/crawler/companion, permission leases and operator review, supervised code improvements, full agent crash/replay proof.
4. **DM13–DM18: Finished Game Studio.** Prompt-to-playable and native export, tested advanced engine families, coherent NPC/quest/worlds, 9,999-scene production and game handoffs, automated adversarial game acceptance, verified hardware/homebrew/rights.
5. **DM19–DM22: Durable learning.** Dragon crawler and media acquisition with safety provenance, fact-checked almanac, source-expiry reconfirmation, independent sandbox improvement tests before shadow-to-normal-to-hyperweight promotion.
6. **DM23–DM26: Full assembly.** Real user/device smoke, authorization and multitenancy, data-loss fault injection, native installer/updater and measured performance envelope.
7. **DM27–DM30: Product/enterprise release.** 12 system journeys, 16 enterprise workstreams, independent per-volume qualification, gated canary and tested rollback.

## Actual tests and acceptance

```bash
python -m py_compile skeleton/ai/game_builder/jeeves_completion_census.py
python -m unittest tests.test_game_builder_jeeves_completion_census tests.test_game_builder_jeeves_appwide_fabric tests.test_game_builder_jeeves_capability_intelligence -v
python scripts/check_architecture_map.py
python scripts/check_ai_app_construction.py
python scripts/check_capability_interfaces.py
python scripts/check_provider_bootstrap.py
python scripts/check_enterprise_ai_superiority.py --json
python scripts/check_enterprise_ai_implementation_notes.py --json
```

This branch implements DM01/DM02. L00–L13: owner is the preexisting Jeeves appwide runtime; machine authorities are inputs, not alternate state owners; outputs are content-addressed read-only evidence; private paths/symlinks/duplicate JSON/oversized documents fail closed; no persistence, shell, model promotion, or mutation is added; tests gate Windows/Linux exact-head; rollback is additive code/action/test/workflow removal. The whole-app completion percentage is deliberately **unmeasured**, while registry-level complete AI product capabilities on main are **0/9 (0%)**.
