# Skeleton — measured full-app completion contract
**Updated:** 2026-10-13  
**Implementation:** `skeleton/ai/game_builder/jeeves_measured_completion.py`  
**Canonical fixed taxonomy:** `machine/app_completion_scope.json`  
**Runtime integration:** existing authenticated Studio / Jeeves `ai.product.measure` and `ai.product.measure.page` adapters.  
**Scope:** 42 source-grounded product families, with 5 independent measurement stages per family. The taxonomy groups functionality; it is not a claim that the app contains exactly 42 end-user features.

## What can be measured right now

The repository's canonical machine authorities currently enumerate **489 atomic acceptance obligations** in six non-overlapping obligation classes: 421 AI masterplan volumes; 9 AI end-user capabilities; 5 assembled runtime services; 16 enterprise workstreams; 12 end-to-end journeys; and 26 terminal release gates. These 489 are **not** weighted into one marketing percentage because a volume, workflow and installed app are different units of work.

| Family acceptance stage | Evidence required | Can source-only scanner certify it? |
| --- | --- | --- |
| 1. Source owner present | Canonical source owner/path, readable selected checkout | Yes, *presence only* |
| 2. Implementation test passed | Exact-head, independent functional test result for the feature | **No** |
| 3. Runtime integration passed | Real frontend/API/engine/storage exchange with failure recovery | **No** |
| 4. User journey passed | End-to-end representative task including outputs, quality and real state | **No** |
| 5. Release/device qualified | Installer/hardware, adversarial security, latency, monitoring, rollback | **No** |

**Fixed denominator:** 42 families / 168 independent functional acceptance stages (four per family). Every family has a human-reviewable acceptance target and concrete source scope. The code explicitly refuses to shrink the denominator or auto-promote a runtime gate by changing a JSON flag.

**Conservative currently admitted functional evidence:** 0 of 168 independent acceptance stages **observed by this source-only scanner**, not a claim that there are zero existing passing tests anywhere. All 168 are **unverified**, not failed. All 42 families remain **release qualification unknown** to this scanner. Therefore the actual all-app percentage is **unmeasured**; the scanner emits a lower proven release bound of 0%, but does not report that the application is actually 0% built.

**Separately recorded registry metrics** (as of source authority checked on 2026-10-13): AI product capability labels = 0 complete / 9 registered; independent enterprise volume qualification labels = 0 / 421 qualified; plan maturity classifications = 421 / 421 verified-or-hardened. Never equate plan maturity with real product readiness.

The measured *source presence percentage* (and root-path presence percentage) are calculated from the currently scanned checkout, excluding restricted/unreadable sources. They are intentionally labeled **static discovery**, never functional completion.

## Direct operation

```python
from pathlib import Path
from skeleton.ai.game_builder.jeeves_appwide_fabric import (
    AppwideInventory, JeevesAppwideRuntime
)
inventory = AppwideInventory(Path.cwd())
inventory.scan()
jeeves = JeevesAppwideRuntime(inventory)

overview = jeeves.invoke("ai.product.measure", {
    "expected_snapshot": inventory._digest
})["result"]

assert overview["family_count"] == 42
assert overview["atomic_product_contract_obligations"] == 489
assert overview["full_app_completion_percent"] is None
assert overview["family_independent_acceptance_stage_obligations"] == 168

page = jeeves.invoke("ai.product.measure.page", {
    "limit": 15,
    "only_missing": True,
    "expected_snapshot": inventory._digest,
    "expected_measurement_digest": overview["digest"],
})["result"]
```

The Studio **Deathmarch Production Deck** includes *Measure full-app acceptance scope* and *Inspect missing source owners*. It invokes the same secured loopback adapter and prints separate source, contract and independent-evidence measurements. It does not start tests, mutate weights, promote milestones or touch source files.

## Source-identical acceptance and reproducibility

Both responses bind to: the exact inventory snapshot, SHA-256 of the 42-family contract, the canonical eight-document completion census digest, and SHA-256 of the required P1 gate authority. Pagination requires the same full report digest. Changing a family target, source owner, volume, capability or release-gate authority invalidates the relevant source receipt. Duplicate JSON keys, malformed path scope, private path, an optionalized release gate, scope reduction, or attempts to auto-verify runtime stages are rejected.

The canonical taxonomy cannot be silently cut to fewer families to inflate scores. Adding or renaming families requires a reviewed schema/denominator migration and a new baseline. Domain-level static presence is computed per feature family, not extrapolated from 58,884 historical file entries.

### Required CI

The Jezves Story Canon Production workflow now compiles the measurement module, runs adversarial `tests.test_game_builder_jeeves_measured_completion`, and loads the **real** 42-family and 489-obligation baseline from the exact checked-out PR head on **Ubuntu 24.04 and Windows 2022**.

The baseline job asserts schema/denominator integrity and that the independent acceptance status remains unknown. Its passing result would prove this **measurement tool**, *not* release qualification of the game studio or AI model.

### Engineering priority using actual measurements

1. **Unlocated source owners**: first inspect those reported by `ai.product.measure.page(only_missing=True)`, distinguish missing owner from renamed/migrated directory, and reconcile with `machine/ai_file_tree.json` and active PRs.
2. **Incomplete AI capabilities**: the 9 canonical product entries need real model/provider readiness, full frontend/backend traces and recovery + safety evaluations.
3. **Engine/game/editor delivery**: attach exact-head per-genre and per-target installed replay evidence for the feature families that currently have source but lack independent acceptance.
4. **Enterprise workstreams/journeys**: every workstream's `exit` clauses and the 12 journeys need real outcome receipts.
5. **Release gates**: every one of the 26 required policies must have externally verified successful exact-head CI observation; queued, skipped, canceled or absent runs never count.
6. **Independent device/quality validation**: baseline representative Windows/macOS/Linux and consoles/homebrew where applicable; performance, real trained-model quality, safe recovery, privacy and legal provenance.

## What changes the completion percentage

Do not edit `family_stage_status` manually; there is intentionally no writable stage completion flag. A future **independent-evidence admission gate** must verify CI run identity, run head and workflow, authorized review, immutable artifact hashes, real runtime test criteria, evidence freshness and rollback. Only then can it populate objectively accepted statuses. Until that gate exists and authentic independent evidence is admitted, `full_app_completion_percent` remains `null`.

The contract is intentionally rigorous so the project can run large batches without having the plan, source index or automatic generator falsely report that the application is done.
