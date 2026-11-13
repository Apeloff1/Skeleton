# `create_app` composition order

Source: `skeleton/api/server.py::create_app` (the `skeleton/ai/runtime/api/server.py` copy is a twin).

## Build order (as written)

1. `FastAPI(title="Skeleton API", version="16.0.0")`, `RuntimeServiceLifecycle("skeleton")` on
   `app.state.runtime_lifecycle`, then `install_error_handlers(app)`.
2. `RuntimeAdmissionMiddleware` (exempt prefix `/api/v1/health`): refuses traffic until the
   lifecycle is ready and while draining.
3. Routers under `/api/v1`, in order: `routes`, `command_routes`, the 13 `swarm_*_routes`
   routers, `engine_routes`, then `projects_routes` (restored after the #4139 stale-base merge).
4. `cockpit` router, mounted **without** a prefix.
5. `omnifabric_routes` under `/api/v1` when `SKELETON_OMNIFABRIC_API` is not `0/false/no/off`
   (default on). It is mounted *before* the gate, so the gate covers `/api/v1/omnifabric/*`;
   it is never an open prefix. Cortex is not mounted here.
6. Realtime (ADR #4101): `RealtimeHub(authorizer=sealed_principal_authorizer)` is stored on
   `app.state.realtime_hub`, and `realtime_routes` goes under `/api/v1`.
7. `install_gate(app, policy=GatePolicy(open_prefixes=_gate_open_prefixes(),
   body_limits=_gate_body_limits()))`.
8. `install_registered_agent_edge(app)`: folds in a registered agent-edge gateway, if any,
   using the gate's extend-only `register_domain`.
9. `CORSMiddleware` (methods GET/POST/OPTIONS, no credentials).
10. Startup/shutdown handlers, plus the inline `/`, `/health`-style and `/cortex/status` routes.
11. `reject_cortex_secret_routes(app)`: a one-shot walk of the assembled route graph that
    raises if any `/secrets` path or cortex `register_routes` endpoint is present.
12. `CortexRouteGuardMiddleware(guarded_app=app)`: added last, so it is the **outermost** layer.

## Request path (outer to inner)

Starlette `add_middleware` is LIFO, so a request passes through:

`CortexRouteGuard -> CORS -> HeaderBound -> RequestSeal -> WriteAdmit -> BodyBound -> WormAudit
-> Auth -> PolicyGate -> RuntimeAdmission -> router`

(`install_gate` registers PolicyGate first and HeaderBound last.)

## Open prefixes

`_gate_open_prefixes()` = `DEFAULT_OPEN_PREFIXES` + `/` (exact only) + `/api/v1/engine`, plus
dev surfaces when `_public_dev_surfaces_enabled()`. Matching is segment-aware
(`_matches_path_prefix`): `/api/v1/engine` does not open `/api/v1/engineer`. The engine
prefix skips the HMAC gate but has its own service bearer token and principal validation.

## Cortex guard fingerprint

`route_table_fingerprint(app)` is a cheap identity/shape tuple over the whole route graph,
including FastAPI's lazy `_IncludedRouter` children. On each request the middleware compares it
with the last fingerprint that passed a full walk. The full `iter_route_paths` walk reruns only
when the fingerprint changed, so late or nested router additions are still refused. Uninspectable
nodes (opaque mounts, cycles, depth over `_MAX_DEPTH`, StaticFiles at or above a protected
prefix) fail closed.

## References

- `skeleton.api.server:create_app`
- `skeleton.api.server:_gate_open_prefixes`
- `skeleton.api.server:_gate_body_limits`
- `skeleton.api.server:_omnifabric_api_enabled`
- `skeleton.api.server:_bind_realtime`
- `skeleton.api.middleware:install_gate`
- `skeleton.api.middleware:GatePolicy`
- `skeleton.api.middleware:DEFAULT_OPEN_PREFIXES`
- `skeleton.api.middleware:_matches_path_prefix`
- `skeleton.api.agent_edge_mount:install_registered_agent_edge`
- `skeleton.api.cortex_mount_guard:reject_cortex_secret_routes`
- `skeleton.api.cortex_mount_guard:CortexRouteGuardMiddleware`
- `skeleton.api.cortex_mount_guard:route_table_fingerprint`
- `skeleton.api.cortex_mount_guard:iter_route_paths`
- `skeleton.kernel.runtime_supervision:RuntimeAdmissionMiddleware`
- `skeleton.kernel.runtime_supervision:RuntimeServiceLifecycle`
