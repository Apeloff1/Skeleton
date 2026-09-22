# Skeleton Architecture Master Index

> Canonical navigation for architecture, construction, research evidence, and promotion.
>
> Updated: 2026-09-21
>
> Rule: an architecture feature is not complete if it exists only in prose, only in code, or only in a historical round. It must be reachable from this index and represented in the machine architecture index where applicable.

## 1. Authority order

When documents overlap, resolve them in this order:

1. **Runtime and dependency contracts** — [FRONTIER_ARCHITECTURE.md](FRONTIER_ARCHITECTURE.md) and `skeleton/architecture.py`.
2. **Machine-readable architecture registry** — `skeleton/architecture_index.py`.
3. **Definitive architecture narrative** — [ARCHITECTURE.md](ARCHITECTURE.md).
4. **Current construction sequence** — [BUILD_PLAN.md](BUILD_PLAN.md).
5. **Research/evidence/evolution contract** — [architecture/research-evidence-evolution.md](architecture/research-evidence-evolution.md).
6. **Exotic architecture laboratory** — [architecture/exotic-architecture-lab.md](architecture/exotic-architecture-lab.md).
7. **Frontier research atlas** — [architecture/frontier-research-atlas-2026.md](architecture/frontier-research-atlas-2026.md).
8. **Research experiment protocols** — [architecture/frontier-research-experiment-protocols-2026.md](architecture/frontier-research-experiment-protocols-2026.md).
9. **Research saturation accountability** — [architecture/research-saturation-checklist-2026.md](architecture/research-saturation-checklist-2026.md).
10. **Historical research lineage** — [architecture/research-historical-lineage.md](architecture/research-historical-lineage.md).
11. **Research source topology** — [architecture/research-source-topology.md](architecture/research-source-topology.md).
12. **Research dependency map** — [architecture/research-dependency-map-2026.md](architecture/research-dependency-map-2026.md).
13. **Research execution program** — [architecture/research-execution-program-2026.md](architecture/research-execution-program-2026.md).
14. **Research program scorecard** — [architecture/research-program-scorecard-2026.md](architecture/research-program-scorecard-2026.md).
15. **Research control-plane internals** — [architecture/research-control-plane-internals-2026.md](architecture/research-control-plane-internals-2026.md).
16. **Research control-plane build backlog** — [architecture/research-control-plane-build-backlog-2026.md](architecture/research-control-plane-build-backlog-2026.md).
17. **Research control-plane adversarial gap audit** — [architecture/research-control-plane-gap-audit-2026.md](architecture/research-control-plane-gap-audit-2026.md).
18. **Knowledge absorption and promotion mechanics** — [architecture/sota-absorb-engine.md](architecture/sota-absorb-engine.md) and [architecture/adaptive-absorption-fabric.md](architecture/adaptive-absorption-fabric.md).
19. **Hostile gap audit** — [architecture/masterplan-gap-audit.md](architecture/masterplan-gap-audit.md).
20. **Historical architecture rounds** — `skeleton/architecture_round3.py` through `skeleton/architecture_round22.py`.

Historical rounds are evidence of design evolution, not permission to override newer contracts.

## 2. Frozen architectural invariants

These rules survive model, provider, framework, and research changes:

- dependencies point inward; core contracts do not depend on cockpit/UI/vendor implementations;
- model and provider implementations sit behind explicit interfaces;
- state authority is explicit and durable where durability is required;
- external side effects pass through admission, validation, authorization, execution, and receipt production;
- tool output and retrieved content are data, not privileged instructions;
- serving reads promoted state; research, ingestion, learning, and experimentation do not mutate serving state directly;
- promotion is versioned, replayable, measurable, canaried, and rollbackable;
- provenance follows evidence, memory, generated artifacts, experiments, and promoted architecture decisions;
- failures are observable and bounded; retries, cancellation, idempotency, and recovery are designed rather than improvised;
- a paper, benchmark result, model answer, or verifier score is evidence — never authority by itself.

## 3. Architecture registry

The executable architecture history is:

`base` + rounds `3..22`.

That is **21 indexed architecture entries**: one base architecture and twenty numbered rounds.

Any future `architecture_roundN.py` must be added to:

- `skeleton/architecture_index.py`;
- this master index when it introduces a new architectural family;
- the build plan if it creates unfinished construction work.

A round that is not indexed is considered structurally incomplete.

## 4. Canonical subsystem map

| System concern | Canonical source | Supporting source | Required evidence |
| --- | --- | --- | --- |
| Kernel / invariants | `skeleton/architecture.py` | `docs/ARCHITECTURE.md` | unit + invariant tests |
| Provider/model neutrality | `docs/FRONTIER_ARCHITECTURE.md` | research evidence manual | adapter conformance + regression |
| Memory / retrieval | architecture + memory/retrieval packages | absorb engine | retrieval quality, provenance, freshness |
| Planning / reasoning | intelligence + Jeeves planning packages | build plan | quality-per-compute + failure analysis |
| Agents / swarm | agent and swarm packages | architecture treatise | coordination, liveness, bounded retries |
| Tool execution | application/gate/tool surfaces | frontier contract | authorization + idempotency + receipts |
| Knowledge absorption | `sota-absorb-engine.md` | adaptive absorption fabric | replay + challenge + rollback |
| Research evolution | `research-evidence-evolution.md` | adaptive absorption fabric | reproduction + benchmark + canary |
| Evaluation | `eval/`, tests, build plan | research manual | deterministic + adversarial + benchmark |
| Serving/inference | runtime/provider adapters | build plan | latency, throughput, memory, failure recovery |
| Optimizer/training internals | `docs/BUILD_PLAN.md` Track Z | research source catalog | quality/token, stability, memory, communication, checkpoint/replay |
| Massive upgrade program | `docs/BUILD_PLAN.md` Track AA | research/evidence evolution contract | ablation, full-stack benchmark, failure injection, migration + rollback |
| Adversarial foundations | `docs/BUILD_PLAN.md` Track AB | `docs/architecture/masterplan-gap-audit.md` | P0 closure, fault injection, recovery, signed evidence |
| Exotic architecture laboratory | `docs/BUILD_PLAN.md` Track AC | `docs/architecture/exotic-architecture-lab.md` + research source catalog | reproduction, falsification, kill criteria, sandbox, staged graduation |
| Frontier research saturation | `docs/BUILD_PLAN.md` Track AD | `docs/architecture/frontier-research-atlas-2026.md` | source maturity, contradictions, reproduction, counterevidence, scale/system transfer |
| Deployment | deploy/resilience packages | build plan | canary + rollback + observability |
| Machine organization | `.machine/`, `machine/` | architecture index | deterministic inventory + drift checks |

## 5. Research source hierarchy

Skeleton treats source type and evidence maturity separately.

### Discovery sources

- arXiv;
- OpenReview;
- conference and workshop proceedings;
- ACL Anthology;
- ACM / IEEE / journal indexes;
- official model and system technical reports;
- reference implementations, model cards, benchmark repositories, and reproducibility reports.

arXiv and OpenReview are high-value discovery surfaces, but publication location alone does not establish truth or production readiness.

### Evidence maturity

| State | Meaning | Maximum architectural effect |
| --- | --- | --- |
| `foundational` | historically durable idea with broad downstream validation | may influence defaults |
| `replicated` | independently reproduced or strongly corroborated | candidate implementation |
| `frontier` | strong recent result with meaningful evidence | controlled candidate |
| `emerging` | promising new/pre-review result | experiment only |
| `mixed` | credible evidence disagrees | experiment + explicit uncertainty |
| `negative` | useful failure or null result | guardrail / test / rejection knowledge |
| `superseded` | replaced for current use | lineage/history only |

## 6. Research families currently mapped into the plan

The research manual maps these families to concrete Skeleton construction work:

- Transformer attention and sequence modeling;
- scaling laws and compute-optimal training;
- retrieval-augmented generation and retrieval-enhanced pretraining;
- state-space, hybrid, and mixture-of-experts model substrates;
- instruction tuning, preference optimization, reinforcement learning, and distillation;
- self-consistency, search, decomposition, and adaptive test-time compute;
- tool use and reasoning/action loops;
- long-context versus retrieval routing;
- paged KV-cache and memory-aware inference systems;
- verifier ensembles and verifier-failure analysis;
- software-agent and computer-use evaluation;
- prompt-injection resistance and instruction privilege;
- formal methods, property testing, fuzzing, and deterministic verification where appropriate.

These are implementation inputs, not frozen dependencies.

## 7. Research-to-production path

```text
DISCOVER
  -> NORMALIZE
  -> CLAIM / PROVENANCE EXTRACTION
  -> TRIAGE
  -> REPRODUCE
  -> PROTOTYPE
  -> BENCHMARK
  -> ABLATE
  -> ADVERSARIAL CHALLENGE
  -> SHADOW
  -> CANARY
  -> PROMOTE
  -> MONITOR
  -> REFRESH | ROLLBACK | SUPERSEDE | RETRACT
```

No source may skip from discovery directly to production.

## 8. Build-plan frontier

The current construction frontier is organized into Tracks Q–AD in [BUILD_PLAN.md](BUILD_PLAN.md):

- **Q** — research evidence substrate;
- **R** — model/training substrate;
- **S** — adaptive reasoning and test-time compute;
- **T** — context and hierarchical memory;
- **U** — tool authority and instruction security;
- **V** — inference and serving systems;
- **W** — controlled learning and post-training;
- **X** — evaluation, verification, and formal correctness;
- **Y** — experiment, promotion, rollback, and continuous scientific refresh;
- **Z** — deep internals and optimizer control plane;
- **AA** — rare massive upgrades and full-stack step changes;
- **AB** — adversarial foundations and systemic hardening;
- **AC** — exotic architecture laboratory;
- **AD** — research saturation, replication, and frontier synthesis.

The tracks are deliberately cross-linked. A model improvement is not finished until its serving, security, evaluation, provenance, and rollback consequences are accounted for.

## 9. Existing absorption architecture retained

Do not replace the current absorption work.

`sota-absorb-engine.md` already defines:

- durable intake;
- source-independent claim consensus;
- provenance and reliability calibration;
- challenge and contradiction handling;
- immutable snapshots;
- rollback;
- serving isolation.

`adaptive-absorption-fabric.md` already defines:

- FAST / DEEP / ADVERSARIAL / SPECULATIVE / REFRESH / GAP lanes;
- champion/challenger policy evolution;
- constitutional safety floors;
- Pareto evaluation;
- claim lifecycle;
- canary promotion.

The research evidence plane **specializes and feeds these mechanisms**. It does not create a second knowledge authority.

## 10. Completion rule

A SOTA claim in Skeleton must answer all of the following before promotion:

1. What concrete problem does it solve?
2. What is the strongest baseline?
3. What evidence supports it?
4. What evidence contradicts or limits it?
5. Can we reproduce the claimed effect?
6. Which subsystem and interface does it change?
7. What does the ablation show?
8. What are quality, latency, memory, throughput, cost, and security effects?
9. Does it preserve all frozen invariants?
10. Can it be rolled back without corrupting state?
11. What monitor detects regression after promotion?
12. When will the evidence be refreshed?

If these answers are missing, the item remains research or backlog, not architecture truth.


## 11. Deep internals and massive-upgrade authority

Tracks Z and AA extend the masterplan below the model API and across the full systems stack.

Track Z makes weight-update mechanics explicit architecture:

- stable optimizer baselines remain available permanently;
- optimizer state, precision, sharding, checkpointing, and migration are first-class contracts;
- parameter semantic classes may use different optimizers through one versioned \`ParameterOptimizationMap\`;
- structure-aware, curvature-aware, low-rank, sign, schedule-free, orthogonalized, and parameter-free optimizers are challenger families, not defaults by novelty;
- step telemetry and an optimization flight recorder preserve evidence around divergence and rare catastrophic updates;
- bounded counterfactual optimizer replay can compare alternate updates without mutating the authoritative training trajectory;
- numerical/stability circuit breakers preserve evidence before recovery;
- optimizer promotion requires equal-token and equal-wall-clock comparisons, scale transfer, checkpoint/resume, failure injection, downstream evaluation, and signed ADR evidence.

Track AA is the quarantine for unusually large architectural step changes:

- hardware-native sparse attention;
- hybrid attention/state-space/recurrent blocks;
- fine-grained/shared-expert MoE and expert parallelism;
- latent/compressed KV architectures;
- 100K→1M+ useful-context programs;
- FP8-first and experimental FP4 training;
- topology-aware 6D+ distributed training;
- communication/computation overlap and kernel autotuning;
- elastic training and asynchronous verified checkpointing;
- dynamic-depth inference;
- speculative/multi-token generation;
- disaggregated prefill/decode;
- multi-tier KV fabrics;
- cross-model distillation;
- architecture surgery/transplant;
- bounded optimizer/architecture co-search;
- quarantined learned optimizers.

A Track AA candidate is not promotable from a microbenchmark alone. It must carry model-quality, training, serving, memory, communication, reliability, migration, security, and rollback evidence.

### Mandatory accountability

Every Z/AA work item carries a stable ID, checkbox/status, created/updated timestamps, dependencies, evidence references, and mandatory signed acceptance for validated/promoted states. The signature binds the evidence/artifact digest. Rejected and superseded items remain in history as negative evidence.

Planning checkpoint:

\`\`\`text
PLAN-20260921-INTERNALS-OPTIMIZERS-MASSIVE-UPGRADES
created_at=2026-09-21T21:33:00+02:00
scope=Track Z + Track AA
implementation_claims_require_signed_evidence=true
\`\`\`


## 12. Hostile gap audit authority

The canonical adversarial review is [architecture/masterplan-gap-audit.md](architecture/masterplan-gap-audit.md).

Track AB exists because the frontier model/reasoning/optimizer plan did not, by itself, close several cross-cutting production risks. The hostile audit assigns stable gap IDs and makes the most dangerous omissions construction blockers.

P0 families include:

- representation/tokenizer identity;
- deterministic training-data lineage;
- unified model artifact identity;
- schema/state-compatible rollback;
- evaluation firewall and adaptive-overfitting controls;
- authenticated principal/tenant/delegation;
- execution containment;
- supply-chain trust;
- authoritative storage semantics;
- distributed leases/fencing/ordering;
- secret lifecycle;
- verified disaster recovery;
- control-plane isolation;
- immutable configuration identity;
- reconciliation for unknown side-effect outcomes;
- deletion/tombstone propagation;
- training poisoning/backdoor defense;
- safe artifact loading;
- tamper-evident authority audit;
- unified safe mode/break-glass recovery;
- root signing/trust key compromise, revocation, re-root and historical verification;
- deterministic invariant/policy precedence, recovery dependency cycles, dependency-reduced safe mode, internal service identity, and disaster-restore external-effect reconciliation.

No subsystem with an applicable open P0 gap may claim production-grade status.

The audit also defines a multi-axis fault campaign across state, network, worker, artifact/input, authority, resources and observability. P0 paths require single-axis testing; consequential side effects and promotion/rollback paths require pairwise and selected three-axis campaigns.

Planning checkpoint:

PLAN-20260921-HOSTILE-GAP-AUDIT
scope=G001..G200 + Track AB
production_readiness_blocked_by_applicable_open_P0=true


## 13. Exotic architecture authority

Track AC is a quarantined laboratory for architecture-changing ideas that challenge assumptions such as fixed tokenization, fixed depth, autoregressive decoding, dense activation, static inference-time model state, conventional precision, and modality-specific generation.

Evidence-backed frontier families include:

- Titans/MIRAS-style test-time neural memory;
- tokenizer-free dynamic byte-latent modeling;
- discrete diffusion and AR/diffusion hybrids;
- recurrent latent-depth reasoning;
- Universal YOCO-style efficient recursion;
- equilibrium/fixed-point language modules;
- Mixture-of-Depths conditional depth;
- differential/noise-canceling attention;
- native ternary/1.58-bit model families;
- fully sparse activation and Sparse-BitNet compounds;
- cross-layer shared sparse routing;
- latent multimodal language modeling;
- reversible blocks.

Track AC also keeps deliberately speculative lanes for fast weights, generated adapters, expert lifecycle changes, neural execution graphs, neuro-symbolic substrates, world models, graph-native computation, continuous-time/event-driven models, neuromorphic/analog hardware, error-correcting neural compute, explicit belief states, energy-based generation and bounded architecture search.

The authority rules are stricter than the research scope:

1. exotic architecture candidates cannot directly become production defaults;
2. each candidate declares a falsifiable hypothesis and kill criteria;
3. mutable inference-time neural state has owner/scope/TTL/reset semantics and is not trusted durable memory;
4. tentative diffusion/revision/speculative output is not committed output;
5. compound candidates require component-level ablation;
6. Track AB P0 invariants remain binding;
7. a candidate with real full-stack advantage graduates through Track AA rather than bypassing it.

Planning checkpoint:

PLAN-20260921-EXOTIC-ARCHITECTURE-LAB
scope=Track AC1..AC44
production_authority_granted=false
promotion_requires_track_ab_p0_closure=true


## 14. Frontier research saturation authority

The canonical dated synthesis is [architecture/frontier-research-atlas-2026.md](architecture/frontier-research-atlas-2026.md).

Track AD does not create a second research authority. It operationalizes Track Q by maintaining:

- scoped research conclusions;
- explicit confidence and source maturity;
- supporting and contradictory evidence;
- unresolved variables;
- local reproduction status;
- scale/hardware/system transfer;
- falsification conditions;
- open research debt;
- statistical/tuning-budget rigor;
- source-status freshness;
- next experiments and refresh dates.

The 2026-09-21 atlas currently defines:

- **FR001–FR144** — scoped research conclusions;
- **RQ001–RQ082** — unresolved frontier questions;
- **SV001–SV072** — verified source/status records;
- **FD001–FD031** — post-freeze frontier-delta findings;
- **CX001–CX024** — explicit research contradictions/tensions;
- **RDE001–RDE046** — local research-debt items;
- **RXP001–RXP062** — predeclared high-information local experiment protocols;
- **HL001–HL110** — historical cross-disciplinary research lineage anchors;
- **RS001–RS055** — research source families and archive/artifact topology;
- **RCB001–RCB120** — research control-plane implementation backlog;
- a staged experiment queue from foundational measurement through architecture, optimizer/data, reasoning, memory, agents, serving, safety, formal methods and interpretability.

Research conclusions are not production defaults. A conclusion can recommend a contract, baseline, experiment, watch state or negative guardrail. Architecture changes still require the normal experiment/ADR/shadow/canary path.

### Research source-status discipline

Skeleton preserves distinctions among:

- accepted/peer-reviewed;
- preprint;
- submission/ARR;
- withdrawn;
- official-organization evidence;
- unresolved status.

A status change is a new evidence event. It does not retroactively alter the exact evidence known to an earlier architecture decision.

### Research-debt discipline

A borrowed assumption remains visible until locally retired. A paper or external benchmark result alone cannot retire local research debt.

Debt can be:

```text
OPEN
EXPERIMENT_DESIGNED
RUNNING
EVIDENCE_COLLECTED
CHALLENGED
RETIRED
PARTIALLY_RETIRED
INVALIDATED
DEFERRED
```

Retirement records exact task/model/hardware/scale scope and can reopen after material changes.

### Research-rigor discipline

Consequential comparisons report:

- tuning/selection budget;
- failed/diverged runs;
- variance or explicit uncertainty;
- multiple-comparison/search pressure;
- baseline parity;
- lifecycle cost;
- untested/external-validity dimensions.

Planning checkpoint:

```text
PLAN-20260921-FRONTIER-RESEARCH-SATURATION
track=AD
research_conclusions=FR001..FR144
research_questions=RQ001..RQ082
source_verifications=SV001..SV072
frontier_delta=FD001..FD031
contradictions=CX001..CX024
research_debt=RDE001..RDE046
experiment_protocols=RXP001..RXP062
production_authority_granted=false
research_refresh_required=true
```


### Track AD accountability checkpoint

Planning coverage and local reproduction are separate states. The current checkpoint records all 24 research domains as planning-covered while local reproduction remains pending.

```text
PLAN-20260921-RESEARCH-SATURATION-ACCOUNTABILITY
domain_count=24
planning_status=PLANNING_COVERED
local_reproduction_status=REPRODUCTION_PENDING
production_authority_granted=false
signoff_required_for_reproduction_claims=true
signoff_required_for_production_claims=true
```
