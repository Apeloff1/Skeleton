# Exact-head, three-level reconciliation policy

STATUS: DRAFT / REVIEW ONLY / NO MERGE / NO AUTO-MERGE / NO RELEASE / NO PRODUCTION MODEL ACTIVATION.

Date: 2026-11-08. This is a source custody repair log. It is not proof of successful live CI, real devices, owner security signoff or end-user release.

## 1. Repository dependency topology

main -> #5074 -> #5081 -> #5089.

Do not squash or rebase descendants onto main until all dependencies and final-head security reviews are qualified. Live refs and GitHub workflow results must be re-read before every decision, because this document is necessarily historical.

Observed heads before this source repair:
- #5074: c59778c74d1869447dcd60d0f18f2143166a67a7
- #5081: ce4f067dd0acd5b7b45395b3e68bdfad00140d5d
- #5089: 145c1c88789f761fa5452c3100f7f8917ef95f2e
- #5079: 14411d93da21379e5dac33fb7736955d86f894b3
- #5090: 6022a96f032ef751d113fd708acc0c169372c21d
- #5091: 417f638eaa9fcf1f9fb07c1aa7596559a74c2875
- #5038: 7d36f98753fbf9bd07076f14dff2191871a0eed1

These snapshots are not live final SHA values after repair commits.

## 2. Identified and reconciled scanner capacity conflict

The common ancestor's maximum machine inventory was 100,000 files. Its actual scanned source tree had exceeded that limit, with a documented observed count of 102,945. #5074 raised the finite cap to 150,000; child #5081 independently raised it to 250,000. Their same-file modifications caused GitHub to report the child as nonmergeable.

The #5081 source repair replaces the divergent header in .machine/repository.toml with the exact current #5074 version, retaining 150,000 and leaving every remaining TOML line untouched. The scanner must still count until max_files+1, signal truncation and fail any truncated CI run. It may not drop files, suppress critical scan findings or silently expand the source filter.

A dedicated #5089 regression was previously pinning the old child value of 250,000 exactly. That assertion now tests a finite, measured admissible range and preserves the exact-bound and one-over-bound overflow denial tests. A larger future repository must present new inventory data, resource-pressure qualification and finite-budget tests before the ceiling changes.

The branch mergeability response after this change is not a green-source verdict and cannot substitute for exact-head review.

## 3. Historical source custody versus live-head CI

The frozen 19-item action ledger, machine/backlog19_actions_20261108.json, was recorded before later commits to its own source PR and donor heads. Its older SHAs and path counts must be interpreted as intake observations, never as authoritative current-head CI evidence or publication admission.

Retired without merging:
#4885, #5056, #5055, #5049, #5033, #4902, #4990, #4889, #4836.

Review-only, not approved:
#5090, #5091, #5038.

Still held:
#5089, #5081, #4870, #5022, #4991, #4853, #4838.

The action ledger requires 9 retired, 3 review-only and 7 held decisions. Other repositories, duplicated PR numbers, forged success flags, unauthorised survivor substitution, changed quarantine statuses, or an assertion of merge/release authority must fail closed.

The older machine/draft19_reconciliation.json represents an earlier and different source classification. Do not conflate its 19 source donors with the later 19-action disposition ledger. R03 through R13 are the complete eleven currently staged source-convergence audit rounds and require explicit negative release/merge language.

## 4. Sibling overlap and material risks

#5079 includes overlapping implementations with #5074 and #5081:
- .machine/repository.toml machine capacity, complete inventory and truncation denial;
- backend/core/lazy_registry.py literal deferred-loader ownership;
- skeleton/app/offline_delivery_archive.py finite, canonical archive and provenance guards;
- skeleton/testing/test_ai_next_model.py true digest, circuit rejection and native receipt;
- skeleton/local_ai/model_loader.py descriptor-bound no-follow GGUF path admission.

Review exact Git blob identities and behavioral differences before any sibling merge. When source bytes match, deduplicate. When tests are complementary, retain both. Do not wholesale overwrite tighter security, newer lifecycle or provenance behavior.

All seven held sources retain explicit no-merge authority; #5022 remains quarantine, #4991 historic Godot source remains unresolved, and #4870 remains stacked. #4853 and #4838 require semantic, source/mirror and first-install overlap analysis. No consumer installer, release signing, model rights, trusted inference or hardware evidence is implied by source-copying.

The promoted API and replay branches #5090/#5091 expanded far beyond their frozen action-ledger path counts, so their entire new exact-head diffs require independent authentication, tenant, idempotency, replay and dependency review. Preliminary GGUF preflight #5038 must never be called a safe model loader or real-device inference.

## 5. Independent CI acceptance contract

scripts/check_reconciliation_exact_head.py is an offline structural verifier for a review-only export of GitHub Actions workflow/job results. It does not authenticate that export; no successful local run authorizes merger, release, user installation, signing, production ingress, live crawler activation, or model execution.

Input schema: skeleton.reconciliation.head-checks.v1.
Repository: Apeloff1/Skeleton.
Chain: #5074 -> #5081 -> #5089.
Every PR entry must carry its own full 40-digit lowercase head SHA, its base-head SHA, its draft flag, false merged flag and bounded workflow records. Each workflow must identify an actual run ID, attempt, exact PR head, status completed, conclusion success, and all its named completed-success jobs on that same SHA.

The ten required workflows are read from machine/draft19_reconciliation.json, including Merge Readiness, Backend Quality, App Foundation E2E, Malware Gate, Artifact Policy, Repository Hygiene Gate, Secret scanning, Dependency Review, Workflow Input Security and Sealed Context Guard.

Every Merge Readiness workflow must contain all eight Canonical Domain Suite shards (0 through 7) and PR Automation Tests, Lint Type Security, Quarantine Policy and Integration Smoke. The #5089 child must additionally have Jeeves integrated mirror, native SQLite and Draft19 GGUF source qualification workflows. Duplicates, absent gates, queued, skipped, cancelled, failing, neutral, wrong-head or older-run artifacts are rejected.

Command: python scripts/check_reconciliation_exact_head.py --evidence /path/to/operator-captured-read-only-bundle.json

Even a structurally complete input returns only structurally_complete_only, with approval denied and all merger/release/device flags false. Capturing the live GitHub API, checking current branch heads, full job pagination and authenticating the input is an independent operator obligation.

Unit tests exercise hypothetical successful source structures only to prove denial of false approval. They never claim real successful workflows. The new read-only policy workflow compiles, checks both existing 19-source guards and executes adverse negative tests; it cannot replace existing native, frontend, hardware or supply-chain CI.

## 6. Broad repair and qualification ordering

1. Fetch latest branch heads and validate main -> #5074 -> #5081 -> #5089 Git topology. Re-fetch after any commit.
2. Qualify #5074's final-head canonical shards and the full Backend Quality, App Foundation E2E, inventory, artifact, malware, secret, dependency, workflow-security and owner-policy gates.
3. Reconcile #5081 implementation against the latest #5074 parent, preserving its archive forged-payload rejection and true native receipt digest. Keep max-files measured and finite.
4. Perform independent sibling #5079 exact-object and semantic overlap analysis. Do not double-merge or drop retained regression cases.
5. Qualify #5089's source/mirror Git-tree pins, retained owners, R03-R13 ledger custody, backend loader, archive inspection and Python/TypeScript source import graph. Recompute affected pins from the actual final Git tree.
6. Review expanded API and replay PRs #5090/#5091 and held history/quarantine #5022/#4991 separately, without granting production authority.
7. Collect all required final-head GitHub workflow runs, job evidence, run attempts and independent security/owner review. Any newer commit invalidates older results.
8. Qualify separate real Windows 11/WSL2 and Docker installation, native GGUF and device pressure, Godot export/playthrough, artifact provenance, signed release and recoverable first-start. Mock tests alone do not qualify these.
9. Maintain NO MERGE / NO AUTO-MERGE / NO RELEASE / NO MODEL ACTIVATION until every source, CI, independent security and device requirement is fulfilled.

## 7. Rollback

Review and revert an incremental child commit if necessary, never force-rewrite main, prune donor branches, delete source signatures, disable quarantine, loosen symlink/hardlink/path protections, or silently override a source tree SHA. Recheck workflow identities after rollback. Source-only improvements cannot revoke the recorded release holds.


## 8. Finite independent workflow admission repair

The repository's machine contract limits independently event-triggered GitHub
Actions workflows to 26; an extra pull_request workflow is a policy violation,
not an excuse to relax the ceiling. The upstream #5074 repair converted three
privileged workflows to workflow_dispatch-only: release-images,
reproducible-release and owner-historical-actions-cleanup. Their historical
automatic-event registry entries were stale and misclassified manual work.

The repaired #5074 and #5081 source registries each contain 23 explicitly
authorized independent subscribers, rather than the stale 26. The #5089 child
registers exactly three additional PR source qualifiers:
- Draft19 GGUF and source custody qualification.
- Jeeves atomic reviewed-source regression.
- Reconciliation original-game and first-install source qualification.

The total is again exactly 26. Neither the limit nor any core PR security
subscriptions have been weakened. The parent registry contains no fictitious
automatic trigger for privileged owner cleanup or release publication.

VOL-249/250 Research Reasoning Qualification and Reconciliation exact-head
policy and evidence custody are now dispatch-or-call only. They do not consume
separate independent event slots. Their existing workloads are executed by
reusable job calls from the registered original-game source and Draft19 source
qualifiers respectively. There is no new unregistered PR subscriber or
mainline release path. Existing independent Backend Quality, Malware Gate,
Workflow Input Security, Artifact Policy, Secret Scanning and dependency
review remain separately mandatory for actual signoff.

The Jeeves atomic qualifier previously checked out the GitHub PR merge ref.
Its repaired checkout now pins the immutable PR head SHA and fails closed if
the actual checkout does not match that head. A merge-ref green result never
qualifies a different head.

Run scripts/check_ci_workflow_tiers.py and the new
tests/test_reconciliation_workflow_admission_20261108.py regressions on the
final source. Correct any newly observed admission drift with explicit
registry reconciliation, not by increasing the numeric cap, deleting core
security gates or treating manually dispatched release as automatic CI.

The case work remains source-only. Call and child workflow results still
must report success for the *final exact head* before review can proceed.
