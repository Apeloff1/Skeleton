# Native AI flight HTTP — bearer-authenticated real inference boundary

The older v1 `Dispatcher` addresses `OfflineAIService`; this source adds a
**separate** v2 transport for the authoritative `ExecutionSpine` and durable
`FlightLedger`. It is not a replacement for either owner and does not merge
their different session stores. The v2 server can be created only after a
real approved GGUF has activated through `activate_flight()`.

## Execution ordering

1. Approve, install and digest-check the real offline model through the
   preexisting GGUF and private-state boot path.
2. Bind the tenant, subject, model and tokenizer to the private state.
3. The production activation verifies knowledge source audit and FTS5 index
   integrity, then constructs the durable spine and flight ledger.
4. Start only a *literal* 127.0.0.1 HTTP server with an independently
   provisioned 32–512 character bearer. Do not publish a token in Git.
5. Explicitly `create` a session, `submit` a bounded signed-by-identity
   inference intent, then `work_one` to execute a real bounded model call.
   The queue and SQLite ledger own all replay, revision and worker fences.
6. `job`, `queue`, `history` and `replay` expose scoped receipts; replay never
   calls the model. `knowledge_search` returns digest and source location,
   not raw passages unless separately disclosed by an operator path.

No privileged `pause`, `resume`, `recover`, `rebuild-index`, `knowledge_ingest`,
or `call_tool` action is reachable through the bearer user API. Those remain
independent operator commands, with separate approvals and fail-closed holds.
Model generations cannot execute tools or mutate approved source records.

## Local-only launch

```sh
python -m skeleton.ai.runtime.operational_ai.transport.flight.serve \
  --model-root /private/approved-model --state-dir /private/ai-state \
  --bearer-file /private/secrets/local-ai-bearer \
  --tenant mytenant --subject myuser --port 8766
```

The token is **not included in the repository**. Independently provision a
strong random bearer in a unique owner-owned regular file mode 0600, under a
trusted private parent. The launcher descriptor-opens and verifies it; no
secret is accepted from command-line arguments or environment variables. This server is
plain HTTP on a loopback literal; it must not be exposed to remote clients,
other users, a browser origin or a reverse proxy without additional security.

## Trust and validation

The transport reuses the existing hardened request-framing/Host/Origin/bearer
checks, bounded connection slots, bounded HTTP I/O and JSON parsing. The
schema `skeleton.ai.native-flight-http.v2` distinguishes the v2 operations
from legacy v1. Unknown fields/routes, missing bearer, nonloopback bind and
payloads exceeding 65,536 bytes all fail closed. Application/model error
strings never reach clients. No model, network provider or emulator fallback
is introduced.

```sh
python -m unittest skeleton.testing.test_ai_flight_http -v
python -m unittest skeleton.testing.test_ai_flight_control \
    skeleton.testing.test_ai_execution_spine -v
```

The socket tests are concrete request/response tests with a deterministic
*fixture backend*, not a benchmark of model quality. The mandatory real native
GGUF first-install, final-head Merge Readiness, Backend Quality, App E2E,
Security/Artifact/Malware/Hygiene/Secret/Dependency checks must still succeed
on the final SHA. This transport change retains all draft/release holds.
