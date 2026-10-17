# ADR: Canonical realtime transport and event envelope (v1)

- **Status:** Accepted (TD ruling, 2026-10-17)
- **Owner:** Walt (Network / Online Services)
- **Consumers:** SDK (`skeleton/client/`, Coder Lead), Frontend, Jobs/agents (Internal Systems)

## Context

Three realtime-shaped paths exist or are planned:

1. **#3862** (merged): `/api/ai/chat/turns/{thread_id}/events` streams bounded immutable journal events as SSE on `Accept: text/event-stream`, with a cursor sequence. Without that header it keeps JSON paging.
2. **#4085** (merged): the frontend tunnel heartbeat. This is a single-owner liveness probe for the dev/app tunnel. It is not an event channel.
3. **#4095** (draft): the SDK `BuildsClient.stream_events(execution_id)` against `GET /api/v1/executions/{execution_id}/events`, using an SSE/NDJSON parser.

Without a single decision, the SDK and frontend would build three incompatible clients.

## Decision

### 1. One transport: Server-Sent Events over HTTP

- Every server-to-client app event (build progress, agent activity, presence, chat turn replay) is delivered as **SSE** (`Content-Type: text/event-stream`).
- Each frame is `id: <envelope.id>`, `event: <envelope.type>`, `data: <envelope JSON>`.
- **WebSocket is not canonical.** We may add it later behind the same envelope if a bidirectional, high-rate need appears, for example live co-editing. Until then, client-to-server actions (presence join, leave and heartbeat) are plain HTTP `POST`s.
- **NDJSON is not a supported streaming format** for new endpoints. The #4095 parser should treat SSE as primary.

### 2. Endpoint family

| Endpoint | Purpose |
|---|---|
| `GET /api/v1/events?channels=build,agent,presence[&job_id=...]` | Canonical multiplexed stream |
| `GET /api/v1/executions/{execution_id}/events` | Filtered view: `job_id`/`execution_id` scope, same envelope |
| `GET /api/ai/chat/turns/{thread_id}/events` (#3862) | Filtered view for chat. SSE frames adopt the v1 envelope; the JSON paging contract is unchanged |
| `POST /api/v1/presence` | Presence join, heartbeat and leave (body: `{action, scope, client_id}`) |

All endpoints reuse the app's existing auth and the tenant/owner checks.

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
- **Payloads never carry secrets, tokens or credentials** (#3637). The hub publish path enforces this with a guard.

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
- Jobs publish through the `JobEventPublisher` protocol. The hub is a sink, so there is no import of queue internals.
- The #3862 chat SSE frames migrate to the v1 envelope. This is additive, and JSON paging is untouched.
