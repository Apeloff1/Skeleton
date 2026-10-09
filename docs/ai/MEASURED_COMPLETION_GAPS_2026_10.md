# Skeleton AI — Measured Implementation Gaps

**Evidence snapshot:** 2026-10-09. **Purpose:** report reproducible gaps and
close them in implementation order without conflating masterplan signoffs,
source presence, passing checks and a genuinely usable standalone AI product.

This document is a working engineering ledger, **not** a completion signature.
Every `implemented_in_pr` item still requires exact-head validation and release
acceptance. The figures below are classifications from canonical machine
authorities inspected on this date, not a measured quality benchmark.

## Baseline measurements

| Authority | Recorded value | What it proves / does not prove |
| --- | --- | --- |
| `machine/ai_master_plan.json` | 421 volumes; 414 verified, 7 hardened | Plan implementation classifications, **not** a tested application |
| Masterplan enterprise state | 421 designed, 0 enterprise-qualified | Enterprise qualification is still outstanding |
| `machine/ai_capabilities.json` | 9 product capabilities; 0 marked complete | Functional product closure is **not recorded** |
| Capability distribution | 5 partial, 3 present-transport/partial-product, 1 planned | Product maturity differs substantially by capability |
| `machine/ai_app_construction.json` | 27 declared planes, 17 registered construction gaps | The 17 are declarations; cannot alone prove all releases/gates pass |
| `machine/ai_masterplan_parse_index.json` | 421/421 recorded signed, indexed master blob `5f6c1119…` | The actual masterplan Git blob `1733c384…` differs; signatures are stale as an exact-source claim |
| Standalone offline app PR | #3597, unmerged at snapshot | Contains implementation; must pass exact-head CI and installed Windows/GGUF acceptance |
| Serving-hardening PR | #3595, unmerged at snapshot | Separate patch; production validation and landing still required |

**Global completion:** intentionally **not estimated as a single percentage**.
No defensible cross-domain weighting, trained-model quality benchmark or
release attestation exists to support one.

## Ordered gap register

### A-01 · Release and exact-head proof — BLOCKING

**Gap:** GitHub reported major PR validation checks queued rather than
successful, and neither AI PR is merged. A Git-mergeable branch is not a
passing application.

**Implementation:** `p2-local-inference.yml` now runs native runtime, desktop
persistence, headless chat, offline reference library, localhost API and
cancellation regressions. `windows-installer.yml` checks out the exact
PR SHA, builds Setup.exe and invokes frozen
`Skeleton.exe --local-ai-smoke` plus `--local-http-smoke`. The second smoke
requires a real authenticated local request, native generation, identical
request replay, local document search, clean HTTP shutdown and fresh SQLite
recovery.

**Exit:** successful checks on **the exact final commit**, reproducible local
installer run and reviewed evidence. Do not sign before execution.

### A-02 · Durable offline conversation and interruption recovery — implemented_in_pr, unqualified

**Prior gap:** context-window eviction dropped historical chat turns; an HTTP
retry after a lost reply could create duplicate output; cancellation could
outlive its inference worker; stored turn counters did not validate all
historical receipts.

**Repairs:** `offline_chat.py`, `local_ai.py`, `local.py`,
`offline_web.py`; full SQLite message/receipt snapshot, content-bound
optimistic CAS, pre-generation capacity checks, idempotent retry, bounded
shutdown, cancelled/deadline output denial, reference-preserving imports,
forking and explicit session switching.

**Exit:** the focused CI suite, real restart/fault injection on installed
Windows and independent corrupted-file review.

### A-03 · Offline searchable sources — implemented_in_pr, unqualified

**Prior gap:** the local standalone chat had no way to ingest and retrieve
operator-owned documentation without hosted search.

**Repairs:** `skeleton/app/offline_knowledge.py` stores exact-byte-hashed
text references inside the same **model-tokenizer-pinned SQLite authority**.
It provides deterministic indexed chunks with verified source character
offsets, authenticated localhost upload/search/delete, browser controls
and headless text-file ingestion/search. Re-opening and corrupt-file tests
check that every returned citation is traceable to its original full bytes.

**Exit:** local inference CI and installed executable HTTP smoke must pass,
including tamper tests. This closes the **searchable evidence** subgap only.

### A-04 · Evidence-grounded answer generation — OPEN / product capability partial

**Gap:** retrieved passages are intentionally **not yet supplied to the
model with atomic evidence-to-turn manifests**. A retrieved citation is not
proof that the model based its answer on it, and no answer-faithfulness
evaluation has passed.

**Implementation needed:** read-only evidence selection, bounded untrusted
context, stable query/source fingerprints, request-ID replay across source
updates, atomic turn/evidence receipts, export/import preserving lineage,
and attribution/contradiction evaluations. Model responses must not inherit
source text as system authority.

**Exit:** adversarial answer-grounding fixtures, citation verification after
restart, drift-safe replay, no fabricated sources, and a trained-model
acceptance run.

### A-05 · Useful trained local weights and GGUF execution — OPEN / release-critical

**Gap:** native TinyTransformer CI fixtures prove transport but are
**untrained**. The GGUF integration admits operator-installed digest-pinned
local weights/executable; a real trained model has not been demonstrated
against an agreed quality benchmark within this PR.

**Exit:** licensed operator-supplied GGUF, measured chat quality, real
`--local-gguf-smoke`, model/executable integrity during generation, CPU/GPU
profiles, bounded latency/context and visible accuracy results.

### A-06 · Model-safe read/write tools — OPEN / product capability partial

**Gap:** `assistant.tool_read` and `assistant.tool_write` remain registry
partial. Offline chat must not silently gain filesystem, shell or external
network execution by ingesting an untrusted source.

**Exit:** explicit user-granted tool scopes, typed admission, prompt injection
containment, least-privilege sandbox, rollback, refusal and approval tests.

### A-07 · Crawler-to-curated-knowledge pipeline — OPEN / separate integration

**Gap:** the existing crawler and research modules are not proven to feed a
license-aware, canonical, cited and adversarially rechecked local model
knowledgebase. Manual bounded text ingestion is a useful prerequisite, not
full autonomous acquisition.

**Exit:** source custody, robots/licensing policy, dedup/versioning,
multi-pass evidence extraction, data poisoning defenses, review/replay
records and integration with the local reference index.

### A-08 · Game-builder actual deployable artifacts — OPEN / separate integration

**Gap:** real console-era and native executable game outputs, compiled tool
chains, runtimes/emulators, packaging and historical-platform legality/quality
checks have not been demonstrated end-to-end by this offline chat PR.

**Exit:** build a reproducible target game from a text goal, provide source
and binary artifacts, run an appropriate emulator/native smoke, validate
determinism, controls, performance and license constraints.

### A-09 · Background autonomy, media and enterprise controls — OPEN

**Gap:** `assistant.background_agent` is planned, while image generation,
image editing and speech synthesis are partial product capabilities. Offline
GUI work does not complete them. Enterprise assurance volumes are still
recorded designed.

**Exit:** independently executable and policy-bound agents/media pipelines,
native asset and model provenance, recovery/security controls, active
evaluation and qualified release evidence.

### A-10 · Accurate masterplan signatures — OPEN

**Gap:** source Git SHA values in the signature parse index do not match
the current canonical masterplan. Replacing a digest without reopening the
relevant verification would launder stale signatures into apparently current
ones.

**Exit:** re-parse exact masterplan and accountability authorities, verify
signatures/gates, record immutable provenance and required signoffs. **Do
not retroactively assert functional validation merely because an index is
rehashed.**

## Rules for future closures

- **Discovered** means a reproducible contract, end-user, safety or
  deployment gap grounded in a current file, test, workflow or machine authority.
- **Implemented** means a code change committed with an executable regression.
- **Verified** means relevant exact-head CI/local smoke has actually passed.
- **Release-qualified** means a real assembled app and trained model have
  passed production acceptance and required signing.
- Failed/queued/skipped checks never count as passed checks; masterplan
  `verified` labels never substitute for executable acceptance.
- Rank work by missing user capability, data-loss risk, incorrect behavior and
  integration failure—not number of files, commits or lines.

**Current next integration target:** A-04 grounded answer production with
atomic evidence custody, followed by A-05 trained-model evaluation and the
A-01 release gates. A-06 through A-09 remain separate major workstreams.
