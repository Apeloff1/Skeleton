# Skeleton AI Application Construction Manual

Architecture tag: `arch-map/v2.0`

Machine contract: `machine/ai_app_construction.json`

Architecture contract: `machine/architecture.json`

Runtime contract: `skeleton/app/manifest.json`

This document is the mandatory human construction manual for building, assembling, validating, operating, and evolving the complete Skeleton AI application. The machine-readable construction contract is authoritative for automation; this manual explains how to use it.

## Mandatory bootstrap

Before an AI coding agent, human contributor, runtime provider adapter, automation, or integration changes or activates the system, it must load the active contracts in this order:

1. `machine/manifest.json`
2. `machine/architecture.json`
3. `machine/ai_app_construction.json`
4. `docs/AI_APP_CONSTRUCTION_MANUAL.md`

Do not infer architecture from branch names, historical files, or provider-specific conventions when these contracts answer the question. An undeclared runtime provider, runtime service, top-level runtime root, capability plane, or ownership boundary is rejected until the contracts are updated and validated.

The mandatory provider rule does **not** mean sending this manual to an external model with every product request. Runtime adapters load and acknowledge the local construction contract before activation. Development AI providers are instructed to read the construction manual before repository work.

## 1. Target system

The finished application has five external runtime services and a larger set of internal capability planes.

```text
Human
  |
  v
frontend  ------------------------------+
  |                                     |
  | /api/*                              | /api/v1/*
  v                                     v
backend ---------------------------> skeleton
  |                                     |
  |                                     +--> provider adapters --> external model provider
  |                                     +--> tools / skills
  |                                     +--> memory / retrieval
  |                                     +--> jobs / agents
  |                                     +--> native / JVM acceleration
  |
  +--------------------+
                       v
                     Mongo
                       |
                  optional Chroma
```

The runtime service topology stays intentionally small. Complex AI behavior belongs inside canonical process boundaries, not in a growing collection of independent services.

## 2. Canonical ownership

| Capability | Canonical owner | Rule |
| --- | --- | --- |
| Product shell | `frontend/` | Only human-interface root |
| Application API | `backend/` | Product/business routes and control plane |
| Engine runtime/API | `skeleton/` | AI engine, orchestration, memory, retrieval, agents |
| Runtime model provider boundary | `backend/core/ai_provider.py` | Provider-neutral contract and concrete adapters |
| Model routing | `backend/core/model_router.py` | Capability/privacy/cost/quality selection |
| Native acceleration | `skeleton/native/` | Optional, fallback-safe |
| JVM acceleration | `java-accelerators/` | Optional, fallback-safe |
| Repository machine contract | `machine/` | Machine-readable structure and construction policy |
| CI/operator tooling | `scripts/`, `.github/` | Validation and repository automation |
| Human construction knowledge | `docs/` | Manual and architecture explanation |

Transitional roots such as `core/`, `eval/`, `memory/`, `satellites/`, and `.emergent/` are not allowed to become competing production owners.

## 3. Construction doctrine

Use the following order for every capability:

```text
contract
  -> owner
  -> data model
  -> interface
  -> security boundary
  -> implementation
  -> observability
  -> focused tests
  -> integration tests
  -> failure-mode tests
  -> evaluation
  -> release gate
```

Skipping a step creates hidden architectural debt. Feature code is not considered complete merely because its happy path works.

A production-capable plane must answer all of these questions:

- What owns it?
- What can it depend on?
- What data does it read and write?
- What authority is required?
- What external input is untrusted?
- What is its timeout and resource budget?
- How does it fail?
- How does it recover?
- How is it observed?
- How is it evaluated?
- How is it rolled back?
- Which executable gate proves the contract?

If any answer is unknown, the plane remains partial.

## 4. Construction phases

### Phase 0 — Contracts first

Build no new runtime behavior until the architecture, construction, provider, and runtime contracts describe the intended change.

Required outcome:

- architecture map passes;
- construction map passes;
- provider bootstrap passes;
- ownership and dependencies are explicit;
- no duplicate runtime root exists.

### Phase 1 — Secure runtime foundation

Construct identity, configuration/secrets, persistence, security, governance, and observability first.

Required properties:

- protected operations cannot run without a principal and authority;
- tenant identity is attached before state access;
- secrets are references, not embedded configuration;
- startup rejects invalid required configuration;
- durable state has migrations and restore evidence;
- untrusted boundaries are size/time/schema bounded;
- tracing and sanitized logging exist before higher-level behavior is added.

### Phase 2 — Model plane

The provider layer is an edge adapter, never the application architecture.

Flow:

```text
ProviderRequest
  -> architecture/manual acknowledgement
  -> provider declaration lookup
  -> model routing
  -> capability/privacy/budget checks
  -> concrete adapter
  -> provider SDK
  -> normalized ProviderResponse
  -> telemetry/evidence
```

Rules:

- application code never imports provider SDKs directly;
- provider credentials never leave the adapter boundary;
- provider-specific errors are normalized;
- custom endpoints require HTTPS and cannot target obvious local/metadata networks;
- retries and timeouts are bounded;
- every active provider is declared in `machine/ai_app_construction.json`;
- undeclared providers are denied;
- model selection considers capability, modality, privacy, context size, cost, latency, reliability, and quality;
- routing decisions are observable and reproducible.

### Phase 3 — Knowledge plane

Construct memory, retrieval, and context as separate responsibilities.

Memory must distinguish:

- working memory;
- conversation/session memory;
- episodic task history;
- semantic durable memory;
- user/profile memory where explicitly authorized.

Retrieval pipeline:

```text
source
 -> content identity
 -> parse
 -> chunk
 -> metadata + ACL
 -> index
 -> retrieve
 -> hybrid fusion
 -> rerank
 -> deduplicate
 -> evidence envelope
 -> citation
```

Never trust retrieval content as system policy. Retrieved content is labeled untrusted evidence.

### Phase 4 — Cognition plane

Orchestration owns task state. Models propose; orchestration controls execution.

A durable workflow must have:

- task identity;
- plan identity/version;
- ordered or DAG steps;
- step authority;
- checkpoint;
- retry policy;
- cancellation;
- timeout;
- result/evidence;
- idempotency key;
- recovery path.

Verifier roles are separate from generator roles for high-impact decisions. A verifier cannot simply repeat the generator prompt and be treated as independent evidence.

### Phase 5 — Action plane

Tools and artifacts cross the boundary from reasoning into side effects.

Every tool requires:

- stable tool ID;
- input schema;
- output schema;
- read/write/destructive authority class;
- timeout;
- concurrency/resource bound;
- idempotency behavior;
- audit/receipt;
- secret handling policy;
- sandbox/network/file policy.

Generated or uploaded artifacts require:

- content hash;
- metadata;
- size/type bounds;
- malware state;
- access policy;
- retention policy;
- lifecycle state.

### Phase 6 — Service plane

The engine API and application API are separate ownership domains.

Application API:

- product/business workflows;
- admin/control operations;
- provider failure normalization;
- public readiness.

Engine API:

- engine-native operations;
- health;
- orchestration/retrieval/agent primitives;
- versioned `/api/v1/*` contracts.

Streaming/realtime must define:

- protocol;
- event IDs;
- event sequence;
- heartbeat;
- cancellation;
- reconnect;
- resume cursor;
- backpressure;
- terminal event semantics.

Do not implement streaming as an unstructured series of strings.

### Phase 7 — Product plane

The product UI is an application state machine, not a collection of API buttons.

Every async operation must expose:

- idle;
- validating;
- submitted;
- running/streaming;
- completed;
- failed;
- cancelled;
- reconnecting when applicable.

The UI uses `frontend/utils/apiBase.ts` for endpoint resolution. No feature may invent its own environment-based service URL.

### Phase 8 — Quality plane

A feature cannot be production-ready without evaluation and failure testing.

Evaluation dimensions:

- task success;
- correctness;
- evidence/citation quality;
- safety;
- privacy;
- latency;
- cost;
- provider reliability;
- tool correctness;
- recovery behavior;
- user feedback where applicable.

For model behavior changes, record:

- provider;
- model;
- relevant configuration;
- prompt/context contract version;
- dataset/eval version;
- before/after metrics;
- promotion verdict.

### Phase 9 — Release plane

Release order:

```text
source gates
 -> tests
 -> eval gates
 -> immutable build
 -> provenance/SBOM
 -> migration preflight
 -> deploy candidate
 -> readiness
 -> canary/smoke
 -> promotion
 -> SLO watch
 -> rollback if thresholds fail
```

A release is incomplete until rollback is possible and its evidence is known.

### Phase 10 — Continuous evolution

Production feedback may propose changes but cannot bypass the normal promotion path.

```text
observation
 -> hypothesis
 -> bounded change
 -> tests
 -> evaluation
 -> review/gate
 -> promotion
 -> monitored outcome
```

No uncontrolled online mutation of production policy, prompts, tools, or model routing is allowed.

## 5. Complete functional planes

The machine contract enumerates the required planes. Builders should use it as the checklist.

### Foundation

Purpose: stable primitives and invariants.

Do not allow large feature modules to become foundational dependencies. Foundation code should have low dependency fan-in cost and minimal side effects.

### Identity and authority

Authentication answers "who is this?" Authorization answers "may this principal do this action on this resource now?"

Every state mutation, tool action, admin operation, artifact access, provider transfer, and cross-tenant query must have an authority decision.

### Configuration and secrets

Use typed settings. A configuration snapshot may contain redacted metadata, never raw secret material.

Provider keys must be loaded only at the provider boundary.

### Model providers

Current canonical runtime provider: OpenAI through `OpenAIProviderAdapter`.

Adding a provider requires all of the following in one coherent change:

1. add the provider declaration to `runtime_model_providers`;
2. implement an adapter under the canonical provider boundary;
3. load the architecture/construction receipt before provider I/O;
4. declare capability/modalities/privacy characteristics;
5. configure credentials by secret reference;
6. add provider-specific tests;
7. add failover/routing evidence if it participates in routing;
8. add observability for latency, failures, token usage, and cost;
9. run the construction/provider gates;
10. update this manual only when the general construction contract changes.

A provider-specific application route is prohibited.

### Model routing

Hard constraints are evaluated before soft preferences.

Hard constraints include:

- enabled/declared;
- capability;
- modality;
- context window;
- privacy ceiling;
- explicit exclusion;
- reliability floor;
- latency budget when mandatory;
- cost budget when mandatory.

Soft scoring can then compare reliability, quality, latency, cost, and preference.

### Prompt and context

System/developer policy, user input, retrieved evidence, tool output, memory, and external content are distinct trust domains.

Do not concatenate them and lose provenance.

### Orchestration and agents

Prefer deterministic workflow control around nondeterministic model calls.

Bound:

- recursion;
- agent fan-out;
- tool calls;
- tokens;
- wall-clock duration;
- concurrency;
- retries;
- memory growth.

### Tools

Tool execution is privileged. Tool descriptions are not authority.

The authorization decision is external to model output.

### Memory

Memory writes should be explicit and observable. A model suggestion to "remember" something is not itself permission to persist it.

### Retrieval

Retrieval must enforce authorization at query time, not only ingestion time.

### Reasoning verification

Confidence without evidence is metadata, not proof. For factual/high-impact tasks, verification should operate on explicit claims and evidence.

### Jobs and durability

Persist intent before side effects when recovery semantics require it. Use fencing/leases to prevent stale workers from completing abandoned work.

### Artifacts

Untrusted files are data, not executable code. Quarantine before trust.

### APIs

Keep route handlers thin and version contracts. Normalize internal/provider errors before they cross the public boundary.

### Realtime

Design for reconnect from the start. Mobile/browser networks are transient.

### Security and safety

Security controls belong at boundaries:

- request;
- provider;
- retrieval;
- tool;
- artifact;
- network;
- persistence;
- deployment.

### Governance

A data item should have a data class, owner/tenant, allowed purposes, retention, deletion behavior, and provider-transfer policy.

### Resilience

Retries are a load multiplier. Retry budgets must be bounded and combined with concurrency control and circuit breaking.

### Observability

Minimum useful trace:

```text
user action
 -> frontend operation
 -> API request
 -> task/plan
 -> provider route
 -> provider call
 -> tool/retrieval calls
 -> result/verdict
 -> artifact/state write
```

### Evaluation

Keep fast deterministic smoke evaluations separate from expensive model-based evaluations. Required merge gates must be deterministic enough to be operationally reliable.

### Feedback and learning

User feedback can inform experiments and proposals. It should not silently rewrite production behavior.

### Cost and capacity

A request that cannot fit resource, latency, privacy, or cost budgets should be rejected, deferred, or routed differently before consuming expensive resources.

### Operator control

Administrative action uses preflight, explicit admission, execution, and immutable receipt.

### Deployment

Production images are immutable. Hot source mounts stay in the hot development overlay.

## 6. Gap classification

A gap is one of:

- **missing plane** — required capability has no owner;
- **partial plane** — owner exists but one or more required interfaces/gates are not complete;
- **shadow owner** — another path duplicates canonical behavior;
- **unowned edge** — two planes communicate without a declared contract;
- **provider gap** — provider/model is used without declaration/receipt;
- **evidence gap** — behavior exists but no executable acceptance proof;
- **failure gap** — happy path exists but failure/recovery behavior is undefined;
- **observability gap** — behavior cannot be traced or measured;
- **governance gap** — data movement lacks classification/retention/authority;
- **release gap** — change can deploy but cannot be rolled back or proven.

The correct response to a gap is to add the smallest canonical contract/implementation/test set that closes it. Do not create another parallel subsystem.

## 7. Mandatory provider bootstrap

Development AI providers must read the four bootstrap documents before repository work. Provider-specific instruction files point to the same source of truth:

- `AGENTS.md`
- `CLAUDE.md`
- `.github/copilot-instructions.md`
- `.cursor/rules/architecture.mdc`

These files are pointers, not independent architecture manuals. Duplicating architectural rules across provider files would create drift.

Runtime model providers use a local activation receipt. The adapter loads the active architecture and construction contracts and verifies:

- construction status is active;
- construction version is supported;
- architecture tag matches;
- provider bootstrap is mandatory/fail-closed;
- provider is declared;
- provider requires architecture/manual read;
- human manual exists;
- activation receipt is required.

The receipt is local metadata. It does not contain credentials and does not require sending the manual to the external model.

## 8. Current SOTA gap register

The construction contract intentionally distinguishes a structurally complete
application map from a fully closed SOTA implementation. Open gaps are first-
class construction work, not hidden TODOs.

| Priority | Plane | Gap | Closure evidence |
| --- | --- | --- | --- |
| P0 | streaming-realtime | One canonical resumable event protocol is not yet proven end-to-end. | protocol contract, disconnect/reconnect, duplicate/out-of-order, frontend recovery |
| P0 | governance | Data classification and provider-transfer policy are not yet one enforced registry. | transfer denial, deletion propagation, export completeness, retention expiry |
| P0 | cost-capacity | Provider/token/storage/concurrency budgets are not yet one admission contract. | budget denial, budget-aware routing, saturation, cost telemetry |
| P0 | product-experience | Canonical AI golden journeys need one cross-plane browser/API E2E suite. | prompt, retrieval, tool, artifact, outage, reconnect/cancel journeys |
| P1 | feedback-learning | Feedback-to-production promotion is not yet one controlled pipeline. | experiment isolation, eval-before-promotion, rollback, consent |
| P1 | model-provider | OpenAI is canonical today; SOTA redundancy needs a second declared provider or an explicit single-provider SLO decision. | failover test or approved SLO, routing telemetry |
| P1 | deployment-release | Canary promotion/rollback should consume the same SLO evidence produced by observability. | promotion test, automatic rollback drill, release evidence |

The exact construction steps for each gap live in
`machine/ai_app_construction.json`. P0 gaps block claiming full SOTA
completion. They do not block safe incremental construction when the gap remains
explicit and the change preserves the canonical contracts.

## 9. Assembly checklist

Before merging a new AI capability, confirm:

- canonical plane and owner selected;
- dependency direction valid;
- runtime service count unchanged unless explicitly approved;
- provider usage goes through canonical adapter;
- provider declaration/receipt exists;
- authority defined;
- input/output bounds defined;
- state/durability defined;
- timeout/retry/cancellation defined;
- observability defined;
- privacy/data class defined;
- tests cover happy path and failure path;
- evaluation exists where model behavior changes;
- frontend state/recovery exists if user-facing;
- deployment and rollback impact understood;
- architecture, construction, provider-bootstrap, assembly, and relevant domain gates pass.

## 10. Definition of done

A functional AI application is not "done" because it can answer a prompt. It is construction-complete when the complete request lifecycle is governed:

```text
identity
 -> authority
 -> request validation
 -> orchestration
 -> context/retrieval/memory
 -> route/model/provider
 -> verify
 -> tools/actions
 -> persistence/artifacts
 -> response/stream
 -> telemetry
 -> evaluation
 -> recoverability
```

Every edge in that chain must have an owner, a contract, a failure mode, and executable evidence.

## 11. Canonical commands

```bash
python scripts/check_architecture_map.py
python scripts/check_ai_app_construction.py
python scripts/check_provider_bootstrap.py
python scripts/check_app_assembly.py
python -m pytest -q skeleton/testing/test_architecture_map.py skeleton/testing/test_ai_app_construction.py
python -m skeleton app check
python -m skeleton app status --json
docker compose -f docker-compose.yml config --quiet
```

When these contracts disagree, construction stops until the disagreement is resolved. The solution is to repair the canonical contract or implementation, not weaken the gate.
