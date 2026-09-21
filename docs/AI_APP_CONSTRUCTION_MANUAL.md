# Skeleton AI Application Construction Manual

Architecture tag: `arch-map/v3.4`

Machine contract: `machine/ai_app_construction.json`

Construction version: `3.4.0`

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
- `GEMINI.md`

Grok and other coding agents without a dedicated repository instruction format use
`AGENTS.md` as the generic bootstrap entrypoint.

These files are pointers, not independent architecture manuals. Duplicating architectural rules across provider files would create drift.

All credential-bearing AI provider families use a local activation receipt from
`skeleton/provider_contract.py`. Product runtime providers use the
`runtime_model` family; repository automation uses the `automation_model`
family. `backend/core/provider_architecture.py` is only a compatibility
re-export.

The shared loader verifies:

- construction status is active;
- construction version is supported;
- architecture tag matches;
- provider bootstrap is mandatory/fail-closed;
- provider is declared;
- provider requires architecture/manual read;
- human manual exists;
- activation receipt is required.

The receipt is local metadata. It does not contain credentials and does not require sending the manual to the external model.

## 8. Current-state execution roadmap

The generic construction phases describe how to build the system from zero. The
current repository is already partially assembled, so active work follows this
gap-closure roadmap:

```text
Wave 1  policy + provider + budget foundation
        ├─ provider-surface convergence
        ├─ governance registry
        └─ cost/capacity admission
             |
             v
Wave 2  realtime + provider resilience
        ├─ resumable event protocol
        └─ provider redundancy / explicit single-provider SLO
             |
             v
Wave 3  golden journey integration
        └─ prompt + retrieval + tools + artifacts + outage + reconnect E2E
             |
             v
Wave 4  controlled learning + release control
        ├─ feedback/eval/promotion pipeline
        └─ canary SLO promotion + automatic rollback
             |
             v
Wave 5  SOTA closure
        └─ zero P0 gaps + all gates + chaos/eval/release evidence
```

Wave 1 tracks can proceed in parallel. Wave 2 starts only after data-transfer
policy and admission budgets are enforceable. The golden E2E suite comes after
realtime/provider failure semantics are stable; otherwise it would encode
temporary behavior. Learning and automated release promotion come last because
they must consume trustworthy evaluation and operational evidence.

The machine-readable source for this sequence is
`execution_roadmap` in `machine/ai_app_construction.json`. Every open gap must
appear exactly once before SOTA closure.

## 9. Current SOTA gap register

The construction contract intentionally distinguishes a structurally complete
application map from a fully closed SOTA implementation. Open gaps are first-
class construction work, not hidden TODOs.

| Priority | Plane | Gap | Closure evidence |
| --- | --- | --- | --- |
| P0 | model-provider | Provider transport/credentials are structurally centralized; current-head CI still must prove repository-wide discovery and SDK isolation before closure. | shared receipt, text/image/speech convergence, undeclared-provider denial, provider-surface inventory, SDK isolation |
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

## 10. Assembly checklist

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

## 11. Definition of done

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

## 12. Canonical commands

```bash
python scripts/check_architecture_map.py
python scripts/check_ai_app_construction.py
python scripts/check_provider_bootstrap.py
python scripts/check_app_assembly.py
python -m pytest -q skeleton/testing/test_architecture_map.py skeleton/testing/test_ai_app_construction.py skeleton/testing/test_provider_contract.py
python -m skeleton app check
python -m skeleton app status --json
docker compose -f docker-compose.yml config --quiet
```

When these contracts disagree, construction stops until the disagreement is resolved. The solution is to repair the canonical contract or implementation, not weaken the gate.


## 13. End-to-end request lifecycle

Every non-trivial AI operation follows the same logical lifecycle even when an
implementation optimizes away internal hops. The machine-readable source is
`request_lifecycle` in the construction contract.

```text
0 ingress
  -> 1 identity + authority
  -> 2 admission / budgets
  -> 3 orchestration + durable identity
  -> 4 context / retrieval / memory
  -> 5 routing
  -> 6 provider execution
  -> 7 verification
  -> 8 tools / side effects
  -> 9 state + artifacts
  -> 10 response / resumable stream
  -> 11 telemetry + evaluation hooks
```

### 13.1 Ingress

Ingress performs cheap rejection before expensive work. Validate schema, size,
content type, supported operation, explicit user input limits, and request
metadata. A malformed request must never consume a provider call merely to learn
that it was malformed.

The ingress result is a validated request envelope. It is not yet authorized.

### 13.2 Identity and authority

Attach principal, tenant, session, and capability scope before reading protected
memory or data. Authentication and authorization remain separate decisions.

Authority is evaluated against the concrete resource and action, not a model's
natural-language claim that an action is needed.

### 13.3 Admission

Admission decides whether the operation fits current cost, latency, token,
concurrency, storage, and queue budgets. This decision occurs before spawning
large agent graphs, provider calls, or privileged tools.

The long-term contract is an admission receipt containing the budget class,
estimated consumption, decision, and reason.

### 13.4 Orchestration

Create an operation ID, task/plan identity, idempotency key, deadline, and trace
ID. Durable workflows persist enough intent to recover without repeating
non-idempotent work.

The orchestrator owns state transitions. A provider response cannot directly
declare an operation complete.

### 13.5 Context

Build context from separately typed sources:

```text
system/developer instructions
user request
authorized session history
authorized memory
retrieved evidence + provenance
tool results
explicit product state
```

Preserve the source and trust level of each section. Do not flatten untrusted
retrieval or tool output into system instructions.

### 13.6 Routing

Apply hard constraints before scoring preferences. If privacy, capability,
context, cost, reliability, or latency constraints eliminate every endpoint,
return a sanitized no-route decision rather than silently using an incompatible
provider.

### 13.7 Provider execution

A provider adapter may execute only after a valid architecture receipt exists.
Credentials stay at the provider edge. Timeout, retry, output-size, endpoint,
and error-normalization rules are part of the adapter contract.

### 13.8 Verification

Verification converts raw candidate output into a qualified result. Depending on
risk this may be structural validation, deterministic checks, retrieval-backed
claim verification, policy checks, or a separate verifier.

Verification failure can produce retry, abstention, escalation, or a partial
result. It must not be silently converted into confidence.

### 13.9 Actions

A model can propose an action. The tool runtime decides whether that action is
authorized, valid, affordable, safe, and idempotent.

Write/destructive actions require stronger authority and receipts than reads.

### 13.10 State and artifacts

Persist only under the declared data lifecycle. State writes and artifacts need
tenant ownership, hashes/versions where relevant, retention, and rollback or
compensation behavior.

### 13.11 Response and stream

The response plane converts internal state into an API result or ordered event
stream. A transient transport loss must not imply task loss.

### 13.12 Telemetry and evaluation

Close the trace with the route, provider/model actually used, tool receipts,
artifact/state references, latency/cost, terminal status, and evaluation hooks.
Operational telemetry must not contain secrets or unrestricted user payloads.

## 14. Canonical envelopes

The machine contract defines minimum fields; implementations may add fields but
may not remove required semantics.

### 14.1 Operation envelope

Required semantic fields:

- `operation_id`
- `tenant_id`
- `actor_id`
- `capability`
- `created_at`
- `deadline`
- `idempotency_key`
- `trace_id`

The operation ID identifies the user-visible unit of work. The trace ID can span
multiple internal operations but must never replace idempotency identity.

### 14.2 Provider request

The provider-neutral boundary carries instructions, prompt, history, requested
model, and output budget. Provider-specific optional knobs belong in a carefully
bounded extension layer, not feature routes.

### 14.3 Route decision

Record selected endpoint, candidates, hard rejections, applicable budgets, and
routing timestamp. This allows later explanation of why a provider/model was
used without exposing credentials.

### 14.4 Evidence envelope

Evidence requires source, hash, retrieval time, authority/ACL context, and
provenance. A citation without retrievable provenance is presentation metadata,
not evidence.

### 14.5 Tool receipt

A tool receipt binds operation, tool, authority, normalized input hash, start/end
time, status, and result reference. The raw secret input must not be stored just
because a receipt exists.

### 14.6 Artifact envelope

Artifacts require content identity, media type, size, owner/tenant, malware
state, and retention state. Generated artifacts and uploaded artifacts share the
same lifecycle after creation.

### 14.7 Stream event

A resumable event must include operation ID, globally or operation-unique event
ID, monotonically ordered sequence, type, timestamp, and payload.

### 14.8 Release evidence

A release evidence envelope binds source SHA, architecture tag, construction
version, tests, evaluations, security evidence, provenance, and rollback target.

## 15. Data classification and movement

The four baseline classes are hierarchical.

| Class | Typical content | Provider transfer | Logging |
| --- | --- | --- | --- |
| public | published docs, public examples | allowed for declared purpose | allowed |
| internal | repository/product internals | declared provider + purpose | sanitized |
| confidential | tenant/user/business-sensitive | explicit policy, minimization, tenant and purpose | metadata only |
| restricted | credentials, prohibited transfer data, high-risk private material | deny by default | never raw |

Classification travels with data. Copying confidential text into a prompt does
not downgrade it to "prompt data."

Every cross-boundary movement answers:

1. what data class is this?
2. which tenant/owner controls it?
3. what purpose authorizes movement?
4. which destination receives it?
5. is the destination allowed for this class?
6. what minimum subset is required?
7. how long may it remain?
8. how is deletion/export propagated?
9. what receipt records the decision?

Provider routing therefore consumes privacy classification as a hard constraint,
not merely a preference score.

## 16. Trust-zone topology

### 16.1 Human client

Treat all client input as untrusted. The frontend may improve UX validation but
server boundaries repeat authoritative validation.

### 16.2 Application API

The backend can hold secret references and credentials at approved edges, but
request payloads remain untrusted after authentication.

### 16.3 Engine runtime

Skeleton code is trusted executable code; task payloads, model output, memory,
retrieved evidence, and tool results remain typed data with their own trust
levels.

### 16.4 Data plane

Mongo, Chroma, and artifact storage contain durable governed state. Durable does
not mean trusted: content may originate from users, models, or external sources.

### 16.5 External provider

External providers are processors at a trust boundary. Only declared providers
receive approved data classes. Provider output is untrusted until normalized
and, where required, verified.

### 16.6 Tool sandbox

Tools receive least privilege. File, network, credential, and subprocess access
are capabilities, never defaults.

### 16.7 Accelerators

Native/JVM accelerators can implement compute primitives but cannot become
policy owners. A correct fallback path must exist unless the capability is
explicitly declared accelerator-required.

### 16.8 Repository automation

Repository automation is a privileged control plane. It can modify source and
may possess scoped GitHub/provider credentials, so its model client uses the
separate `automation_model` provider family and the same mandatory manual
receipt.

## 17. Provider surface inventory

The repository currently recognizes six provider-related surfaces.

| Surface | Role | Credential-bearing | Status |
| --- | --- | ---: | --- |
| `backend/core/ai_provider.py` | canonical product runtime provider execution | yes | canonical |
| `backend/core/ai_provider_compat.py` | legacy backend source compatibility | no | compatibility |
| `skeleton/jeeves/providers.py` | synchronous Jeeves network compatibility | yes | transitional |
| `skeleton/automation/free_model.py` | repository automation model execution | yes | canonical automation |
| `skeleton/frontier/model_runtime.py` | provider-neutral runtime protocols/adapters | no | library |
| `skeleton/jeeves/agent/provider.py` | provider-neutral retry/cache/circuit logic | no | library |

The transitional Jeeves surface is an explicit P0 convergence gap. It is now
receipt-gated, and undeclared Anthropic activation is denied even if a legacy
key exists. The remaining closure step is transport convergence so credential
ownership no longer exists in two product-runtime locations.

A provider-neutral library may model provider concepts without an activation
receipt only when it does not own credentials or network activation. The moment
it becomes credential-bearing, it must become a declared provider surface.

## 18. Provider onboarding protocol

Adding a runtime provider is a construction change, not a configuration toggle.

1. Add a declaration to `runtime_model_providers`.
2. Specify state, protocol, credentials, optional configuration, capabilities,
   undeclared-capability policy, and network policy.
3. Add a concrete adapter behind the canonical product provider boundary.
4. Ensure the adapter cannot activate before
   `load_provider_architecture(provider_id, provider_family="runtime_model")`.
5. Add endpoint validation appropriate to the provider.
6. Add bounded timeout/retry/output behavior.
7. Normalize response and error types.
8. Add provider metadata to routing.
9. Add privacy ceiling and cost/latency characteristics.
10. Add contract, malformed-output, timeout, unavailable, secret-redaction, and
    outage tests.
11. Add failure/fallback evaluation.
12. Update provider-surface inventory only if a new credential-bearing owner is
    truly necessary; normally it is not.
13. Run all architecture/construction/provider gates.
14. Do not advertise the provider as available until the declaration and receipt
    path are green.

Repository automation follows the same protocol under
`automation_model_providers`; it must not be conflated with the product model
plane.

## 19. Environment profiles

### Development

Development may use local source mounts and disposable state. Secrets remain
external to source. Provider declarations still apply: development is not a
permission to bypass provider policy.

### CI

CI favors deterministic fakes and contract tests. Live provider access is not a
required merge gate. CI secrets are narrowly scoped and should be unnecessary
for static architecture validation.

### Staging

Staging rehearses production network policy, migrations, persistence,
governance, budgets, and rollback. Staging budgets may be smaller but semantics
should match production.

### Production

Production uses immutable images, explicit egress, managed secret references,
durable migration/backup/restore, provider privacy/cost/SLO admission, canary
promotion, and proven rollback.

A behavior that only works under a development hot mount is not production
functionality.

## 20. Operation state machines

### 20.1 Generic operation

```text
created
 -> validated
 -> authorized
 -> admitted
 -> running
 -> {completed | failed | cancelled}
```

Optional states may include queued, waiting-for-tool, waiting-for-user,
reconnecting, retrying, or degraded. Every state transition has one owner.

### 20.2 Durable job

```text
queued
 -> leased
 -> running
 -> checkpointed*
 -> terminal
```

A lease requires expiry/fencing. A stale worker must not commit after ownership
moves to another worker.

### 20.3 Tool action

```text
proposed
 -> validated
 -> authorized
 -> admitted
 -> executing
 -> {committed | compensated | failed | cancelled}
```

### 20.4 Artifact

```text
created/uploaded
 -> quarantined
 -> scanned/validated
 -> trusted-or-rejected
 -> retained
 -> expired/deleted
```

### 20.5 Release

```text
source
 -> candidate
 -> built
 -> verified
 -> staged
 -> canary
 -> {promoted | rolled-back | rejected}
```

## 21. Failure and degradation matrix

| Failure | Required behavior |
| --- | --- |
| provider credentials absent | report unavailable; do not fabricate model output |
| provider undeclared | fail closed even if credentials exist |
| provider timeout | bounded retry/fallback; sanitized error |
| provider malformed output | reject/normalize; never trust shape implicitly |
| no route fits privacy/cost/capability | explicit no-route result |
| retrieval unavailable | degrade only if product contract allows context-free execution |
| tool denied | operation records denial; no attempted side effect |
| tool timeout | bounded cancellation/compensation policy |
| storage unavailable | do not claim durable completion |
| duplicate request | idempotency returns prior/in-progress result instead of duplicating side effect |
| stale worker | fencing rejects commit |
| stream disconnect | task continues according to operation policy; client can resume |
| event duplicate/out-of-order | client reducer deduplicates/orders by sequence |
| artifact scan failure | remain quarantined/rejected |
| telemetry sink unavailable | product may degrade, but security/audit-critical evidence can block protected operations or promotion |
| migration failure | do not route production traffic |
| canary SLO breach | stop promotion and rollback |
| architecture/manual mismatch | provider/build activation fails closed |

## 22. Resource budget hierarchy

Budgets exist at multiple scopes and are composed, not overwritten:

```text
deployment
  -> tenant
     -> user/session
        -> operation
           -> model call / tool call / retrieval / artifact
```

Budget dimensions include:

- input tokens;
- output tokens;
- provider monetary estimate;
- wall-clock deadline;
- provider timeout;
- tool timeout;
- total retries;
- agent fan-out;
- concurrent operations;
- queued operations;
- retrieval documents/chunks;
- memory/context characters or tokens;
- artifact bytes;
- storage retention;
- network response bytes.

A child operation cannot grant itself a larger budget than its parent.

## 23. Concurrency, retries, and idempotency

Retries multiply load and cost. Combine them with deadlines, idempotency, circuit
breaking, queue bounds, and concurrency caps.

Rules:

- one layer owns retries for a given failure;
- nested retry loops require an explicit total-attempt bound;
- retry only errors classified as retryable;
- preserve the operation deadline across attempts;
- jitter backoff for shared upstream failures;
- writes use idempotency keys or explicit compensation;
- a timed-out caller does not automatically mean a timed-out side effect;
- cancellation propagation is explicit.

## 24. Observability contract

Every significant operation should be reconstructable without exposing secrets.

Minimum correlation keys:

- trace ID;
- operation ID;
- tenant ID or privacy-safe tenant reference;
- route/provider/model IDs;
- tool IDs;
- artifact/state references;
- release/build ID where applicable.

Minimum metrics:

- request success/failure/cancellation;
- p50/p95/p99 latency where volume supports it;
- provider latency and failure class;
- token/usage/cost estimate;
- route rejection reasons;
- retrieval hit/quality metrics;
- tool success/timeout/denial;
- queue depth and admission denial;
- stream disconnect/resume;
- artifact scan/rejection;
- eval/regression result;
- canary/rollback result.

Logs are structured and redacted. Metrics should avoid cardinality explosions from
raw user IDs, prompts, or arbitrary model text.

## 25. Evaluation ladder

Use the cheapest trustworthy evidence first.

```text
static/schema checks
 -> deterministic unit tests
 -> contract tests
 -> integration tests
 -> golden journeys
 -> deterministic offline eval
 -> model-based eval where justified
 -> chaos/fault injection
 -> canary production evidence
```

Model-based evaluation does not replace deterministic assertions when expected
behavior can be encoded directly.

Promotion compares against a baseline and records the dataset/eval version,
provider/model/configuration, significant prompt/context contract version, and
metrics.

## 26. Release evidence bundle

Every production candidate should be able to produce or reference:

1. source SHA;
2. architecture tag and construction version;
3. architecture validator output;
4. construction validator output;
5. provider bootstrap output;
6. app assembly output;
7. focused and broad test evidence;
8. security/dependency/malware/provenance evidence;
9. behavior evaluation evidence where relevant;
10. migration/preflight evidence when state changes;
11. build artifact identity and SBOM/provenance;
12. smoke/canary evidence;
13. explicit rollback target and triggers.

"CI was green earlier" is not a release evidence bundle unless it is bound to
the exact source/artifact being promoted.

## 27. Current construction work packages

### WP-P0-PROVIDER-SURFACES

**Objective:** one mandatory receipt semantics and ultimately one product-runtime
credential/transport owner.

Current construction already completed in this lane:

- shared receipt loader: `skeleton/provider_contract.py`;
- backend loader converted to compatibility re-export;
- direct backend provider registry/adapter receipt enforcement;
- AI Assistant, AI Hub, game LLM service, and legacy LLM router converged on the
  canonical registry semantics;
- repository automation declared as a separate provider family and receipt-gated;
- Jeeves OpenAI/Anthropic network adapters receipt-gated;
- Anthropic remains denied because it is undeclared;
- provider-surface inventory and validator enforcement added.

Remaining closure:

- retain `LocalEchoProvider` as offline deterministic fallback;
- prove on the current head that repository-wide provider discovery reports only
  the declared credential-bearing owners;
- prove SDK isolation across backend and engine source;
- close the gap only after those CI receipts are green.

The canonical runtime now owns text generation, image generation, image
variation, image editing, and speech synthesis. Application routes and
`core/expressive_tts.py` consume provider-neutral media contracts and do not
own runtime-model credentials. Gemini and Grok remain explicit undeclared states
until their adapters are formally onboarded through the provider protocol.

### WP-P0-GOVERNANCE

**Status: in progress.** Baseline provider-transfer classification and pre-I/O
enforcement are implemented; broader lifecycle governance remains open.

Owners are materialized in `skeleton/kernel/governance.py`,
`skeleton/shells/ai/governance.py`, `backend/routes/governance.py`,
`backend/core/model_router.py`, context, and memory surfaces.

Construction sequence:

1. define one data-class enum/registry matching this manual;
2. add a governance decision object with tenant, purpose, source class,
   destination, decision, and reason;
3. attach classification to memory and retrieval evidence;
4. require provider-transfer decision before provider invocation;
5. require artifact/write classification;
6. implement retention/deletion/export hooks;
7. emit privacy-safe decision telemetry;
8. add denial-first tests.

### WP-P0-COST-ADMISSION

**Status: in progress.** Deterministic admission contracts, provider pre-I/O
gating, and model-routing budget projection are implemented. Durable tenant
quotas, live pressure, and actual-usage accounting remain open.

Construction sequence:

1. define hierarchical budget object;
2. estimate provider input/output cost before route execution;
3. combine tenant quota, request budget, queue pressure, and deadline;
4. produce admit/defer/reject receipt;
5. pass residual budget to routing;
6. meter actual provider/tool/storage use;
7. close the estimate/actual loop;
8. test saturation and graceful shedding.

### WP-P0-STREAM

Construction sequence:

1. freeze stream event schema;
2. assign monotonic per-operation sequence;
3. persist or reconstruct replay state;
4. define heartbeat and idle policy;
5. define cancellation race semantics;
6. define terminal events;
7. implement frontend reducer with event-ID dedupe;
8. implement resume cursor;
9. bound per-client buffers/backpressure;
10. test disconnects at every transition.

### WP-P1-PROVIDER-REDUNDANCY

Do not recreate the old "catalog says three providers" behavior. Either add a
real declared second provider or explicitly approve a single-provider
availability objective.

A real second provider must pass the complete onboarding protocol in section 18.

### WP-P0-GOLDEN-JOURNEYS

The E2E suite must prove at least:

- simple prompt -> result;
- retrieval -> evidence/citation -> result;
- tool proposal -> authority -> receipt -> result;
- artifact creation -> validation -> reference;
- provider unavailable -> truthful degraded state;
- cancel while running;
- disconnect -> reconnect -> resume;
- duplicate submission -> idempotent behavior;
- trace continuity across frontend/backend/engine/provider/tool.

### WP-P1-FEEDBACK

Feedback collection and behavior mutation are separate systems. Promotion
requires an experiment/evaluation receipt and rollback baseline.

### WP-P1-RELEASE-SLO

Canary promotion consumes the same error/latency/provider-quality signals that
operators observe. Rollback is automated for objective breach with an auditable
override path.

## 27A. Wave 1 implementation ledger

### Governance slice implemented

The provider edge now performs a baseline governance decision before constructing
or invoking the external provider client.

Implemented code:

- `skeleton/vault/data_governance.py` defines `DataClass`,
  `ProviderTransferRequest`, `ProviderTransferDecision`, and fail-closed
  evaluation;
- `backend/core/ai_provider.py` requires a transfer decision before provider
  I/O;
- restricted data is denied by the generic external-provider path;
- confidential data requires a tenant identity;
- transfer purpose is allowlisted;
- successful calls return a non-secret `gov-*` decision ID and the effective
  data class;
- the decision receipt never contains prompt or payload content.

This does **not** close the governance P0 gap. Still required:

- classification propagation through memory, retrieval, artifacts and durable
  state;
- a single provider privacy-ceiling bridge across every route;
- deletion propagation;
- export inventory;
- retention expiry enforcement;
- durable governance/audit evidence at all required boundaries.

### Cost/admission slice implemented

`skeleton/intelligence/admission.py` now defines the shared pre-allocation
budget vocabulary:

- `ResourceBudget`;
- `UsageEstimate`;
- `RuntimePressure`;
- `AdmissionRequest`;
- `AdmissionDecision`;
- admit/defer/reject semantics.

The deterministic gate currently covers:

- input token ceiling;
- output token ceiling;
- estimated provider cost;
- wall-time estimate;
- provider attempt count;
- tool-call estimate;
- artifact-byte estimate;
- concurrency saturation;
- queue saturation;
- operation deadline.

Provider execution now receives an admission receipt before the SDK client is
used. `RouteRequest.from_resource_budget(...)` projects the same cost,
output-token, and wall-time ceiling into model routing, preventing downstream
routing code from silently widening the caller's resource envelope.

Successful provider responses therefore carry two independent non-secret
control receipts:

```text
governance_decision_id = gov-...
admission_decision_id  = adm-...
```

This does **not** close the cost/capacity P0 gap. Still required:

- durable/per-tenant quota accounting;
- live concurrency and queue pressure feed;
- actual token/cost/tool/storage usage accounting;
- estimate-versus-actual feedback;
- admission integration at expensive tool/artifact/non-provider operations.

### Required ordering at the provider edge

The enforced order is:

```text
validate ProviderRequest
  -> governance decision
  -> resource admission
  -> architecture/provider receipt
  -> provider client
  -> external I/O
  -> normalized ProviderResponse
```

No denied request should increment the provider-call counter. Regression tests
explicitly assert that property.

## 28. Work-package execution protocol

When a builder takes a work package:

1. read the four mandatory bootstrap documents;
2. locate its gap and work package in the machine contract;
3. inspect every declared owner/evidence path;
4. confirm the gap still exists on the current base;
5. write or refine the interface contract first;
6. implement the smallest vertical slice that can produce closure evidence;
7. add unit and failure tests with the slice;
8. update observability with the behavior, not afterward;
9. run architecture/construction/provider gates immediately;
10. run focused domain tests;
11. run integration/golden tests appropriate to the package;
12. update gap status only when closure evidence exists;
13. if architecture changed, update the machine contract and manual in the same
    lane;
14. never delete a gap merely because work moved to another branch.

## 29. Architecture-change protocol

A change is architectural when it adds or moves any of:

- runtime root;
- runtime service;
- canonical capability owner;
- provider family or credential-bearing provider surface;
- cross-plane dependency;
- durable store;
- external trust boundary;
- public API version;
- authority model;
- release/promotion mechanism.

For architectural changes:

```text
proposal
 -> machine contract update
 -> dependency/cycle validation
 -> implementation
 -> migration/compatibility layer
 -> evidence
 -> architecture tag bump
 -> release
 -> compatibility retirement
```

Do not perform physical directory moves first. Establish ownership, adapters,
imports, routes, tests, packaging, and rollback before relocating implementation.

## 30. Testing matrix

Each capability should be tested across these dimensions where applicable:

| Dimension | Examples |
| --- | --- |
| happy path | valid request, valid provider response |
| malformed input | schema/type/size violation |
| authorization | unauthenticated, unauthorized, wrong tenant |
| dependency unavailable | provider/storage/retrieval/tool down |
| timeout | provider/tool/job deadline |
| cancellation | before start, during I/O, during side effect |
| retry | retryable vs non-retryable |
| idempotency | duplicate submit, duplicate delivery |
| concurrency | saturation, lease race, stale worker |
| security | injection, SSRF, secret leakage, unsafe file |
| privacy | prohibited provider transfer, cross-tenant retrieval |
| observability | trace/receipt emitted and sanitized |
| recovery | restart, reconnect, resume, restore |
| performance | budget and backpressure |
| compatibility | old client/manifest/schema where supported |
| rollback | release or migration reversal |

## 31. Production-readiness decision tree

A capability may be marked structurally present when its owner, interfaces,
dependencies, failure behavior, and acceptance evidence exist.

It may be marked production-ready only when:

```text
declared?
  no -> stop
owned?
  no -> stop
authorized?
  no -> stop
bounded?
  no -> stop
observable?
  no -> stop
tested happy + failure paths?
  no -> stop
evaluated where nondeterministic?
  no -> stop
deployable and rollback-capable?
  no -> stop
P0 gap for this capability still open?
  yes -> stop
otherwise -> eligible for production promotion
```

This distinction prevents "code exists" from being confused with "system is
operationally complete."

## 32. Provider-readable construction guarantee

The mandatory provider rule is enforced at three different layers:

1. **Development-provider layer.** Provider-specific repository instruction
   files point every coding agent to the same four bootstrap documents.
2. **Runtime/automation activation layer.** Credential-bearing AI provider
   clients call `skeleton/provider_contract.py` and receive a digest-bound
   receipt before external I/O.
3. **CI layer.** `scripts/check_provider_bootstrap.py` verifies instruction
   entrypoints, shared loader semantics, provider-family declarations, provider
   surface inventory, image materialization, SDK isolation, and receipt tokens.

This is deliberately redundant. The goal is not to trust that a provider
"probably saw" the architecture; the goal is to make architecture
acknowledgement a condition of activation or repository work.


## 33. Canonical operation and stream construction

The first transport-independent portion of `WP-P0-STREAM` is now materialized.

### 33.1 Operation identity

Use `skeleton/contracts/operation.py` for operation identity and state. Do not
create route-local or provider-local operation state machines.

The required path is:

```text
created
 -> validated
 -> authorized
 -> admitted
 -> {queued ->} running
 -> optional waiting/retrying/degraded states
 -> {completed | failed | cancelled}
```

Terminal states are final. Skipping validation/authorization/admission is an
architecture violation for governed expensive work.

`operation_id` is the durable unit-of-work identity. `trace_id` is only
correlation. `idempotency_key` participates in duplicate identity and must not
be replaced by the trace identifier.

### 33.2 Event protocol

Use `skeleton/frontier/operation_stream.py` as the protocol oracle.

Every event has:

- schema version;
- operation ID;
- unique event ID;
- positive monotonic sequence;
- normalized event type;
- timezone-aware timestamp;
- strict JSON bounded payload.

The reference log intentionally fails on overflow. Dropping retained events to
make room is prohibited because it can turn a reconnect into silent state loss.

### 33.3 Replay

A reconnect presents the operation ID plus last acknowledged sequence. Replay
returns later events in sequence. If requested history was compacted, return an
explicit replay-gap failure and reconstruct from durable operation state or force
a state resync; never pretend that no events occurred.

### 33.4 Duplicate and ordering semantics

The same event ID may be accepted twice only when its full canonical content is
identical. Reusing an event ID for different content is corruption.

Pre-built events from durable producers must arrive at exactly the next
sequence. Out-of-order delivery is rejected at the protocol boundary and may be
buffered only by a higher-level adapter with explicit bounded policy.

### 33.5 Terminal events

`operation.completed`, `operation.failed`, and `operation.cancelled` are
terminal. No later progress/result event may be appended for that operation.

### 33.6 Backpressure

The reference log backpressures publishers when its retained window is full.
Production adapters may use bounded queues, durable streams, credits or consumer
acks, but may not silently drop unacknowledged operation events.

### 33.7 Remaining stream closure work

This does not close the P0 streaming gap. Remaining required work is:

1. durable stream storage preserving event IDs and sequence;
2. backend SSE or WebSocket transport;
3. heartbeat and idle timeout;
4. cancellation bridge into `OperationEnvelope`;
5. frontend reducer with event-ID and sequence handling;
6. reconnect cursor and resync UX;
7. multi-client acknowledgement strategy;
8. slow-client, cancel-race and disconnect/reconnect E2E evidence.


## 34. Durable stream store

`SQLiteOperationEventStore` is now the durable reference implementation for
the canonical stream protocol.

It provides transactional exact-next sequence enforcement, operation-scoped
unique event IDs, durable terminal fencing, replay from an explicit cursor,
explicit compaction watermarks, replay-gap failure, strict corruption rejection,
and bounded retained-event capacity with backpressure.

SQLite is a portable conformance backend, not an architectural mandate. Another
durable substrate may replace it only if the same protocol invariants and tests
remain green.

The P0 stream gap remains open only for transport/client integration: backend
SSE or WebSocket, heartbeat/idle policy, cancellation bridge, frontend
reducer/resume, multi-client acknowledgement, and end-to-end recovery evidence.

## 35. Physical structure and assembly law

This section is mandatory for implementation work. Logical capability design is
not sufficient; every change must land in the physical structure declared by
`machine/architecture.json -> structural_blueprint`.

The structural checkpoint is `structure-map/v1.1`.

### 35.1 Construction decision sequence

Before creating or moving code, resolve the change in this order:

1. **Capability plane** — identify the existing plane in
   `machine/ai_app_construction.json`. If no plane owns the capability, the
   contract must be extended before implementation.
2. **Runtime zone** — use the plane's structural placement. Do not choose a
   convenient neighboring root.
3. **Physical owner** — extend the declared package/module owner unless the
   architecture change intentionally transfers ownership.
4. **Composition point** — wire the capability only from an approved
   composition root when multiple owners must be assembled.
5. **Cross-zone contract** — if execution crosses a zone boundary, preserve an
   existing declared interface or add the interface to the architecture first.
6. **State authority** — determine which plane owns durable truth. Caches,
   projections and transport buffers remain subordinate.
7. **Recovery domain** — define failure, restart, retry and degraded behavior
   according to the plane's recovery domain.
8. **Evidence** — add focused tests proving placement, contract behavior,
   authority, failure behavior and any state transition.
9. **Manifest linkage** — keep architecture, repository and runtime tags aligned.
10. **Validation** — run architecture validation before dependency-heavy test
    suites so structural drift fails early.

### 35.2 Plane placement registry

The following registry is generated from the machine contract and is the
physical destination map for implementation:

| Plane | Zone | Canonical owner | Structural role |
| --- | --- | --- | --- |
| `foundation` | `engine` | `skeleton/kernel` | internal-capability |
| `identity` | `engine` | `skeleton/api` | internal-capability |
| `configuration-secrets` | `engine` | `skeleton/config` | internal-capability |
| `model-provider` | `engine` | `skeleton/provider_runtime.py` | provider-boundary |
| `model-routing` | `application` | `backend/core/model_router.py` | policy-boundary |
| `prompt-context` | `engine` | `skeleton/context` | internal-capability |
| `orchestration` | `engine` | `skeleton/intelligence` | internal-capability |
| `reasoning-verification` | `engine` | `skeleton/intelligence` | internal-capability |
| `tool-runtime` | `engine` | `skeleton/skills` | internal-capability |
| `memory` | `engine` | `skeleton/memory` | state-boundary |
| `retrieval` | `engine` | `skeleton/retrieval` | internal-capability |
| `data-persistence` | `engine` | `skeleton/persistence` | state-boundary |
| `jobs-durability` | `engine` | `skeleton/agents` | state-boundary |
| `artifact-files` | `engine` | `skeleton/artifact_plane` | state-boundary |
| `application-api` | `application` | `backend` | service-boundary |
| `engine-api` | `engine` | `skeleton/api` | service-boundary |
| `product-experience` | `product` | `frontend` | product-shell |
| `streaming-realtime` | `application` | `backend` | transport-boundary |
| `security-safety` | `engine` | `skeleton/security` | security-boundary |
| `governance` | `engine` | `skeleton/vault` | governance-boundary |
| `resilience` | `engine` | `skeleton/reliability` | internal-capability |
| `observability` | `engine` | `skeleton/observability` | telemetry-boundary |
| `evaluation` | `engine` | `skeleton/eval` | evidence-boundary |
| `feedback-learning` | `engine` | `skeleton/learning` | promotion-boundary |
| `cost-capacity` | `engine` | `skeleton/intelligence` | admission-boundary |
| `operator-control` | `application` | `backend/core/product_control_runtime.py` | control-boundary |
| `deployment-release` | `engine` | `skeleton/deploy` | release-boundary |

Do not create a second owner because an existing owner is large. Split the
existing owner internally first, then transfer ownership through an explicit
architecture change if the split deserves a new plane.

### 35.3 Composition discipline

Approved composition roots are:

- `skeleton/app/assembly.py` — Compose declared runtime services and operator topology; never absorb domain business logic.
- `skeleton/__main__.py` — Dispatch operator commands into owned engine/application surfaces without creating alternate runtimes.
- `backend/server.py` — Mount application routes, middleware, and shared application dependencies; feature logic remains in owned modules.
- `frontend/app/_layout.tsx` — Mount product providers, guards, and navigation shell; service ownership remains behind canonical API clients.
- `skeleton/provider_runtime.py` — Construct credential-bearing runtime provider adapters after governance, admission, and architecture receipt checks.
- `backend/core/model_router.py` — Select among declared provider capabilities using bounded evidence and budgets without performing provider network I/O.

Composition code should be shallow. It may instantiate, inject, mount, select or
sequence owned components. It should not contain durable business rules,
provider-specific transport, cross-tenant state, or hidden fallback behavior.

When a composition root starts accumulating domain behavior, move that behavior
back into the plane owner and leave only wiring in the composition root.

### 35.4 State ownership discipline

Canonical state authorities are:

- **identity-and-principal** → `identity` → `skeleton/api`
- **runtime-configuration-and-secrets** → `configuration-secrets` → `skeleton/config`
- **provider-activation** → `model-provider` → `skeleton/provider_runtime.py`
- **conversation-and-working-memory** → `memory` → `skeleton/memory`
- **retrieval-index-and-ranking-state** → `retrieval` → `skeleton/retrieval`
- **durable-application-records** → `data-persistence` → `skeleton/persistence`
- **job-checkpoints-and-resume** → `jobs-durability` → `skeleton/agents`
- **artifact-bytes-and-metadata** → `artifact-files` → `skeleton/artifact_plane`
- **governance-policy-and-retention** → `governance` → `skeleton/vault`
- **evaluation-evidence** → `evaluation` → `skeleton/eval`
- **feedback-experiments-and-promotion** → `feedback-learning` → `skeleton/learning`
- **quota-budget-and-admission** → `cost-capacity` → `skeleton/intelligence`
- **release-and-rollback-evidence** → `deployment-release` → `skeleton/deploy`

Rules:

- one state class has one canonical writer-of-record authority;
- read models may duplicate representation but not authority;
- caches must be disposable and reconstructable;
- transport buffers do not become durable operation truth;
- provider responses become application state only after the owning plane
  accepts them through its contract;
- deletion, retention, export and tenant isolation follow the authority owner,
  not whichever adapter happens to store a copy.

### 35.5 Recovery-domain discipline

#### bootstrap-authority

Planes: `foundation`, `identity`, `configuration-secrets`

Restart scope: engine bootstrap/configuration

Degraded mode: fail closed for authority-bearing work; health may remain diagnostic-only

#### provider-execution

Planes: `model-provider`, `model-routing`, `cost-capacity`

Restart scope: provider/routing workers

Degraded mode: deny or route only to already-declared healthy capacity; never bypass receipts or budgets

#### knowledge-state

Planes: `memory`, `retrieval`, `data-persistence`, `prompt-context`

Restart scope: knowledge and persistence adapters

Degraded mode: bounded stateless mode only where the request contract permits it; never cross tenant boundaries

#### cognition-action

Planes: `orchestration`, `reasoning-verification`, `jobs-durability`, `tool-runtime`, `artifact-files`

Restart scope: operation/job execution

Degraded mode: checkpoint, cancel, or return partial evidence; never silently repeat side effects

#### service-transport

Planes: `application-api`, `engine-api`, `streaming-realtime`, `operator-control`

Restart scope: API/transport process

Degraded mode: health and explicit unavailable responses; resumable operations preserve identity and terminal state

#### product-shell

Planes: `product-experience`

Restart scope: frontend process/session

Degraded mode: preserve local UI state and surface backend/engine degradation without fabricating completion

#### security-governance

Planes: `security-safety`, `governance`

Restart scope: policy/security boundary

Degraded mode: fail closed for protected actions and external transfers

#### quality-release

Planes: `observability`, `resilience`, `evaluation`, `feedback-learning`, `deployment-release`

Restart scope: evidence/promotion control

Degraded mode: freeze promotion and learning mutation while preserving current known-good release


A retry or restart policy that crosses one of these domains needs explicit
evidence that it cannot duplicate side effects, widen authority, lose terminal
operation state, or bypass a fail-closed policy.

### 35.6 Adding a new capability without creating an island

Use this assembly recipe:

```text
user/product need
      ↓
existing plane? ── no ──> declare plane + dependencies + owner
      │ yes
      ↓
structural placement
      ↓
extend canonical owner
      ↓
state authority / interface / recovery classification
      ↓
composition wiring
      ↓
focused tests
      ↓
architecture + construction validators
      ↓
cross-plane integration evidence
```

The prohibited shortcut is "temporary parallel ownership." Temporary adapters
are allowed; temporary second authorities are not.

### 35.7 Moving an existing capability

Physical migration is a controlled ownership transfer:

1. declare the destination owner;
2. keep the old public contract stable through an adapter;
3. move one bounded behavior slice;
4. prove equivalent behavior and failure semantics;
5. move state authority only after migration and rollback are explicit;
6. update imports, manifests, package data and CI ownership;
7. remove the old implementation path;
8. leave a compatibility facade only when consumers still require it;
9. remove the facade when all callers have converged.

Never bulk-move a capability merely to make the tree look cleaner. Structure is
an execution contract, not a cosmetic directory layout.

### 35.8 Structural definition of done

A structural change is complete only when:

- every affected plane still has exactly one owner and one placement;
- every owner path exists inside its declared zone;
- cross-zone dependencies are legal in the zone DAG;
- state authority remains singular;
- composition roots contain wiring rather than domain ownership;
- every plane remains assigned to one recovery domain;
- architecture, repository and runtime manifests report the same structure tag;
- `python scripts/check_architecture_map.py` passes;
- focused behavioral tests for the changed plane pass;
- no transitional root has become a new runtime authority.

### 35.9 Reverse dependency exception procedure

A reverse dependency is architecture debt, not permission to widen the zone
graph. When a construction prerequisite cannot yet follow the runtime zone DAG:

1. keep the zone DAG unchanged;
2. declare the exact source plane(s) and dependency plane;
3. classify the exception as `ownership-migration` or
   `control-observation`;
4. document why the dependency is not equivalent to runtime ownership;
5. for ownership migration, declare the intended destination owner;
6. provide a concrete removal condition;
7. add regression coverage proving the exception is both necessary and exact;
8. remove the exception as soon as the edge becomes legal or disappears.

Never use a wildcard exception, root-wide exception, or an exception that
creates an implicit cyclic zone dependency.

