# C4 container

| Container | Code | Role |
|-----------|------|------|
| Engine API | `skeleton/api/server.py` `create_app` | FastAPI process. The mount list is [api-gateway.md](../api-gateway.md). `create_app` leaves cortex, OmniFabric, Pack H, and the GameForge sidecar unmounted. Projects routes arrive with #4097 at `/api/v1/projects`. |
| Backend API | `backend/server.py` | Product control plane. Own health routes under `/api/health`. Proxies engine work with a service token. |
| App shell | `frontend/` | Expo/browser UI. Session and query foundation are landing separately. |
| Client SDK | `skeleton/client` | In-process HTTP client for auth, agents, and builds. Projects client uses `skeleton.projects.v1` at `/api/v1/projects`. |
| Worker / CLI | `python -m skeleton`, `skeleton/deploy/harness.py` | `skeleton game` is a thin adapter over `build_playable_game`. The dev harness boots Genesis and mounts the main router plus command routes, leaving the GameForge sidecar unmounted. |
| MongoDB | compose service | Canonical memory and product records. |
| Chroma | compose service | Vector projection. Not the memory authority. |

Health: the engine exposes `GET /api/v1/health`, `/health/live`, and `/health/ready`. The backend exposes `GET /api/health/live` and `/api/health/ready`. Payloads stay as they are; `skeleton/contracts/health.py` is the typed reading of them.

Logs, traces, and counters go through `skeleton/observability/platform_hooks.py`, which delegates to the existing structured logger and tracer. Tracing stays in-process unless `SKL_OBS_TRACING_ENABLED` is later wired to an exporter. That flag already exists on observability settings and defaults off.
