
# Research Saturation Checklist — 2026-09-21

Status: planning accountability record
Track: AD
Canonical atlas: docs/architecture/frontier-research-atlas-2026.md
Experiment manual: docs/architecture/frontier-research-experiment-protocols-2026.md

## Rule

A domain can be **planning-saturated** while still being **locally unvalidated**.

These statuses are deliberately separate:

- PLANNING_COVERED — required research categories and experiments are mapped;
- REPRODUCTION_PENDING — local evidence is not yet sufficient;
- PARTIALLY_REPRODUCED — some claims reproduced within bounded scope;
- REPRODUCED_IN_SCOPE — declared local scope reproduced;
- PRODUCTION_EVIDENCE_READY — applicable architecture and hardening gates have also passed.

No domain in this checklist is upgraded to production evidence from literature coverage alone.

## Required planning fields

Every domain must have:

- [x] foundational anchor;
- [x] current frontier source or explicit "no credible frontier candidate";
- [x] negative/counterevidence;
- [x] source-status discipline;
- [x] mandatory baseline;
- [x] local experiment protocol;
- [x] research-debt assessment;
- [x] scale/hardware scope;
- [x] contradiction handling;
- [x] refresh trigger.

Local reproduction is tracked separately.

## Domain matrix

| Domain | Planning coverage | Local reproduction | Key protocol(s) | Debt focus |
| --- | --- | --- | --- | --- |
| model architecture | PLANNING_COVERED | REPRODUCTION_PENDING | RXP001, RXP006, RXP007, RXP034 | RDE001, RDE002 |
| representation/tokenization | PLANNING_COVERED | REPRODUCTION_PENDING | RXP009 | RDE003 |
| neural memory/retrieval | PLANNING_COVERED | REPRODUCTION_PENDING | RXP008, RXP013, RXP014, RXP015 | RDE013–RDE018 |
| training data/mixtures | PLANNING_COVERED | REPRODUCTION_PENDING | RXP002, RXP003 | RDE004–RDE006 |
| optimization/numerics | PLANNING_COVERED | REPRODUCTION_PENDING | RXP004, RXP005 | RDE007–RDE009 |
| test-time reasoning | PLANNING_COVERED | REPRODUCTION_PENDING | RXP007, RXP010, RXP011, RXP012 | RDE010–RDE012 |
| formal reasoning/verification | PLANNING_COVERED | REPRODUCTION_PENDING | RXP025 | RDE032 |
| agents/long horizon | PLANNING_COVERED | REPRODUCTION_PENDING | RXP016, RXP017, RXP029 | RDE019–RDE021 |
| agent memory/procedures | PLANNING_COVERED | REPRODUCTION_PENDING | RXP014, RXP015 | RDE015–RDE017 |
| serving/inference | PLANNING_COVERED | REPRODUCTION_PENDING | RXP018, RXP019, RXP020 | RDE022–RDE025 |
| distributed training | PLANNING_COVERED | REPRODUCTION_PENDING | RXP033 | topology/elasticity debt remains scoped |
| multimodal/world models | PLANNING_COVERED | REPRODUCTION_PENDING | RXP031 | RDE031 plus world-model transfer debt |
| evaluation science | PLANNING_COVERED | REPRODUCTION_PENDING | RXP028, RXP035 | RDE035, RDE036 |
| safety/security/monitorability | PLANNING_COVERED | REPRODUCTION_PENDING | RXP017, RXP021, RXP022, RXP026 | RDE021, RDE028, RDE029, RDE033 |
| interpretability | PLANNING_COVERED | REPRODUCTION_PENDING | RXP023, RXP024 | RDE026, RDE027 |
| uncertainty/calibration | PLANNING_COVERED | REPRODUCTION_PENDING | embedded in RXP010/RXP011/RXP021 | calibration debt remains scoped |
| continual adaptation | PLANNING_COVERED | REPRODUCTION_PENDING | RXP008, RXP030, AC fast-weight experiments | RDE018, RDE030 |
| hardware/precision/efficiency | PLANNING_COVERED | REPRODUCTION_PENDING | RXP005, RXP019, RXP032, RXP033 | RDE008, RDE009, RDE024 |
| research automation | PLANNING_COVERED | REPRODUCTION_PENDING | RXP026, RXP027, RXP035, RXP040, RXP050 | RDE033, RDE034, RDE036 |
| model compression/distillation/pruning | PLANNING_COVERED | REPRODUCTION_PENDING | RXP051–RXP053 | RDE037–RDE038 |
| privacy-preserving learning/inference | PLANNING_COVERED | REPRODUCTION_PENDING | RXP054–RXP056 | RDE039–RDE040 |
| software-engineering/code agents | PLANNING_COVERED | REPRODUCTION_PENDING | RXP057–RXP059 | RDE041–RDE042 |
| human–AI/operator science | PLANNING_COVERED | REPRODUCTION_PENDING | RXP060 | RDE043–RDE044 |
| causal/counterfactual modeling | PLANNING_COVERED | REPRODUCTION_PENDING | RXP047, RXP061, RXP062 | RDE045–RDE046 |

## Cross-domain blockers

Even after local research reproduction, production claims remain blocked by applicable Track AB P0 gaps.

Examples:

- a better model family cannot bypass artifact identity;
- a better optimizer cannot bypass checkpoint integrity;
- a better memory algorithm cannot bypass tenant isolation/deletion;
- a better agent cannot bypass capability policy;
- a better serving topology cannot bypass recovery/control-plane reserve;
- a better research agent cannot validate its own result.

## Signoff model

Each status transition must bind:

~~~text
checkpoint_id
domain
old_status
new_status
changed_at
evidence_ids[]
experiment_result_ids[]
open_debt[]
artifact_digest
signer
decision
~~~

For REPRODUCED_IN_SCOPE or above, evidence must include local result artifacts.

For PRODUCTION_EVIDENCE_READY, evidence must additionally include applicable:
- Track AB closure;
- benchmark/eval firewall;
- migration;
- rollback;
- monitoring;
- signed ADR.

## Planning checkpoint

~~~text
checkpoint_id: PLAN-20260921-RESEARCH-SATURATION-ACCOUNTABILITY
created_at: 2026-09-21T22:39:00+02:00
scope: Track AD / 24 research domains / FR-RQ-SV-FD-CX-RDE-RXP-HL-RS namespaces
planning_status: PLANNING_COVERED
local_reproduction_status: REPRODUCTION_PENDING
production_authority_granted: false
signoff_required_for_reproduction_claims: true
signoff_required_for_production_claims: true
~~~

## Completion interpretation

Research-planning completion means:
- the domain is mapped;
- uncertainty is explicit;
- the strongest baseline exists in the plan;
- negative evidence is retained;
- a local protocol exists;
- debt is visible.

It does **not** mean:
- the research claim has been reproduced;
- the implementation exists;
- the candidate is superior;
- the production system is safe;
- the debt has been retired.

This distinction is mandatory.
