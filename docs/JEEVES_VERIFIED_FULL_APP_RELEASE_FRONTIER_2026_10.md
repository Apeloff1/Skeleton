# Jeeves — independently verified 100% full-app release frontier
**Established:** 2026-10-13  
**Branch:** `feat/jeeves-measured-app-closure-20261013` (draft PR #3747, stacked; not mainline)  
**Canonical family scope:** `machine/app_completion_scope.json`  
**Canonical enterprise journeys:** `machine/enterprise_system_architecture.json`  
**Journey acceptance specifications:** `machine/app_release_journey_contract.json`  
**Runbook:** `JeevesEnterpriseJourneyFrontier`, `JeevesReleaseExecutionQueue`

## Why the pre-existing 100% was not application completion

42/42 source-backed feature families and 42/42 scheduled targeted test-family subsets establish a **test selection baseline**, not a complete operational AI game-creation application. Actual complete product requires independent evidence of the real model, API/client integration, durable transactions, game creation, user workflow, recovery, native device installation, legal provenance and safe release rollback.

The previously asserted 100-commit target has been exceeded, but commit count does not qualify functionality. The masterplan's 421 `verified`/`hardened` planning classifications do not prove 421 enterprise-qualified volumes.

## Precise release obligations sourced from canonical machine authority

| Type of independent release evidence | Leaves | Required proof |
| --- | ---: | --- |
| 421 registered masterplan volumes | 421 | Real enterprise-grade objective implementation and verification, not a volume label |
| 42 product families × 4 independent stages | 168 | Functional test, runtime integration, actual user journey, installed release/device |
| 12 golden enterprise journeys × 7 axes | 84 | Real executable target, user outcome, durability, denied/negative path, restart/recovery, traces, deployed release proof |
| 26 terminal mandatory gates | 26 | Verified exact-head CI, source and artifact custody, no skipped/canceled/missing required checks |
| 16 enterprise workstreams | 16 | Evidence for each workstream's original exit criteria |
| 9 public AI product capabilities | 9 | Trained/useful model, routing, safety, tool permission, output quality and real client deliverables |
| 5 assembled runtime services | 5 | Real healthy/durable/running transport and restart isolation |
| **Total lower-level evidence obligations** | **729** | Hierarchical evidence leaves, *not* equal-weight percent of application implementation |

These obligations are source-defined and may be causally dependent. They are not summed into an application completion percentage. The **12 terminal journey completions** are derived from their 84 axes; they are not counted a second time. Volume implementation labels are not treated as accepted receipts.

## Jeeves source-grounded execution queue

`JeevesReleaseExecutionQueue` assembles exact-source SHA256 receipts for the masterplan, runtime manifest, required gate authority, product capability registry, enterprise contract, and 42-family taxonomy; the journey frontier binds the additional 12-journey contract. It assembles finite `id`-stable leaves with priority: mandatory release gates, AI product functionality, enterprise journeys, family-level integrated acceptance, service processes, enterprise workstream exits, enterprise volume qualifications.

Use inside the authenticated local Studio or via the existing governed Jeeves runtime:

```python
from pathlib import Path
from skeleton.ai.game_builder.jeeves_appwide_fabric import (
    AppwideInventory, JeevesAppwideRuntime)

inventory = AppwideInventory(Path.cwd())
inventory.scan()
jeeves = JeevesAppwideRuntime(inventory)
journeys = jeeves.invoke("ai.product.journeys", {})["result"]
queue = jeeves.invoke("ai.product.release.queue", {})["result"]

assert journeys["canonical_journey_count"] == 12
assert journeys["total_journey_acceptance_axes"] == 84
assert queue["leaf_evidence_denominator"] == 729
assert queue["full_app_completion_percent"] is None

first = jeeves.invoke("ai.product.release.queue.page", {
    "offset": 0, "limit": 30,
    "expected_queue_digest": queue["digest"],
})["result"]
```

Read-only `ai.product.journeys.page` returns a particular golden journey's candidate test sources, family dependencies and seven unknown axes. The Studio Deathmarch Deck has buttons for the complete release queue, top 30 blocker items and the first six enterprise journeys.

**Security model:** A user cannot pass `verified=true` or a new signoff into the source reader. Stale source digests, optionalized required gates, truncated denominators, duplicate IDs, fabricated receipt arrays, invalid test file sources and weakened policies fail closed. Test file presence is reported only as a *candidate*. A real authorized external run must be independently verified before an axis is accepted. A local source-only scan always reports that all newly defined journey axes remain unverified, not failed.

## Two actual runtime slices now scheduled for exact-head CI

1. `tests/test_game_builder_jeeves_product_studio_journey.py` — real token-protected loopback Studio project, prompt planning, advanced tower-defense execution, replay verification, portable save/reload, tamper denial and no unintended workspace writes.
2. `tests/test_ai_native_session_recovery_journey.py` — actual native CPU transformer multi-turn conversation, model/session checkpoint restoration, deterministic continuation, exactly-once streamed turn acceptance and corrupt-state denial. **Untrained local graph is not proof of useful AI model quality or installed chat.**

Both are linked into the reviewed 42-family test matrix, and native conversation recovery is an explicit J01 golden journey test *candidate*. These are individual verified-code paths only after CI succeeds, and do not independently qualify a whole enterprise journey.

## Minimum evidence for independently qualified 100% app

Each of the following must actually be independently observed at the tested commit, using source-identity checked receipts:

1. **Runtime services and local models:** real AI model quality including held-out evaluation, model provenance, provider/local failover, GPU/CPU memory budgets, streaming and durable multi-turn session.
2. **Jeeves operational capability:** real operator-governed function calls for every material UI editor, Dragon, crawler, forge, asset pipeline, shell and application management action; read/write scopes, JIT approval, audit and rollback.
3. **Game creation to executable:** prompt→original game plan→engine scenes→editable NPC and branching story state→asset provenance→native playable export→device gameplay with restart/save/restore; comprehensive engine/genre/platform acceptance.
4. **Dragon learning:** RSS/video/article source acquisition, independent fact checks, provenance, shadow candidate, adverse improvement and safety evaluation, operator-approved model promotion, regression rollback. Weight changes cannot be inferred from source updates.
5. **Enterprise golden journeys:** all 12 journey contracts are run end-to-end, each with 7 real acceptance axes including adverse/failure paths and durable traces.
6. **Delivery and operations:** 26 actual release gates, 16 workstream exit criteria, 5 services, installer, OS/device matrix, tenant lifecycle/consent, backup restore, disaster recovery, performance limits, security controls, and independent rollback verification.
7. **Review and landing:** prerequisite stacked PRs land in dependency order; real mainline build and installed user testing is repeated at the resulting commit, not inferred from passing a draft branch.

## Next milestones

- **R-01:** Exact-head execution of all 20 curated unittest modules and 25 pytest family subsets on Windows/Linux, independently authenticated GitHub run artifacts, no zero-test false success.
- **R-02:** Expand actual authenticated app/service E2E tests with real persistence and trained model to qualify user journey 01 and 03 instead of static simulation.
- **R-03:** Run golden journeys J01–J12 against real deployed services, persist read-only signed proof artifacts by axis, independently verify against the same binary/commit.
- **R-04:** Verify all 26 release gates at the tested HEAD; map their actual workflows and required checks, explicitly block missing/queued/skipped/canceled.
- **R-05:** Measure model output and game artefact quality against scored, blind expert holdouts; tests must prove genuine original playable targets and legally clean ownership.
- **R-06:** Qualify services/enterprise workstreams and installed OS/device build, including recovery and rollback.
- **R-07:** Recompute an independently justified all-app completion figure from accepted *outcome-level* receipts, not plan statuses or source presence.
- **R-08:** Perform adversarial regression on actual exact-head mainline and publish a reviewable release signoff.

### Status as of the established baseline

- 42 product families indexed and target-test selected: **42/42**, static planning only.
- Enterprise end-to-end journeys defined: **12/12**, no accepted end-to-end signoffs from the source reader.
- Independent journey proof axes: **84 unresolved by source observation**.
- Source-defined release proof leaves: **729**, no accepted external release-proof ledger ingested by this reader.
- **Full installed-app functional percentage: unknown**, until independently authenticated end-to-end evidence is available.

Do not mark any of these obligations completed solely because their corresponding file, check definition, or planning signature exists.
