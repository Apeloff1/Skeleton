# Cross-subsystem integration matrix

This matrix is the canonical map from critical Skeleton subsystem boundaries to executable regression coverage. It complements unit tests: a matrix scenario must cross at least two production subsystem boundaries and must use local deterministic fixtures in place of external providers.

## Required pull-request matrix

| Boundary chain | Happy path | Failure path | Provider isolation | Canonical test | Merge Readiness job |
| --- | --- | --- | --- | --- | --- |
| HTTP API -> request gate -> Genesis -> retrieval -> RAG -> fusion -> provenance | ingest then query returns the stored RAG fragment and source provenance | invalid HMAC seal is rejected before storage mutation | deterministic `HashEmbedder`; no network/provider | `tests/test_cross_subsystem_integration.py::test_boundary_api__retrieval__rag__fusion__provenance_happy_path` and `...rejects_invalid_seal_without_mutation` | `integration_smoke` |
| API request correlation -> orchestrator -> tool registry -> tool -> run state -> telemetry | one tool call mutates state and completes with the request ID on every telemetry event | tool failure/retry is redacted and correlated | local tool handlers; no external provider | `tests/test_cross_subsystem_integration.py::test_boundary_api_correlation__orchestrator__tool__state_happy_path` plus `skeleton/testing/test_frontier_observability_correlation.py` | `integration_smoke` |
| Agent runtime -> memory retriever -> memory store -> agent context -> provenance | retrieved memory reaches the agent with source metadata and provenance digest | missing provenance and storage exceptions fail closed before agent execution | `InMemoryStore` / local exploding fixture | `tests/test_frontier_runtime_memory_retrieval.py` | `integration_smoke` |
| Model runtime -> provider adapter -> retry/timeout/cancellation | provider-neutral chat contract succeeds across adapters | transient provider failure retries; timeout and cancellation are deterministic | in-process OpenAI/LiteLLM-shaped fake clients | `tests/test_model_runtime.py` | `integration_smoke` |
| Model runtime -> streaming adapter -> normalized stream events | text deltas normalize into a completed response | non-stream fallback is explicit and capability-gated | in-process async stream fixture | `tests/test_model_runtime.py` | `integration_smoke` |
| Backend process -> Mongo service | application imports against a live Mongo service | service/import failures fail the job | local CI Mongo container | Merge Readiness workflow import probe | `integration_smoke` |

## Contract

The `integration_smoke` job is required to run the matrix on pull requests to `main`. Scenario names intentionally include the boundary chain (for example `test_boundary_api__retrieval__rag__fusion__provenance_happy_path`) so a failing test identifies the subsystem seam directly in CI output.

External model providers are forbidden in this required PR matrix. Provider behavior is represented by stable adapters/fixtures with deterministic outputs, retries, errors, cancellation, and async streams. Live-provider or capacity experiments belong in scheduled/release reliability work rather than merge-readiness checks.

## Coverage policy

A new critical production boundary should be added to this table in the same change that introduces it. Happy-path coverage alone is insufficient for state-changing boundaries: the matrix must also prove at least one fail-closed or degraded path. Tests must not persist credential or exception payloads in failure output, and they must avoid network calls outside explicitly provisioned CI services.