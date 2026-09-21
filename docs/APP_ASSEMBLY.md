# Application Assembly

This repository is being consolidated into one coherent application while
preserving the internal boundaries that already carry production behavior.

The canonical application boundary is now the `skeleton.app` package plus
`skeleton/app/manifest.json`. Docker Compose remains the process supervisor;
the assembly layer gives the repository one topology, one preflight contract,
and one operator command.

## Application surfaces

| Service | Role | Public development endpoint |
| --- | --- | --- |
| `frontend` | Expo / browser interface | `http://localhost:3000` |
| `backend` | Tutolage application API | `http://localhost:8001` |
| `skeleton` | Skeleton v16 engine API | `http://localhost:8010` |
| `mongo` | durable state | local-only host binding |
| `chroma` | optional vector store | `http://localhost:8000` with `--full` |

The backend and Skeleton API remain separate processes during consolidation.
Combining them prematurely would create route, dependency, startup, and
security regressions. They are one application at the operational boundary
and can be progressively reconciled behind that boundary.

## Canonical commands

```bash
# Inspect topology
python -m skeleton app status

# Structural repository validation
python -m skeleton app check

# Validate Docker plus required runtime environment
python -m skeleton app check --runtime

# Build and start the core application
python -m skeleton app up
# app up waits for frontend + backend + engine readiness before success

# Include optional Chroma
python -m skeleton app up --full

# Inspect / operate
python -m skeleton app ps
python -m skeleton app smoke
python -m skeleton app logs backend
python -m skeleton app logs -f
python -m skeleton app config
python -m skeleton app down
```

After startup, `python -m skeleton app smoke` probes the frontend, backend health endpoint, and Skeleton liveness endpoint as one application verdict. `app up` performs the same bounded readiness verification by default; `--no-verify` is reserved for diagnostics where Compose launch success is intentionally inspected separately.\n\nThe CLI never uses a shell to construct Docker commands. Service names are
validated against the manifest before they are passed to Compose.

## Runtime modes

The canonical Compose file runs application code from built images. Source
bind-mounts are isolated in `docker-compose.hot.yml`.

```bash
# Built development images, verified after startup
python -m skeleton app up

# Development images plus source bind mounts for hot reload
python -m skeleton app up --hot

# Production backend stage + production Nginx frontend stage
python -m skeleton app up --production
```

`--production` and `--hot` are intentionally mutually exclusive. Production
keeps the public frontend URL at `http://localhost:3000` while mapping that
host port to Nginx's container port 8080, so the same readiness manifest works
in both modes.

## Runtime configuration

Copy `.env.example` to `.env` and set at least:

- `MONGO_URL`
- `SKL_MONGO_URI`
- `MONGO_INITDB_ROOT_PASSWORD`
- `JWT_SECRET`

Optional provider/payment/seal values remain optional until the corresponding
feature is used. `app up` fails closed when required runtime values are empty
or obvious placeholders.

## Frontend endpoint boundary

`frontend/utils/apiBase.ts` is the single endpoint resolver for browser and
native clients. Backend clients consume `API_BASE`; Skeleton-engine clients
consume `SKELETON_API_BASE`.

Resolution is explicit override first, then browser same-origin for
reverse-proxied deployments, then the local assembled ports
(`:8001` backend, `:8010` Skeleton). Do not read `EXPO_PUBLIC_*_URL`
directly from feature clients.

The engine liveness contract is `GET /api/v1/health/live`; frontend health
checks must not invent a shorter `/health` path on the Skeleton service.

## Production web ingress

The production Nginx image is the browser-facing ingress for the assembled app.
When no explicit public endpoint override is baked into the Expo export,
`apiBase.ts` uses the browser origin. Nginx then routes:

- `/api/v1/*` to the Skeleton engine service.
- all other `/api/*` traffic to the application backend.

Development remains explicit-port based (`:8001` backend and `:8010` engine)
because the Expo development server is not the production reverse proxy.

## Assembly rules

1. New user-facing capabilities should attach to one of the declared service
   boundaries, not create another top-level application.
2. New long-running services must be added to both Docker Compose and the
   application manifest in the same change.
3. Browser-facing environment variables must use host-resolvable URLs. Docker
   service DNS names are internal implementation details and must not be
   embedded into the exported frontend bundle.
4. `python -m skeleton app check` is the minimum structural regression gate
   for assembly work.
5. Existing subsystem PRs should reconcile into
   `integration/app-consolidation` rather than create a competing assembly
   trunk.
