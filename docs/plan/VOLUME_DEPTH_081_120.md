# Volume Depth Pass 081–120

Architecture lane: `plan/volume-depth-041-080-20260922`

Machine authority: [`machine/ai_master_plan.json`](../../machine/ai_master_plan.json)

Depth pass: **DP-081-120 — Formal-methods-to-final-assembly depth**

This pass continues the frozen masterplan sequentially from DP-041-080. It converts VOL-081 through VOL-120 from title-only scope markers into buildable planning records without claiming implementation or verification.

| Volume | Domain | Primary build intent | Key acceptance pressure |
| --- | --- | --- | --- |
| VOL-081 | Formal Methods | Apply formal specification selectively to high-risk invariants, protocols and state transitions. | specification diverges from code; state-space explosion |
| VOL-082 | Benchmark Lab | Run reproducible benchmark comparisons with strong baselines, contamination controls and cost/latency context. | benchmark leakage; leaderboard optimization replaces product quality |
| VOL-083 | Red Team | Continuously attack authority, data, tool, model and recovery boundaries under controlled conditions. | red-team payload escapes sandbox; findings do not become regression tests |
| VOL-084 | Human Control | Preserve meaningful human authority over consequential, long-running and autonomous operations. | override arrives too late; automation can bypass approval |
| VOL-085 | Explainability | Expose evidence-backed reasons, provenance and uncertainty without inventing unverifiable internal narratives. | plausible explanation not faithful; sensitive data leaks through traces |
| VOL-086 | Accessibility | Make all critical product and operator flows usable with assistive technology and reduced sensory/motor load. | critical controls inaccessible; visual-only state hides failures |
| VOL-087 | Internationalization | Separate locale-sensitive presentation from canonical data, identifiers and protocol semantics. | locale changes machine meaning; untranslated critical warning |
| VOL-088 | Compliance & Legal Engineering | Translate applicable obligations into scoped engineering controls, evidence and reviewable decisions. | legal claim encoded as universal rule; compliance evidence incomplete |
| VOL-089 | Documentation Engine | Generate and validate maintainable human documentation from authoritative machine contracts plus curated narrative. | docs drift from runtime; generated content overwrites human rationale |
| VOL-090 | Generated Documentation | Publish generated API, schema, topology and capability views with reproducible source identity. | generated docs treated as authority after source changes; nondeterministic output churn |
| VOL-091 | Operations Manual | Maintain executable runbooks for startup, shutdown, degradation, recovery, rollback and incident handling. | runbook assumes unavailable dependency; operator steps contradict automation |
| VOL-092 | Repository Maintenance | Keep repository health bounded through cleanup, dependency upkeep, generated-file control and ownership hygiene. | maintenance bots create churn; cleanup removes live compatibility path |
| VOL-093 | Backlog Control | Maintain one deduplicated, dependency-aware queue of actionable work tied to gaps, risks and evidence. | duplicate tasks inflate progress; stale tasks survive closed gaps |
| VOL-094 | Priority Engine | Prioritize work from dependency, severity, value, cost, evidence and blocking impact without allowing self-serving metric gaming. | easy tasks crowd out critical blockers; priority score hides hard constraints |
| VOL-095 | Build Work Packages | Turn architecture requirements into bounded implementation packets with owners, dependencies, tests and evidence obligations. | packages too broad to verify; package completion bypasses atomic tasks |
| VOL-096 | VS-000 Foundation Recovery Slice | Prove install/boot/persist/event/shutdown/restart/recovery before higher AI behavior is trusted. | happy-path boot passes while recovery corrupts state |
| VOL-097 | VS-001 Functional AI | Prove one complete user AI operation across context, memory/retrieval, model routing, governed tools, verification, commit and streaming. | components pass independently but end-to-end authority breaks |
| VOL-098 | VS-002 Engineering Agent | Prove repository inspect→plan→lease→edit→build→test→review→verify with rollback and custody. | agent edits outside lease; test gaming passes bad change |
| VOL-099 | VS-003 Scientific Researcher | Prove source acquisition, evidence graph, reproduction, experiment and conclusion with uncertainty and lineage. | citation exists without supporting claim; reproduction silently changes method |
| VOL-100 | VS-004 Multi-Agent Engineering | Prove multiple bounded agents can collaborate on one engineering objective without authority amplification or conflict corruption. | child authority exceeds parent; concurrent edits silently overwrite |
| VOL-101 | VS-005 Self-Improvement | Prove candidate self-improvement remains sandboxed, benchmarked and independently promoted or rejected. | candidate mutates champion directly; benchmark gaming drives promotion |
| VOL-102 | VS-006 Distributed Execution | Prove distributed workers/inference survive partition, retry, failover and stale leases without duplicated effects. | split brain executes action twice; failover loses authoritative state |
| VOL-103 | VS-007 Desktop Product | Prove clean-machine desktop install→operation→artifact→restart→update→rollback as one release flow. | installer succeeds but app cannot operate; update breaks stored state |
| VOL-104 | Acceptance: Functional AI | Define the evidence threshold for claiming a usable end-to-end AI capability. | demo success mistaken for acceptance; missing degraded/failure evidence |
| VOL-105 | Acceptance: Autonomous AI Worker | Define evidence required before autonomous long-running work is trusted. | autonomy works only under supervision; hidden budget/authority creep |
| VOL-106 | Acceptance: Research System | Define evidence required before research outputs can be treated as a reliable system capability. | citation count substitutes for evidence quality; irreproducible conclusions |
| VOL-107 | Acceptance: SOTA Candidate | Define a conservative, reproducible gate for describing a capability as a state-of-the-art candidate. | benchmark win over weak baseline becomes SOTA claim |
| VOL-108 | Anti-Patterns | Maintain an executable catalogue of architectural and operational patterns that repeatedly create hidden failure. | anti-pattern list becomes prose only; exceptions spread silently |
| VOL-109 | Build Order | Encode dependency-safe construction order while allowing controlled parallelism. | parallel work solidifies against unstable contract; hidden cyclic dependency |
| VOL-110 | Definition of Done | Make completion a cumulative evidence contract, not a subjective status label. | merged code marked done without recovery/security/operations proof |
| VOL-111 | Full Construction Manual Format | Standardize the build packet handed to humans and agents so implementation context is complete and reviewable. | critical context omitted during delegation; manual duplicates machine truth inconsistently |
| VOL-112 | Master Traceability Matrix | Maintain requirement→component→contract→implementation→test→evidence→promotion lineage. | orphan code/evidence; one requirement mapped to obsolete implementation |
| VOL-113 | Capability Map | Represent available, planned, degraded and retired capabilities with owner, contracts and evidence. | capability exists in code but not discoverable; planned capability advertised as live |
| VOL-114 | Technology Radar | Track technologies as adopt/experiment/watch/retire decisions with evidence and exit criteria. | novelty drives production adoption; experimental dependency becomes permanent |
| VOL-115 | Technical Debt Ledger | Track debt as explicit cost/risk with owner, interest signal and retirement condition. | debt becomes permanent label; cleanup breaks compatibility unknowingly |
| VOL-116 | Architecture Fitness Functions | Continuously test structural invariants so architecture erosion fails early. | fitness test encodes obsolete structure; exemptions become architecture |
| VOL-117 | Project Metrics | Measure delivery, quality, reliability and evidence health without turning metrics into completion authority. | metric optimization hides real risk; vanity progress percentages |
| VOL-118 | Roadmap Control | Maintain roadmap sequencing from dependencies, risk, capacity and evidence rather than static dates. | roadmap ignores blockers; scope creep bypasses breadth freeze |
| VOL-119 | Completion Model | Compute completion from atomic implementation, verification and evidence state across tasks, packages, slices and maturity. | manual percentages disagree with actual signed work; aggregate hides critical open item |
| VOL-120 | Final Assembly Test | Qualify the assembled product across clean install, functional AI, autonomous work, recovery, update/rollback and release evidence. | component greens mask integration failure; release qualification omits real clean-machine path |

## Sequential dependency spine

```text
VOL-081 formal methods
  -> VOL-082..088 benchmark/red-team/human-control/explainability/accessibility/i18n/compliance
  -> VOL-089..094 documentation/operations/repository/backlog/priority
  -> VOL-095 build work packages
  -> VOL-096..103 VS-000 through VS-007
  -> VOL-104..107 acceptance gates
  -> VOL-108..116 anti-patterns/build-order/DoD/manual/trace/capability/radar/debt/fitness
  -> VOL-117..119 metrics/roadmap/completion
  -> VOL-120 final assembly qualification
```

## Acceptance law

This tranche is where planning becomes explicitly qualification-oriented. It still does not manufacture evidence.

- formal proof is scoped to its assumptions and implementation binding;
- benchmark wins cannot substitute for credible baselines, robustness and contamination analysis;
- red-team findings must become tracked fixes and regression evidence;
- human override and revocation remain authoritative over delegated automation;
- generated explanations/documentation cannot outrank canonical runtime or machine contracts;
- accessibility, internationalization and compliance obligations are release concerns where applicable;
- vertical slices must prove cross-component behavior, not simply aggregate unit-test greens;
- SOTA language remains a reproducible scoped candidate claim, not an architectural status;
- work-package, roadmap and completion percentages derive from signed atomic evidence;
- final assembly promotion requires digest-bound release evidence and independent verification.

## Depth law

Every VOL-081..VOL-120 record now has non-empty requirements, capabilities, contracts, implementation paths, tests, evaluations, risks and gaps. `planned:` references are construction intent only. Maturity remains governed by the existing signed accountability, engineering and adversarial-closure contracts.

## Remaining work after DP-081-120

- continue sequentially with **DP-121-160**;
- bind newly deepened acceptance and governance volumes to exact W/AIQ/evidence owners;
- materialize the VS-000..VS-007 acceptance harnesses rather than treating their planned paths as proof;
- converge completion/roadmap/project metrics on the signed atomic accountability source;
- keep breadth frozen at VOL-420 while increasing implementation depth.
