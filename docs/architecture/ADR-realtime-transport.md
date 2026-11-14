# ADR: Canonical realtime transport and event envelope (v1)

- **Status:** Accepted (TD ruling, 2026-10-17)
- **Owner:** Walt (Network / Online Services)
- **Consumers:** SDK (`skeleton/client/`, Coder Lead), Frontend, Jobs/agents (Internal Systems, `skeleton/app_services/`)

## Context

Three realtime-shaped paths exist or are planned:

1. **#3862** (merged): `/api/ai/chat/turns/{thread_id}/events` streams bounded immutable journal events as SSE on `Accept: text/event-stream`, with a cursor sequence. Without that header it keeps JSON paging.
2. **#4085** (merged): the frontend tunnel heartbeat. This is a single-owner liveness probe for the dev/app tunnel. It is not an event channel.
3. **#4095** (draft): SDK `BuildsClient.stream_events(execution_id)` against the existing engine route `GET /api/v1/engine/executions/{execution_id}/events`.

Without a single decision, the SDK and frontend would build three incompatible clients.

## Decision

### 1. One transport: Server-Sent Events over HTTP

- Every server-to-client app event (build progress, agent activity, presence, chat turn replay) is delivered as **SSE** (`Content-Type: text/event-stream`).
- Each frame is `id: <envelope.id>`, `event: <envelope.type>`, `data: <envelope JSON>`.
- **WebSocket is not canonical.** We may add it later behind the same envelope if a bidirectional, high-rate need appears, for example live co-editing. Until then, client-to-server actions (presence join, leave and heartbeat) are plain HTTP `POST`s.
- **NDJSON is not a supported streaming format** for new endpoints.

### 2. Endpoint family

| Endpoint | Status | Purpose |
|---|---|---|
| `GET /api/v1/events?channels=build,agent,presence[&job_id=...]` | Lands with the realtime transport implementation PR | Canonical multiplexed stream |
| `GET /api/v1/engine/executions/{execution_id}/events` | Exists (engine) | Filtered view scoped to one execution; adopts the v1 envelope, and existing behaviour stays compatible |
| `GET /api/ai/chat/turns/{thread_id}/events` (#3862) | Exists | Filtered view for chat. SSE frames adopt the v1 envelope; the JSON paging contract is unchanged |
| `POST /api/v1/presence` | Lands with the implementation PR | Presence join, heartbeat and leave (body: `{action, scope, client_id}`) |

All endpoints reuse the app's existing auth and the tenant/owner checks. SDK route-conformance lists add each route only once it exists on main.

### 3. Event envelope v1

```json
{
  "v": 1,
  "id": "<monotonic per stream; string>",
  "ts": "<RFC 3339 UTC>",
  "channel": "build | agent | presence",
  "type": "build.started | build.progress | build.log | build.completed | build.failed | agent.started | agent.step | agent.completed | presence.joined | presence.left | presence.snapshot",
  "payload": {},
  "job_id": "<optional>",
  "correlation_id": "<optional>"
}
```

- Field names are snake_case. Unknown fields must be ignored, so additive changes stay within `v: 1`. Breaking changes bump `v`.
- Producers build envelopes with `skeleton/app_services/events.make_envelope` (#4097). The realtime hub **owns the delivered `id`**: it re-sequences each stream monotonically so that a multiplexed `/api/v1/events` stream has one resume cursor. A producer's per-channel id may be kept as `payload.source_id`.
- `correlation_id` carries the originating request's `x-request-id`.
- **Payloads never carry secrets, tokens or credentials** (#3637). Producers redact through observability `redact_payload`, and the hub publish path guards again.

### 4. Resume, liveness and backoff

- **Resume:** the SSE `id` equals `envelope.id`. Clients reconnect with the `Last-Event-ID` header, or `?cursor=<id>` where headers are unavailable. The server replays from a bounded buffer. If the cursor has aged out, the server sends a `stream.reset` event and the client refetches state over REST.
- **Liveness:** the server sends an SSE comment heartbeat (`: hb`) every 15 s. If the client sees nothing for 45 s (3 missed heartbeats), it treats the stream as dead and reconnects. The #4085 tunnel heartbeat stays a transport liveness probe and is not used for app events.
- **Backoff:** exponential with full jitter, reusing the SDK `RetryPolicy` (`base_delay_seconds` 0.5, `max_delay_seconds` 30). It resets after 60 s of a healthy stream. The SSE `retry:` field is honoured as a floor.
- **Backpressure:** the per-subscriber queue is bounded. On overflow the server drops the oldest events for that subscriber and sends `stream.lagged {dropped}`, and the client resumes from its last id.

### 5. SLOs (measured server-side, exported via the existing observability layer)

| SLI | Target |
|---|---|
| Stream connect success | >= 99.5% / 28 d |
| Publish-to-delivery latency | p95 < 500 ms, p99 < 2 s |
| Successful resume after reconnect | >= 99% |
| Heartbeat miss rate | < 0.5% of stream-minutes |
| Events dropped (lagged) | < 0.1% |

## Consequences

- The SDK ships one realtime client under `skeleton/client/realtime/` (SSE, resume, heartbeat, backoff, envelope dataclass). `BuildsClient.stream_events` and `AgentsClient` switch to it after #4095 merges.
- The frontend uses `EventSource`, or a fetch-stream polyfill where headers are needed, against `/api/v1/events`, with the same resume and heartbeat rules.
- Jobs publish through the `JobEventPublisher` protocol (#4097). The hub subscribes as a sink on `AppServices.events` (the shared `FanOutPublisher`), so there is no import of queue internals.
- The #3862 chat SSE frames migrate to the v1 envelope. This is additive, and JSON paging is untouched.


## Hardening limits and single-process hub (Jenkins #4128 Sev2)

- **Single process.** The hub, replay ring and presence table live in one process's memory. Running several workers or replicas does NOT share events. A shared bus (Redis Streams / NATS) is future work. Until it exists, deploy realtime on one worker.
- **Epoch cursors.** Every hub has a random per-process epoch. The SSE `id:` line is `<id>-<epoch>`, while the envelope `id` stays a decimal string. A cursor from another process (foreign epoch), one older than the ring (evicted), one ahead of head, or a legacy cursor below this process's seed gets `stream.reset` with `head_cursor`. It never gets a silent gap.
- **Stream lifetime.** A stream lives at most 15 min by default. The hub then sends `stream.reauth` with `{cursor, reason:"max_lifetime"}` and closes. `RealtimeClient` reconnects immediately from that cursor. The transport mints a fresh seal and the backoff is not advanced.
- **Caps.** 8 streams per principal (429 + `Retry-After`) and 10000 per process (503). Presence meta is capped at 2 KiB (413) and members at 256 per scope (422). Both checks run before anything is stored.
- **Presence scope.** Snapshots, join/leave events and `GET /presence?scope=` show a member only to its owner, or to principals that `presence_scope_authorizer(principal, scope)` allows. The default is deny.
- **Verified tenant.** A plain stream is tenant-scoped only when the engine backend service vouches for it (bearer service token plus gate attester, the same check as `job_id` grants). `wants()` requires `owner == principal` and `event.tenant == sub.tenant`, both live and on replay.
- **Secret guard.** Keys are normalized (camelCase, `-`, and `_`) and matched on substring tokens. Embedded JSON is scanned, and so are percent-encoded and base64 values. bytes and other non-JSON types are rejected, and the envelope has no `default=str`.
- **Metrics.** Realtime series are dropped from `/api/v1/metrics` when it is a public dev surface. They stay on the sealed `/api/v1/events/slo`.
