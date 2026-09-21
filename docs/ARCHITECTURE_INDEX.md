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
6. **Knowledge absorption and promotion mechanics** — [architecture/sota-absorb-engine.md](architecture/sota-absorb-engine.md) and [architecture/adaptive-absorption-fabric.md](architecture/adaptive-absorption-fabric.md).
7. **Historical architecture rounds** — `skeleton/architecture_round3.py` through `skeleton/architecture_round22.py`.

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

The current construction frontier is organized into Tracks Q–Y in [BUILD_PLAN.md](BUILD_PLAN.md):

- **Q** — research evidence substrate;
- **R** — model/training substrate;
- **S** — adaptive reasoning and test-time compute;
- **T** — context and hierarchical memory;
- **U** — tool authority and instruction security;
- **V** — inference and serving systems;
- **W** — controlled learning and post-training;
- **X** — evaluation, verification, and formal correctness;
- **Y** — experiment, promotion, rollback, and continuous scientific refresh.

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
