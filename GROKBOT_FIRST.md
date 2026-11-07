
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
