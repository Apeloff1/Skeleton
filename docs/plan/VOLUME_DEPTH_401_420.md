# Volume Depth Pass 401–420

Architecture lane: `plan/volume-depth-041-080-20260922`

Machine authority: [`machine/ai_master_plan.json`](../../machine/ai_master_plan.json)

Depth pass: **DP-401-420 — Evaluation-governance-to-scope-freeze depth**

This final sequential pass closes the frozen 421-volume architecture with
evaluation/research compute infrastructure, quotas/budgets/forecasting,
license/data-rights/ethics controls, model/provider lifecycle governance,
experimental promotion/retirement, failure knowledge, and the final scope freeze.

| Volume | Domain | Primary requirements |
| --- | --- | --- |
| VOL-401 | Evaluation Farm | Distribute evaluation jobs from immutable eval/model/dataset specs. Results bind to worker/environment/scorer identity and aggregate deterministically. |
| VOL-402 | Research Compute Queue | Queue experiments/reproductions/research workloads with priority, quota and provenance. Research jobs cannot preempt critical production work outside declared policy. |
| VOL-403 | Compute Quotas | Enforce per-tenant/project/team/workload compute limits across CPU/GPU/time/storage. Quota reservations and usage reconcile durably after failure/cancellation. |
| VOL-404 | Budget Accounting Ledger | Record monetary/token/compute/storage budgets, reservations, charges, refunds and adjustments immutably. Ledger entries are attributable to objective/task/tenant/provider. |
| VOL-405 | Forecasting Engine | Forecast demand, capacity, queue, spend and resource pressure with uncertainty bands. Forecasts inform planning but never bypass hard quotas/capacity/security. |
| VOL-406 | Cost Anomaly Detection | Detect unexpected spend/token/compute/storage patterns against workload-normalized baselines. Anomalies link to concrete operations/providers/tenants before action. |
| VOL-407 | License Intelligence | Track software/model/data licenses, obligations, compatibility and provenance per artifact/version. Unknown or conflicting license state blocks incompatible distribution/use. |
| VOL-408 | Data Usage Rights | Represent permitted purposes, geography, retention, training/eval/use restrictions and consent for data. Rights propagate to derivatives/models/artifacts where required. |
| VOL-409 | Attribution Engine | Generate traceable attribution for code/data/models/research/artifacts from provenance and license obligations. Attribution references exact contributing versions where feasible. |
| VOL-410 | Research Ethics Review | Gate sensitive human/data/dual-use research activities through explicit risk, consent and oversight criteria. Review status cannot be inferred from technical test success alone. |
| VOL-411 | Model Lifecycle Governance | Govern model intake, training, evaluation, deployment, operation, update, retirement and archive states. Every transition requires declared evidence/owner and rollback/retention semantics. |
| VOL-412 | Model Deprecation | Deprecate models with usage inventory, replacement path, deadline, compatibility and rollback considerations. Remove deprecated models only after supported consumers migrate or explicit exception. |
| VOL-413 | Provider Migration | Migrate external/internal providers through capability, policy, quality, cost and data-boundary parity evidence. Support staged dual-run/shadow/canary and rollback before full cutover. |
| VOL-414 | Shadow Traffic | Replay or mirror eligible requests to candidate systems without affecting authoritative user outcomes. Shadow path strips/limits sensitive side effects and records comparability metadata. |
| VOL-415 | Champion / Challenger Registry | Track incumbent and candidate models/strategies/providers with evaluation lineage and promotion state. Promotion compares predeclared metrics, robustness, safety, cost and rollback evidence. |
| VOL-416 | Experimental Feature Sandbox | Run new capabilities behind isolated scopes, synthetic/shadow traffic and explicit kill switches. Experimental state cannot satisfy production capability/acceptance claims. |
| VOL-417 | Research Branching Model | Separate research branches/experiments from production integration while preserving lineage and merge criteria. Research changes use bounded ownership and cannot bypass production gates on merge. |
| VOL-418 | Technique Retirement | Retire algorithms/strategies/tools no longer competitive, safe or maintainable while preserving reproducibility history. Retirement records replacement, reason, affected consumers and archive location. |
| VOL-419 | Knowledge of Failure | Preserve incidents, failed experiments, rejected designs and counterexamples as searchable structured engineering knowledge. Failure records distinguish context-specific lessons from universal rules. |
| VOL-420 | Architecture Scope Freeze | Freeze top-level volume breadth at VOL-420 and route new requirements into existing volumes/subchapters by default. A new top-level volume requires explicit ADR proving existing domains cannot represent the requirement. |

## Closure spine

```text
VOL-401..406 evaluation/research compute + quotas/budget/forecast/anomaly
 -> VOL-407..410 license/data rights/attribution/research ethics
 -> VOL-411..415 model/provider lifecycle + shadow + champion/challenger
 -> VOL-416..419 experimental sandbox/research branches/retirement/failure knowledge
 -> VOL-420 architecture scope freeze
```

## Closure law

All VOL-000..VOL-420 volumes now belong to an enforced sequential depth pass.
No additional top-level volume is implied by future discoveries. New work must
deepen an existing volume unless an ADR demonstrates that the frozen taxonomy
cannot represent the requirement cleanly.

Planning depth still does not equal implementation. All existing signed
accountability, evidence, verification, hardening, release, rollback, SLO and
production-promotion gates remain in force.

## Remaining work after DP-401-420

- convert planned paths/tests/evaluations into implemented, artifact-bound work;
- close gaps and risks by priority/dependency order;
- finish AI-tree ownership cutover only after parity/import/recovery evidence;
- build vertical slices VS-000..VS-007 and the final assembly acceptance bundle;
- keep breadth frozen at **VOL-420** while increasing verified construction depth.
