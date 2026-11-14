# Realtime transport (live builds, agent activity, presence)

Implementation guide for the decision in the ADR
[`docs/architecture/ADR-realtime-transport.md`](https://github.com/Apeloff1/Skeleton/pull/4101) (PR #4101, TD ruling).
If this guide and the ADR disagree, the ADR wins.

| Piece | Location | Owner |
|---|---|---|
| Envelope v1, hub, secret guard, SLOs, SSE framing, job sink | `skeleton/realtime/` | Network / Online (Walt) |
| HTTP endpoints | `skeleton/api/realtime_routes.py`; hub lifecycle in `skeleton/api/server.py` | Network / Online (Walt) |
| SDK client (SSE, resume, backoff, heartbeat, presence) | `skeleton/client/realtime/` | Network / Online (Walt), reviewed by the SDK owner (Coder Lead, #4095) |
| Job queue + `FanOutPublisher` | `skeleton/app_services/events.py` (#4097) | Internal Systems |

## Endpoints

All of these sit behind the existing gate. `/api/v1/events` and `/api/v1/presence` are written gate
domains (`realtime`), so the `x-gf-seal` HMAC seal is required. The verified principal reaches handlers
as `x-zaibatsu-attester`.

| Method and path | Purpose |
|---|---|
| `GET /api/v1/events?channels=build,agent,presence[&job_id=][&cursor=]` | Canonical multiplexed SSE stream. `channels` defaults to all three. |
| `GET /api/v1/engine/executions/{execution_id}/events` | Existing engine route. JSON is unchanged. With `Accept: text/event-stream` it becomes the execution-scoped filtered view (`job_id = execution_id`, channels `build` and `agent`), with the same envelope and the same engine service-token authorization. |
| `POST /api/v1/presence` | Body `{action: join\|heartbeat\|leave, client_id, scope="app", meta?}`. Returns the scope snapshot. |
| `GET /api/v1/presence?scope=` | Current members of a scope. |
| `GET /api/v1/events/slo` | SLO snapshot and hub stats. |

WebSocket is deliberately not offered (ADR §1). NDJSON is not supported for these endpoints.

## Envelope v1

```json
{
  "v": 1,
  "id": "1792252800123456",
  "ts": "2026-10-17T16:00:00.123Z",
  "channel": "build",
  "type": "build.progress",
  "payload": {"pct": 40, "source_id": "3"},
  "job_id": "job-7",
  "correlation_id": "req-abc"
}
```

| Field | Type | Notes |
|---|---|---|
| `v` | int | `1`. A breaking change bumps it. Unknown fields are ignored. |
| `id` | string | Decimal, monotonic per hub stream, shared by all channels, so one cursor resumes the whole multiplexed stream. Seeded from wall-clock µs at hub start, so ids keep increasing across restarts. Equal to the SSE `id:` line. |
| `ts` | string | RFC 3339 UTC with millisecond precision, set at hub publish time. |
| `channel` | string | `build`, `agent` or `presence`. |
| `type` | string | `<channel>.<verb>`. |
| `payload` | object | At most 64 KB, secret-scrubbed. A producer's own id is kept here as `payload.source_id`. |
| `job_id`, `correlation_id` | string, optional | Bounded identifiers `[A-Za-z0-9][A-Za-z0-9._:@/-]{0,127}`. Free text is dropped. |

Known types:

- build: `build.started`, `build.progress`, `build.log`, `build.completed`, `build.failed`
- agent: `agent.started`, `agent.step`, `agent.completed`
- presence: `presence.joined`, `presence.left` (with `reason`: `left` or `heartbeat_timeout`), `presence.snapshot`

`presence.snapshot` is sent to each presence subscriber when it connects. It is not stored, and its id
is the current head.

Control events have no `id:` line, so they never move `Last-Event-ID`:

- `stream.reset {reason, cursor, head_id, oldest_id}`: the cursor aged out of the replay ring, is ahead
  of the stream, or belongs to a previous hub. The client refetches state over REST and continues from
  `head_id`.
- `stream.lagged {dropped, resume_from}`: the subscriber's queue overflowed and the oldest events were
  dropped. The client reconnects from its last delivered id, or from `resume_from` if it has none yet,
  and the ring replays the gap. `resume_from` is an additive field.

## SSE frames

```
retry: 2000

id: 1792252800123456
event: build.progress
data: {"channel":"build","id":"1792252800123456",...}

event: stream.lagged
data: {"payload":{"dropped":3,"resume_from":"1792252800123452"},"ts":"...","type":"stream.lagged","v":1}

: hb
```

- The client resumes with the `Last-Event-ID` header, or `?cursor=` when it can't set headers.
- The server writes a heartbeat comment `: hb` every 15 s. A client that sees no bytes for 45 s treats
  the stream as dead.
- Browsers: `EventSource` can't send `x-gf-seal`, so use a fetch-stream reader against `/api/v1/events`
  with the same rules.

## Server semantics (`RealtimeHub`)

- Replay ring of 4096 events by default. A resume replays everything the ring still holds. During
  replay the subscriber's queue bound is widened by the size of the backlog.
- Each subscriber has a live queue of 512 by default. On overflow the oldest events are dropped and
  one merged `stream.lagged` is sent. Publishers never block.
- `publish()` is thread-safe, so job workers can publish from other threads.
- Secret guard (#3637) runs on every publish and every presence `meta`. It reuses
  `skeleton.observability.redaction` (sensitive keys and inline `key=value` credentials) plus the
  sandbox credential patterns (GitHub, OpenAI, AWS, Slack, JWT, PEM, bearer). The default mode redacts;
  `PayloadSecretGuard(mode="reject")` refuses the publish instead.
- `authorizer(principal, channel)` hook: by default any verified principal is allowed. Presence
  `client_id`s are bound to the principal that joined, so another principal can't take over or remove
  them.
- Presence members expire after 45 s without a heartbeat (`presence.left` with reason
  `heartbeat_timeout`).

## Jobs seam (#4097)

`skeleton.realtime.HubJobEventSink` implements the `JobEventPublisher` shape (`publish(event: dict)`).
At startup, `api/server.py` calls `attach_hub(AppServices.events, sink)` when app services are mounted
on `app.state.app_services` or `ServerState.app_services`. Otherwise nothing happens, so either PR can
merge first. The sink re-sequences producer envelopes onto the hub stream, keeps the producer id as
`payload.source_id`, carries `job_id` and `correlation_id`, and never raises into the fan-out
(rejections are counted in `realtime.publish_rejected{reason=job_sink}`).

## SDK client (`skeleton.client.realtime`)

```python
from skeleton.client.realtime import RealtimeClient, SSETransport, PresenceClient, HttpPresencePoster

client = RealtimeClient(SSETransport(base_url, headers=mint_seal_headers), channels=("build", "agent"))
async for event in client.events():
    ...
```

- Backoff is exponential with full jitter over the SDK `RetryPolicy` (base 0.5 s, cap 30 s). It resets
  after 60 s of a healthy stream, and the server `retry:` value is treated as a floor.
- A `stream.lagged` triggers an immediate reconnect. A `stream.reset` calls `on_reset` and moves the
  cursor to the head. 401 and 403 are never retried.
- `RetryPolicy` and `SkeletonClientError` come from `skeleton.client` once #4095 lands. Until then,
  import-guarded fallbacks with the same names and signatures live in `skeleton/client/realtime/_compat.py`.
- Nothing is exported from `skeleton/client/__init__.py` yet; that follows #4095.

## SLOs (ADR §5)

Measured server-side by `RealtimeSLO` and exported through the existing observability collector
(`ServerState.metrics`, served at `/api/v1/metrics`) under `realtime.*`.

| SLI | Target | Metric |
|---|---|---|
| Stream connect success | ≥ 99.5% / 28 d | `realtime.connect_successes / connect_attempts` |
| Publish-to-delivery latency | p95 < 500 ms, p99 < 2 s | `realtime.delivery_latency_ms` (histogram, live events only) |
| Resume success after reconnect | ≥ 99% | `realtime.resume_successes / resume_attempts` (failures are `stream_resets`) |
| Heartbeat miss rate | < 0.5% | `realtime.heartbeat_misses / (heartbeats_sent + heartbeat_misses)`; a miss is a server write gap longer than 2× the interval (event-loop stall) |
| Lagged drops | < 0.1% | `realtime.events_dropped / events_published` |

Also exported: `reconnects`/`disconnects{reason}`, `events_published{channel}`, `events_delivered`,
`events_resumed`, `stream_lagged`, `presence_timeouts`, `payload_redactions`,
`publish_rejected{reason}`, and the gauge `active_connections`.

## Follow-ups (not in this change)

- Move the #3862 chat SSE frames (`/api/ai/chat/turns/{thread_id}/events`) onto envelope v1. This is
  additive; JSON paging stays unchanged.
- Add `/api/v1/events` to the SDK route-conformance list, and switch `BuildsClient.stream_events` over
  once #4095 merges.
- Frontend fetch-stream adapter.


## Hardening limits and single-process hub (Jenkins #4128 Sev2)

- **Single process.** The hub, replay ring and presence table live in one process's memory. Running several workers or replicas does NOT share events. A shared bus (Redis Streams / NATS) is future work. Until it exists, deploy realtime on one worker.
- **Epoch cursors.** Every hub has a random per-process epoch. The SSE `id:` line is `<id>-<epoch>`, while the envelope `id` stays a decimal string. A cursor from another process (foreign epoch), one older than the ring (evicted), one ahead of head, or a legacy cursor below this process's seed gets `stream.reset` with `head_cursor`. It never gets a silent gap.
- **Stream lifetime.** A stream lives at most 15 min by default. The hub then sends `stream.reauth` with `{cursor, reason:"max_lifetime"}` and closes. `RealtimeClient` reconnects immediately from that cursor. The transport mints a fresh seal and the backoff is not advanced.
- **Caps.** 8 streams per principal (429 + `Retry-After`) and 10000 per process (503). Presence meta is capped at 2 KiB (413) and members at 256 per scope (422). Both checks run before anything is stored.
- **Presence scope.** Snapshots, join/leave events and `GET /presence?scope=` show a member only to its owner, or to principals that `presence_scope_authorizer(principal, scope)` allows. The default is deny.
- **Verified tenant.** A plain stream is tenant-scoped only when the engine backend service vouches for it (bearer service token plus gate attester, the same check as `job_id` grants). `wants()` requires `owner == principal` and `event.tenant == sub.tenant`, both live and on replay.
- **Secret guard.** Keys are normalized (camelCase, `-`, and `_`) and matched on substring tokens. Embedded JSON is scanned, and so are percent-encoded and base64 values. bytes and other non-JSON types are rejected, and the envelope has no `default=str`.
- **Metrics.** Realtime series are dropped from `/api/v1/metrics` when it is a public dev surface. They stay on the sealed `/api/v1/events/slo`.
