# Autonomous Studio

The Autonomous Studio is a bounded virtual engineering organization for advancing Skeleton as a frontier game-building AI system. It registers **1,000 deterministic worker identities** but deliberately activates only a small cohort at a time. The goal is high work throughput without turning repository automation into an uncontrolled swarm.

## Directive

Build game-building systems that are more complete, more testable, more composable, and more useful to developers than narrow demo-oriented systems. The studio should look for leverage across model/runtime architecture, game design, mechanics, procedural generation, embodied agents, world simulation, physics, animation, graphics, audio, tooling, engine runtime, networking, QA, security, performance, evaluation, research synthesis, developer experience, and release operations.

The studio is expected to improve the project continuously, but **evidence beats activity**. A rejected proposal, a failed-closed task, or a no-op run is preferable to an unsafe change.

## 1,000-worker topology

`studio_registry.py` creates 20 divisions × 10 tracks × 5 worker modes = exactly 1,000 stable identities.

Each division contains workers in these modes:

- **Scout** — finds opportunities, gaps, regressions, and relevant evidence.
- **Builder** — proposes a small code change for one bounded objective.
- **Reviewer** — adversarially reviews a proposed patch before it may advance.
- **Tester** — focuses on invariants, regressions, and evaluation design.
- **Integrator** — focuses on compatibility, composition, and landing quality.

The registry is deterministic and fingerprinted so every audit log can identify the exact virtual organization that existed for a run.

## Night-shift execution

`.github/workflows/autonomous-studio.yml` schedules four bounded overnight shifts. Each shift:

1. Checks out trusted `main` with persisted Git credentials disabled.
2. Snapshots open PRs, open issues, recent failed workflow runs, and the current queued Actions-run count.
3. Applies repository backpressure before any model call: at **40 or more queued Actions runs**, the shift becomes a logged safe no-op instead of generating or publishing work.
4. Selects a diverse deterministic worker cohort when queue pressure is below the threshold.
5. Gives a planner the backlog, tracked-file manifest, live repository state, and cohort context.
6. Allows up to three narrow tasks per run.
7. Assigns a specialist builder and an independent senior reviewer to each task.
8. Treats every model response as untrusted data.
9. Rejects malformed, oversized, high-risk, out-of-scope, rename, delete, dependency-control, workflow, auth, secret, or security-boundary proposals.
10. Uses `git apply --check` before accepting a proposal.
11. Copies the accepted patch and audit evidence outside the disposable worktree and seals the patch with SHA-256.
12. Explicitly blanks `OPENAI_API_KEY`, `GH_TOKEN`, and `GITHUB_TOKEN` for generated-code validation.
13. Runs Python compilation, Ruff on changed Python files, studio control regressions, and the full `skeleton/testing` suite.
14. Resets the repository and removes all untracked test side effects after generated-code execution.
15. Verifies the sealed patch hash and reapplies the exact pre-test patch.
16. Writes every run to the durable **Autonomous Studio Ledger**, including queue-pressure, no-op, and rejected runs.
17. For an accepted patch, creates a new `studio/night-*` branch and opens a reviewable PR.
18. Never writes directly to `main` and never enables auto-merge.

Normal repository PR CI remains an additional independent validation boundary after the studio's own pre-publication checks.

### Actions backpressure

The Studio deliberately refuses to add model/build/PR load when the repository is already congested. The workflow queries the repository-wide queued Actions-run count before proposal generation. When the count is at or above the current threshold of **40**, it:

- skips the OpenAI proposal call;
- skips generated-code execution;
- skips branch and PR publication;
- records `shift_skipped_queue_pressure` in the machine audit;
- writes a human-readable no-op report; and
- still appends the shift to the durable Studio Ledger.

This makes overload handling fail-safe and observable while allowing the existing Actions queue to drain.

## Secret boundary

The workflow expects one GitHub Actions repository secret:

```text
OPENAI_API_KEY
```

The key is exposed only to the proposal-generation step. It is not written to audit files, patches, commit messages, PR bodies, or the Studio Ledger. The workflow fails closed when the secret is missing.

An optional repository variable can override the configured model:

```text
OPENAI_MODEL
```

If omitted, the existing bounded Responses API adapter uses its default model configuration.

The GitHub write token is exported only by trusted metadata/publication steps. It is explicitly blank during generated-code validation. Generated tests therefore cannot read the repository write token or the OpenAI key from their process environment.

## Mutation boundary

Studio v1 is intentionally conservative.

Allowed model-selected source roots:

- `skeleton/`
- `backend/`
- `scripts/`
- `docs/`

The deterministic repair policy rejects trust/security-sensitive paths. The studio additionally blocks workflow/control-plane paths, secrets, environment files, dependency manifests and lockfiles, renames, deletions, and new-file creation in model-generated patches.

That means v1 optimizes and extends **existing ordinary source files**. New-file creation can be introduced later as a separately reviewed capability once the base system has accumulated evidence.

## Logging: nothing silent

Every model-driven shift emits JSONL events with timestamps, run ID, registry fingerprint, active cohort, plan, accepted/rejected task outcomes, assigned builder/reviewer IDs, review reasons, patch budget decisions, and final status. Queue-pressure no-ops emit a dedicated machine event containing the measured queue depth and threshold.

When a patch is published, the latest machine log, human report, and sealed patch hash are committed as:

- `.studio/audit/latest.jsonl`
- `.studio/audit/latest.md`
- `.studio/audit/latest.patch.sha256`

Every scheduled run also comments a human-readable summary on the durable `bot: autonomous studio ledger` GitHub issue. A run with no accepted code is still recorded.

Secrets are recursively redacted **before** JSON serialization so redaction cannot corrupt the audit structure.

## Daily reporting

The reporting layer is designed around two consolidated reports rather than one message per bot:

- **12:00 Europe/Oslo — Progress report.** Exhaustive but condensed explanation of code built, PRs, CI, architecture, tests, failures, lessons, and next work. It should teach the owner how the system is evolving.
- **00:00 Europe/Oslo — Silent-actions audit.** Consolidates everything the automation did since the prior audit, including scans, rejected proposals, no-op decisions, failures, comments, branches, and validation results.

Email delivery is intentionally kept outside the repository's OpenAI key boundary. A connected mail integration can send the two consolidated reports without granting generated code access to mailbox credentials.

## Safety invariants

The following are non-negotiable:

- No direct autonomous write to `main`.
- No autonomous weakening of CI, security gates, provenance, authentication, or secret handling.
- No model-generated shell command execution.
- No generated-code validation step receives `OPENAI_API_KEY` or an explicitly exported GitHub write token.
- Generated-code test side effects are discarded; publication is reconstructed from the sealed pre-test patch.
- No silent mutation: every run has a durable ledger record.
- No unbounded concurrency: 1,000 identities are a specialization map, not 1,000 simultaneous processes.
- No model/build/PR amplification while repository Actions queue pressure is above the bounded threshold.
- No automatic merge of code changes in v1.
- A failure to prove safety or applicability becomes a logged rejection, not a best-effort mutation.

## Scaling path

Once v1 has a clean operating history, the next safe expansions are:

1. Add a dedicated tester-agent pass that critiques likely regression surfaces before publication.
2. Add isolated new-file creation with explicit per-directory quotas and provenance.
3. Add benchmark-aware task selection so game-building improvements are tied to measurable eval deltas.
4. Add CI-result feedback so the next cohort learns from the previous studio PR's concrete failures.
5. Add dependency graphs and ownership maps to route work to specialists more accurately.
6. Add branch supersession logic so stale studio PRs are replaced rather than accumulated.
7. Add cost/token budgets and per-division throughput metrics to optimize useful work per model call.
8. Add a promotion controller that can only request merge after required checks and explicit repository policy permit it; code auto-merge should remain opt-in.
