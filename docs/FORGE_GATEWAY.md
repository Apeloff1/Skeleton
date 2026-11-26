# Forge gateway (backend-for-frontend for sealed engine routes)

The Skeleton engine protects `/api/v1/game/build` and `/api/v1/gameforge/*` with an
HMAC request seal (`x-gf-seal`). A seal secret in a browser or mobile bundle would be
public, so the Expo app never holds one. Instead it calls the application backend,
which authenticates the user and seals the engine request server-side.

```
Expo app ──Bearer──▶ backend /api/forge-gateway/* ──x-gf-seal──▶ engine /api/v1/*
```

| Gateway route | Role | Engine route |
| --- | --- | --- |
| `GET /api/forge-gateway/status` | viewer | none (reports readiness, no secrets or URLs) |
| `POST /api/forge-gateway/game/build` | editor | `POST /api/v1/game/build` (202 + `status_ref`) |
| `GET /api/forge-gateway/game/build/{id}` | viewer | `GET /api/v1/game/build/{id}` |
| `POST /api/forge-gateway/gameforge/run` | editor | `POST /api/v1/gameforge/run` |
| `POST /api/forge-gateway/gameforge/intake` | editor | `POST /api/v1/gameforge/intake` |

## Guarantees

- **Seal custody.** Each upstream request gets a fresh 30-second PrincipalAuth
  seal (`forge-gateway.<actor>.<expiry>.<hmac>`) minted from `GF_SEAL_SECRET` /
  `GF_SEAL_KEYRING`. The seal and its key never appear in a response. Without a key
  the gateway returns 503 (fails closed).
- **Per-user isolation.** The seal's attester is a pseudonymous actor:
  `app-` plus the first 32 hex characters of `sha256(tenant, lower(email))`. The
  engine already scopes build status by actor and tenant, so another user's build
  id returns 404.
- **Allow-listed bodies.** Pydantic models with `extra="forbid"`. Server
  file-write keys (`project_root`, `out`, `overwrite`) and identity overrides
  (`actor_id`, `tenant_id`) are rejected with 422 before anything reaches the
  engine. Briefs are capped at 4000 characters.
- **Headers.** Only `Idempotency-Key` (validated) and `X-Request-Id` are
  forwarded. Client `Authorization` never reaches the engine.
- **Abuse limits.** Build starts are limited per user, `FORGE_GATEWAY_BUILDS_PER_MINUTE`
  per minute (default 6), returning 429 with `Retry-After`. Responses are capped
  at 16 MiB.
- **Error mapping.** Engine 401 becomes 502 ("rejected this server's credentials",
  logged). A charter denial (403) passes through. 400/404/409/413/422/429 pass
  through with the engine's `detail`. 503 becomes 503 with `Retry-After`. Other 5xx
  become 502 with a fixed message, so no engine internals leak. A timeout is 504.
- **Observability.** One `forge_gateway.call` log line per request: operation,
  pseudonymous actor ref, status, latency and request id.

## Configuration

| Variable | Meaning |
| --- | --- |
| `FORGE_GATEWAY_ENGINE_URL` | Engine origin. Falls back to `SKELETON_INTERNAL_URL` (Compose: `http://skeleton:8001`). Must be a plain http(s) origin. |
| `GF_SEAL_SECRET` / `GF_SEAL_KEYRING` | The same seal key the engine verifies with (already in the backend's Compose env). |
| `FORGE_GATEWAY_BUILDS_PER_MINUTE` | 1–600, default 6. |
| `FORGE_GATEWAY_TIMEOUT_S` | 1–300, default 30. |

## App

`/new-game` (`frontend/app/new-game.tsx`, `src/forgeGateway/`) is the
prompt → live build → result flow. It is linked from the menu (Build → **New Game
from a Prompt**) and from the Create pillar's **New project** action. It resumes
with `?build=<execution_id>` and retries a start with the same `Idempotency-Key`,
so a lost response never starts a duplicate build.

Tests: `backend/tests/test_forge_gateway.py`, which runs against the real engine app,
and `yarn test:forge-gateway` (model, client and SSR accessibility rendering).
