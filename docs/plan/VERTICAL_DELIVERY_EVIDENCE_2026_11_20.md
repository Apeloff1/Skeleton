# Vertical prototype delivery — 2026-11-20

Review draft: [#5709](https://github.com/Apeloff1/Skeleton/pull/5709).
Priority: **Jeeves → Dragon → Skeleton → broader game-builder quality**.
The [execution brief](VERTICAL_PROTOTYPE_DELIVERY_2026_11_12.md) remains the
enhanced project prompt. The [integration record](VERTICAL_INTEGRATION_2026_11_19.md)
and frozen PR ledger explain the current-main base and donor decisions.

## Implemented user journeys

| Vertical | Complete increment | Continuity and failure behavior |
| --- | --- | --- |
| Jeeves | Five guided journeys: research, planning, creative work, study and studio. Typed choices change the prompt and expected result. Review an exact prompt, validate the response and apply reviewed notes, tasks or cards through the existing Workbench. | Invalid output remains editable. Plan dependencies, cycles, totals, budgets and critical paths are checked. Account/source changes invalidate stale work. Atomic task batches retain actual dependency IDs and one undo action. Studio requests retain the existing execution authority. |
| Dragon | Save, reopen, copy, revise, import and export a complete creator project: design controls, targets, seed, cited brief and up to eight authored puzzle boards. | Optimistic concurrency preserves unsaved work. Exact retries recover their original save. Every stored revision is reachable. Reopening/importing does not restore prior review approval. Portable exports remain within the import byte limit. |
| Skeleton Forge | Save a source project, submit an explicit build, observe its durable receipt, cancel or resume eligible publication, reopen history and download the original ZIP. | Unknown dispatch is never silently repeated. Paged history reaches older receipts beyond the latest 24. The original ZIP remains available after later builds. Delayed responses cannot replace another selected project or job. |

These adapters reuse the existing Mongo project, revision, job and artifact
collections and the existing device-local Workbench store. No new provider,
compiler, executor, database or release authority was introduced. Generated
source is distinguished from a native binary and from a qualified release.

## Executed verification

The first implementation freeze is `2e854e3f16337a32fe076a265933a31a76114602`.
Mirror and product-source reconciliation is
`12b9b88af916ac9a2cf6489e0f5d92b1ae51993f`. Browser reports retain individual
source SHA-256 values, harness identity, observed fixture boundaries and errors;
later unrelated mirror changes do not replace those source identities.

| Evidence | Observed result | Scope |
| --- | --- | --- |
| Three new backend selectors | 96 passed, zero skipped | CI-equivalent selectors with a real authenticated disposable MongoDB 7.0.41; explicit test-only storage admission where declared. |
| New frontend contract tests | 69 passed | Journey state, atomic Workbench application, portable Dragon documents and durable Forge clients. |
| Existing Jeeves frontend suite | 313 passed | Existing suite plus journey coverage. |
| Full frontend TypeScript check | Passed | `corepack yarn tsc --noEmit`, including the three integrated verticals. |
| Jeeves browser journeys | 6 passed | Actual Chromium, Expo and workflow HTTP handlers; identity lookup and model reply are declared fixtures. No live model-quality result. |
| Dragon browser journeys | 9 passed | Actual API and authenticated Mongo saves, painted-board restoration, conflicts, history, JSON export and mobile layout. |
| Forge browser journeys | 8 passed | Actual API, Mongo, 25 source compiler dispatches, lost acknowledgements, older-history recovery, exact ZIP restoration and mobile layout. |
| Exported ZIP in installed Godot | Import, main boot and extraction completion passed | Exact browser-downloaded source; Godot 4.6.3, automated headless execution. Installed engine distribution is **not artifact-admitted**. |
| Governed source reconciliation | 183 mappings and independent ownership/index pins passed | 43 reconciled mirror pairs, including pre-existing drift; 17 pin changes tied to the frozen source. |
| Product and construction checks | Passed | 266 product source facts; architecture, construction, interfaces, state, provider bootstrap and mandatory dossier validators. These validate contracts, not competitive superiority. |

Maintained browser entry points are
`scripts/qualify_dragon_creator_browser.py` and
`scripts/qualify_forge_source_browser.py`; their `--help` describes local
configuration. The new selectors are integrated into existing Backend Quality
jobs with pinned authenticated Mongo and a zero-skip assertion. Existing gates
and release holds remain active.

Some wider historical tests fail identically at the frozen main base: two
legacy memory-policy fixtures lack required storage admission, and a historical
preview test constructs an invalid empty Pydantic value outside its exception
assertion. Those are not counted as successful checks and their validators were
not weakened. The table reports completed relevant checks rather than claiming
the repository's entire test inventory passed.

## Local review artifacts

These are workspace artifacts, not files committed into the repository:

- `/workspace/artifacts/jeeves-journeys/report.json`, `guided-desktop.png`,
  `guided-mobile.png`.
- `/workspace/artifacts/dragon-creator-browser-final-current/dragon-creator-browser-report.json`,
  `dragon-creator-desktop.png`, `dragon-creator-mobile.png`, `creator-project.json`.
- `/workspace/artifacts/forge-source-browser-final-current/forge-source-browser-report.json`,
  `forge-source-desktop.png`, `forge-source-mobile.png`, `original-godot-source.zip`,
  `reopened-godot-source.zip`.
- `/workspace/artifacts/verticals/native-export-check/native-export-report.json`.
- `/workspace/artifacts/verticals/mirror-reconciliation-2e854e3f.json` and
  `/workspace/artifacts/verticals/closure/machine-checks.json`.
- `/workspace/artifacts/verticals/pr-audit-full.zip`; the frozen ledger records
  its component identities and the cutoff, including all observed run IDs.

The exact original Forge ZIP contains **28 files / 16,551 bytes**, SHA-256
`633c1cb24841fc997501c252029695ced11eb213c00b7d39287069e123c2da6e`.
Its native run emitted
`ARCHETYPE_LOOP_COMPLETE extraction extracted loot=3 heat=18`.
The installed Godot executable SHA-256 is
`f64d4ed19fc9df9440321653fcc80df8c6e365ba7b6de0a29e2cfa9fa71bfeb3`;
this observed binary hash does not establish distribution admission.

## Setup, operation and rollback

Use the repository's existing frontend/backend environment and canonical
authenticated Mongo configuration. Preserve the normal account and storage
admission dependencies. Test harness fixture injection is confined to the
isolated qualification application; it is not production setup guidance.
No migration is required: the increments use existing versioned documents and
collections. Keep existing backups and tenant scope when moving environments.

Use source-only Forge projects for source generation. A source-ready job and
ZIP do not grant engine execution or distribution rights. Inspect exact job
status and uncertainty before deciding to submit a new build. Cancel/resume
acts on the original admitted job; a new build is a distinct explicit action.

Rollback deploys the prior frontend/backend together while retaining persisted
data and exported source. Do not delete projects or artifact collections to
roll back application code. Keep the new source-only documents inaccessible to
older incompatible execution paths. Forward recovery should restore the same
document/job identities rather than replaying uncertain compiler work.

## Remaining acceptance boundaries

This increment does not qualify a trained model, production identity/storage
admission, native export templates, physical mobile devices, licensed original
Dragon asset bundles or a production release. Browser model replies are
explicit fixtures. The Godot check demonstrates a real generated loop under
automated headless control; human playtesting and visual/device acceptance
remain separate work. Competitor superiority requires equivalent current
tasks and measured results; none is asserted here.
