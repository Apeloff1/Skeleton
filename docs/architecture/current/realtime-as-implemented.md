# Realtime ADR #4101: what main actually implements

The ADR is `docs/architecture/ADR-realtime-transport.md`: SSE only, envelope v1, resume via
`Last-Event-ID` / `?cursor=`, a 15 s heartbeat and 45 s dead-stream detection, and bounded
per-subscriber queues with `stream.lagged`.

## Implemented on main (`9a73a0cb`)

- **Routes** (`skeleton/api/realtime_routes.py`, under `/api/v1`, all sealed by the gate):
  `GET /events` (SSE), `GET /events/slo`, `POST /presence`, `GET /presence`.
- **Hub:** `create_app` builds `RealtimeHub(authorizer=sealed_principal_authorizer)`. The module
  default `_default_authorizer` is `deny_all_authorizer`. `sealed_principal_authorizer` only opens a
  *channel* for any gate-verified principal; per-event owner and job-grant checks in
  `Subscription.wants` decide delivery (Jenkins S1-1).
- **Hub bounds (constructor defaults):** `replay_capacity` 4096, `subscriber_queue` 512,
  `heartbeat_interval_s` 15, `presence_ttl_s` 45, `max_subscribers` 10 000.
- **Wiring:** at startup, `_bind_realtime` binds `hub.slo` to `ServerState.metrics` and
  attaches a `HubJobEventSink` to `AppServices.events` when app services are mounted.
  `_close_realtime` runs during shutdown.
- **Secret guard:** `PayloadSecretGuard` walks payloads to depth 8, redacts by key
  (`SENSITIVE_KEYS` plus `EXTRA_SENSITIVE_KEYS`), and scrubs text through
  `redact_text` + `skeleton.sandbox.sanitizers.redact_secrets`. On a sanitizer error the value
  is replaced with `REDACTED` (fail closed).

## Drift from the #4253 hardening (TD finding, 2026-10-31)

#4253 shows as merged (Oct 28, head `ed9f416a`), but these parts of its reviewed design are
**not** present on main:

- `RealtimeHub.__init__` has no `presence_meta_max_bytes`, `presence_max_members_per_scope`,
  `max_streams_per_principal` or `max_stream_lifetime_s` parameters.
  `skeleton/realtime/limits.py:realtime_limits_from_env` exists, but nothing calls it, and
  `server.py` still has the pre-#4253 hub line.
- `guard.py` has no bounded %- / base64 decode loop. `sanitizers.py` still uses `\bsk-` /
  `\b`-anchored token prefixes, which my #4253 attack tests showed can be bypassed by
  multi-encoded tokens or tokens glued to a preceding letter or digit.
- `skeleton/testing/test_gate_plane_pack_f_agent_edge_gateway.py` allowlists the *new*
  `realtime_limits_from_env` lines, which main doesn't contain.

These should be fixed in normal fix PRs, with no reverts. Until then, treat per-principal stream
caps, stream lifetime and encoded-token redaction as **not enforced**.

## References

- `skeleton.realtime:RealtimeHub`
- `skeleton.realtime:sealed_principal_authorizer`
- `skeleton.realtime:PayloadSecretGuard`
- `skeleton.realtime:HubJobEventSink`
- `skeleton.realtime.hub:deny_all_authorizer`
- `skeleton.realtime.hub:Subscription`
- `skeleton.realtime.hub:EventAccess`
- `skeleton.realtime.guard:EXTRA_SENSITIVE_KEYS`
- `skeleton.realtime.limits:realtime_limits_from_env`
- `skeleton.api.realtime_routes:router`
- `skeleton.api.server:_bind_realtime`
- `skeleton.api.server:_close_realtime`
- `skeleton.sandbox.sanitizers:redact_secrets`
