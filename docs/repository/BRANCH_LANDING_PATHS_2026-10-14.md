# Skeleton branch landing ledger — 2026-10-14

> Historical evidence snapshot, NOT permission to delete. Recheck branch heads, PR protections, `main` and CI immediately before any mutation.

- Audited `main`: `e029d150cab04b80b83385794e8c6802579fcf75`
- Inventory: **853 branches**, **769 distinct tip SHAs**, **21 shared-tip clusters covering 105 refs**.
- **12 groups / 82 refs** have head commit proven ancestor of audited `main`; these are cleanup *candidates*, not approved deletions.
- **9 groups / 23 refs** diverge from `main`, with explicit landing routes below. Preserve all unique work until resolved.
- 748 singleton tips remain outside this duplicated-tip ledger; do not infer they are redundant.

## Already-integrated ancestry: 12 groups / 82 refs

These tips have zero commits ahead of the audited main. Retirement requires fresh open PR head/base checks, branch creation/commit age, protected ref names, current main ancestry, and exact-tip lease. The guarded `branch-clean.yml` owns pruning; this ledger executes no deletions.

### `66a43b0fcb6e` (36 refs; ancestor of main)

- `fix/current-main-gates-20260920`
- `reconcile/assets-manifest-current-main-v2`
- `stabilize/shell-ai-assurance-context-20260920-clean`
- `stabilize/shell-ai-durable-archive-20260920-v1`
- `stabilize/shell-ai-durable-archive-repair-20260920-v1`
- `stabilize/shell-ai-durable-checkpoint-20260920-v1`
- `stabilize/shell-ai-durable-recovery-20260920-v1`
- `stabilize/shell-ai-durable-retention-20260920-v1`
- `stabilize/shell-ai-durable-sequence-20260920-v1`
- `stabilize/shell-ai-durable-session-state-20260920-v1`
- `stabilize/shell-ai-eval-safety-20260919-v1`
- `stabilize/shell-ai-execution-evidence-20260920-v1`
- `stabilize/shell-ai-governance-rollout-20260919-v1`
- `stabilize/shell-ai-mcp-20260920-clean`
- `stabilize/shell-ai-merkle-session-store-20260920-v1`
- `stabilize/shell-ai-orchestration-20260919-v1`
- `stabilize/shell-ai-planning-core-20260920-clean`
- `stabilize/shell-ai-proof-window-20260920-v1`
- `stabilize/shell-ai-recovery-integrity-20260919-v1`
- `stabilize/shell-ai-release-foundation-20260919-v1`
- `stabilize/shell-ai-release-manager-20260919-v1`
- `stabilize/shell-ai-runtime-trust-20260919-v1`
- `stabilize/shell-ai-sandbox-20260920-clean`
- `stabilize/shell-ai-session-runtime-20260920-clean`
- `stabilize/shell-ai-source-integrity-20260919-v1`
- `stabilize/shell-ai-verification-cursor-20260920-v1`
- `stabilize/shell-ai-verification-ops-20260920-v1`
- `stabilize/shell-contracts-20260920-clean`
- `stabilize/shell-evidence-20260920-clean`
- `stabilize/shell-governance-20260920-clean`
- `stabilize/shell-orchestration-20260919-v2`
- `stabilize/shell-toolchain-extended-tests-20260920-clean`
- `stabilize/shell-toolchain-pack-20260920-clean`
- `stabilize/shell-worker-runtime-20260920-v2`
- `stabilize/shell-workspace-txn-20260920-clean`
- `tmp/java-accelerator-operations-rebase-20260920`

### `fcb72464f32f` (14 refs; ancestor of main)

- `ai/deferred-canonical-identity-fcb7246-r12`
- `ai/deferred-canonical-identity-fcb7246-r13`
- `ai/deferred-canonical-identity-fcb7246-r14`
- `ai/deferred-canonical-identity-fcb7246-r15`
- `ai/deferred-canonical-identity-fcb7246-r16`
- `ai/deferred-canonical-identity-fcb7246-r17`
- `ai/deferred-canonical-identity-fcb7246-r19`
- `ai/deferred-canonical-identity-fcb7246-r20`
- `ai/deferred-canonical-identity-fcb7246-r21`
- `ai/deferred-canonical-identity-fcb7246-r23`
- `ai/deferred-canonical-identity-fcb7246`
- `ai/provider-runtime-mirror-reconcile-20261007`
- `ai/reconcile-vol055-architecture-linter-20261007`
- `fix/deferred-canonical-identity-20261007-r24`

### `0dafc1ac422f` (11 refs; ancestor of main)

- `ai/deferred-canonical-bytes-0dafc1`
- `ai/oct2026-gpu-kv-governance`
- `ai/oct2026-outbox-claim-ledger-v1`
- `ai/oct2026-placement-locality`
- `ai/oct2026-write-recovery-hardening-v1`
- `ai/p1-canonical-evidence-hourly-0dafc1`
- `ai/p1-evidence-canonical-0dafc1`
- `ai/2026-resource-cache-locality-0dafc1`
- `ai/2026-resource-decision-receipts-0dafc1`
- `feat/ai-tree-oct-2026-execution-envelope`
- `feat/vol012-knowledge-store-20261006`

### `b2b7c1a7a541` (3 refs; ancestor of main)

- `ai/deferred-import-surface-b2b7c1a-r11`
- `ai/provider-runtime-mirror-reconcile-20261006-v2`
- `fix/current-main-python-syntax-20261006`

### `92a6dcc85976` (3 refs; ancestor of main)

- `ai/vol028-canonical-principal-92a6dc`
- `ai/vol364-governed-memory-rollback-r6`
- `fix/deferred-runtime-compile-blockers`

### `445e5f69770d` (3 refs; ancestor of main)

- `ai/vol188-chaos-engineering-v2`
- `ai/vol189-recovery-drills-v2`
- `ai/vol190-release-qualification-v2`

### `43867c098e9b` (2 refs; ancestor of main)

- `ai/current-main-evidence-json-hardening-20261005`
- `ai/vol210-research-agent-team`

### `116eb5c4a78f` (2 refs; ancestor of main)

- `ai/deferred-canonical-identity-116eb5c`
- `ai/deferred-canonical-identity-116eb5c-r11`

### `d4c4744b97b2` (2 refs; ancestor of main)

- `ai/reconcile-vol031-d4c4744`
- `reconcile/vol029-current-main-20261006`

### `857b3b46f78c` (2 refs; ancestor of main)

- `ai/vol028-authority-policy-20261005`
- `ai/vol210-research-agent-team-v2`

### `c0d24a59a5a4` (2 refs; ancestor of main)

- `ci/preempt-stale-main-68a6-20261004`
- `fix/main-signing-validation-unblock-20261004`

### `de1c7870e4c2` (2 refs; ancestor of main)

- `ops/preempt-doomed-mr-batch2-20261004`
- `ops/preempt-doomed-mr-batch3-20261004`

## Divergent history: 9 groups / 23 refs

Branch names in this section are **not** safe to delete merely because their related PR was closed. Backups are intentionally retained; stacked PR merges require final code-equivalence review.

### QUEUE — `badd53ca9086` (7 refs)

**Landing/disposition:** Modern `main` has `scripts/drain_actions_queue.sh` and its regression test, but the old tip differs. Reconcile only missing fail-closed queue constraints through a new current-main PR; no whole-branch merge.

- `fix/owner-queue-drain-current-main-pr`
- `fix/owner-queue-drain-current-main-pr2`
- `fix/owner-queue-drain-current-main-pr3`
- `fix/owner-queue-drain-current-main-pr4`
- `fix/owner-queue-drain-current-main-pr5`
- `fix/owner-queue-drain-current-main-v2`
- `fix/owner-queue-drain-current-main-v3`

### MASTERPLAN-BACKUP — `4853d74a4dac` (2 refs)

**Landing/disposition:** Historical masterplan/provider closure snapshots; preserve `backup/*`. Newer masterplan and provider verifiers are present on `main`. Review individual missing assertions before archival, not dated machine-ledger replacement.

- `backup/final-masterplan-closure-pre-reconcile-20260927`
- `backup/terminal-masterplan-pre-reconcile-20260927`

### PROVIDER-BACKUP — `b2e03064ec26` (2 refs)

**Landing/disposition:** Historical provider restack snapshot; preserve `backup/*`. The modern provider closure verifier exists on `main` but differs. Audit parity and port only demonstrably missing checks.

- `backup/provider-2082-pre-main-restack-20260927`
- `backup/provider-implementation-clean3-pre-main-restack-20260927`

### SUPERVISOR-BACKUP — `9f8d10b93b91` (2 refs)

**Landing/disposition:** Historical supervisor pre-stack snapshot; preserve `backup/*`. Newer supervisor runtime/workflow exists on `main`; only reimplement individually missing authority controls via a current-main PR.

- `backup/supervisor-1544-pre-stack-20260919`
- `repair/supervisor-secret-clean-20260919`

### GAME-STACK — `49f199b5a11c` (2 refs)

**Landing/disposition:** PR #3715 merged to base `feat/game-builder-dual-runtime-playable-20261011`; PR #3642 later merged that base to `main`. The advanced-dialogue documentation blob is identical on `main`. Stacked lineage established, but require final changed-file equivalence before deleting old refs.

- `feat/game-builder-advanced-dialogue-20261012`
- `feat/game-builder-advanced-narrative-20261012`

### JEEVES-EVIDENCE — `924ee7f54f01` (2 refs)

**Landing/disposition:** PR #1749 closed unmerged against `integration/app-consolidation`. The old `skeleton/testing/test_learning_evidence_integration.py` is absent on `main`, while main's learning evidence module is substantially newer. Port compatible regressions and any missing invariants to a fresh main-based PR; never replay the dated module wholesale.

- `fix/jeeves-learning-evidence-contract-seams-1038-validation`
- `fix/jeeves-learning-evidence-contract-seams-1038`

### ACCOUNTABILITY — `58c9b12c4243` (2 refs)

**Landing/disposition:** Historical closure bridge; modern masterplan verifier/workflow is present on `main`. Compare old receipt tests and carry forward missing assertions only, preserving current canonical machine state.

- `masterplan/accountability-closure-bridge-20260927-clean8`
- `masterplan/final-masterplan-closure-20260927-clean7`

### FEEDBACK — `a5f1c490df9a` (2 refs)

**Landing/disposition:** Historical P1 feedback closure; `main` already contains a newer feedback gate. Compare missing controls, then mark superseded or create a small additive main PR; preserve old closure-state JSON.

- `masterplan/closure-p1-feedback-release-20260927`
- `masterplan/closure-p1-provider-redundancy-20260927`

### STAGE7 — `f85b7ae75012` (2 refs)

**Landing/disposition:** Old Stage-7 work was superseded by main landing PR #2081; PRs #2067/#2075 were closed without merging. The historical `verify_stage6_streaming_closure.py` is not on `main`; determine whether the current streaming verifier covers its acceptance checks before treating this cluster as redundant.

- `masterplan/closure-stage7-final-20260927`
- `masterplan/closure-stage7-golden-20260927`

## Live open-PR integration targets

- [#3788](https://github.com/Apeloff1/Skeleton/pull/3788): fail-closed archive fix on a current-main branch; wait for exact-head required CI. Workflow Input Security currently rejects pre-existing `chickensoft-games/setup-godot` action uses; never weaken the allowlist to merge.
- [#3629](https://github.com/Apeloff1/Skeleton/pull/3629): Dragon native feature ahead of main, updated head undergoing CI; Repository Hygiene has reported changed-file whitespace errors. Repair at the captured current head and re-run all required checks.
- [#3605](https://github.com/Apeloff1/Skeleton/pull/3605): divergent Dragon Wisdom draft; reconcile conflicts with main, then perform exact-head acceptance.
- [#3782](https://github.com/Apeloff1/Skeleton/pull/3782): divergent AI Chat draft; reconcile with main while preserving governed streaming/upload/runtime boundaries, then perform exact-head acceptance.

## Rules for promotion

1. Capture current main and branch SHA, open PR head/base ownership and current queued Actions pressure.
2. If head is ancestor of main, treat as a retirement *candidate* only after open-PR, protected-name, grace, race and exact-tip checks. Do not fast-forward only to make a stale branch look current.
3. If diverged, never force-reset. Establish main-equivalent tree/path evidence or port missing behavior through a bounded current-main PR. Closed PRs merged to non-main bases are not themselves main integration evidence.
4. Do not rewrite historic backup/retention refs. Verify supersession by scope and invariants, not merely presence of similarly named files.
5. `branch-flow.yml` correctly backs off at 40 queued Actions runs and does not rewrite drafts, workflow-changing or conflicting heads. Preserve these fences.
6. Only mark an actual landing complete once the required exact-head checks have passed, the PR has merged to main (directly or verified stacked chain), and the new main commit is recorded.

**Audit disposition completed:** every member of the 21 shared-tip groups has a named path. **Integration/deletion not completed**; code parity, CI and cleanup confirmation are still separate work.
