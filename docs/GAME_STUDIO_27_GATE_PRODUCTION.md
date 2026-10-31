# Canonical game studio — 27 source-bound acceptance gates

This document describes executable candidate-quality work in `skeleton/game`.
It is **not** a new game engine, second application controller, model provider,
license authority, native graphics benchmark, or production-release signer.

## Current owner and composition

- Seven foundational gates: world graph, narrative canon, assets, deterministic
  build replay, frame budget, rights-evidence declarations, composite readiness.
- Seven production-depth gates: GDD traceability, quest endings, accessible UI,
  controller mapping, hardware envelopes, session hash chains, package closure.
- Seven frontier gates: asset lineage, longform character/plot continuity,
  multi-scenario navigation, physics observations, LOD, localization, comparable
  performance.
- Seven studio gates: cinematic shots; spoken dialogue/captions/phonemes; NPC
  state liveness; streamable world-chunk residency; save version migration;
  dynamic environmental replay; controller input-to-render latency.

Audits are deterministic, bounded, source-pinned Python functions. The
`audit_complete_studio(candidate)` function produces `game.candidate.complete_studio.v1`
and runs all **27** checks in the above ordered hierarchy. It returns a
canonical report with `source_digest`, `gates`, `findings`,
`evidence_digest`, `candidate_passed`, and `release_certified=False`.

`verify_complete_studio(original, report)` recomputes the source and compares
the complete report; `verify_report_structure(report)` independently rejects
malformed or inconsistent outcomes. Neither proves that original source bytes
were actually captured by a third party. Hash checks alone are not signatures.

## Authoring and source input

Each candidate retains the existing complete 20-gate input contract and adds:

```text
candidate["source_sha256"] : sha256 hex of the same authoring source
candidate["studio"]["source_sha256"] : identical canonical source digest
candidate["studio"]["cinematics"] : authored scenes and shot timelines
candidate["studio"]["dialogue"] : caption/phoneme timings and voice hash declarations
candidate["studio"]["npcs"] : typed NPC state graphs, timeouts, terminal states
candidate["studio"]["streaming"] : chunk budgets, dependencies, neighborhoods
candidate["studio"]["saves"] : supported schema versions, migration steps, proofs
candidate["studio"]["environment"] : source hazard states, transitions, observations
candidate["studio"]["latency"] : actual observation records and response thresholds
```

Every studio subsection must contain `source_sha256` equal to the root and
all previous frontier source families. Mixed-source evidence raises a
`QualityGateError`. Unavailable evidence must remain missing and block its
gate rather than be filled by model-generated favorable values.

## Seven substantive original-game audit policies

| Plane | Contract | Critical fail-closed observation |
|---|---|---|
| Cinematics | Ordered frame-exact shots, camera FOV/clip bounds, intentional shot direction | Gap, overlap, camera failure or incomplete scene |
| Dialogue sync | Voice hash and caption timing, observed phonemes, bounded sync tolerance | Missing voice, subtitle drift or invalid phoneme ordering |
| NPC behavior | Traversable state transitions, finite nonterminal timeouts, path to terminal | Unreachable branch, dangling link or deadlocked behavior |
| World streaming | Traversable chunk adjacency, derived preload dependency closure, per-region bytes | Oversized source chunk, dangling dependency, resident-memory overrun |
| Save evolution | Monotonic schema migration paths with source/transform/output hashes | Unrecoverable historical save, missing independent replay |
| Dynamic world | Source-pinned hazard effects, weighted transitions, mitigation and replay coverage | Unmitigated hazard, invalid transition distribution or missing effect proof |
| Input latency | Separate keyboard/gamepad timestamps, p95/p99 from independently supplied samples | Missing device, nonmonotonic observation, out-of-budget latency |

All limits are resource/abuse boundaries on individual audit requests; they
are **not** a limit on total campaign duration or number of authored games.
Partition large productions into independently receipted source snapshots.

## Six operational augmentations

1. **Independent integrity + Dragon adversarial review:** mutate each studio
   plane, forge one gate and forge the aggregate summary; pass only if all
   mutations are rejected.
2. **Objective comparative evaluation:** count new/resolved gate findings and
   mark critical regressions; compare distinct source snapshots without
   pretending they are identical workloads or interchangeable releases.
3. **Canonical owner routing and measured repair:** route each finding to a
   subsystem owner. Independently authorize each exact old-value edit, replay
   all 27 gates and accept only strictly decreasing defect counts. A preview
   edits an isolated in-memory candidate and cannot forge SHA/approval fields.
4. **Persistent quality lifecycle:** the existing SQLite `QualityHistoryStore`
   accepts 13-, 20-, and 27-plane reports in one source-bound journal, using
   WAL, optimistic generation checks, chained SHA-256 receipts and independently
   checked historical generations. Operator decisions are a separate append-only
   chain. Pin the latest head externally to detect truncation.
5. **Jeeves Studio authorization:** tool handlers are injected by a trusted
   game host and registered through the existing `StudioCommand` tool registry
   with per-command authorization. No model may supply its own trusted
   `source provider`, filesystem root, reviewer identity or native witness.
6. **Native-source evidence bridge:** a host may supply a real
   `run_headless_expedition` report and compiled source-backed Godot files.
   `inspect_native_game_witness` checks the runner's claimed native execution,
   source digest, game/world digest and canonical package receipt. It does
   **not** assert GPU capture, process attestation, physical-device latency
   or legal rights clearance.

## Trusted-host tool contract

`complete_studio_quality_handlers(projects, store=..., operator_id=...)`
returns eight concrete owner functions:

- Read: `game.studio.quality.audit`,
  `game.studio.quality.dragon`, `game.studio.quality.work`,
  `game.studio.quality.diff`, `game.studio.quality.history`,
  `game.studio.quality.native.inspect`.
- Write: `game.studio.quality.record`,
  `game.studio.quality.review`.

When the host additionally injects **both** `approve_patch` and
`verify_candidate`, it also exposes the isolated read-only
`game.studio.quality.repair.preview` operation. It accepts only bounded
scalar edits under the seven governed studio authoring families. Source
identity, provenance, review, native claims, hashes and observation metadata
cannot be edited by this preview. It returns a diagnosis and receipt; it never
writes the original game.

The model/Studio user must receive an exact per-invocation tool grant.
Simply registering the handler does not grant execution rights.

## Verification expectations

Specialized `.github/workflows/game-frontier-validation.yml` invokes syntax
compilation, original frontier acceptance and every `test_game_production_*`
suite, including synthesized negative fixtures for all 27 gates, persistence,
adversarial checks and tool authorization. Pinned Godot smoke is a **separate**
real-native qualification route, not an autogenerated substitute for hardware
or external reviewer evidence. A red check means the current PR cannot claim
verified acceptance. An unstarted or pending check is not a pass.

## Release boundary

Passing the game-production candidate gate is necessary but not sufficient
for shipping. The existing authoritative release process must still establish
legal/copyright originality and independently reviewed source rights, exact
built binaries, source-to-native replay, target hardware/device performance,
user-approved platform packaging and production-signature authority. The
assistant must never replace missing rights or native evidence with claimed
success, retitle a simulated playthrough as native, or merge an unverified head.
