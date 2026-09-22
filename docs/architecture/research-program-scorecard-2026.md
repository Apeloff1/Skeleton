
# Research Program Scorecard — 2026

Status: canonical Track AD research-accountability metrics
Updated: 2026-09-22
Authority: reporting only; never a promotion score

## 0. Rule

There is **no single research completion score**.

A large bibliography can coexist with zero local reproduction.
A high experiment count can coexist with poor experimental validity.
A low debt count can be gamed by hiding uncertainty.

The scorecard therefore reports independent dimensions.

## 1. Current planning snapshot

~~~text
research_domains_planning_covered: 24/24
frontier_findings_defined: FR001..FR144
research_questions_defined: RQ001..RQ082
source_status_attestations_defined: SV001..SV072
frontier_delta_findings_defined: FD001..FD031
contradictions_defined: CX001..CX024
research_debt_defined: RDE001..RDE046
local_experiment_protocols_defined: RXP001..RXP062
historical_lineage_anchors_defined: HL001..HL110
source_families_defined: RS001..RS055
research_control_plane_backlog_defined: RCB001..RCB120
research_control_plane_gaps_defined: RCG001..RCG100
research_control_plane_acceptance_campaigns_defined: RCB-A01..RCB-A10

local_protocol_execution_claimed_by_this_planning_pass: 0
research_control_plane_backlog_items_claimed_implemented: 0
research_control_plane_gaps_claimed_closed: 0
local_reproductions_claimed_by_this_planning_pass: 0
research_debt_retired_by_literature_only: 0
production_authority_granted: false
~~~

This is intentional. Planning completeness is not experimental completion.

## 2. Coverage metrics

### 2.1 Domain planning coverage
Number of domains with:
- foundational anchor;
- frontier source;
- counterevidence;
- baseline;
- question;
- debt;
- protocol;
- refresh rule.

Target: 24/24 planning-covered.

### 2.2 Protocol coverage
Questions with:
- direct RXP protocol;
- or explicit non-testable/deferred reason.

Report numerator and denominator.

### 2.3 Dependency coverage
Architecture decisions with explicit:
- research blockers;
- systems blockers;
- safety/authority blockers.

Hidden blockers count as failure.

## 3. Evidence-health metrics

### 3.1 Source-status completeness
Sources with:
- identifier;
- exact version;
- status;
- observed date;
- claim scope.

### 3.2 Source freshness
Report:
- within refresh SLA;
- stale;
- status unresolved;
- changed since last review.

### 3.3 Evidence independence
Report:
- number of supporting records;
- estimated independent clusters;
- same-lab/code/model/benchmark correlations.

### 3.4 Negative-evidence coverage
For each high-impact claim:
- negative evidence present?
- counterexample?
- known failure regime?

Target is not "more negatives"; target is absence of one-sided search.

## 4. Reproduction metrics

### 4.1 Protocols executed
Count by decision state:
- supported;
- partial;
- null;
- falsified;
- inconclusive;
- invalid;
- reproduction failed.

### 4.2 Reproduction class
Count:
- sanity;
- paper-scale;
- transfer;
- systems;
- adversarial;
- negative;
- independent.

### 4.3 Independent implementation rate
Fraction of architecture-changing claims with a reproduction not using the same implementation assumptions.

### 4.4 Scale-transfer coverage
Claims with:
- proxy evidence only;
- medium confirmation;
- systems-scale confirmation.

## 5. Research-debt metrics

### 5.1 Debt state
Counts:
- OPEN;
- EXPERIMENT_DESIGNED;
- RUNNING;
- EVIDENCE_COLLECTED;
- CHALLENGED;
- RETIRED;
- PARTIALLY_RETIRED;
- INVALIDATED;
- DEFERRED.

### 5.2 Debt age
Track:
- opened date;
- last activity;
- refresh deadline;
- architecture decisions blocked.

### 5.3 Debt reopening
Count retired debt reopened after:
- model change;
- data change;
- hardware change;
- benchmark correction;
- contradictory telemetry.

Reopening debt is healthy when assumptions changed.

## 6. Experimental-validity metrics

Report:
- baseline-parity reviews passed;
- failed/diverged runs retained;
- primary metrics preregistered;
- post-hoc exploratory changes disclosed;
- tuning budgets comparable;
- multiple-comparison count known;
- blind-eval access clean;
- artifact bundle complete.

An experiment can complete computationally and still fail validity.

## 7. Measurement-quality metrics

### Systems
- cold/warm paths separated;
- p50/p95/p99 reported;
- failure rate reported;
- synchronized timing;
- workload distribution declared.

### Model
- task strata;
- long-tail;
- OOD;
- calibration;
- failure mode;
- resource cost.

### Human/operator
- decision quality;
- reliance calibration;
- correction;
- fatigue;
- workload.

## 8. Research-agent metrics

Report:
- tasks attempted;
- stage-wise success;
- code build/run success;
- valid experiments;
- independent recompute agreement;
- scorer-gaming attempts;
- blind-eval violations;
- human review minutes;
- accepted useful findings.

Do not report only:
- commits;
- LOC;
- experiments launched.

## 9. Information-yield metrics

For each RXP:
- cost;
- uncertainty reduction;
- debts changed;
- RQs changed;
- architecture decision changed;
- follow-up experiments avoided.

A cheap null result can have higher information yield than an expensive benchmark win.

## 10. Decision-quality metrics

Track ADRs by outcome:
- adopted;
- rejected;
- deferred;
- reverted.

Later review asks:
- was the evidence available at decision time sufficient?
- did production contradict the research scope?
- was rollback successful?
- which missing evidence would have changed the decision?

## 11. Safety/authority research metrics

Report separately:
- capability improvement;
- policy correctness;
- authority violations;
- prompt injection success;
- cross-tenant leakage;
- deletion failures;
- unknown side-effect outcomes;
- safe-mode recovery.

Capability gains never offset hard authority failures.

## 12. Research freshness dashboard

Recommended fields:

| Metric | Meaning |
| --- | --- |
| sources_due_refresh | source records past SLA |
| conclusions_due_refresh | FR conclusions past review date |
| unresolved_status | sources with unresolved venue/status |
| new_counterevidence | new evidence against current posture |
| stronger_baseline_detected | new baseline requiring re-evaluation |
| benchmark_changed | task/scorer/version changed |
| provider_semantic_drift | canary detected behavior change |

## 13. Planning vs evidence dashboard

The dashboard must show at least three independent bars:

~~~text
PLANNING COVERAGE
LOCAL REPRODUCTION
PRODUCTION EVIDENCE READINESS
~~~

Never combine them into one percentage.

## 14. Current Track AD accountability state

At this planning checkpoint:

- planning coverage is intentionally high;
- local reproduction remains pending unless backed by actual experiment bundles;
- open research debt remains open;
- Track AB production blockers remain binding;
- CI status is external repository evidence and must be checked against the current head.

## 15. Anti-gaming rules

Do not improve scorecard appearance by:
- splitting one experiment into many;
- deleting failed runs;
- closing debt without evidence;
- counting citations as reproductions;
- counting correlated papers as independent;
- increasing LOC;
- increasing agent count;
- launching expensive runs without decision value;
- weakening hard floors.

## 16. Planning checkpoint

~~~text
checkpoint_id: PLAN-20260922-RESEARCH-PROGRAM-SCORECARD
created_at: 2026-09-22
domain_count: 24
research_findings: 144
research_questions: 82
source_attestations: 72
frontier_deltas: 31
contradictions: 24
research_debt_items: 46
experiment_protocols: 62
historical_anchors: 110
source_families: 55
research_control_plane_backlog_items: 120
research_control_plane_gaps: 100
research_control_plane_acceptance_campaigns: 10
planning_coverage_is_not_reproduction: true
single_scalar_score_forbidden: true
production_authority_granted: false
~~~
