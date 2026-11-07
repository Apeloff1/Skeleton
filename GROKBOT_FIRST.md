
# GROKBOT FIRST — Skeleton Completionist Engineering Constitution
**Document ID:** SKL-GROK-FIRST-2026-11-07  
**Repository:** https://github.com/Apeloff1/Skeleton  
**Audit baseline:** main at e00bfb0809b34573c2df313ea16e17fd10bead38  
**Audience:** one coordinating Grokbot and eleven equal-capability specialist bots, twelve active bots total  
**Scope:** secure local-first AI game production, original-world generation, complete playable games, asset and media pipelines, knowledge, integration, deployment, commercialization and independent assurance  
**Status:** living, source-anchored implementation constitution — NOT a claim of implementation, certification or one-million-word completion  
**Delivery rule:** code, interoperable interfaces, real runnable examples, actual target-machine evidence, and independent playtests outrank catalog size, files, LOC, commits, and prose length.

> Treat the existing product as an ambitious but incompletely integrated first draft. Every feature is suspect until it works in a representative real user journey. Critical gaps block release regardless of how much neighboring software is present. Do not delete prior work or replace canonical owners. Diagnose, consolidate, implement, validate, then promote through existing protected release gates.

## Master index

- 00. Reading protocol, provenance and nonclaims
- 01. Product north star and nonnegotiable user journeys
- 02. Source audit: what exists, what is known to fail, and what remains unverified
- 03. Gap taxonomy and severe risk register
- 04. Completion doctrine, maturity rubric and proof levels
- 05. Twelve-bot ownership and conflict-free coordination
- 06. Execution dependency graph, first-install critical path and release stages
- 07. Common architectural contracts and schemas
- 08. Cross-cutting security, rights and operator-control invariants
- 09. Universal acceptance matrix and game-quality proof
- 10. Work-order format, lifecycle, quotas and scheduling rules
- 11. Twelve detailed bot backlogs (indexed BOT-01..BOT-12)
- 12. Frontier innovations, provocative gap challenges and optional high-risk research
- 13. Whole-product integration campaigns and adversarial red-team matrix
- 14. Release gates, artifact provenance, certification, and rollback
- 15. Expansion ledger toward one million meaningful words
- 16. Source and competitive benchmark references

## 00. Reading protocol, provenance and nonclaims

This file is the **first document read by Grokbot**. An executor must read Sections 00–10 before any planning or mutation, then its assigned BOT chapter and the relevant cross-bot dependencies. A verifier must independently reread the originating work order, exact code changes, tests, and live artifact rather than repeating the builder's claims.

The repository default branch and PRs were inspected through an authenticated GitHub connector on 2026-11-07. A direct container-side git clone was attempted and failed because DNS resolution of github.com was unavailable. This is not a complete local checkout, whole-tree object census or full automated test run. The baseline is therefore a grounded **risk and completion plan**, not an assertion that every file was inspected. The first bot task is to obtain a complete verified clone or equivalent Git object snapshot, retain exact tree/object proofs, recursively inventory every tracked path and reconcile the findings here. The audit must include submodules, Git LFS, generated and ignored artifacts, license files, tags, hidden CI paths, active draft PR heads and migration manifests, not just README-level surfaces. Do not mark the census complete until a verified enumeration with counts, hashes, missing-object detection and visibility limitations is attached.

Interpretation classes: **OBSERVED** means directly inspected source/document/path; **SELF-REPORTED** means repository docs/PR descriptions claim a behavior; **CANDIDATE** means open PR or staged code without merged/full qualification; **BLOCKED** means a recorded unmet contract; **UNKNOWN** means no relevant proof was obtained; **PROPOSED** means a new build target. The existence of a class/module, fixture, CLI command, smoke test or named feature is never proof of successful user workflow. Present implementation levels separately for source presence, compilation, unit proof, integration proof, live engine interaction, physical target test and independent release approval.

### Current inspected anchors
| Anchor | Observed/recorded significance | Required follow-up |
|---|---|---|
| README.md | Mainline v16, canonical Godot brief-to-project path, first-install tester release explicitly not ready; many game/media surfaces are not complete play | Run golden briefs end to end on real engine, inspect human interaction |
| pyproject.toml | Python 3.11+, FastAPI/Mongo and numerous Jeeves, training, builder and native entrypoints | Runtime dependency, import and executable ownership census |
| frontend/package.json | Expo-router application with extensive targeted JS tests and UI scopes | Full web build, native compatibility, accessibility, Playwright and device journeys |
| skeleton/app/manifest.json | Five-service planned topology; default four services plus optional Chroma; explicit ingress and secrets | Verify runtime graph/health and live mounted routes |
| machine/ai_first_install.json | First-install implementation candidate and stable-secret invariants | Fresh install, upgrade, target laptop acceptance |
| machine/ai_master_plan.json | 421 declared volumes, 20 thematic parts, 29 laws, 8 vertical slices, multi-layer maturity policy | Do not confuse plan size with completed work; derive gap-by-gap proof |
| machine/ai_build_queue.json | Forty-two P0 tasks; explicit task dependency and accountability model | Map every bot work order to existing tasks and avoid duplicate authorities |
| machine/ai_file_tree.json | 182 migration mappings, 181 native AI owners, staged mirror, unsigned verification/cutover | Reconcile parity and independent exact-head cutover evidence |
| docs/APP_ASSEMBLY.md | Real named frontend/backend/engine/Mongo/Chroma topology; explicit Chroma persistence warning | Non-destructive migration and actual restore checks |
| docs/ai/CONSUMER_READINESS_2026-10-31.md | Guard bootstrap, local chat, Chroma, payments, real Windows qualification and source-scan blockers | Maintain release hold while repairs are proven |
| docs/qa/GUARDED_LOCAL_READINESS_2026-10-28.md | Shared epoch, backend writer custody, reviewer, tokenizer and actual Mongo topology still require integration | Build closed authority path, verify fail-closed behavior |
| skeleton/forge/game_build_queue.py | Bounded game.build handler/queue, 120-second dispatch cap | Test end-to-end deadline, durable idempotence, generated project and proof |
| skeleton/ai/runtime/operational_ai/laptop_runtime/README.md | Real GGUF and SQLite candidate, desktop workbench, separate native proof | Perform live GGUF/WSL/device tests; source-level casebooks are insufficient |
| backend/core/dragon_crawler.py | Scoped Mongo crawl operations, leases, budgets, worker handles | Prove legal/technical transport, source grant, real backend bridge and withdrawal |
| frontend/src/features/Jeeves/CrawlerWorkspace.tsx | Crawler workspace, authentication controls and frontend state machinery | Browser-driven authenticated capture/review and denied-action tests |
| PR #4875 | Broad first-install candidate, 1,860 changed paths at observed head 646526a88f3406d4a9c3b0c253417ccdabdc919a | Candidate != merged/certified; evaluate latest exact head and failing gates |
| PR #4876 | Dragon research/Atlas draft, 1,981 changed paths including large shared AI-tree overlays; head 14d8613cc2a9e7f465b8817623f5b78ad782d9a3 | Maintain draft and security holds; separately inspect adapter and architecture failures |
| PR #4870 | AI mirror reconciliation stack, 1,667 changed paths | Determine canonical source, semantic parity and source pin breakage |
| PR #4872 | First-install and backend/native bridge patch set | Test independently and reconcile into approved integration head |
| PR #4686 | Very large offline cognition/reliability source candidate | Validate true runtime behavior; casebook quantity does not certify native operation |

### External frontier reference baseline
As of this audit, Godot's official release policy lists 4.7 as supported and 4.8 as development; actual project toolchains must be pinned from a verified stable artifact, not blindly upgraded by language-model advice. Engine Grounding, Artifact Completeness and Interactive Verification are explicit, useful evaluation dimensions in GameCraft-Bench (2026). GameXpert-Bench evaluates generation, defect repair and optimization as distinct skills. GameASG-Bench highlights the discrepancy between average check pass and strict whole-task pass. These findings justify independent input-driven play, rendering checks, and cumulative regressions at every integration milestone. Sources appear in Section 16. Do not extrapolate benchmark numbers into a claim about this repo without running an independently comparable suite.

## 01. Product north star

Skeleton must become a **coherent original-game production operating system**. A user with a legitimate brief, an appropriately provisioned local model, and admitted compiler/media tools should be able to turn an idea into an original playable product through one consistent cockpit. The workflow spans brief, design charter, prototype, playable iteration, assets, world state, characters, animation, audio, cinematics, content systems, game AI, QA, optimization, export, signing, distribution and post-launch repair. Multiple genres and engine targets are optional compatibility profiles, not excuses for unfinished base quality.

### Mandatory user journeys, named J-01..J-18
| ID | Journey | Hard exit condition |
|---|---|---|
| J-01 | First install on new Windows 11/WSL2 laptop | Setup is reachable even if engine unavailable; exact recovery steps, real local AI after trusted guard and model activation |
| J-02 | Air-gapped native Jeeves | Actual verified GGUF dialogue, bounded cancellation and durable SQLite restart |
| J-03 | From natural-language brief to a complete 2D game | User controls character, can win/lose/retry, sees assets/UI/audio, save/reload and actual engine boot |
| J-04 | From brief to complete 3D game slice | Real models/materials, lighting, camera, collision, input and replay on target |
| J-05 | Human in visual editor | Change a scene, character, quest and gameplay rule, undo, save, rebuild and observe effect |
| J-06 | Agent assists without taking unauthorized control | One bounded proposal -> preview -> human approval -> canonical commit -> independent test |
| J-07 | Dynamic story campaign | Reach at least two causally distinct valid endings, inspect choices and replay seeds |
| J-08 | World simulation | NPCs remember events; factions, time and economy evolve without breaking quests |
| J-09 | Assets & media | Original sourced/rights-cleared art, animation, effects, voice/audio and cinematic sequences actually render/play |
| J-10 | Dragon grounded research | Owner-scoped lawful capture -> quote -> approve -> cite -> use in design -> withdraw -> invalidation |
| J-11 | Game bug repair | Reproduce failing play trace; propose minimal patch; demonstrate regression pass and new play evidence |
| J-12 | Generate, test and improve gameplay quality | Baseline/candidate run on held-out seeds, independent player judge and measured accepted improvement |
| J-13 | Offline studio recovery | Crash/power loss in save/build/crawl/model call; restart without duplication or data loss |
| J-14 | Cross-target export | Generate verified playable web+desktop packages; unsupported device features fail explicitly |
| J-15 | Publish original work | Verify attribution/rights, SBOM, vulnerability policy, metadata, game package and rollback path |
| J-16 | Multi-person production | Join scoped project, edit with conflict handling, audit decisions, review rights |
| J-17 | Portfolio project management | Multiple projects, isolated identities/permissions, reusable permitted assets, cost budgets |
| J-18 | Durable game maintenance | Save migration, hotfix, telemetry with consent, dependency updates, replayable QA and release chain |

A **first-install-ready** release must meet J-01, J-02, J-03, J-05, J-06, J-11, J-13 and J-14 for declared targets, plus applicable identity/rights/security gates. A later fully capable studio must prove all eighteen. Marketing-level “full” requires explicit feature/target matrix, not an unfalsifiable global label.

## 02. Source diagnosis: critical missing seams

1. **Local AI guard composition:** docs say the default local provider enforces a sealed-context guard yet default Compose lacks its trusted bootstrap. Do not bypass it. Share a fenced epoch across backend/engine, establish writer custody, real independent reviewer and tokenizer attestation; preserve historical stores.
2. **Mongo source authority:** default standalone Mongo cannot provide the primary-bound linearizable reads needed for the documented fence. Replica-set topology and real concurrent write tests are acceptance dependencies.
3. **Chroma storage:** the /data write path mismatches the existing volume mount and full mode is blocked. Preserve both legacy sources and prove a non-destructive migration; do not silently recreate containers.
4. **Windows reality:** a previous hosted installer test is not current-head or target laptop proof. Independently qualify Windows 11/WSL2, Docker, verified GGUF runtime, browser UI, actual Godot and disk-pressure/restart.
5. **Game completeness:** mainline README describes Godot 4 generation and CORE_LOOP_OK proof but says sprites, meshes, audio, complete input-driven play, multiplayer and driving simulation are not finished. Code for any of these on draft heads must be evaluated as candidates until real adoption and proof.
6. **Quality confounds:** simulation traces, model judging and source-side fixtures alone do not prove player enjoyment, comprehensible feedback or export-ready polish. Require independent play, human reports and improvement tests.
7. **AI migration custody:** staged mirrors and unsigned implementation+verification signoffs create accidental split brain risk. Complete exact source object and semantic parity audits before cutover.
8. **Dragon Atlas integration:** PR #4876 explicitly remains draft with open backend-adapter, architecture, backend-integration and release holds. A UI panel or import does not prove a mounted route; verify policy and actual backend wiring.
9. **Native laptop workbench:** source docs describe genuine GGUF/SQLite paths and distinguish native receipt quality from input-driven studio integration. Bridge tools only via approved, finite, authenticated contracts.
10. **Payments/marketplace:** checkout and premium upgrade lack atomic settlement and verified entitlement delivery. Preserve holds until webhook replay, concurrent settlement and consumer recovery are proven.
11. **Historical security:** readiness docs report historical secret findings and frontend dependency advisory. Triage every real secret, rotate if necessary and reject blanket suppression.
12. **Unbounded feature catalogs:** hundreds of plan volumes and thousands of paths create false-completion risk. Attach claims to landed exact SHA, tested binaries, actual device trace and independent owner.
13. **PR overlaps:** active PR stacks contain shared AI mirror and game-forge paths; avoid mechanically merging same assets from #4870/#4875/#4876 without overlap/dependency resolution.
14. **Toolchain correctness:** host glibc binaries are not valid merely because an Alpine service mounts them; compiler/emulator rights, ABI, sandbox, firmware and hardware are separate admission requirements.
15. **Content quality:** original asset and story generation requires provenance, style continuity, animation+audio integration, playable tests and an explicit distinction between placeholders and shipped content.
16. **Autonomy/authority:** automated workers must not promote their own spec, acquire rights, spend unlimited money, modify private credentials, merge unqualified PRs or claim launch readiness without independent evidence.

## 03. Gap taxonomy and prioritization

Use the following stable priorities: **P0** release-blocking system reality and user data safety; **P1** finished single-player vertical slice; **P2** integrated professional creator workflow; **P3** advanced simulation and multiplatform; **P4** frontier research experiments. Ranking within a priority: actual user harm > unavailability > broken core loop > irreversible asset loss > rights exposure > build cost > UX debt > aesthetic polish > optional breadth. A newly found blocker can supersede a backlog lane only with recorded evidence and critical-path rationale.

Work IDs are BOT-NN-WMM. Each work ID MUST reference canonical owner paths, a source head, dependency IDs, existing masterplan/queue links if applicable, an implementation delta, expected user effect, deterministic checks, adverse tests, live proof, and independent reviewer. Mark **UNKNOWN** rather than inventing absence from limited sampling. Feature statuses: discovery / planned / source-candidate / compilation-proven / integration-proven / play-proven / target-proven / independently-verified / released. Refuse automatic transitions.

## 04. Completion doctrine

### Maturity levels
- M0 inventory only: name and ownership without runtime proof.
- M1 spec: schemas, finite permissions, behavior and failure semantics reviewed.
- M2 implementation: concrete executable code, static inspection, unit and type tests.
- M3 integrated: canonical API/CLI/UI/queue/database/engine path passes with real dependencies.
- M4 interactive: actual input-driven test, scene rendering, feedback, save, crash and replay.
- M5 target: real target OS/hardware, long-run resource/thermal constraints, representative users.
- M6 release: independently approved exact-head security, artifact, licensing and rollback evidence.
No level may be skipped. An M2 module in a 1000-file PR is **not** an M5 feature. Completion numerator counts accepted user journeys, not generated LOC.

### Quantified acceptance score
Measure weighted journey completion, severity-weighted unresolved blockers, actual play coverage, platform qualification, source/right provenance and independent tests. Report six axes separately: reliability; accessibility; creative control; game quality; toolchain coverage; privacy/security. A composite index is for navigation only and cannot cancel a hard failed gate. Disaggregate performance by device profile (low-memory, medium laptop, GPU workstation), input device, network condition, game genre, accessibility option and install lifecycle.

### “Beast mode” means integration, not opaqueness
A labyrinth of components is acceptable only when boundaries are typed, owned, observable, explainable, versioned, testable and fully recoverable. Complexity without meaningful user capability is negative engineering value. Favor a small path that can make one exceptional game over 10000 inactive modules. The frontier target is trustworthy production throughput: one prompt creates a compelling editable game; an agent can *play* it, detect a meaningful defect, fix it and preserve all existing functionality.

## 05. The 12-bot federation

| Bot | Exclusive primary remit | Boundary | First major result |
|---|---|---|---|
| BOT-01 | First install, deployment, persistence recovery | skeleton/app, installers, Compose, Windows | trusted local AI and clean install |
| BOT-02 | Canonical architecture, data contracts, ledgers | architecture, identity, schemas, lineage | one authoritative and audited state model |
| BOT-03 | Jeeves runtime, native model, cognition | skeleton/ai/runtime, model/runtime/training | real guarded inference with durable tooling |
| BOT-04 | Creative director and autonomous studio | Jeeves agents, forge orchestration | bounded agent generates/repairs full game |
| BOT-05 | Worlds, narrative, canon, simulation | worlds, quest/story/state | causally correct persistent world |
| BOT-06 | Gameplay, physics, NPC intelligence | game/gameplay, combat/input | complete controller-driven core gameplay |
| BOT-07 | Procedural game and level generation | game builder/procgen | varied solvable replayable campaigns |
| BOT-08 | Art, asset, animation, cinematics, audio | asset/media pipelines | real output integrated in play |
| BOT-09 | Godot/web/mobile/desktop/retro builds | compiler/toolchains/export | verified playable target packages |
| BOT-10 | Dragon crawler, lawful knowledge and Atlas | webcrawler/Dragon backend | live authorized capture-to-game bridge |
| BOT-11 | Creator UX, collaboration, commerce | frontend/product/backend UI | cohesive usable visual studio |
| BOT-12 | Integration, red-team, QA and releases | CI, assurance, repo/cross-plane checks | independent exact-head acceptance |

### Concurrency and ownership law
Twelve bots means at most **twelve authorized concurrent bot roles**, not twelve overlapping writers. Each work order has exactly one owning bot. Cross-bot patches require an interface contract and the dependent bot's review. BOT-12 owns verification but cannot fabricate test evidence or overrule security holds. BOT-01 controls installation and state migration. BOT-02 controls schema and authority changes. BOT-03 controls inference activation and resource fences. BOT-09 controls target toolchains. BOT-10 controls crawler transport/rights. Product-facing changes require BOT-11 review. Frontend design, structured objects and binary artifacts remain canonical owner outputs; a new assistant chat log is not a second data store.

### Federation operating cycle
1. Snapshot main, candidate PR heads, CI and source state. Pin exact SHAs and working path leases.
2. Apply preflight admission: actor/tenant rights; permissions; disk/memory/time; branch graph; edit scope.
3. BOT-02 issues schema/interface constraints; each bot derives a finite artifact and acceptance dossier.
4. Partition by unique owner and changed-path overlap. Serialise conflicting mutations.
5. Build only affected graph nodes; run focused checks after **complete** code edits rather than continuously mutating untested half-steps.
6. Run integration tests with real service, client and game engine when required. Produce signed evidence where policy demands it.
7. BOT-12 independently reviews current head, observed executable/game, adverse conditions, security scans and source rights.
8. On conflict, fail, drift, source revocation or device uncertainty, preserve draft with recorded next blocker.
9. Merge only per existing protected branch policy; release only after separate human/operator authorization.
10. Feed defects back to originating owner; no circular self-approval, phantom status or default retry storm.

## 06. Critical path and implementation sequence

```text
P0-A: Source/object census and PR conflict map (02+12)
       -> P0-B: trusted authority & model bootstrap (01+02+03)
       -> P0-C: install + backend + native + browser + storage (01+03+11)
       -> P0-D: basic real Godot vertical slice (04+06+08+09)
       -> P0-E: actual independent play and repair (04+09+12)
       -> P0-F: cold restart, backup/restore and target laptop (01+02+12)
       -> P0-G: exact-head protected release candidate (12; human approval)

P1: Full 2D genre kit -> visual world editor -> authored assets -> quest + save
P2: Complete 3D slice -> physics, rigs, cameras, sound -> gameplay QA
P3: Narrative/campaign -> procedural safety -> adaptive NPC/director
P4: Dragon lawful research -> referenced knowledge -> approved mechanics
P5: Multi-agent studio -> project branching, reviews, code+no-code parity
P6: Desktop/web/mobile/export, mods, collaboration and commerce
P7: Frontier R&D: real-time synthesis, world digital twins, neural asset tooling,
    interactive self-play, emergent complex narrative, higher-end engines;
    no release claim before replacement of hypotheses with runtime proof.
```

Within any milestone, unblock the next real user journey before increasing catalog breadth. A 10x file-count gain that leaves the install broken has zero critical-path credit. Prefer source-closed modifications over parallel PR floods. Explicitly bind source, test and device receipts to the same final SHA.

## 07. Common architectural contracts

Every substantial subsystem must expose these typed interfaces, retaining existing canonical names where already present:

- **Principal:** tenant, actor, capability grants, consent/rights, role, session and private audit identity.
- **WorkIntent:** request id, source head, desired project revision, schema, finite tools/actions/model calls, deadline, budget, priority, dependency refs and explicit operator authorizations.
- **Plan:** immutable source-and-input commitments, ordered DAG tasks, intended side effects, reversible/irreversible stages and materialized manifests.
- **WorkLease:** exactly scoped resource reservation, physical worker token, heartbeat epoch, cancellation, join and idempotent recovery.
- **Artifact:** source lineage, content digest, media type, size, game-target profile, rights, compiler/model/tool receipts, immutable URL/reference and retention.
- **Evidence:** type, source head, host profile, method, original trace/log, digest, observation time, pass/fail/skip classification, bounded redactions, verifier identity and chain.
- **GameSnapshot:** project id, revision, RNG algorithm/seed, scene/world/quest graph IDs, asset refs, player state, compatible save schema and event ledger.
- **EditorCommand:** exact owner/revision, typed mutation and preview/undo semantics with deterministic validation; model output is merely a proposal.
- **BuildContract:** source tree, pinned toolchain, target capabilities, dependency graph, compilation, interactive proof and packaging expectations.
- **ReleaseCandidate:** immutable aggregate of verified artifacts and independent approvals; cannot be inferred from all-green summary without exact-head checks.

A contract's version must be public to all consuming bots. Breakages require a migration test matrix, not separate undocumented variants. Unknown versions fail closed. HTTP, CLI, frontend and native desktop project the same state rather than creating shadow-truth. No untrusted document grants permissions, no implicit internet for offline work, no inherited owner privilege and no synthetic evidence.

### Suggested work order shape
```yaml
schema: skeleton.grokbot.work_order.v1
id: BOT-06-W01
bot: BOT-06
status: discovery
priority: P0
source:
  repo: Apeloff1/Skeleton
  main_sha: e00bfb0809b34573c2df313ea16e17fd10bead38
  candidate_head: null
ownership:
  canonical_paths: []
  integration_paths: []
  intersecting_prs: []
dependencies: []
user_journeys: [J-03]
requirements:
  current_behavior: "unknown until executable proof"
  intended_behavior: "real input-driven, finishable loop"
  authority: "gameplay runtime and canonical game project"
  fail_closed_cases: []
deliverables:
  source_changes: []
  golden_games: []
  migration_changes: []
  proof_receipts: []
verification:
  focused: []
  integrated: []
  interactive: []
  target: []
  adversarial: []
  independent_reviewer: BOT-12
promotion:
  source_exact_head: null
  required_workflows: []
  known_holds: []
  result: not_claimed
```

## 08. Cross-cutting invariants

**S-01** Model output is always untrusted until typed, admitted and committed by an owner.  
**S-02** Every external source and binary preserves consent, rights, origin, hashes, expiry and withdrawal propagation.  
**S-03** All remote interactions use explicit network/host/IP/redirect protection and finite byte/time/page budgets; no SSRF or implicit credential forwarding.  
**S-04** All file operations on untrusted roots use descriptor-relative bounds or equivalent safe primitives, no parent symlink traversal, no TOCTOU assumption, no unbounded reads.  
**S-05** Never log secrets, full prompts, raw untrusted HTML, private source bodies or sensitive credentials into public PR/CI receipts.  
**S-06** Tenant, principal, source and project identities are bound at creation, reading, mutation, scheduling, background work, export and retention.  
**S-07** Missing/uncertain source authority, primary fencing, signatures, entitlement and native worker join are denial conditions.  
**S-08** Payments require atomic idempotent settlement, verified webhook identity, entitlements and refund/reversal consistency.  
**S-09** Unsafe model/asset/media rights disallow generation, voice cloning, publication and training until explicitly approved.  
**S-10** Offline mode does not hide a hosted fallback or silent telemetry.  
**S-11** A tool's ability to produce a source file is not permission to run arbitrary executable instructions.  
**S-12** Hardware overload, disk exhaustion and cancellation must degrade use safely, retaining evidence and recoverability.  
**S-13** Replay, resume and retry cannot double count game events, AI inference, payments, crawls, training or artifact publication.  
**S-14** A sandbox cannot be bypassed by compatibility code, plugin, import, archive extraction or indirect subprocess.  
**S-15** Autosave, branch switching, merges and migrations are transactionally safe and independent of LLM promises.  
**S-16** Unfinished PRs stay drafts or otherwise explicitly blocked; passed sibling jobs are not overall qualification.  
**S-17** All critical claims reference actual current source, host, workload and observed behavior; no paper-only certification.  
**S-18** Every subsystem supports accessible operation, diagnosable failure and reversible correction where possible.

## 09. Universal proof matrix

| Probe | Required meaning |
|---|---|
| Static source | syntax, typing, lint, contract, SBOM and ownership consistency |
| Unit | deterministic pure-contract behavior, bounds, state machines and adverse inputs |
| Integration | actual backend/engine/queue/database/filesystem/identity path, not mocked siblings |
| Native | actual loaded GGUF, compiler, Godot, emulator or platform binary at admitted pinned version |
| Interactive | recorded player inputs, observed state transitions, frames, audio where applicable and finished core loop |
| Crash/fault | process kill, network outage, stale lease, concurrent writer, low disk/memory, restart and source revocation |
| Security | threat model, fuzzing, malicious payloads, path races, permission isolation, dependency+malware+secret gates |
| Accessibility | keyboard/controller/touch navigation, assistive text/audio, reduced motion, contrast and captions |
| Performance | startup p50/p95/p99, frame pacing, memory/VRAM, CPU utilization, model tokens/sec, long-run leaks |
| Quality | blind human observation, independent UI agent play, objective success/fail, comparative held-out regressions |
| Target | exact OS/device/toolchain build, executable start, file IO, rights, save/resume and uninstall/update |
| Release | verified artifact, source exact SHA, approvals, rollback, independent attestation and support docs |

### Minimum golden games
G1: top-down action shooter with waves, movement/combat, HUD, inventory/resource sink and victory. G2: platformer with actual grounded jumps, collisions, hazards, camera and level finish. G3: roguelike RPG with generation seed, inventory, dialogue, quest and save/reload. G4: 3D exploratory micro-world with full input, collisions, NPC, animation and spatial audio. G5: driving/racing demonstration with genuine steering/traction/checkpoints. G6: strategy/puzzle with solvable state transitions. Each is a distinct code/asset/runtime artifact, not merely a manifest entry; mark unsupported exports as held. At least one broken golden fixture must be diagnosed and repaired using Jeeves through a human-approved patch and independently replayed proof.

Acceptance for a single game is conjunctive: install/load AND input AND scene render AND objective AND reward/failure AND restart/save AND target ABI AND no fatal error. No averaging across these conditions.

## 10. Work scheduling, mutation and evidence

Each bot accepts only bounded tasks within its write authority. Work-ready means necessary source objects exist; dependencies are merged or explicitly available as isolated tested inputs; owner is uniquely assigned; tests are known; no active hold is hidden. A “workload” is not counted as delivered until remote GitHub contains actual code changes and a machine-verifiable change SHA. PR creation and test dispatch are separately tracked. Push failures, tool outages, branch drift and GitHub permission restrictions are explicit blocked conditions, never simulated success.

Every 12-bot cycle: obtain exact branch refs; update discrepancy registry; select dependency-unblocked high-priority jobs; reserve paths; implement one complete coherent subsystem; run focused tests; run integration and playtest if needed; independently review; publish draft PR or append to existing owning PR; surface failures with first reproducible blocker; release path leases. Where PR edits overlap, stop and reconcile against upstream commit DAG before any merge. Do not force-update main, override branch protections or suppress security blockers. Budget remaining time, disk, latency, physical worker slots and model context, with a terminating plan on exhaustion.

**Source of truth:** Git object+receipt > executed test > verified runtime artifact > PR description > README > planning metadata > agent statement. Disagreeing lower-priority records become a tracked discrepancy, not silently rewritten truth.

---

# 11. Detailed twelve-bot backlog and technical design dossiers

These work orders are **proposed completeness obligations**, not claims that a feature is absent or unfinished until exact source/runtime evidence identifies its current maturity. Each task must be reconciled with an existing owner and PR before editing. Work IDs remain stable across revisions and are meant to drive GitHub issues, artifact manifests and test plans. Detailed source authority and exact accepted interfaces are to be concretized from the full clone, never invented. All baseline/test results are UNKNOWN until evidenced.

## BOT-01 — First install, hardware, native recovery and deployment

**Primary owner boundary:** skeleton/app, scripts/install_app.py, scripts/windows, docker-compose.yml, machine/ai_first_install.json. **Default priority:** P0. **Coordination edges:** 01->02/03/11/12. **Integration contract:** bot 01 must produce schema-bound deliverables under the existing application authority and obtain peer review for every touched cross-bot file. **Required feedback:** an observable user workflow improvement, tests at the actual owner boundary, negative/abuse cases, and independent receipt. Any unverified feature remains tagged CANDIDATE/UNKNOWN even if a class or PR exists.

### BOT-01-W01 — Clean-host installation transaction

**Capability and expected mechanism.** Stage preflight, private configuration, dependency installation, volumes, service boot, readiness and atomic install receipt. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Interrupted staging must preserve old installation and demand an explicit resumable action. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Windows/WSL2 and Linux fresh installs with reboot at each transaction boundary. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-01-W02 — Trusted sealed-context guard startup

**Capability and expected mechanism.** Connect common Mongo epoch, backend writer authority, bounded reviewer, tokenizer attestation and canonical engine without runtime bypass. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Missing verifier, unsigned policy, unknown writer or insufficient privileges blocks inference. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Real backend-engine-Mongo-replica integration with adversarial stale-writer traces. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-01-W03 — Replicated Mongo epoch custody

**Capability and expected mechanism.** Establish replica-set authority, primary-bound read concern, idempotent migrations, persisted epoch and writer fencing. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Primary transition or split epoch cannot admit writes or create divergent histories. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Concurrent mutation and primary loss/recovery on two real application processes. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-01-W04 — Chroma persistence reconciliation

**Capability and expected mechanism.** Inventory legacy container /data and named volume, backup both, compare digests and migrate into qualified durable mount. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Unknown divergent histories are quarantined; do not recreate/remove old container. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Backups restored to isolated volume and exact query/readback equivalence independently checked. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-01-W05 — First-run setup isolation

**Capability and expected mechanism.** Serve setup UI independent of Mongo/backend/guard/AI readiness and show exact categorized failure. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Setup never claims inference, payments, crawler or model availability from service health alone. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Disable each dependent service and verify setup renders and guides actionable recovery. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-01-W06 — Windows standalone installer

**Capability and expected mechanism.** Package pinned Python, launcher, signed manifest, safe uninstall, repair and first-start UI. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Never silently remove state, leak private passwords or claim a hardware run from hosted CI. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Exact-head hosted Windows build followed by physical Windows 11 laptop install, repair, upgrade, rollback. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-01-W07 — WSL2 and Docker alignment

**Capability and expected mechanism.** Detect WSL distro, architecture, Docker integration, file mount paths, ports, DNS and CPU/IO quotas. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Refuse invalid ABI and absent daemon instead of attempting privileged auto-installs. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Cold launch, Docker reset, WSL restart, sleep/wake and browser-origin smoke. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-01-W08 — Offline install artifact

**Capability and expected mechanism.** Package pinned application images, runtime, opt-in models, legal toolchains, checksums and licenses as staged bundle. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Missing optional model never triggers hidden online fetching or fallback. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Fully disconnected install with explicit negative cases and local GGUF inference. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-01-W09 — Resource preflight estimator

**Capability and expected mechanism.** Probe real RAM, VRAM, disk, swap, CPU, thermal signals, cgroup and model footprint before admission. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** No speculative capacity overcommit; unknown telemetry means conservative limited mode. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Low-RAM, disk-full, GPU-unavailable and competing-worker pressure benchmark. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-01-W10 — Native GGUF first conversation

**Capability and expected mechanism.** Guide user through source-approved model, hash, template, runtime, owner state and durable chat. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Invalid artifact, missing tokenizer or absent guard fails closed with safe diagnosis. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** End-to-end live model reply, cancellation, reopen, token count and unchanged existing sessions. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-01-W11 — State and credential initialization

**Capability and expected mechanism.** Create private durable secrets, owner setup, service credentials, permissions and index bootstrap once. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** No shared admin password, first-user elevation or secret echo in logs. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Fresh and repeated install compare stable identity/secret bytes with no plaintext leak. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-01-W12 — Upgrade migration manager

**Capability and expected mechanism.** Version manifests, schema migrations, backup snapshots, compatibility mapping, app and model updates. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Unsafe downgrade or unsupported source state blocks before mutation. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Historical installation upgrade, state graph hash comparison and cold restore. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-01-W13 — Installer rollback and repair

**Capability and expected mechanism.** Reconstruct component state by receipts without deleting external Docker assets. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Failure halfway through package replacement retains known-good launcher and data. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Kill process during extract, configure, service boot and finalize; inspect recovery. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-01-W14 — Startup supervision

**Capability and expected mechanism.** Bind service health, dependency order, jittered bounded retries, failure categories and authenticated readiness. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Infinite restart loops and force-recreation under data uncertainty forbidden. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Restart engine/backend/Mongo individually and validate truthful health transitions. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-01-W15 — Operating system lifecycle

**Capability and expected mechanism.** Manage suspend/resume, shutdown, power loss and local-network change with durable worker join. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Interrupted tasks remain pending or terminal until physical worker outcome known. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Target laptop lid close/reopen, WSL termination and corrupted-cache reproduction. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-01-W16 — User data backup control

**Capability and expected mechanism.** Define complete backup of Mongo, SQLite, Chroma, assets, keys, manifests and saves with compatible consistency points. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Partial snapshot is not presented as recoverable; do not rotate keys during backup. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Offline restore into clean host with per-object checksum and logical integrity queries. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-01-W17 — Runtime model manager

**Capability and expected mechanism.** List verified model profiles, download/provision, storage accounting, choose active model, rollback selection. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Never overwrite old checkpoint or silently convert model template. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Test switching chat/coding profile while preserving established receipts and sessions. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-01-W18 — GPU driver and ABI qualification

**Capability and expected mechanism.** Detect native provider backends, architecture, driver, Vulkan/Metal/CUDA options and fallback CPU admission. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** A mounted binary path is not proof of ABI; no implicit arbitrary executable. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Per-device executable smoke and memory-pressure proof of selected backend. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-01-W19 — Dependency update pipeline

**Capability and expected mechanism.** Pin image digest, Python/npm dependency set, runtime build inputs, SBOM and vulnerability status. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Unreviewed transitive dependency cannot silently promote release. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Rebuild image with exact source head, compare staged receipts and independent dependency gate. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-01-W20 — Engine and compiler installer

**Capability and expected mechanism.** Offer pinned Godot and user-authorized optional SDKs/cores with explicit provenance and legal boundaries. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** No unauthorized firmware/ROM/SDK downloads or root privilege. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Actual Godot headless boot and licensed optional native target smoke. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-01-W21 — Service diagnostics archive

**Capability and expected mechanism.** Produce bounded redacted sanitized support packet containing service status, versions, source head and failing gate. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Omit prompts, secret values and raw captured pages. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Reviewer can reproduce failure from sanitized artifact while secret canary tests stay clean. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-01-W22 — Real release channels

**Capability and expected mechanism.** Define nightly/beta/stable attested manifest, update and support policy. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Unknown binary signing provenance blocks stable artifact. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Signed source-exact installer, independent QA and rollback practice. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-01-W23 — Install accessibility

**Capability and expected mechanism.** Make setup keyboard navigable, localized, reduced-motion and screen-reader legible. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Recovery prompts cannot require mouse-only or network access. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Accessibility audit including failed-backend state and mobile-width browser. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-01-W24 — Targeted installation endurance

**Capability and expected mechanism.** Sustain repeated upgrade/repair/reboot cycles on constrained laptop. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** No SQLite journal leakage, data loss, handle leak or cumulative model download. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** 20-cycle qualification with snapshots and independent metrics. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.


**BOT-01 exit dossier:** enumerate implemented versus planned rows, dependencies merged or isolated, open bugs, exact target and engine versions, project data migration status, functional UX tests, security holds, unfinished platforms and independent acceptance signoff. A bot does not achieve closure merely by exhausting its list; its user journey must work.

## BOT-02 — Canonical architecture, ownership, state, schemas and integrity

**Primary owner boundary:** machine/architecture.json, machine/ai_file_tree.json, skeleton/app, skeleton/api, backend/core, skeleton/provenance. **Default priority:** P0. **Coordination edges:** 02->all. **Integration contract:** bot 02 must produce schema-bound deliverables under the existing application authority and obtain peer review for every touched cross-bot file. **Required feedback:** an observable user workflow improvement, tests at the actual owner boundary, negative/abuse cases, and independent receipt. Any unverified feature remains tagged CANDIDATE/UNKNOWN even if a class or PR exists.

### BOT-02-W01 — Repository source/object census

**Capability and expected mechanism.** Enumerate tracked files, Git objects, submodules, LFS, generated routes, canonical providers, all open PR overlays. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Partial search results must be labeled partial and never imply complete audit. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Independently count and hash full tree against pinned main and candidate refs. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-02-W02 — Single-authority topology

**Capability and expected mechanism.** Assign one owner per storage mutation, workspace, ledger, AI provider, game editor, renderer and export. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Duplicate live writer must be quarantined or converted into read-only facade. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Build endpoint-to-owner map and prove side-effect path from UI/API/CLI. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-02-W03 — Domain entity schema registry

**Capability and expected mechanism.** Version Project, World, Scene, Asset, Actor, Quest, Build, Capture, Model, WorkOrder, Receipt and Rights. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Unknown versions and nondeterministic coercion rejected before mutation. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Backward/forward compatibility fixtures plus normalized serialization roundtrip. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-02-W04 — Event journal determinism

**Capability and expected mechanism.** Define event IDs, idempotency, ordered append, transactional snapshots and source digest commitments. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Lost or reordered events cannot produce false accepted state. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Cold replay of varied game/crawl/bot histories produces identical state digest. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-02-W05 — Workspace branch and revision system

**Capability and expected mechanism.** Enable project edit isolation, snapshots, merge, semantic conflicts, undo/redo and restoration. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Last writer cannot silently replace a newer revision. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Concurrent editor/model mutations with revision compare-and-swap. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-02-W06 — Model-to-command authority bridge

**Capability and expected mechanism.** Compile proposed tool actions into typed, validated, scoped deterministic commands. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Prompt injection or generated JSON cannot mint a capability or grant. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Property tests on malformed tool outputs, grants and parser boundaries. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-02-W07 — Cross-store identity and epoch

**Capability and expected mechanism.** Bind backend Mongo, engine Mongo, SQLite and asset storage to consistent tenant/project/epoch. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Quiescence assertion does not imply known writers stopped. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Mixed-version writer fencing, restart and replica-set failure suites. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-02-W08 — Physical-resource reservation ledger

**Capability and expected mechanism.** Account CPU, GPU, RAM, disk, network and worker capacity with lease ownership and actual join. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Timeout cannot release a physically running native process. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Double-booking and cancellation race stress with bounded physical resources. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-02-W09 — Immutable artifact content store

**Capability and expected mechanism.** Use content digests, immutable storage refs, provenance, per-tenant ACL and consistent lifecycle. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** GC cannot delete live referenced content or expose another tenant. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Corrupted-object, dedup/refcount and concurrent publication tests. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-02-W10 — Rights and source lineage graph

**Capability and expected mechanism.** Propagate attribution, license, consent, source origin, revocation and dependency invalidation. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Invalidated rights cannot survive in cached recommendations or exports. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Transitive withdrawal through derived mechanic, asset, knowledge and model inputs. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-02-W11 — Game snapshot schema

**Capability and expected mechanism.** Represent world/scene/quest, actor, economy, RNG, AI, controller, audio and save compatibility. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Unknown action/entity or mismatched level seed blocks recovery. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Stable save/replay across cold restart and committed migration. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-02-W12 — Canonical build dependency DAG

**Capability and expected mechanism.** Track source edits -> generated assets -> Godot project -> playtest -> package -> release. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Stale downstream proof cannot remain valid after source change. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Single-file mutation invalidation reaches exactly affected proofs. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-02-W13 — API and CLI parity

**Capability and expected mechanism.** Unify public route schemas, command errors, identity, limits, pagination and idempotency. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** No shadow ownership via duplicate API entrypoints. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Property-based CLI vs authenticated HTTP side-by-side comparison. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-02-W14 — Eventual consistency disclosure

**Capability and expected mechanism.** Classify linearizable, snapshot and eventual reads; expose stale/unknown state intentionally. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Uncertain currency/entitlement/auth state never treated as confirmed. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Network partition tests for each observable consistency contract. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-02-W15 — Type-safe extension registry

**Capability and expected mechanism.** Register plugins, genres, codecs, engines and resource adapters by explicit versioned capabilities. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** New plugin cannot bypass sandbox, network, payment or content policy. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Unknown capability schema rejection and signed package import tests. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-02-W16 — Schema migration engine

**Capability and expected mechanism.** Plan monotonic migration revisions, backups, readback and interrupted replay. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Migration does not fabricate missing records or silently rewrite history. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Mid-migration process kill, restart, drift and downgrade tests. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-02-W17 — Multi-tenant authorization graph

**Capability and expected mechanism.** Enforce scoped principal roles, project grants, group membership and least privilege. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Cross-tenant lookup must not reveal object existence by timing or error. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Fuzz endpoints, jobs, exports and caches with owner/tenant swaps. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-02-W18 — Audit and privacy lifecycle

**Capability and expected mechanism.** Configure retention, export, tombstones, erasure eligibility and historical evidence custody. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Delete request cannot erase unrelated tenants or preserve withdrawn source in retrieval. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Cascaded deletion and recovery policy tests over all stores. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-02-W19 — Package and artifact interchange

**Capability and expected mechanism.** Encode stable typed manifests for worlds, assets, builds, mods and external toolchains. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Path traversal, zip bombs and unsupported codec fail before side effects. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Import/export roundtrip on mixed-size original user-owned projects. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-02-W20 — Dependency-aware GC

**Capability and expected mechanism.** Remove expired bytes and checkpoints only after committed ownership and legal hold checks. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Race between writer and collector cannot delete active artifacts. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Fault injection around publication, lease release and object retirement. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-02-W21 — Query planner and indexes

**Capability and expected mechanism.** Offer bounded world, spatial, graph and text search using declared indexes. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Query complexity cap must prevent memory exhaustion and cross-project leakage. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Large synthetic-world benchmarks, index rebuild and low-memory fault cases. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-02-W22 — Semantic mirror and facade retirement

**Capability and expected mechanism.** Reconcile 182 mapped files, 181 native owners, import routes, AST/byte parity and cutover signoffs. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Staged mirror not authoritative while signed cutover missing. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Exact-head AI-tree validator, semantic parity and independent evidence. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-02-W23 — Architecture lint and dependency banlist

**Capability and expected mechanism.** Prevent forbidden imports, bypasses, cyclical services, hidden providers and duplicate app creation. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Inadmissible dependency cannot be excused as mere compatibility. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Static dependency graph plus runtime import/route trace. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-02-W24 — Formal ownership and decision log

**Capability and expected mechanism.** Require ADR for authority changes, source migrations and irreversible behavior changes. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** No assistant may silently edit state-owner contract in another bot's lane. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** ADR to code to test and signoff linked at final SHA. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.


**BOT-02 exit dossier:** enumerate implemented versus planned rows, dependencies merged or isolated, open bugs, exact target and engine versions, project data migration status, functional UX tests, security holds, unfinished platforms and independent acceptance signoff. A bot does not achieve closure merely by exhausting its list; its user journey must work.

## BOT-03 — Jeeves native intelligence, cognition, resource fabric and tool supervision

**Primary owner boundary:** skeleton/ai/runtime, skeleton/ai/model_runtime, skeleton/ai/training, skeleton/ai/agents/jeeves. **Default priority:** P0/P1. **Coordination edges:** 03->01/02/04/10/12. **Integration contract:** bot 03 must produce schema-bound deliverables under the existing application authority and obtain peer review for every touched cross-bot file. **Required feedback:** an observable user workflow improvement, tests at the actual owner boundary, negative/abuse cases, and independent receipt. Any unverified feature remains tagged CANDIDATE/UNKNOWN even if a class or PR exists.

### BOT-03-W01 — Real local inference activation

**Capability and expected mechanism.** Wire verified GGUF runtime, model digest, tokenizer, template, backend and guarded engine. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Never claim model quality from provisioned file alone. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Live response/cancellation/cold restart on installed laptop. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-03-W02 — Adaptive hardware admission

**Capability and expected mechanism.** Plan context, batch, threads, GPU offload, RAM/VRAM, swap and disk spill from measured signals. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Overcommit, thermal overload and unknown system memory fail into conservative limits. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Sustained inference under CPU/GPU/swap pressure and physical worker audit. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-03-W03 — Durable instruction hierarchy

**Capability and expected mechanism.** Keep system, user, tools and external evidence roles separate with provenance and finite serialization. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Role delimiter injection and untrusted page text never become privileged. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Native GGUF adversarial test with exact serialized token frames. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-03-W04 — Model tool planner

**Capability and expected mechanism.** Parse typed JSON tool intents, schema check, dry-run and require scoped grants. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Invalid or ambiguous action has no side effect. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Adversarial tool argument corpus through real owner APIs. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-03-W05 — Live token stream and commit protocol

**Capability and expected mechanism.** Deliver incremental output with ordered chunk IDs, cancel and final durable checkpoint. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Partial output never authorizes a code commit or release. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Backpressure, client disconnect and retry replay without duplicate inference. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-03-W06 — Long-context relevance manager

**Capability and expected mechanism.** Budget instructions, source facts, history, task plans and summaries with verifiable omission metadata. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Never silently drop an active grant or confuse prior tenant history. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Long project conversation retrieval + position-swap stress. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-03-W07 — Project-scoped durable memory

**Capability and expected mechanism.** Store reviewed facts/preferences, code decisions, correction history and explicit retention policy. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Source revocation removes eligibility without rewriting unrelated chat. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Memory restart, selective erase and stale-snapshot tests. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-03-W08 — Multi-model capability routing

**Capability and expected mechanism.** Route optional specialized small/large local and hosted models by explicit policy and measured task ability. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Offline user never silently sends data to remote host. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Each configured route records model identity and privacy decision. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-03-W09 — Native execution spine recovery

**Capability and expected mechanism.** Persist request, lease, action, receipt and cold restart, with exactly-once committed side effects. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Timed-out worker retains physical slot; uncertain result blocks replay. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Kill child during token, patch, tool and commit phases. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-03-W10 — Model output validation firewall

**Capability and expected mechanism.** Check schema, token/control delimiters, UTF-8, max output, finiteness, budgets and typed constraints. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Invalid finish/tool shape denied before owner mutation. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Fuzz tokenizer, model output and tool parse with zero unsafe mutations. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-03-W11 — Source-bound coding agent

**Capability and expected mechanism.** Supply authorized source snapshots, patch proposals and exact file hash custody. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** No arbitrary filesystem, shell command or unreviewed auto-apply. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Generate/edit code, apply only after user grant, run real diff/test. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-03-W12 — Independent review deliberation

**Capability and expected mechanism.** Use separately configured finite critical reviewer on same immutable candidate and source. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Mere repeated sampling by same model is not represented as independent. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Review disagreement and failed-attestation trace. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-03-W13 — Creative/game-design specialty profiles

**Capability and expected mechanism.** Register bounded game systems roles with genre/engine domain constraints. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** No profile may invent compiler/toolchain readiness. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Compare game design outputs on fixed held-out brief families. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-03-W14 — Retrieval + knowledge synthesis

**Capability and expected mechanism.** Fuse lexical, embeddings, graph, reviewed notes and source-cited retrieval. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Withdrawn or unlicensed text must be excluded before prompt formation. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Source dependency revocation with RAG cache invalidation. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-03-W15 — Agent planning with checkpoints

**Capability and expected mechanism.** Turn broad goals into atomic tasks, expected artifacts, budgets and evidence gates. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Infinite loops, deadlocks and unbounded tool costs terminate honestly. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Interrupt and resume multi-step game editing campaign without repeats. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-03-W16 — Model candidate evaluation

**Capability and expected mechanism.** Test code generation, debugging, visual reasoning, narrative and tool correctness separately. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** One aggregate win rate cannot certify every game family. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Held-out tasks, real engine evaluation and error taxonomies. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-03-W17 — On-device inference optimization

**Capability and expected mechanism.** Profile KV cache quantization, prompt reuse, prefill, microbatching and speculative decode where safe. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Speedup claim needs measured TTFT and output correctness tradeoff. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Reproducible low/medium/high spec device benchmark. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-03-W18 — Optional multimodal perception

**Capability and expected mechanism.** Admit image, sound, frame, log and scene graph observations through typed bounded readers. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** External binary cannot execute or smuggle privileged instructions. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Real visual bug detection from Godot screenshot with verified image custody. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-03-W19 — Private network listener hardening

**Capability and expected mechanism.** Enforce loopback origin, bearer, host, CORS, finite reads and anti-CSRF where relevant. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** No unauthorized remote access to local project prompts or model. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** HTTP Host/Origin and token abuse on localhost and LAN adversaries. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-03-W20 — Native adapter training

**Capability and expected mechanism.** Support explicit licensed datasets, preprocessing, isolation, validation and real weight/adapter changes. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** A Q-learning game policy update is not transformer weight training. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Parameter delta, held-out gain and reproducible checkpoint lineage. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-03-W21 — Preference optimization lifecycle

**Capability and expected mechanism.** Gather operator consent, preference pairs, judge blinding and regression tests. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Never contaminate held-out test data or silently train on crawler pages. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Model comparison on previously unseen original game tasks. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-03-W22 — Context and tool budget accounting

**Capability and expected mechanism.** Attribute tokens, tool calls, CPU seconds, GPU bytes, deadline and storage to exact work. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** No work that exceeds grant or hides pending physical costs. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Concurrent stress of 12 bots with conservative admission. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-03-W23 — Explainable agent trace

**Capability and expected mechanism.** Show plan, selected evidence, proposed mutations, tool admission and validation without private prompt leak. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Redact secrets; do not expose raw proprietary source in public logs. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Reviewer reconstructs a safe high-level action chain from receipt. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-03-W24 — Inference security isolation

**Capability and expected mechanism.** Separate untrusted model/runtime process from host secrets and arbitrary file writing. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Unsafe model file or executable cannot escape admitted sandbox. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Malicious weight/archive/runtime tests and permission scans. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-03-W25 — Quality-aware abstention

**Capability and expected mechanism.** Teach assistant to report unknown and request missing source authority instead of fabricating success. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** No hallucinated API route, game build or tool result presented as observed. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Blind golden defects where correct behavior is explicit abstention. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.


**BOT-03 exit dossier:** enumerate implemented versus planned rows, dependencies merged or isolated, open bugs, exact target and engine versions, project data migration status, functional UX tests, security holds, unfinished platforms and independent acceptance signoff. A bot does not achieve closure merely by exhausting its list; its user journey must work.

## BOT-04 — Game studio director, hierarchical agent orchestration and production planning

**Primary owner boundary:** skeleton/ai/agents/jeeves, skeleton/forge, skeleton/automation, skeleton/jeeves. **Default priority:** P1. **Coordination edges:** 04->02/03/05/06/07/08/09/11/12. **Integration contract:** bot 04 must produce schema-bound deliverables under the existing application authority and obtain peer review for every touched cross-bot file. **Required feedback:** an observable user workflow improvement, tests at the actual owner boundary, negative/abuse cases, and independent receipt. Any unverified feature remains tagged CANDIDATE/UNKNOWN even if a class or PR exists.

### BOT-04-W01 — Brief-to-design charter

**Capability and expected mechanism.** Transform natural language into versioned scope, genre, fantasy, core loop, technology and target profiles. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Unresolved choices become operator-reviewable assumptions, not invented commitments. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Brief edits regenerate impacted spec only while preserving approved choices. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-04-W02 — Role-specialist virtual studio

**Capability and expected mechanism.** Provide producer, designer, engineer, writer, level artist, animator, sound designer, QA and build roles. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Specialists do not self-approve their own release, rights or security outcomes. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Multi-role rehearsal with separated source, critique and adoption evidence. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-04-W03 — Plan DAG and milestone synthesis

**Capability and expected mechanism.** Decompose game design into stable ordered artifacts with acceptance tests and dependencies. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Plans are finite, coherent and cannot skip a critical playable dependency. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Complete small 2D game graph with traceable source-to-export path. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-04-W04 — Authoritative tool invocation

**Capability and expected mechanism.** Bind each AI action to typed game-editor/compiler API and explicit grant. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Text-only completions and hallucinated tools never mutate source. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Execute authorized edit/build/review/export from real user workbench. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-04-W05 — Iterative creative prototyping

**Capability and expected mechanism.** Generate multiple coherent candidates, compare gameplay and adopt chosen implementation. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Candidate selection cannot silently overwrite approved content. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Blind playtest comparison with retained screenshots, metrics and reason. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-04-W06 — Playable-first production scheduling

**Capability and expected mechanism.** Prioritize input, scene, feedback, victory/defeat and build before optional lore catalog. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Deadline pressure cannot create a shell game of metadata-only completion. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Timed game-jam brief produces a finishable build. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-04-W07 — Agent-driven diagnostic repair

**Capability and expected mechanism.** Capture real compiler/engine/gameplay failure and propose targeted bounded patch. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Never declare repaired based solely on successful code generation. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Inject real collision/quest/save bug, replay before and after. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-04-W08 — Studio asset brief pipeline

**Capability and expected mechanism.** Convert design/scene rules to structured art, animation, audio and license briefs. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Media request cannot bypass content rights or source provenance. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Art bundle matches actual run-time rig/scene/use requirements. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-04-W09 — Production board observability

**Capability and expected mechanism.** Expose current milestone, blocked dependencies, owner, cost, evidence and next action. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** UI never fabricates progress by counting drafted documentation. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Refresh live work graph while process and network faults occur. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-04-W10 — Human-in-the-loop approval

**Capability and expected mechanism.** Offer diff, predicted change scope, reversible preview and explicit consent per risk class. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** No unattended destructive edit, spend or publication from agent intent. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Human rejects a proposal and history remains unchanged. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-04-W11 — Adversarial design critique

**Capability and expected mechanism.** Check loop quality, pacing, difficulty, novelty, retention ethics and player agency. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Model self-critique alone cannot establish enjoyment. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Compare against actual human/game-agent observations and issue false-positive analysis. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-04-W12 — Production memory and art continuity

**Capability and expected mechanism.** Record approved style bible, design laws, canon, team decisions and asset reuse. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Memory invalidation occurs on rights withdrawal or project branch. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Regenerate one level without losing character art consistency. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-04-W13 — Cross-role conflict reconciliation

**Capability and expected mechanism.** Apply semantic merge for story, code, assets and economy with audit of disputed edits. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Conflicting authorities never silently last-write-wins. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Simultaneous writers trigger bounded conflict review. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-04-W14 — Campaign planning at scale

**Capability and expected mechanism.** Coordinate chapters, acts, scenes and large quest networks with content-percentage gates. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** A thousand empty scene manifests count as zero realized content. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Source-backed playable campaign sample and topology solver. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-04-W15 — Design-to-engine trace

**Capability and expected mechanism.** Maintain mapping from original brief to concrete script, scene, asset and test. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Missing requirement trace blocks completion. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Bidirectional trace drill from gameplay feature to design/user acceptance. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-04-W16 — Auto playtester commissioning

**Capability and expected mechanism.** Invoke independent game player with private rubric, input actions and screenshots. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Builder cannot alter judge rubric or claim from canned input. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Repeatable counterexample gameplay trace and repair loop. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-04-W17 — User-controlled creativity slider

**Capability and expected mechanism.** Offer style, novelty, fidelity, complexity and safety targets with explicit budget/quality tradeoff. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Feature changes cannot override data/license constraints. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Same seed/profile comparison on diverse briefs. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-04-W18 — Integrated level pacing director

**Capability and expected mechanism.** Coordinate encounters, loot, narrative beats, travel and rest windows with measurable challenge. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Director cannot produce required inaccessible quest/room. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Simulated player policies detect pacing softlocks. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-04-W19 — Persistent project campaigns

**Capability and expected mechanism.** Resume multi-week plans with durable tasks, per-step receipts and bounded context recovery. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Replanning does not repeat succeeded financial/build/crawl actions. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Cold resume campaign after multiple source revisions. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-04-W20 — Genre-specific production kits

**Capability and expected mechanism.** Define minimal complete ARPG, platformer, shooter, strategy, RPG, simulator and puzzle packages. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Unsupported engine variants declared upfront. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** At least one real finished golden game in each claimed genre. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-04-W21 — Project-wide refactoring steward

**Capability and expected mechanism.** Plan scene/entity ID changes, import updates and save migrations as coherent transactions. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Never leave broken cross-module references or accidental schema drift. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Safe rename/refactor of in-use quest, NPC and world asset. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-04-W22 — Autonomous workload fairness

**Capability and expected mechanism.** Schedule 12 bots with admission and priorities respecting physical worker/branch restrictions. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** No noisy role can starve core install, compiler or QA. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Reproducible fairness/cancellation run under CPU pressure. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-04-W23 — Reconciliation with backlog truth

**Capability and expected mechanism.** Cross-reference 421 volumes/42 P0 tasks to real current source/evidence. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Already-built work should be improved, not recoded as duplicate system. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Gap registry lists implemented vs documented vs candidate with citations. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-04-W24 — Final game design signoff

**Capability and expected mechanism.** Produce independent review-ready release rationale, open limitations and test proofs. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** No role may self-certify overall product or origin rights. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Human operator sees precise satisfied and unsatisfied journeys. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.


**BOT-04 exit dossier:** enumerate implemented versus planned rows, dependencies merged or isolated, open bugs, exact target and engine versions, project data migration status, functional UX tests, security holds, unfinished platforms and independent acceptance signoff. A bot does not achieve closure merely by exhausting its list; its user journey must work.

## BOT-05 — Causal worlds, narrative lattice, canon, characters and social simulation

**Primary owner boundary:** skeleton/ai/agents/jeeves/worlds, skeleton/game/world, skeleton/forge. **Default priority:** P1/P2. **Coordination edges:** 05->02/04/06/07/08. **Integration contract:** bot 05 must produce schema-bound deliverables under the existing application authority and obtain peer review for every touched cross-bot file. **Required feedback:** an observable user workflow improvement, tests at the actual owner boundary, negative/abuse cases, and independent receipt. Any unverified feature remains tagged CANDIDATE/UNKNOWN even if a class or PR exists.

### BOT-05-W01 — Multiworld spatial scene graph

**Capability and expected mechanism.** Represent worlds, maps, regions, portals, coordinates and layered traversal in canonical graph. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Orphan transitions and invalid parent-child cycles denied. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Load, visit, save and replay five connected world locations. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-05-W02 — Longform story hierarchy

**Capability and expected mechanism.** Support prologue, chapters, acts, scenes, interlude and multiple endings with meaningful causality. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Capacity for 100/1000/9999 is not a promise that content is meaningful. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Validate scene substance, narrative objectives and game transitions. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-05-W03 — Consequence and choice ledger

**Capability and expected mechanism.** Bind decisions to characters, quests, faction state and story endings with causal effects. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Player action cannot retroactively change witnessed history unnoticed. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Two seeded runs reach distinct endings with traceable witness events. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-05-W04 — NPC motivations and emotions

**Capability and expected mechanism.** Model goals, trust, needs, memory, beliefs and character development separately. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Agent knowledge cannot exceed observed game state by default. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** NPC revises behavior appropriately after player betrayal or help. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-05-W05 — Faction diplomacy and politics

**Capability and expected mechanism.** Support treaties, wars, reputation, trade, territorial control and resource pressure. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Conflicts cannot bypass world-law, save or quest authority. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Multi-faction simulation with post-restart deterministic history. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-05-W06 — Economy and markets

**Capability and expected mechanism.** Model resource extraction, prices, producers, sinks, barter and scarcity with constraints. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Reject impossible minting, negative budgets and circular free rewards. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Long-horizon economy tests for inflation/exploit and player viability. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-05-W07 — Quest graph and recovery

**Capability and expected mechanism.** Express objectives, dependencies, time gates, failure, alternative route and completion witness. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Softlocks and unreachable required keys invalidate generation. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Model-check small quest topology and agent-play representative campaign. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-05-W08 — Dialogue-state compiler

**Capability and expected mechanism.** Generate branching dialogue anchored to exact actor knowledge, relationship and choice state. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Dialogue cannot claim a fact unknown to speaker or incompatible with canon. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Interactive dialogue replay under changing game state. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-05-W09 — Temporal mechanics

**Capability and expected mechanism.** Track calendars, weather, seasons, daily NPC schedules and causal time rules. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Time travel or save changes cannot break temporal ordering without explicit rules. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Roundtrip schedule under save/load, pause, fast travel and replay. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-05-W10 — Environmental storytelling

**Capability and expected mechanism.** Place interactive clues, locations, collectibles, sound and visuals supporting plot. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Clues must exist in exported playable scene not only source prose. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Player obtains clue through actual interaction and quest updates. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-05-W11 — Ecology, biomes and habitats

**Capability and expected mechanism.** Model food webs, terrain, hazards, settlement influences and biome transitions. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Ecosystem cannot generate impossible essential resources or impassable default path. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Seeded 1000-tick ecology stability and traversal test. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-05-W12 — Character arc planner

**Capability and expected mechanism.** Track setup, disruption, agency, change and payoff per character. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Character scenes without progression do not qualify as arc beats. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Narrative consistency rubric on divergent playthroughs. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-05-W13 — Lore contradiction graph

**Capability and expected mechanism.** Compare new facts against approved canon and provenance, return localized conflicts. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Canon cannot silently overwrite signed player history. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Inject contradicting faction origin and verify explicit review. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-05-W14 — Multiending satisfiability

**Capability and expected mechanism.** Ensure all advertised endings have reachable and distinct requirements. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Arbitrarily named copies of same terminal scene are not distinct. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Solver witnesses and controller-driven replays for each ending. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-05-W15 — World event director

**Capability and expected mechanism.** Create dynamic bounded events from state predicates and budgeted randomness. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Events cannot destroy mandatory quest entity without a recovery path. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Event stress includes cancellation/replay and critical quest preservation. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-05-W16 — Cross-world migration

**Capability and expected mechanism.** Preserve inventories, quest flags, companion state, physics profile and rights across transitions. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Duplicate avatars and identity drift cause denial. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** World portal journey twice, including network interruption and recovery. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-05-W17 — Save compatibility mapping

**Capability and expected mechanism.** Migrate campaign state and actor IDs across content releases. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Missing old state is quarantined instead of fabricated. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Save in old campaign, update content, resume with identical confirmed choices. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-05-W18 — Cultural worldbuilding toolkit

**Capability and expected mechanism.** Generate original religions, customs, design languages, settlements and languages as fiction. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Avoid plagiarism and unsupported real-world cultural appropriation. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Human review of generated lore plus source provenance checks. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-05-W19 — Social relationship simulation

**Capability and expected mechanism.** Network reputation, friendships, rivalries, trust, rumor propagation and cooperative goals. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Social edges must remain finite and appropriately scoped. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Small-town simulation yields interpretable relationship changes. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-05-W20 — Moral choice and player agency

**Capability and expected mechanism.** Support tradeoffs and lasting player-visible consequences without manipulative dark patterns. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Director cannot fake meaningful choice where actions converge indistinguishably. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Paired alternative input traces and outcome comparison. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-05-W21 — Dynamic world continuity editor

**Capability and expected mechanism.** Permit human changes to canon with impact prediction, diff and explicit migration. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Approved canon cannot be regenerated away casually. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Editing capital-city status propagates to scenes, dialogue, routes and saves. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-05-W22 — Localization-aware storytelling

**Capability and expected mechanism.** Support tone, pronouns, world-specific grammar and longform narrative translation memory. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Localized text cannot leak spoiler state or misrepresent game rules. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Multi-language dialogue functional playtest with captions and UI fit. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-05-W23 — NPC offscreen simulation

**Capability and expected mechanism.** Run schedules and faction events efficiently without simulating irrelevant full scenes. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Event catch-up cannot replay duplicate economy/quest commits. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Travel far away then return; world state consistent and resource bounded. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-05-W24 — World debugging and time travel

**Capability and expected mechanism.** Expose causal inspection, state snapshot diffs and controlled deterministic rewind. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Undo of irreversible out-of-world action forbidden. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Rewind user game action without reverting payment/source rights evidence. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.


**BOT-05 exit dossier:** enumerate implemented versus planned rows, dependencies merged or isolated, open bugs, exact target and engine versions, project data migration status, functional UX tests, security holds, unfinished platforms and independent acceptance signoff. A bot does not achieve closure merely by exhausting its list; its user journey must work.

## BOT-06 — Gameplay, mechanics, combat, physics, navigation and competitive systems

**Primary owner boundary:** skeleton/game/gameplay, skeleton/ai/game_builder, skeleton/forge. **Default priority:** P1. **Coordination edges:** 06->02/05/07/08/09/12. **Integration contract:** bot 06 must produce schema-bound deliverables under the existing application authority and obtain peer review for every touched cross-bot file. **Required feedback:** an observable user workflow improvement, tests at the actual owner boundary, negative/abuse cases, and independent receipt. Any unverified feature remains tagged CANDIDATE/UNKNOWN even if a class or PR exists.

### BOT-06-W01 — Real core game loop

**Capability and expected mechanism.** Implement title/start, control, objective, feedback, win/lose, restart and exit in actual target runtime. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** A printed CORE_LOOP_OK marker without input does not satisfy interactive acceptance. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Live controller script completes shooter/platformer/roguelike. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-06-W02 — Input abstraction and remapping

**Capability and expected mechanism.** Support keyboard, mouse, gamepad, touch, rebinding, focus and assistive alternatives. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Unsupported or disconnected device fails visibly without stuck movement. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Browser and Godot input replay, keyboard-only UI and controller hotplug. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-06-W03 — Deterministic fixed timestep

**Capability and expected mechanism.** Separate tick simulation, render interpolation, collision and consistent seeds. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Variable FPS must not change core state beyond declared numerical tolerance. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Cross-FPS replay at 30/60/120 and slow machine conditions. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-06-W04 — 2D and 3D locomotion

**Capability and expected mechanism.** Include grounded jumps, sprint, dash, swim, climb, flight, camera and navigation options. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Movement states cannot pass through colliders or permanently disable controls. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Golden controller traces traverse all declared movement verbs. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-06-W05 — Combat architecture

**Capability and expected mechanism.** Define attack windows, hitboxes, hurtboxes, projectiles, damage, armor, status and recovery. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Infinite attack loop, unearned hits and invincibility exploits denied. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Real combat against moving adversary, victory and defeat paths. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-06-W06 — Enemy AI behavior trees

**Capability and expected mechanism.** Support patrol, investigate, engage, retreat, pursue and contextual action with finite compute budget. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** AI does not read hidden player data unless game rules explicitly allow. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Trace adversary decisions across cover, obstacles and concealment. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-06-W07 — Tactical action planning

**Capability and expected mechanism.** GOAP, utility scoring, hierarchical tasks and fallback policies for advanced NPCs. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Expensive planning cannot starve interactive frame budget. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** High actor-count and unexpected environment stress. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-06-W08 — Encounter generator

**Capability and expected mechanism.** Place enemies, hazards, rewards and objectives according to readable challenge constraints. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Cannot spawn opponents inside walls, inaccessible rooms or on player without warning. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Agent-run encounter fairness and difficulty curves. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-06-W09 — Progression and build system

**Capability and expected mechanism.** Implement XP, skills, levels, equipment and respec with testable character math. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Negative resources or dominant exploits cannot bypass progression. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Diverse seeded build trajectories finish campaign. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-06-W10 — Inventory/ownership model

**Capability and expected mechanism.** Support slots, weight, durability, stacking, equipment, loot and atomic transfers. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Crash cannot duplicate item, lose committed currency or cross tenant. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Concurrent pickup, drop, craft, trade and save stress. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-06-W11 — Crafting and resource chains

**Capability and expected mechanism.** Define recipes, prerequisites, stations, crafting time and economy sinks. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Reject zero-cost cycles producing unlimited valuable resources. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Graph solver for crafting chains and runtime completion. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-06-W12 — Vehicle movement and racing

**Capability and expected mechanism.** Implement actual steering, traction, throttle, collision, checkpoint and lap behavior. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Kinematic visual demo is not claimed as driving simulation. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Interactive lap completion with controller, collisions and braking. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P0. **Current maturity:** to be determined by executable census.

### BOT-06-W13 — Stealth detection and cover

**Capability and expected mechanism.** Model line-of-sight, audibility, alert state, cover and decoy stimuli. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Player must receive explainable feedback and adversaries respect occlusion. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Stealth route completed and detected under controlled action traces. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-06-W14 — Puzzle and maze runtime

**Capability and expected mechanism.** Generate solvable puzzles, visible feedback, hints, progress and reset. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Unsolvable seed blocked or shipped with explicit impossible-state evidence. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Solver witnesses and blind human player completion. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-06-W15 — Platformer collision precision

**Capability and expected mechanism.** Handle coyote time, jump buffers, ledges, moving platforms and one-way surfaces. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** No physics clipping, jitter or invisible collisions that destroy fairness. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Interactive platformer route with recorded jump timings. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-06-W16 — Strategy and simulation turn engine

**Capability and expected mechanism.** Support action phases, pathing, economy, unit orders and deterministic conflict resolution. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Illegal turn transitions and double moves rejected. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Seeded strategy battle with reproducible outcomes. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-06-W17 — Cooperative multiplayer base

**Capability and expected mechanism.** Use authoritative tick state, sessions, identity, reconciliation and deterministic rollback where appropriate. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Client cannot grant own items, warp, or impersonate other player. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Two-client latency/drop test with reconnect and state parity. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-06-W18 — Save and reload of live game

**Capability and expected mechanism.** Persist player, physics, inventory, quest, RNG, world time, AI and pending events atomically. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Duplicate or partial saves never become silently preferred. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Kill game during checkpoint and verify correct subsequent load. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-06-W19 — Dynamic difficulty and assist

**Capability and expected mechanism.** Adapt challenge with declared ranges, choices and accessibility preferences. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Invisible unfair adjustments or removal of meaningful outcomes prohibited. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Distinct difficulty settings reach valid win/lose loops. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-06-W20 — Gameplay analytics with consent

**Capability and expected mechanism.** Track input-derived failure patterns, completion curves and navigation bottlenecks. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** No analytics without consent, raw personal data or hidden network telemetry. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Offline no-telemetry proof and deletion/export functional test. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-06-W21 — Exploit and balance solver

**Capability and expected mechanism.** Model combat effectiveness, loot rarity, experience and economy under varied bot policies. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Failure to find an exploit is not proof none exists; report search envelope. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Property tests plus Monte Carlo seeded optimization study. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-06-W22 — High-agent-count performance

**Capability and expected mechanism.** Bound physics, pathfinding, memory and rendering with LOD/culling and job budget. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Degraded mode must remain playable instead of dropping essential gameplay updates. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** 10/100/1000 actor load bench per supported target. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-06-W23 — Audio/visual gameplay feedback

**Capability and expected mechanism.** Couple gameplay event bus to HUD, animation, sound, VFX and accessibility cues. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Missing effects detected by interaction-level checks not ignored as cosmetic. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Attack and objective trigger visible and audible actual runtime response. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-06-W24 — Anti-cheat and authority hardening

**Capability and expected mechanism.** Protect multiplayer score, movement, rewards and shared inventories. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Client-provided state is not treated as authoritative. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Forged network commands and replayed reward transactions denied. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.

### BOT-06-W25 — Mechanic portability contracts

**Capability and expected mechanism.** State exact Godot/web/native capability requirements and fallback behavior per mechanic. Implement this as a typed, observable, versioned, deterministic contract within the assigned canonical owner. Define the user-visible entry action, durable resource/asset identities, limits and how an operator can inspect/undo the resulting change where reversible. Scope exactly which target/genre/platform variants this work order will actually support; describe unsupported variants explicitly.

**Adversarial and recovery obligations.** Export cannot silently omit essential player actions. Add finite admission, cancellation and idempotent recovery when the operation has side effects. Record independently observable error classifications, make stale source/proofs ineligible, preserve existing trusted artifacts and avoid replacing an authorized older implementation merely to increase file count.

**Acceptance evidence.** Cross-target feature-negotiation and live game parity suite. The proof dossier must contain repository source SHA, precise commands/test harness, software/hardware/toolchain versions, expected and actual outputs, tests of rejected inputs, meaningful performance/resource budgets and a reproducible artifact or trace. Require BOT-12 independent review of a final candidate head; source-only fixtures do not elevate an interactive or platform claim. **Default priority:** P1/P2. **Current maturity:** to be determined by executable census.


**BOT-06 exit dossier:** enumerate implemented versus planned rows, dependencies merged or isolated, open bugs, exact target and engine versions, project data migration status, functional UX tests, security holds, unfinished platforms and independent acceptance signoff. A bot does not achieve closure merely by exhausting its list; its user journey must work.

# 11 (continued). Detailed work orders for bots 07 through 12

## BOT-07 — Procedural level generation, playable worlds, genre kits and balancing

**Primary owner paths:** skeleton/ai/game_builder, skeleton/ai/agents/jeeves/worlds, skeleton/forge. **Priority envelope:** P1/P2. **Integration relationships:** 07->02/04/05/06/08/09/12. The bot must examine merged code, independent PR candidates and existing masterplan rows before deciding whether to build, improve, unify or reject a feature. All proposed capabilities begin at UNKNOWN maturity until evidenced. No platform and no declared engine support is automatically implied by a spec. Every relevant user action must show an actual durable result.

### BOT-07-W01 — Constraint-based spatial generator

**Feature outcome and technical implementation.** Build dungeons, towns, routes and arenas from geometry, connectivity, item-gate and traversal constraints. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Reject maps with unreachable exits, key loops, nonfunctional geometry or invalid spawn points. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Path solver plus interactive run through multiple generated seeds. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-07-W02 — Grammar-driven content synthesis

**Feature outcome and technical implementation.** Express authored content grammar for objectives, encounter design, biome style and story beats with versioned rules. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Repetitious empty scene spam cannot count as original game content. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Semantic diversity and human readability audit on generated assets/scenes. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-07-W03 — Procedural overworlds

**Feature outcome and technical implementation.** Generate hierarchical continents, settlements, dungeons, hubs and transport routes with deterministic identities. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Missing portal or conflicting coordinates block scene publication. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Cross-region travel and stable save/load replay. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-07-W04 — Voxel/heightfield terrain synthesis

**Feature outcome and technical implementation.** Support terrain mesh, erosion, roads, caves, navmesh and collision with finite spatial constraints. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Impassable mission-critical path and excessive render mesh rejected. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Procedural terrain test with actual controller and performance receipts. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-07-W05 — Biome and ecological placement

**Feature outcome and technical implementation.** Co-generate weather, resources, vegetation, fauna, hazards and scenic story landmarks. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Essential quest resource never generated into inaccessible region. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Seeded resource-availability solver plus runtime traversal. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-07-W06 — Quest-level co-design

**Feature outcome and technical implementation.** Align narrative prerequisites with physical level layout, loot keys and objective placement. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Cannot ask player for an object obtainable only after required lock. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Formal constraint proof and blind player run. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-07-W07 — Encounter distribution and pacing

**Feature outcome and technical implementation.** Place enemy mix, cover, hazard, recovery and reward according to skill curve and declared target. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** No unavoidable lethal spawn without telegraph and counterplay. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Simulated novice/expert play through progression curve. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-07-W08 — Dynamic difficulty envelopes

**Feature outcome and technical implementation.** Adjust enemy count, supplies and puzzle complexity within authored fairness constraints. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Challenge adaptation never rewrites live seeded save imperceptibly. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Baseline/candidate difficulty trace with user-visible changes. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-07-W09 — Loot tables and rarity balancing

**Feature outcome and technical implementation.** Define loot probabilities, deterministic random seeds, economy sinks and scarcity targets. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Reject farmable zero-cost duplication loops and impossible drop quests. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Large seeded simulations with confidence intervals and negative seed cases. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-07-W10 — Procedural quest templates

**Feature outcome and technical implementation.** Synthesize meaningful short quests conditioned on world predicates, NPC relationships and events. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Duplicate shallow fetch quests and generic filler fail content quality gate. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Coherence review plus player actions changing world state. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-07-W11 — Puzzle generation with solution witnesses

**Feature outcome and technical implementation.** Generate mazes, switch circuits, logic, tactical puzzles with proof of solvability. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Generator must fail closed when solution witness unavailable. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Independent solver and actual input replay validate solution. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-07-W12 — PCG determinism and seed versioning

**Feature outcome and technical implementation.** Version RNG, algorithm, engine, source assets and constraints in a reproducible generation manifest. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Changed algorithm without migration must not silently alter old saved world. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Same pinned inputs produce same scene/quest digests. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-07-W13 — Adversarial content test agents

**Feature outcome and technical implementation.** Train/evaluate multiple heuristic exploration policies to find deadlocks and exploits. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** No artificial test player may give success without observable game event. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Minimized reproducible counterexample seeds with replay logs. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-07-W14 — Novelty and repetition scoring

**Feature outcome and technical implementation.** Compare topology, dialogue, mechanics, silhouette and item distribution against content corpus. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Large volume of cloned scenes cannot yield high uniqueness score. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Diversity report tied to human review and held-out game families. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-07-W15 — Contextual encounter variation

**Feature outcome and technical implementation.** Generate story-relevant faction, biome, terrain and player-build-specific encounters. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** No incompatible NPC/loot/faction state may be spawned. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Constraint engine plus deterministic game frame evidence. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-07-W16 — Real-time world chunk streaming

**Feature outcome and technical implementation.** Partition scenes and data by level of detail, player proximity, memory pressure and visibility. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Worker eviction cannot delete referenced interactive objects or history. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Long-distance travel under constrained RAM with stable frame pacing. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-07-W17 — Procedural settlement architecture

**Feature outcome and technical implementation.** Create buildable towns with roads, doors, interiors, NPC schedules and economy links. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Houses cannot be inaccessible or collide with world portals. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Human walks between structures and interacts with residents. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-07-W18 — Multi-genre generative templates

**Feature outcome and technical implementation.** Cover shooter, RPG, platformer, roguelike, puzzle, tactics, sandbox and racing with dedicated rule kits. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** One generic scene with a changed label is not genre coverage. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** At least one genuinely different playable exported golden build per admitted genre. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-07-W19 — Narrative branch generation

**Feature outcome and technical implementation.** Compose alternative arcs with choice predicates, stakes and valid endings. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Causal branches cannot converge into mislabeled identical outcomes without rationale. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Solver+player witnesses for distinct choices/endings. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-07-W20 — Procedural motion/animation briefs

**Feature outcome and technical implementation.** Generate compatible art/animation needs from mechanics and entity topology. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Producer cannot handoff missing collision, rig and interaction annotations. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** End-to-end scene creation with asset import and displayed action. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-07-W21 — World repair and regenerate-local

**Feature outcome and technical implementation.** Edit only selected bad procedural region while preserving world seed lineage and approved hand work. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Whole-world random reset or unrelated story rewrite is forbidden. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Surgical repair before/after diff and unchanged unrelated level checks. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-07-W22 — Adaptive content streaming

**Feature outcome and technical implementation.** Generate/compile background scenes ahead of player under finite CPU/storage budgets. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Background activity never stalls critical gameplay or bypasses safety. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Cold load, disk pressure, cancellation and offline test. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-07-W23 — Replayable live event generation

**Feature outcome and technical implementation.** Spawn seasonal/boss/social events from canon predicates and explicit budgets. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Duplicate or unreachable events cannot corrupt quest state. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** World-time replay, skip-ahead and idempotent event journal tests. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-07-W24 — Physical simulation constraints

**Feature outcome and technical implementation.** Generate terrain/water/weather hazards compatible with actual engine physics and navigation. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Physically contradictory terrain blocks or colliders fail build. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Real engine collision and route traces with reproducible states. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-07-W25 — Generator performance and budget

**Feature outcome and technical implementation.** Measure generation wall time, memory, disk, binary size and graph solving complexity. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Worst-case seed cannot run unbounded or hang compiler queue. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Exhaustive adversarial small cases and sampled large-world stress. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.


**BOT-07 closure rule:** all declared feature types have interoperable contracts; exact product journeys pass on supported targets; negative, rights, accessibility and performance obligations are satisfied; bugs/rejected candidates are retained in accountability; independent BOT-12 review agrees with source state. An undocumented limitation is a gap even if the implementation happens to work.

## BOT-08 — Art, 2D/3D media, rigging, cinematics, audio, shaders and presentation

**Primary owner paths:** skeleton/ai/forge, skeleton/ai/game_builder, frontend/src/features, skeleton/forge. **Priority envelope:** P1/P2. **Integration relationships:** 08->02/05/06/07/09/11/12. The bot must examine merged code, independent PR candidates and existing masterplan rows before deciding whether to build, improve, unify or reject a feature. All proposed capabilities begin at UNKNOWN maturity until evidenced. No platform and no declared engine support is automatically implied by a spec. Every relevant user action must show an actual durable result.

### BOT-08-W01 — Safe and provenance-bound asset ingestion

**Feature outcome and technical implementation.** Import user-owned images, 3D models, textures, voice, sound and fonts with exact license and content hashes. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Symlink race, archive bomb, unsupported executable and revocation block adoption. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Malicious format and safe fixture corpus with real import. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-08-W02 — 2D sprites and tilesets

**Feature outcome and technical implementation.** Generate or author original sprite sheets, tile maps, UI icons, parallax and character directions. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Metadata-only sprite entries or invisible textures cannot pass. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Actual rendered Godot sprite with animation and input event. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-08-W03 — 3D mesh modeling workflow

**Feature outcome and technical implementation.** Supply procedural mesh construction, UVs, topology, materials and collision shapes. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Nonmanifold or oversized geometry must trigger review/repair. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Mesh displayed in target engine with collision, shadow and scale. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-08-W04 — 3D asset LOD and optimization

**Feature outcome and technical implementation.** Manage high/medium/low geometry, texture mipmaps, batching and streaming. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Aggressive optimization must not break interactions or silhouettes. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** p95 frame and VRAM before/after on 3D scene. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-08-W05 — PBR/stylized materials

**Feature outcome and technical implementation.** Build shader graphs, material parameters, normal maps, roughness and stylized presets. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Missing shader dependency cannot silently render blank or pink. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Automated material preview in target renderer. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-08-W06 — Character rig and skinning

**Feature outcome and technical implementation.** Construct bone topology, weights, IK targets, sockets and mesh deformations. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Invalid skeleton or missing retarget map denies animation publication. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Real skeleton pose, attack/locomotion and camera tests. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-08-W07 — Animation graphs

**Feature outcome and technical implementation.** Combine idle, walk, jump, climb, hit, attack, death and expression into finite state machine. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Impossible transitions and stuck states surface as gameplay failures. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Complete game-action trace triggers correct animation sequence. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-08-W08 — Motion retargeting

**Feature outcome and technical implementation.** Transfer compatible skeleton motion to original characters with constraints. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Scale/handedness mismatch must not silently distort critical contact. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Before/after motion render and foot-slide metrics. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-08-W09 — Blendshape and facial animation

**Feature outcome and technical implementation.** Expose expressions, phonemes, gaze, blinks and dialogue-linked performance. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Facial stream cannot require voice identity data without consent. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Cutscene with audio-cued mouth motion and context-aware expression. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-08-W10 — Cinematic timeline editing

**Feature outcome and technical implementation.** Compose shots, keyframes, cuts, camera transitions, subtitles, cues and interactive branching. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Timeline cannot steal controls without explicit restore or become unskippable by accident. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Scrub, branch, skip, resume and export a scripted cutscene. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-08-W11 — Cinematography grammar

**Feature outcome and technical implementation.** Use composition, gaze, depth, lighting, occlusion and emotional framing as authorable constraints. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Camera cannot hide essential player actions or create nausea-inducing forced movement. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Visual frame comparisons and player control tests. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-08-W12 — Game-state-driven animation

**Feature outcome and technical implementation.** Bind gameplay and story events to state machines with versioned event names. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Scripted event cannot reference nonexisting scene actor or expired state. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Active in-game story beat fires visible matching animation. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-08-W13 — Particles, VFX and weather

**Feature outcome and technical implementation.** Generate safe bounded emitters, trails, decals, dust, rain and impact effects. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Invalid GPU shader or unbounded particle count fails resource admission. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Real gameplay hit with consistent visual feedback and performance metrics. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-08-W14 — Realtime light and shadows

**Feature outcome and technical implementation.** Author directional/local lighting, exposure, volumetric effects and fallback settings. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** No invisible navigation due to artistic lighting or incompatible target. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Visual regression and contrast checks on representative hardware. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-08-W15 — Audio asset composition

**Feature outcome and technical implementation.** Create original musical themes, adaptive loops, ambience, UI cues and gameplay stingers. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Output must be actual playable audio file with cleared rights, not a description. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Export in multiple codecs; listen/measure loop seam and in-game trigger. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-08-W16 — Procedural sound design

**Feature outcome and technical implementation.** Build attack, footsteps, collision, environment, UI and positional sound via source synthesis. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Missing audio references are blocking if brief explicitly requires sound. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Live audio event capture with content/level validation. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-08-W17 — Spatial sound and mixing

**Feature outcome and technical implementation.** Occlusion, reverberation, positional cues, side-chain ducking and accessibility controls. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Spatial audio cannot mislead critical hazard warning or blast loudness. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** In-game acoustic positioning and user volume/mono tests. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-08-W18 — Voice dialogue rights workflow

**Feature outcome and technical implementation.** Author or record narration with verified identity/consent, translation and retake controls. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Disallow unauthorized celebrity/actor voice imitation or undisclosed recordings. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Signed performer consent and verified audio playback where used. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-08-W19 — Subtitle and dialogue timing

**Feature outcome and technical implementation.** Synchronize text, speaker IDs, phonemes, voice and user text speed settings. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Missing caption for required voiced information fails accessibility. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Real cutscene transcript timing and screen-reader check. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-08-W20 — Asset style bible and continuity

**Feature outcome and technical implementation.** Encode palette, proportions, silhouette, material language, cost and emotional mood per project. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** AI iteration must not discard human-edited character identity. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Regenerate side scene and compare approved main cast continuity. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-08-W21 — Texture/atlas compiler

**Feature outcome and technical implementation.** Pack textures, validate color space, dedupe, mip and compression for each target. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Exceeding texture size/format caps must block unsupported target. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Godot/web build runtime check and package size metrics. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-08-W22 — Media build pipeline

**Feature outcome and technical implementation.** Encode normalized files, thumbnails, previews, licenses and immutable variant provenance. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Failed codec process cannot leave publicly visible corrupt artifact. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Interrupted transform, digest mismatch and clean resume test. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-08-W23 — Player-facing capture tools

**Feature outcome and technical implementation.** Record reproducible gameplay clips, trailers, screenshots and replay edits from real game. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Promotional video cannot be generated from nonexistent gameplay while claiming evidence. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Bind captures to source/game seed, input and frame logs. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-08-W24 — Human creative override

**Feature outcome and technical implementation.** Support manual editing of art, rigs, audio and cinematics with semantic diff and revision branch. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Automatic update cannot silently overwrite approved art or rights. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Manual edit persists through bot regeneration and target export. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-08-W25 — Narrative audiovisual accessibility

**Feature outcome and technical implementation.** Captions, speaker cues, high-contrast visuals, color-safe signaling, motion reduction and descriptive audio. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Gameplay objective cannot rely exclusively on color, hearing or camera shake. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Independent accessibility run through gold game sequence. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-08-W26 — Media quality measurement

**Feature outcome and technical implementation.** Collect objective animation continuity, collision timing, shader compile and audio clipping metrics. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Single subjective model score cannot certify polished visuals/audio. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Automated metrics paired with blinded human aesthetic review. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.


**BOT-08 closure rule:** all declared feature types have interoperable contracts; exact product journeys pass on supported targets; negative, rights, accessibility and performance obligations are satisfied; bugs/rejected candidates are retained in accountability; independent BOT-12 review agrees with source state. An undocumented limitation is a gap even if the implementation happens to work.

## BOT-09 — Godot/compiler toolchain, project interoperability, packaging and cross-platform release

**Primary owner paths:** skeleton/forge, skeleton/ai/game_builder, scripts/game, toolchain installers. **Priority envelope:** P0/P2. **Integration relationships:** 09->01/02/06/07/08/11/12. The bot must examine merged code, independent PR candidates and existing masterplan rows before deciding whether to build, improve, unify or reject a feature. All proposed capabilities begin at UNKNOWN maturity until evidenced. No platform and no declared engine support is automatically implied by a spec. Every relevant user action must show an actual durable result.

### BOT-09-W01 — Canonical Godot 4 project builder

**Feature outcome and technical implementation.** Generate scene tree, input actions, GDScript, assets, signal wiring, save code and gameplay export. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Generated code must not be shell-injection path, placeholder-only or invalid in engine. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Headless load, controller play, full win/lose and restart. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P0. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-09-W02 — Target feature negotiation

**Feature outcome and technical implementation.** Map mechanics/physics/media/saves to explicit Godot/web/mobile/retro target capabilities. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Unsupported mechanic must reject or request explicit reviewed downgrade. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Build requirements matrix and reject unknown platform capability. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P0. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-09-W03 — Game intermediate representation

**Feature outcome and technical implementation.** Compile canonical typed game spec into engine-specific assets with reversible provenance. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Lossy conversion of required mechanic or rights metadata blocked. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** IR to Godot and web differential semantics tests. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-09-W04 — WebGL/HTML5 playable export

**Feature outcome and technical implementation.** Produce sandboxed downloadable browser game with real input, audio and persistence. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Static webpage that only displays game metadata not accepted as game. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Chromium + Firefox interaction and frame capture. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-09-W05 — Windows game package

**Feature outcome and technical implementation.** Build actual game executable, assets, dependency license bundle and safe user data location. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Installer must not require admin or overwrite unrelated saves. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Physical Windows launch, controller completion and uninstall preservation. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-09-W06 — Linux desktop package

**Feature outcome and technical implementation.** Bundle native libraries or document dependency ABI with deterministic packaging. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Alpine/host ABI mismatch not hidden by source success. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Real Linux executable interaction with scene and audio. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-09-W07 — macOS packaging

**Feature outcome and technical implementation.** Provide signed/notarized path when credentials and target host legitimately available. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Cross-compile success not represented as macOS launch proof. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Actual macOS startup and input/gameplay test before target approval. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-09-W08 — Android game export

**Feature outcome and technical implementation.** Implement touch controls, lifecycle, permissions, asset packaging and performance profile. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** No network, mic or tracking permission without clear need. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Real Android device install, suspend/resume and finishable game. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-09-W09 — iOS game export

**Feature outcome and technical implementation.** Provide Xcode/target constraints, touch/input and app-store privacy declarations. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Lacking Apple tooling/device must remain unqualified. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Real iPhone target, test and publishing readiness only if available. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-09-W10 — Homebrew/retro targets

**Feature outcome and technical implementation.** Use approved toolchains, firmware rights, ROM budgets and emulator/hardware parity. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** No commercial ROM/firmware acquisition or unsupported ABI bypass. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Real accepted homebrew test artifact on approved emulator/core. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-09-W11 — Source export

**Feature outcome and technical implementation.** Package original complete editable project, manifests, licenses and source hashes. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Source-only export never counts as playable binary. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Re-import into fresh workspace and rebuild game successfully. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-09-W12 — Asset compatibility pipeline

**Feature outcome and technical implementation.** Convert meshes, audio, textures, sprites and animation to platform resource profiles. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Missing asset in exported scene blocks success. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Engine render/audio capture against produced package. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-09-W13 — Compiler error localization

**Feature outcome and technical implementation.** Map compile/parse/link failures to exact authored file, generated source and design step. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** No retry budget reset or arbitrary generated code execution. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Real compiler failure repair to tested, bounded patch. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-09-W14 — CI build isolation

**Feature outcome and technical implementation.** Run scripts and binary builds in sandbox with pinned inputs, deadlines and filesystem bounds. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Build plugin cannot access host secrets or arbitrary network. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Malicious build config denied in isolated worker. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-09-W15 — Build artifact reproducibility

**Feature outcome and technical implementation.** Seal source SHA, toolchain digest, env, options and package bytes or explain nondeterminism. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Unknown reused artifact or stale head blocked. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Independent repeated builds with declared acceptable digest/tolerance. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-09-W16 — Runtime testing harness

**Feature outcome and technical implementation.** Instrument input, snapshots, frames, logs, audio, victory predicates and player telemetry. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** CORE_LOOP_OK string alone not full interactive acceptance. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Headless plus GUI playthrough on finished golden games. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-09-W17 — Performance and optimization profiles

**Feature outcome and technical implementation.** Build baseline/optimized variants measuring draw calls, CPU, VRAM and load time. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Optimization cannot introduce gameplay regression. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Target device performance and replay comparison. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-09-W18 — Game patch/delta updater

**Feature outcome and technical implementation.** Produce verified update manifest, content delta and atomic rollback of saves/assets. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Interrupted patch cannot corrupt install or make old saves invisible. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Kill process during delta apply and resume safely. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-09-W19 — Modding and extensibility

**Feature outcome and technical implementation.** Export signed constrained data/script plugin APIs and permission manifests. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Arbitrary mod cannot access filesystem/secrets/network beyond grant. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Adversarial mod and compatibility tests. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-09-W20 — Interoperable project import

**Feature outcome and technical implementation.** Accept legitimate user-owned Godot/Unity-like scene/material data under bounded safe parsers. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Proprietary or executable imports require explicit rights and isolated transform. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Import sample user-provided project and preserve playable semantics. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-09-W21 — Storefront packaging

**Feature outcome and technical implementation.** Create compliant icon, trailer, metadata, screenshots, ratings, credits and platform-specific bundle. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Marketing ready does not equal rights, payment or platform approval. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Reviewable packaging dossier with verified source assets. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-09-W22 — Console platform path

**Feature outcome and technical implementation.** Define licensed SDK authorization, hardware testing and legal release prerequisites. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Public repo cannot promise certified proprietary console binaries. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Explicit hold until platform-holder tools and approval provided. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-09-W23 — Multiplayer server exports

**Feature outcome and technical implementation.** Package authoritative server/session state with migration and exposed-port controls. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Client and server version mismatch cannot silently corrupt state. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Reconnect, latency and malicious-client test. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-09-W24 — Game save portability

**Feature outcome and technical implementation.** Export versioned save data preserving player agency, original assets and privacy policy. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Incompatible save migration cannot fabricate player choices. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Transfer save between two declared compatible targets and replay. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-09-W25 — Engine upgrade manager

**Feature outcome and technical implementation.** Treat engine minor/major changes as compatibility and binary requalification campaign. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Do not switch to unverified beta engine just for newest label. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Run matrix on pinned stable supported Godot and feature migration tests. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-09-W26 — Release binary supply chain

**Feature outcome and technical implementation.** Produce signed checksums, SBOM, provenance, reproducible build receipt and rollback package. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Unsigned or ancestor-verified executable cannot become stable release. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Independently verify artifact digest against exact codehead and signing identity. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.


**BOT-09 closure rule:** all declared feature types have interoperable contracts; exact product journeys pass on supported targets; negative, rights, accessibility and performance obligations are satisfied; bugs/rejected candidates are retained in accountability; independent BOT-12 review agrees with source state. An undocumented limitation is a gap even if the implementation happens to work.

## BOT-10 — Dragon crawler, Atlas research campaigns, permissioned source knowledge and game learning bridge

**Primary owner paths:** skeleton/ai/webcrawler, backend/core/dragon_crawler.py, backend/routes/dragon_academy.py, frontend/src/features/Jeeves. **Priority envelope:** P0/P2. **Integration relationships:** 10->02/03/04/11/12. The bot must examine merged code, independent PR candidates and existing masterplan rows before deciding whether to build, improve, unify or reject a feature. All proposed capabilities begin at UNKNOWN maturity until evidenced. No platform and no declared engine support is automatically implied by a spec. Every relevant user action must show an actual durable result.

### BOT-10-W01 — Signed authorized crawl request

**Feature outcome and technical implementation.** Bind owner, tenant, consent, source rights, purpose, hosts and finite request/page/byte budgets. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Missing consent/expired permission prohibits new acquisition without override. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Live authenticated route and denied-scope tests. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P0. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-10-W02 — SSRF-safe network capture

**Feature outcome and technical implementation.** Normalize host/IP, redirects, DNS rebinding and blocked private address ranges. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** No localhost, cloud metadata or internal API fetching via untrusted seed. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Controlled adversarial DNS/redirect/IPv6/private-IP scenarios. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P0. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-10-W03 — Robots and lawful source policy

**Feature outcome and technical implementation.** Respect legal/terms/operator grants, crawl delays and source-specific restrictions. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Source availability is not an automatic copyright/license grant. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Policy matrix with express denial of prohibited hosts. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P0. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-10-W04 — Bounded crawl scheduler

**Feature outcome and technical implementation.** Persist frontier, per-host fairness, leases, request/deadline reservations and resumable slices. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Crash cannot repeat consumed grant or expand host scope. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Multi-host fairness and worker restart without excess requests. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-10-W05 — Differential recrawl pipeline

**Feature outcome and technical implementation.** Use ETag/Last-Modified, digest comparison, content revision and freshness windows. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Stale or changed evidence cannot silently retain old acceptance. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Real versioned controlled website and source update trace. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-10-W06 — HTML/structured content extraction

**Feature outcome and technical implementation.** Parse pages, semantic sections, title, accessible text, tables and anchors safely. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Active content/scripts and embedded instructions remain inert untrusted data. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Known fixtures and real pages retain exact text/citation offsets. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-10-W07 — Research Atlas graph

**Feature outcome and technical implementation.** Link source, passage, claim, topic, contradiction, review and game-design use. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** UI representation cannot imply backend bridge exists when route unmounted. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Authenticated Atlas open/search/cite against actual backend. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-10-W08 — Source dependency and revocation

**Feature outcome and technical implementation.** Maintain transitive graph with erasure, withdrawal and refreshed citation validity. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** A withdrawn source cannot reappear via cache or training/reference store. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Withdraw source and verify every dependent projection becomes invalid. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-10-W09 — Injection and low-signal quarantine

**Feature outcome and technical implementation.** Recognize instruction hijacks, deceptive metadata, missing provenance and truncated pages. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Quarantined content never promoted into trusted model system instructions. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Adversarial page test suite across prompt and evidence consumption. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-10-W10 — Campaign objectives and stop policy

**Feature outcome and technical implementation.** Define research goals, question tree, budget, information gain and clear termination. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Bot cannot expand purpose, budget or target by self-authorized planning. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Campaign stops on budget, novelty floor, consent expiry and owner request. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-10-W11 — Cross-document corroboration

**Feature outcome and technical implementation.** Compare primary and secondary sources, time, dependency, duplicate upstream origins. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Repeated syndicated claims do not count as independent evidence. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Contradictory controlled source experiment with lineage flags. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-10-W12 — Evidence quality scoring

**Feature outcome and technical implementation.** Grade citation specificity, source trust, recency, relevance and contradictory signals. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Scores remain observations, not proof of truth or source license. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Known gold/false source pairs with calibrated abstention. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-10-W13 — Reviewed mechanic inspiration

**Feature outcome and technical implementation.** Translate admitted observations into original mechanic hypotheses with owner approval. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Copying protected passages into game content without license denied. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Reviewer approves original mechanic, exports game with only eligible facts. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-10-W14 — Research-to-world integration

**Feature outcome and technical implementation.** Bind approved observations to world/quest/asset briefs as derived references and limits. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Source withdrawal must invalidate affected generated candidates. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Gameplay world regen after revoked supporting research. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-10-W15 — Live frontend crawl workbench

**Feature outcome and technical implementation.** Implement typed capture, status, review, export, erasure and failure UX. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** UI must reject unauthorized action without fake optimistic completion. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Browser authenticated capture and owner/user role switching. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-10-W16 — Dragon Atlas backend adapter

**Feature outcome and technical implementation.** Connect #4876 bridge to authoritative Mongo campaign/claim data with policy validation. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Do not clear backend-route hold from source-only UI tests. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Reproduce bridge test failure then exact-head focused integration. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-10-W17 — Source-document integrity

**Feature outcome and technical implementation.** Bind retained text SHA, byte size, Unicode offsets and anchored passages. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Cached citation cannot silently refer to revised different page. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Exact passage re-resolution on dynamic source revisions. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-10-W18 — Crawler worker process custody

**Feature outcome and technical implementation.** Track physical executor join, cancellation, heartbeat and crash recovery distinctly. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Expired lease is not evidence worker has terminated. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Kill/wake and delayed worker stress without double reservation. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-10-W19 — Multilingual research and quotes

**Feature outcome and technical implementation.** Retain language, script, encoding and source-offset semantics across extraction/translation. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Unreviewed machine translation is not a source-original quote. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Side-by-side multilingual passage citations and rights. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-10-W20 — Crawler privacy controls

**Feature outcome and technical implementation.** Redact private content, avoid accidental credentials and minimize source-data exposure. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Personal source export not available to unrelated tenant or viewer. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Cross-role export/erase and redacted logging audits. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-10-W21 — Research cache correctness

**Feature outcome and technical implementation.** Cache only immutable source snapshot eligible under current consent and revision. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Consent revocation cannot be bypassed by offline cached response. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Stale-cache isolation and explicit offline-only reading. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-10-W22 — Forensic hash-chain journals

**Feature outcome and technical implementation.** Record command, worker receipt, source outcome and version-CAS as tamper-evident lineage. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Tampered journal invalidates downstream evidence and campaign result. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Replay corruption, missing event and out-of-order manifest tests. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-10-W23 — Research suggestion ranking

**Feature outcome and technical implementation.** Rank useful legitimate sources from admitted frontier without unsolicited new host crawling. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Discovery suggestions are advisory, not network grants. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** User approval before any new-source/host acquisition. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-10-W24 — Dragon companion and practice

**Feature outcome and technical implementation.** Reflect legitimate observed research sessions as companion progression and learning aids. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Pet XP does not equal verified scientific knowledge or trained model weights. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Compare reported XP against actual committed activities. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-10-W25 — Knowledge source lifecycle UX

**Feature outcome and technical implementation.** Provide review queues, approve/reject, citations, withdrawal and replayable reason logs. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** One-click approval cannot promote unauthorized source content. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Reviewer role and source revocation end-to-end browser test. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-10-W26 — Campaign scale performance

**Feature outcome and technical implementation.** Measure per-host throughput, memory, extracted bytes, queue depth and source freshness under limits. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Unbounded spidering, giant HTML and slow remote transport rejected. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Constrained site and intermittent network pressure test. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.


**BOT-10 closure rule:** all declared feature types have interoperable contracts; exact product journeys pass on supported targets; negative, rights, accessibility and performance obligations are satisfied; bugs/rejected candidates are retained in accountability; independent BOT-12 review agrees with source state. An undocumented limitation is a gap even if the implementation happens to work.

## BOT-11 — Visual studio product, creator experience, collaboration, accessibility and monetization

**Primary owner paths:** frontend, backend/routes, skeleton/app, skeleton/forge. **Priority envelope:** P1/P3. **Integration relationships:** 11->01/02/03/04/05/06/08/09/10/12. The bot must examine merged code, independent PR candidates and existing masterplan rows before deciding whether to build, improve, unify or reject a feature. All proposed capabilities begin at UNKNOWN maturity until evidenced. No platform and no declared engine support is automatically implied by a spec. Every relevant user action must show an actual durable result.

### BOT-11-W01 — Unified creator cockpit

**Feature outcome and technical implementation.** Unite setup, Jeeves, worlds, Dragon, build, asset library and operations in one consistent navigation. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** No duplicated hidden project identity or inconsistent route auth. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Fresh owner completes idea-to-play journey from landing screen. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-11-W02 — Real visual scene editor

**Feature outcome and technical implementation.** Provide hierarchy, canvas/viewport, property inspector, gizmos and typed editing operations. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Drag/drop and editor controls must write canonical project state not local demo only. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Open project, move actor, save and see change in exported Godot game. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-11-W03 — Node graph and scripting parity

**Feature outcome and technical implementation.** Author behavior, dialogue, quest and effects through graphs synchronized with typed code. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Unsupported graph nodes must not silently vanish on export. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Edit via graph, inspect code, change code and roundtrip same behavior. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-11-W04 — Embedded playable preview

**Feature outcome and technical implementation.** Let user launch actual game with input, debug controls, frame capture and restart. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Screenshot-only preview does not count as interactive. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Use editor preview to complete golden platformer and observe persistence. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-11-W05 — Editor undo/redo

**Feature outcome and technical implementation.** Persist reversible commands, selection history, branching checkpoints and semantic diff. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** An agent edit cannot erase human work or bypass revision check. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Multiple undo/redo cycles with cold restart and conflict. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-11-W06 — Project templates and onboarding

**Feature outcome and technical implementation.** Offer proven original-game starting kits with asset manifests and game-loop tutorial. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Template cover image without runnable engine is ineligible. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** New account makes first successful playable edit quickly. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-11-W07 — Jeeves conversation UX

**Feature outcome and technical implementation.** Show model readiness, sources, tools, reason for blocked actions, controlled streaming and durable sessions. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Rendered assistant text not treated as committed artifact. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Authenticated source-bound chat with real model + tool approval. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-11-W08 — Collaborator invitations and roles

**Feature outcome and technical implementation.** Invite users to a project with scoped editor, reviewer and viewer access. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Invite link/role must not leak private model, source or external vault data. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Three-account tenant isolation and invitation revocation tests. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-11-W09 — Realtime collaboration CRDT/OT

**Feature outcome and technical implementation.** Converge concurrent scene/text edits with branching, conflict detection and offline rejoin. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Last-writer-wins across structured world/quest edges prohibited. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Two clients offline edit then reconcile without lost data. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-11-W10 — Review and annotation system

**Feature outcome and technical implementation.** Pin comments, design critiques and approval to scene/asset/source revision. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Resolved review cannot apply silently to changed underlying artifact. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Reviewer sees stale annotation and re-review requirement. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-11-W11 — Visual production board

**Feature outcome and technical implementation.** Show deliverable DAG, bot ownership, running jobs, budgets, blocked tests and exact PR refs. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Dashboard cannot represent queued/pending checks as successful. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Compare UI status to actual GitHub/owner receipts. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-11-W12 — Creator asset gallery

**Feature outcome and technical implementation.** Search licenses, thumbnails, rigs, materials and media variants by real provenance. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Withdrawn or unlicensed asset cannot be rediscovered via gallery. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Source withdraw and permission-specific search tests. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-11-W13 — World editor interaction

**Feature outcome and technical implementation.** Author characters, settlements, quests, maps, dialogue and timeline on canonical graph. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** No write through a second disconnected frontend state store. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Multi-step scene + quest edit makes actual game behavior change. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-11-W14 — Localization infrastructure

**Feature outcome and technical implementation.** Support interface and game text, pluralization, RTL/layout and translation management. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Missing translations declared fallback rather than broken control. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Browser and game play at representative languages/screen sizes. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-11-W15 — Responsive and offline UX

**Feature outcome and technical implementation.** Work on desktop, mobile-width browsers and optionally offline project editing with finite sync. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Offline mode must not invent successful server commits. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Disconnected user modifies local draft then explicit reconciliation. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-11-W16 — Keyboard/gamepad accessibility

**Feature outcome and technical implementation.** Navigate cockpit, scene editor and game preview without pointer-only interaction. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Essential workflows fail if only drag gesture exists. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Automated axe/keyboard/manual screen-reader and controller audit. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-11-W17 — Motion, color and audio accessibility

**Feature outcome and technical implementation.** Reduced animation, captions, contrast, focus, large text and mono-audio controls. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Games cannot rely solely on inaccessible sensory channel. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Accessible golden game run plus UI contract checks. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-11-W18 — Private user account and portfolio

**Feature outcome and technical implementation.** Manage projects, owned licenses, public pages, versions, provenance and privacy settings. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Private content must never appear in public search or analytics. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Viewer vs owner vs collaborator result isolation. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-11-W19 — Template/plugin marketplace

**Feature outcome and technical implementation.** Curate signed original templates, kits and extensions with permission/compatibility manifest. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Unverified plugin not executable as host process. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Safe sandbox test and approved package lifecycle. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-11-W20 — Payments and entitlement ledger

**Feature outcome and technical implementation.** Design atomic idempotent checkout, settlement, refunds, upgrades and scoped entitlements. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Duplicate webhook/downgrade cannot double charge or grant wrong owner. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Concurrency/replay fixtures and provider-bound verified delivery. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-11-W21 — Creator publishing flow

**Feature outcome and technical implementation.** Collect game metadata, rights, credits, ratings and storefront-specific export readiness. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Listing does not imply legal or platform certification. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Publish candidate held until independent source and binary verification. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-11-W22 — Playtest user research panel

**Feature outcome and technical implementation.** Capture consented user sessions, notes, bug repro, fun metrics and video artifacts. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Tests must separate simulated telemetry from human player judgment. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Blind playtest and feedback linked to exact game build. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-11-W23 — Studio knowledge/search

**Feature outcome and technical implementation.** Search own projects, authored source, versions, tasks and admitted research with project/rights scope. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Search result cannot reveal private deleted/withdrawn source. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Mixed-tenant and redaction index test. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-11-W24 — Gamified Dragon companion

**Feature outcome and technical implementation.** Render companion progression, journaling and bounded practice without confusing trust. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Companion visual flair cannot become evidence of research truth. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Test experience on low-power reduced-motion devices. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-11-W25 — Help, diagnostics and recovery UX

**Feature outcome and technical implementation.** Explain nonfunctional services, needed models/cores and exact action to fix. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** UI error must not tell owner to disable guard or delete volumes. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Fault each backend dependency and evaluate actionable diagnosis. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-11-W26 — Creator support and updates

**Feature outcome and technical implementation.** Surface verified release notes, backup/restore, known limitations, privacy and rollback. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** No misleading “ready” badge when target/platform unqualified. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** App version and supported-target reporting match artifacts. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.


**BOT-11 closure rule:** all declared feature types have interoperable contracts; exact product journeys pass on supported targets; negative, rights, accessibility and performance obligations are satisfied; bugs/rejected candidates are retained in accountability; independent BOT-12 review agrees with source state. An undocumented limitation is a gap even if the implementation happens to work.

## BOT-12 — Assurance, security, independent gameplay QA, exact-head CI and release governance

**Primary owner paths:** scripts/check_*.py, .github/workflows, skeleton/testing, backend/tests, frontend/scripts. **Priority envelope:** P0. **Integration relationships:** 12->all. The bot must examine merged code, independent PR candidates and existing masterplan rows before deciding whether to build, improve, unify or reject a feature. All proposed capabilities begin at UNKNOWN maturity until evidenced. No platform and no declared engine support is automatically implied by a spec. Every relevant user action must show an actual durable result.

### BOT-12-W01 — Full-source inventory and discrepancy

**Feature outcome and technical implementation.** Obtain complete clone, object-level tree, PR set, file hashes, architecture/manifest conformity. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Partial snapshots and search results cannot certify entire repository. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Independent compare Git object tree, plan registry and artifact manifests. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P0. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-12-W02 — Exact-head workflow reconciliation

**Feature outcome and technical implementation.** Enumerate required workflows by event/branch/PR SHA, versions, outputs and statuses. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Skipped, queued, cancelled, ancestor and superseded checks are not passes. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** GitHub API proof of all mandatory named jobs at exact final head. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P0. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-12-W03 — P0 gate execution campaign

**Feature outcome and technical implementation.** Run architecture, provider guard, assembly, security, frontend, backend, game, native and storage suites. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** One succeeded sibling cannot waive a failed architecture or adapter job. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Record first failing step, repair then rerun all impacted checks. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P0. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-12-W04 — Independent game play agent

**Feature outcome and technical implementation.** Control real Godot/browser game through legal observable inputs and compare expected state. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Model judge cannot read builder private answer or grant itself success. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Blind self-play on golden games with saved trace, screenshots and fail logs. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P0. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-12-W05 — GameCraft-like acceptance benchmark

**Feature outcome and technical implementation.** Assess engine grounding, full artifact completeness and actual interactive success by genre. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Static success marker insufficient for full-task pass. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Curate 2D/3D tasks and score conjunctive input/state/render requirements. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P0. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-12-W06 — Bug detection and repair benchmark

**Feature outcome and technical implementation.** Inject real gameplay, compiler, asset, UX and save defects; evaluate diagnosis/repair. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Test harness cannot leak secret fix or allow skipping hard case. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Independent reproduction before/after patch with regression run. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P0. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-12-W07 — Cumulative optimization benchmark

**Feature outcome and technical implementation.** Measure multiple chained edits maintaining prior function while improving targeted metric. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Optimizer cannot claim progress by dropping features. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Six-turn project evolution with strict overall task pass. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P0. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-12-W08 — Threat model and trust boundaries

**Feature outcome and technical implementation.** Inventory prompt injection, SSRF, deserialization, build sandbox, rights, privilege and third-party supply chain. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Security pass cannot be inferred from absence of alerts in narrow test. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Cross-plane attack tree, test fixtures and manual review. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P0. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-12-W09 — Secret scanning and remediation

**Feature outcome and technical implementation.** Review historical and current findings, decide real vs fixture, rotate confirmed exposed credentials. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Never blanket suppress unknown tokens or publish them in report. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Classified finding ledger, rotation proof and final secret gates. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P0. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-12-W10 — Filesystem and archive fuzzing

**Feature outcome and technical implementation.** Race symlinks, parent swaps, hard links, FIFOs, zip bombs and image/audio decompression. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Any unsafe path or unbounded content fails before read/write. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Cross-platform safe descriptor test and sandbox isolation. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P0. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-12-W11 — Mongo/SQLite/Chroma fault matrix

**Feature outcome and technical implementation.** Simulate primary loss, journal interruption, disk exhaustion, clone conflicts and restore. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Uncertain commit cannot be counted as success. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Real database kill and recovery with authoritative readback. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P0. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-12-W12 — Physical worker accounting

**Feature outcome and technical implementation.** Verify deadlines, cancellations, leases, native worker join, token cost and queue fairness. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Timed-out process cannot release capacity until physical exit. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Stress twelve-bot workload with resource and crash logs. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P0. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-12-W13 — Installer hardware test

**Feature outcome and technical implementation.** Validate clean Windows 11/WSL2 Docker and local GGUF activation on owner-like machine. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Hosted CI is not a physical-device acceptance substitute. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Signed tested host report with full first-install user journey. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P0. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-12-W14 — Accessible UX/game testing

**Feature outcome and technical implementation.** Review screen reader, keyboard, controller, captions, contrast, reduced motion and seizure triggers. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Essential creator workflows inaccessible cannot be marked complete. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Automated+manual accessibility tests on actual runtime. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-12-W15 — Performance and long-run soak

**Feature outcome and technical implementation.** Capture p50/p95/p99 startup, frame time, memory, GPU, model throughput, disk, recovery tails. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Averages cannot hide severe 99th percentile stalls. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Endurance test with explicit target hardware and sample logs. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-12-W16 — Rights and licensing certification

**Feature outcome and technical implementation.** Audit models, toolchains, fonts, audio, assets, sources, game content and distribution terms. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Missing source license or withdrawal blocks dependent release. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Origin/attribution manifest and removed-source artifact test. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-12-W17 — Financial security verification

**Feature outcome and technical implementation.** Confirm payment provider webhook, settlement, charge retries, refunds and entitlements. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** No checkout release until atomic concurrent settlement is proven. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Replay, reorder, forged webhook and timeout cases. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-12-W18 — Malware and dependency gates

**Feature outcome and technical implementation.** Scan code, archives, media, generated artifacts and pinned dependency graph. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Executable-looking media or unknown archive cannot be trusted by extension. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Policy corpus plus real malware/dependency scanning. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-12-W19 — Release provenance and signing

**Feature outcome and technical implementation.** Verify source tree, all required CI, package digest, SBOM, approvals and independent signer. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Never promote on docs-only/ancestor/mock-only evidence. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Rebuild exact source and verify signature/transparency trail. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-12-W20 — Disaster recovery rehearsal

**Feature outcome and technical implementation.** Restore user installation, asset graph, model receipts, games and saves from known backup. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Successful archive creation is not proof archive can restore. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Cold isolated restore and actual game play from recovered snapshot. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-12-W21 — PR dependency and conflict solver

**Feature outcome and technical implementation.** Map stacked branches, overlapping files, changes moved to main and necessary rebase. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Never mass merge incompatible PRs or force over branch protection. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Graph-based conflict-free merge readiness per exact head. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-12-W22 — Regression test quality audit

**Feature outcome and technical implementation.** Find tautological mocks, false-positive fixtures, setup bypasses and brittle source assertions. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Passing tests that never exercise behavior do not qualify. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Mutation testing and live boundary tests with injected defects. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-12-W23 — Quality and human feedback review

**Feature outcome and technical implementation.** Blind score mechanic clarity, audiovisual feedback, engagement and accessibility alongside objective tests. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Model's subjective praise is not independent or release evidence. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Third-party player panel comparing candidate with baseline. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-12-W24 — Documentation-to-runtime truth

**Feature outcome and technical implementation.** Reconcile README, manifest, setup guide, playbook, source, UI and release notes. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Guide cannot promise features blocked or missing in target build. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Follow documentation from clean host and log actual deviation. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-12-W25 — Release hold and risk communication

**Feature outcome and technical implementation.** Distinguish open unknown, confirmed blocker, waived scoped risk, accepted target and release decision. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** Bot cannot unilaterally waive critical trust or content-rights holds. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Human operator sees exact gate IDs, evidence and unresolved risk. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.

### BOT-12-W26 — Final product acceptance scorecard

**Feature outcome and technical implementation.** Compute journey success, genre/platform coverage, risk, resource, accessibility and defect regression. Trace this change from its design/game/source event through canonical API, versioned state, representation, worker or editor, and the target runtime where applicable. Record exactly which subsystem owns the mutation, expected user control, rollback semantics and what happens when a dependent game asset/model/engine is missing. Build one complete representative outcome before multiplying variations.

**Failure, integrity and safe limits.** No completion percentage from file counts or test total alone. Include bounded input/byte/complexity/clock budgets, actor/tenant/permission and current-head checks as appropriate. Preserve human-authored revisions and don't replay already-committed effects. Invalidate outdated previews, game build outputs and source-derived knowledge when authoritative inputs change. A source file, unverified fixture or generated documentation never qualifies as gameplay.

**Completion proof and target behavior.** Independent reproducible multi-axis score tied to shipped artifacts. Capture commands, toolchain versions, actual created files, test output and negative cases on the originating final SHA. Where user experience is material, require independent in-game/button-level interaction, visible output, meaningful player response and save/restart trace. BOT-12 must independently verify before release promotion. **Priority:** P1/P2/P3. **Status:** UNKNOWN until current-tree census and proof review.


**BOT-12 closure rule:** all declared feature types have interoperable contracts; exact product journeys pass on supported targets; negative, rights, accessibility and performance obligations are satisfied; bugs/rejected candidates are retained in accountability; independent BOT-12 review agrees with source state. An undocumented limitation is a gap even if the implementation happens to work.
