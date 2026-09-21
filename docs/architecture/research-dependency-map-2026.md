
# Research Dependency Map — 2026-09-22

Status: canonical Track AD dependency map
Purpose: connect open research to construction decisions
Authority: planning/evidence routing only; no production authority

## 0. Why this exists

A research plan can become huge without becoming useful.

This map forces every major research area to answer:

1. Which architecture decision depends on it?
2. Which open questions matter?
3. Which research debt remains?
4. Which local protocol can retire that debt?
5. Which non-research production gates still block promotion?

The graph is intentionally asymmetric:

```text
ResearchQuestion
 -> ResearchDebt
 -> ExperimentProtocol
 -> Evidence
 -> ArchitectureDecision
 -> Track AA/AC candidate
 -> Track AB compatibility
 -> shadow/canary/promotion
```

No edge runs directly from paper/source to production.

---

# 1. Domain dependency matrix

| Domain | RQ | Research debt | RXP | Main construction targets | Non-research blockers |
| --- | --- | --- | --- | --- | --- |
| model architecture | RQ011–RQ013 | RDE001–RDE002 | RXP001, RXP006, RXP007, RXP034 | ModelPort, Track AA/AC | AB1 representation identity, AB3 artifact identity, AB23 compatibility, rollback |
| representation/tokenization | RQ014–RQ016 | RDE003 | RXP009 | RepresentationSpec, context compiler, model artifact | AB1 identity, cache invalidation, adapter compatibility |
| neural memory/retrieval | RQ017–RQ019 | RDE013–RDE018 | RXP008, RXP013, RXP014, RXP015 | memory plane, context compiler, retrieval router | tenant isolation, deletion, provenance, poisoning |
| training data/mixtures | RQ020–RQ022 | RDE004–RDE006 | RXP002, RXP003 | DatasetManifest, MixtureManifest, training planner | AB2 lineage, contamination firewall, license/provenance |
| optimization/numerics | RQ023–RQ025 | RDE007–RDE009 | RXP004, RXP005 | Track Z optimizer control, checkpoint schema | optimizer-state identity, resume fidelity, numerical circuit breakers |
| test-time reasoning | RQ026–RQ028 | RDE010–RDE012 | RXP007, RXP010, RXP011, RXP012 | ReasoningBudgetAllocator, verifier plane | eval firewall, runaway-compute bounds, monitorability |
| formal reasoning/verification | RQ029–RQ031 | RDE032 | RXP025, RXP039 | typed prover tools, verifier registry | semantic-faithfulness review, tool authority |
| agents/long horizon | RQ032–RQ034 | RDE019–RDE021 | RXP016, RXP017, RXP029 | agent runtime, planner, tool loop | principals, sandbox, side-effect reconciliation, cancellation |
| agent memory/procedures | RQ035–RQ037 | RDE015–RDE017 | RXP014, RXP015 | procedural/prospective memory | authority revalidation, supersession, deletion |
| serving/inference | RQ038–RQ040 | RDE022–RDE025 | RXP018, RXP019, RXP020 | scheduler, KV manager, P/D serving | control-plane reserve, overload/backpressure, recovery |
| distributed training | RQ041–RQ043 | scoped distributed debt | RXP033 | topology planner, elastic training | fencing, checkpoint atomicity, RNG/data cursor recovery |
| multimodal/world models | RQ044–RQ046 | RDE031 + world-model transfer debt | RXP031, RXP038, RXP047 | multimodal ModelPort, world-state interfaces | modality provenance, artifact identity, tool/action grounding |
| evaluation science | RQ047–RQ049 | RDE035–RDE036 | RXP028, RXP040–RXP044, RXP050 | EvaluationRegistry, blind promotion holdout | AB5 eval firewall, benchmark custody, provenance |
| safety/security/monitorability | RQ050–RQ052 | RDE021, RDE028–RDE029, RDE033 | RXP017, RXP021, RXP022, RXP026 | monitor plane, policy/capability boundary | AB6/7 principals+sandbox, trust roots, incident recovery |
| interpretability | RQ053–RQ055 | RDE026–RDE027 | RXP023, RXP024 | diagnostic/monitoring tools | artifact versioning, causal validation, deployment transfer |
| uncertainty/calibration | RQ056–RQ058 | scoped calibration debt | RXP037, RXP045 | uncertainty router, abstention/escalation | provider semantic drift, evaluator versioning |
| continual adaptation | RQ059–RQ061 | RDE018, RDE030 + adaptation debt | RXP030, RXP036 | adapters, memory, slow/medium/fast adaptation lanes | rollback, poisoning, deletion, promotion boundaries |
| hardware/precision/efficiency | RQ062–RQ064 | RDE008–RDE009, RDE024 | RXP005, RXP019, RXP032, RXP033, RXP046 | Track Z/AA hardware profiles | kernel/operator support, portability, recovery |
| research automation | RQ065–RQ067 | RDE033–RDE036 | RXP026, RXP027, RXP035, RXP040, RXP050 | research-agent plane, source adapters, evidence graph | blind-eval isolation, sandbox, anti-cheating, signoff |

---

# 2. Critical research path

The fastest route to architecture-changing evidence is **not** to run the most exotic experiment first.

## Gate A — measurement substrate

Required first:

- experiment manifest;
- artifact identity;
- data lineage;
- evaluation firewall;
- result bundle;
- baseline parity;
- benchmark custody;
- cost accounting.

Unblocked protocols:

- RXP001;
- RXP004;
- RXP010;
- RXP013;
- RXP018.

## Gate B — stable baselines

Need stable references for:

- dense model;
- AdamW/BF16;
- lexical+dense retrieval;
- direct decoding;
- colocated serving;
- single-agent workflow.

Without them, challenger wins are uninterpretable.

## Gate C — high-information routing studies

Highest expected decision value:

1. RXP013 retrieval/context routing;
2. RXP010 test-time scaling;
3. RXP018 serving topology;
4. RXP004 optimizer geometry;
5. RXP014/RXP015 memory;
6. RXP021 monitorability;
7. RXP026 research-agent anti-cheating.

## Gate D — architecture-changing challengers

Only after measurement/baseline stability:

- sparse/differential attention;
- recurrent latent depth;
- neural memory;
- byte-latent representation;
- native low-bit/sparse kernels;
- diffusion/equilibrium/exotic AC candidates.

---

# 3. Decision dependency rules

## D1 — Architecture family switch

Requires evidence from:

- RXP001 baseline;
- family-specific RXP;
- systems/serving comparison;
- migration/rollback analysis;
- artifact compatibility;
- long-context/tool/structured-output regression.

## D2 — Optimizer default switch

Requires:

- RXP004;
- equal tuning/search budget;
- scale transfer;
- numerical stability;
- checkpoint/resume;
- distributed communication;
- at least one larger confirmation run.

## D3 — Retrieval default/router change

Requires:

- RXP013;
- corpus-size and task strata;
- provenance quality;
- build/update cost;
- long-context comparison;
- failure/poisoning behavior.

## D4 — Durable-memory design change

Requires:

- RXP014;
- RXP015 where prospective behavior exists;
- deletion;
- contradiction;
- provenance;
- poisoning;
- tenant isolation;
- historical reconstruction.

## D5 — Agent-action expansion

Requires:

- tool-selection robustness;
- authenticated principal;
- capability scope;
- sandbox;
- unknown-outcome reconciliation;
- cancellation;
- recovery;
- trajectory evaluation.

## D6 — Serving topology change

Requires:

- RXP018;
- RXP019/RXP020 as relevant;
- overload;
- network faults;
- queue tails;
- control-plane reserve;
- rollback/failover.

## D7 — Learned monitor promotion

Requires:

- RXP021/RXP022;
- OOD/evasion;
- version binding;
- false-positive/false-negative costs;
- deterministic policy fallback.

## D8 — Research-agent autonomy increase

Requires:

- RXP026;
- RXP027;
- blind-eval isolation;
- independent recomputation;
- source access controls;
- generated-data provenance;
- human/independent signoff at declared boundary.

---

# 4. Cross-domain dependency edges

Important non-obvious edges:

```text
representation
 -> tokenizer/cache identity
 -> retrieval chunking
 -> adapter compatibility
 -> serving cache
```

```text
data mixture
 -> optimizer dynamics
 -> scaling law
 -> calibration
 -> evaluation interpretation
```

```text
reasoning strategy
 -> inference protocol
 -> latency/cost
 -> monitorability
 -> verifier load
 -> serving scheduler
```

```text
memory
 -> retrieval
 -> privacy/deletion
 -> prospective actions
 -> tool authority
```

```text
quantization
 -> kernel support
 -> interpretability map
 -> calibration
 -> serving KV
 -> portability
```

```text
research agent
 -> source ingestion
 -> code generation
 -> experiment selection
 -> benchmark exposure
 -> scorer interaction
 -> evidence graph
```

A local improvement can create debt in another domain.

---

# 5. Promotion-blocker matrix

| Candidate | Research blocker | Systems blocker | Safety/authority blocker |
| --- | --- | --- | --- |
| Muon/SOAP default | RDE007 | distributed/checkpoint cost | none unique, but rollback required |
| FP8 default | RDE008 | kernel/hardware portability | artifact precision identity |
| FP4 default | RDE009 | immature operator coverage | numerical failure containment |
| sparse attention | route/quality transfer | real-kernel speed | rare-key miss behavior |
| neural memory | RDE018 | reset/replay | state leakage/provenance |
| typed prospective memory | RDE016 | durable trigger lifecycle | fresh execution authority |
| graph RAG | RDE014 | index build/update | poison/provenance |
| multi-agent | RDE020 | coordination cost | delegated authority amplification |
| P/D serving | RDE022–RDE025 | network/KV/queue behavior | control-plane recovery |
| CoT monitor | RDE028 | logging/latency | cannot become sole authorization |
| learned detector | RDE029 | calibration/serving | deterministic fallback |
| research agent | RDE033–RDE034 | orchestration/recompute cost | blind eval and self-validation |

---

# 6. Research dependency status vocabulary

Each dependency edge is one of:

- `REQUIRED`;
- `SUPPORTING`;
- `OPTIONAL`;
- `BLOCKING`;
- `INVALIDATED`;
- `SUPERSEDED`.

Every blocking edge must name the evidence that clears it.

A claim cannot be "90% complete" while an unnamed blocking edge remains hidden.

---

# 7. Research criticality

Research items are prioritized by:

```text
decision_value
× probability_of_changing_architecture
× affected_surface
× uncertainty_reduction
÷ experiment_cost
÷ irreversible_risk
```

This is a planning heuristic, not an automatic scalar authority.

High novelty does not imply high priority.

---

# 8. Planning checkpoint

```text
checkpoint_id: PLAN-20260922-RESEARCH-DEPENDENCY-MAP
created_at: 2026-09-22T00:06:00+02:00
domains: 19
research_questions: RQ001..RQ067
research_debt: RDE001..RDE036
experiment_protocols: RXP001..RXP050
historical_lineage: HL001..HL110
source_families: RS001..RS055
production_authority_granted: false
blocking_edges_must_be_explicit: true
```
