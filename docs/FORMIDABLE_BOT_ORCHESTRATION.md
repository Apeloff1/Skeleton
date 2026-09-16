# Formidable Bot Orchestration

This document records the operating architecture for Skeleton's autonomous Night, Idle, and Studio bot systems.

## Core invariant

One canonical Supervisor plan controls executable work. Normal engineering work is delegated as one task to one four-agent squad:

1. **Researcher** — repository/external evidence, dependencies, contracts, integration risks.
2. **Lead implementer** — sole normal implementation owner for the task.
3. **Adversarial reviewer** — independent challenge of correctness, compatibility, security, and scope.
4. **Verifier** — acceptance evidence, tests, integration checks, security gates, and benchmarks when relevant.

A spare worker never joins an active task as an informal fifth member. A second squad never implements the same ordinary task unless the canonical plan explicitly creates a competing experiment.

## Why this architecture

Production multi-agent systems generally benefit from a central manager when one component must retain workflow control, specialized agents with narrow instructions/tools, layered guardrails, tracing, evaluation, and explicit termination conditions. Skeleton adopts those useful patterns but keeps executable authority in deterministic repository code rather than model-to-model peer handoffs.

The result is:

- centralized intent;
- decentralized bounded execution;
- deterministic task/squad leases;
- explicit role separation;
- conflict-domain exclusion;
- dependency-aware scheduling;
- evidence-based completion;
- durable failure history;
- versioned prompt contracts and regression evals.

## Capacity

The theoretical maximum number of active squads is `eligible_workers // 4`.

That is only an upper bound. The Shift Manager may recommend less concurrency when CI, PR review, model-call budget, repository conflict probability, overtime, blocked work, or validation pressure makes additional work unsafe or counterproductive.

The objective is **verified throughput**, not worker utilization.

## Plan task contract

New Supervisor/Secretary tasks should carry:

- stable `task_key`;
- title and concrete objective;
- target team;
- priority and task type;
- dependencies;
- conflict domain;
- relevant repository paths;
- expected output;
- acceptance criteria;
- validation requirements;
- security considerations;
- performance considerations;
- research references and rationale.

Dependencies produced inside one model response are translated to canonical plan IDs before execution. Unresolvable dependencies fail closed rather than being silently ignored.

## Anti-swarm lease

A squad lease binds:

- task ID;
- squad ID;
- plan generation;
- lease generation;
- four distinct role-to-worker assignments;
- conflict domain;
- start time;
- expiry time.

The assignment of the task and all four workers is atomic. Expired leases return work to the canonical queue and preserve a bounded lease history so failure evidence is not erased.

## Completion

A normal task cannot be marked done merely because the lead says it is done. Completion requires durable evidence for:

- research/integration completion;
- implementation completion;
- reviewer approval;
- verifier approval.

Repository CI and deterministic security/policy gates remain authoritative after model review.

## Inspiration, adapted rather than copied

The architecture intentionally borrows broad production lessons from modern agent systems:

- **OpenAI Agents / manager pattern:** central orchestration, specialist agents, guardrails, tracing and evals.
- **Graph-style supervisors:** explicit dependencies and bounded parallel execution rather than unrestricted handoffs.
- **Agent-team frameworks:** explicit stop conditions and resource budgets to prevent endless conversational loops.

Skeleton goes further for this repository by making task ownership, squad size, conflict exclusion, plan generation, failure durability, and completion evidence deterministic instead of relying on prompt compliance alone.

## Rule of thumb

If four agents disagree, do not summon more agents to vote. Identify the disputed fact and resolve it with the smallest useful repository inspection, test, experiment, benchmark, or authoritative source.

**One plan. One task. One squad. Four responsibilities. Evidence decides completion.**
