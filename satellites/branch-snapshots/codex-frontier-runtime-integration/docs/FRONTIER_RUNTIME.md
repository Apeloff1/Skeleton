# Integrated frontier runtime

The frontier agent/domain branch (`9ce61e23`) and GameForge infrastructure branch
(`13f3f0b4`) are now combined on the `91f66a03` main baseline. Both histories are
retained. `skeleton.frontier.contracts` is a package so its original public
protocols and the admission/recovery submodules can be imported together.

## Run the implementation

```bash
python -m pip install -r requirements-frontier.txt
python -m skeleton frontier agents
python -m skeleton frontier run gameforge.npc "a loyal guardian" \
  --context '{"name":"Sentinel","dialogue_beats":4}'
python -m skeleton frontier run gameforge.logic "combat and exploration"
python -m skeleton frontier run jeeves.review --task-file example.py
python -m skeleton frontier --state-root /tmp/skeleton-state memory put \
  "Guardians protect the northern gate" --id north-gate
python -m skeleton frontier --state-root /tmp/skeleton-state memory search guardian
```

The NPC and game-logic adapters invoke the existing verified generation
pipelines. Jeeves invokes `CodeIntelligenceEngine`. These are deterministic local
implementations; model training, model weights, and external providers are not
part of this runtime change. Pipeline workers receive task text as JSON data.
They execute fixed operations, and are killed and reaped on cancellation.

The CLI exits 0 for successful work, 1 for a failed execution result, and 2 for
invalid command input. Results include request identity, status, attempts,
elapsed time, and provenance.

## Execution contract

```python
from skeleton.frontier import AgentRuntime, CapabilityPolicy, ExecutionPolicy

runtime = AgentRuntime(
    policy=CapabilityPolicy.from_names({"text.generate"}),
    execution_policy=ExecutionPolicy(max_concurrency=4, max_queue=16),
)
runtime.register(my_async_agent)
result = await runtime.execute(
    my_async_agent.name, "task", context={"project": "game"},
    idempotency_key="caller-scoped-request-key",
)
await runtime.aclose(grace_period=5)
```

All declared agent capabilities must be permitted before dispatch. Omitting
`required_capability` does not bypass authorization. Names and capabilities are
captured at registration; changing them requires a new registration. Policy is
checked again after queueing and before retrying. This is a dispatch boundary,
not a sandbox for arbitrary Python adapters.

| Budget | Default |
| --- | ---: |
| Active executions | 8 |
| Queued executions | 64 |
| Queue wait | 5 seconds |
| Agent execution, including retries | 30 seconds |
| Attempts | 1, configurable up to 10 |
| Input/output JSON payload | 1,048,576 encoded bytes each |
| Runtime event delivery | 0.1 seconds per notification |
| Retained telemetry samples | 4,096 |

Ordinary exceptions become failed results without disclosing exception text.
Only `TransientAgentError` permits automatic retries; an adapter raising it must
know that retrying is safe. Each attempt receives a fresh context snapshot. A
caller can shorten the execution timeout but cannot enlarge the configured
budget. Observer delivery has its own small budget.

Cancellation propagates to callers and releases queue/concurrency reservations.
Shutdown stops new admissions, drains previously admitted work, then cancels
remaining tasks after its grace period. Custom async adapters must cooperate
with cancellation and must not block the event loop. The built-in process
adapters provide process termination for the synchronous domain implementations.
A runtime must stay on one event loop while requests are pending.

## Idempotency and observation

Concurrent requests with the same key and request fingerprint share one agent
execution. Cancelling one waiter preserves work needed by another; cancelling
the last waiter cancels the underlying execution. Successful results are copied
into a bounded 60-second in-process cache. Failures are not retained. Reusing a
key with different request content raises `IdempotencyConflict`.

This is a retry window, not durable exactly-once processing. Replays preserve
the original request ID. Clients must scope keys by caller; the HTTP adapter
does so using the verified attester and agent name. Authorization is rechecked
before returning a cached result.

Started/completed/failed/timed-out events carry correlation and causation IDs.
Subscribers receive detached payload snapshots; ordinary subscriber failures
are collected after delivery to the remaining subscribers. Runtime observer
errors are counted without replacing the agent result. Events and provenance
metadata omit raw task text; the execution result itself includes the task.
Telemetry retains a bounded window and reports count, mean, p50, and p95.

## Persistent memory

`SQLiteMemoryStore` implements the same `put/search/delete` protocol as
`InMemoryStore`. Writes return an ID that is also present in search results.
Both stores detach nested data, reject unsupported/non-finite JSON, support
upserts at capacity, and return deterministic ID order with casefolded substring
search and exact metadata filters. This is a reference text store, not a vector
similarity index.

SQLite uses namespace-qualified primary keys, WAL, full synchronization, and
`BEGIN IMMEDIATE` transactions. Capacity checks and writes are atomic across
connections. Deletions and searches are namespace-scoped. Database work runs
off the event loop. Cancelling a waiting coroutine cannot undo an already
running SQLite transaction; it may still commit. Explicitly close stores or use
their async context manager. Namespace selection is an application concern;
the store does not authenticate callers.

## HTTP integration

The normal `skeleton.api.server.create_app()` mounts these routes and closes its
frontier runtime on shutdown. A custom runtime can be injected with
`create_app(frontier_runtime=runtime)`.

| Endpoint | Behavior |
| --- | --- |
| `GET /api/v1/frontier/agents` | Registered names and capabilities |
| `GET /api/v1/frontier/status` | Queue, outcomes, latency and retention counters |
| `POST /api/v1/frontier/execute` | Execute `{agent, task, context?, timeout?, request_id?}` |

All three require an existing valid `x-gf-seal`. The main application also
retains the existing governance middleware, with the frontier routes mapped to
the intelligence domain. `Idempotency-Key` is optional on execution. Responses
echo `X-Request-Id`. Admission saturation returns 429; conflicting keys 409;
unknown agents 404; denied capabilities 403; invalid input 422; unavailable
runtime 503; failed agents 502; execution deadline expiry 504.

## Validation and remaining gates

```bash
python scripts/test_frontier.py
ruff check --config ruff-frontier.toml skeleton/frontier skeleton/services skeleton/api/frontier_routes.py
ruff format --config ruff-frontier.toml --check skeleton/frontier skeleton/services skeleton/api/frontier_routes.py
```

The integration runner includes every promoted frontier and GameForge test plus
CLI, HTTP, subprocess, persistence, and kernel event integration. The initial
verified run passed 413 tests on Python 3.12 with the production backend's
FastAPI/Pydantic versions. CI runs this bundle on Python 3.11 and 3.12 and
retains JUnit results.

The existing main CI had separate frontend TypeScript and backend formatting
failures before this integration. Those broader application gates remain
required. A green frontier suite does not certify the entire application or the
completion of all source-repository consolidation.
