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

## DX-36–DX-44 — candidate tests and executable acceptance evidence

The curated product test matrix is now maintained at `machine/app_acceptance_test_matrix.json`; each mapping is to an **existing, readable test module** on the exact branch, not a proposed filename.

| Metric | Count | Interpretation |
| --- | ---: | --- |
| Source-linked product feature families | 42/42 (100%) | A family has at least one targeted regression candidate, often narrow; **not** a feature-level pass |
| Exact-head CI smoke-selected feature families | 14/42 (33.33%) | Their curated tests are executed in the new workflow; stage-specific outcome must be checked |
| Discovery-only test candidate families | 28/42 (66.67%) | Existing tests identified but **not** scheduled in this smoke run or counted as passed |
| Independent user-journey/device qualifiers admitted | 0 observed | The source-only tool cannot authenticate or perform independent device acceptance |
| Full-app functional completion | Unknown | No invented percentage from test-file discovery |

### New executable evidence lane

`.github/workflows/jeeves-app-acceptance-matrix.yml` performs a pinned **exact-PR-head** checkout on **Ubuntu 24.04 and Windows 2022**. It first runs adversarial test-matrix and evidence-runner checks, then `scripts/run_app_acceptance_matrix.py` performs each reviewed smoke module as an actual Python `unittest` subprocess, recording return codes, timeout, started/ended UTC, selected source digests and explicit non-qualification flags in an ephemeral workflow artifact. The script fails the job when any test fails. GitHub checkout and workflow metadata are checked against the exact repository, head and runner OS before execution.

`ai.product.tests` and `ai.product.tests.page` provide **read-only** source-linked mapping and missing-family data in Jeeves. The Studio Deathmarch Deck has controls to show linked families and remaining unmapped candidates.

**Important:** The runner's JSON is an evidence *claim* until an external trusted verifier separately authenticates the GitHub Actions run identity, exact head, artifact custody and required workflow outcomes. The runner deliberately marks `independent_github_run_identity_verified_externally=false` and `full_app_completion_percent=null`. No shell action or model-weight promotion is granted by the artifact.

### Two previously unmapped source families now have real regressions

**F07 Offline native AI:** `tests/test_ai_offline_native_functional_boundary.py` executes a small actual local transformer in pure Python (embedding, attention, token generation), deterministic replay, checkpoint recovery, bounded chat context and fail-closed model-drift recognition. This **does not** prove competitive language quality, local GGUF loading or hardware installation.

**F37 Shell authority:** `tests/test_ai_shell_approval_contract.py` exercises actual lease-scoped shell-plan approval, exact intent/proposal hashes, expiry, principal fencing, concurrent single-use consumption and denial of malformed/NaN input. `skeleton/ai/shell/approval.py` was hardened against non-finite clocks/TTLs, nonhex SHA-256 receipts and boolean capacity. These tests do **not** grant or perform shell command execution.

### Remaining high-priority completion work

1. Verify latest exact-head Windows/Linux smoke CI and inspect its failure logs; no test path is marked successful based on queued jobs.
2. Convert discovery-only links into reviewed execution tiers selectively after dependency/fixture qualification, never by merely updating the mapping label.
3. Add trusted GitHub run/artifact attestation admission, and score only independently authenticated targeted execution outcomes.
4. Attach functional frontend-to-backend, game engine, real-model, user journey, installed-device and rollback evidence to each of the 42 families.
5. Preserve upstream PR landing order (#3718 → #3729 → #3730 → #3738 → #3747) and do not sign unmerged code as production release.



## DX-49–DX-60 — independent CI test evidence and no-zero-test scoring

The candidate matrix now schedules **17/42 feature families** for actual cross-platform `unittest` execution (19 distinct selected modules), including the repo atlas, build authority and model-serving capacity suites. Another **25/42** have real source/test links but are deliberately discovery-only, often because their real tests use **pytest and fixtures**, which `python -m unittest` would silently skip. No discovery-only suite is counted as passed.

The existing `unittest` runner previously relied on a successful subprocess return code. This has been hardened: `scripts/run_app_acceptance_matrix.py` now parses unittest's `Ran N tests in ...` report, requires `N > 0` for **every scheduled module**, and records per-module and total actual-case counts. A module that reports success with zero discovered tests, missing execution data or a timeout **fails** the acceptance run.

### Separate independent read-only verifier

`skeleton/ai/game_builder/jeeves_acceptance_run_verifier.py` supplies a fail-closed exact-head acceptance algorithm. The separate operator-side `scripts/verify_app_acceptance_ci.py` uses a **read-only GitHub Actions API token** to obtain trusted GitHub run metadata, all jobs and both source-hashed artifact ZIPs. It verifies:

- Repository and workflow identity, exact SHA and run attempt; full successful completed run.
- Both Ubuntu and Windows jobs on the **same SHA**, with the actual regression execution step successful.
- Exact selected-module list, actual positive unittest case counts, per-source SHA-256, matrix and family-scope SHA-256, runner receipt digest and CI artifact custody.
- Artifact origin, run ID, bounded ZIP/JSON input, unique JSON keys, absence of secret-bearing logs, and token stripping on cross-origin HTTPS ZIP redirects.
- No model promotion, device qualification, whole-feature certification, user-journey success or invented full-app percentage.

A verified result can report the independently confirmed **targeted regression-subset coverage**, e.g. **17/42 = 40.48% of family test subsets** when the reviewed exact-head workflow actually passes both platforms. It **cannot** report 40.48% functional app completion, and **must not** be counted while runs remain queued/failed. It explicitly records `complete_family_stage_qualifications_admitted=0` because each subset may be narrower than complete feature acceptance.

This verifier must run from a **trusted code checkout at the exact tested SHA**, with credentials scoped to read GitHub Actions only. Do not give untrusted PR code access to a privileged token. Use a review/operator process rather than automatically triggering a privileged `workflow_run` job that checks out an untrusted pull request.

Once the corresponding CI run is complete:

```bash
# From the exact reviewed repository commit, with a read-only token.
git rev-parse HEAD
GITHUB_TOKEN="<read-only-token-from-secure-environment>" \
  python scripts/verify_app_acceptance_ci.py \
  --run-id <github-actions-run-id> \
  --attempt 1 \
  --head <exact-40-character-commit-sha> \
  --output build/verified_acceptance_ci.json
```

Do not commit the downloaded CI artifacts or tokens. Output reports are run-identity/source-bound but are **not** permissions, live application execution or final product signoff.

### Remaining prioritized work

1. Drain the queued exact-head Windows/Linux workflow runs. Investigate missing Python dependencies, missing fixture roots and actual assertion failures from their logs.
2. For the **25 pytest-backed discovery families**, build a separate reviewed pytest execution lane with pinned dependencies and real nonzero-test counts. Never let unittest report 0 tests as progress.
3. Independently verify any CI outputs, then advance from *targeted regressions* to real runtime integration, story/world/game/Dragon/AI user journeys, installed Windows app smoke, model-quality holdouts, rollback and performance.
4. Keep enterprise acceptance, the 26 required gates, 421 masterplan volumes and 9 AI capability labels in distinct denominators until individually verified.
