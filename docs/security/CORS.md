# CORS deployment policy

The backend resolves CORS configuration before Starlette constructs `CORSMiddleware`, while preserving normal process-environment-over-`.env` precedence.

## Production

Set `CORS_ORIGINS` to a comma-separated list of complete HTTP(S) origins, for example:

```dotenv
CORS_ORIGINS=https://app.example.com,https://admin.example.com
```

A detected deployed runtime fails closed when `CORS_ORIGINS` is missing, blank, malformed, partially malformed, or contains `*`. The resolved value becomes the non-routable sentinel origin `https://cors-disabled.invalid`, so the historical server fallback cannot silently enable wildcard CORS.

Origins must not contain credentials, paths, queries, fragments, or invalid ports.

## `.env` load ordering

`backend/server.py` imports the execution/CORS guard before it calls `load_dotenv`. To avoid replacing an explicit local `.env` value with a synthetic default, the guard reads `backend/.env` as a **non-mutating fallback** during its early bootstrap. A value already present in the process environment always wins, matching `load_dotenv(..., override=False)` semantics.

This also means a deployment marker such as `ENVIRONMENT=production` in `.env` is considered when choosing the early CORS default.

## Local development

When no origin is configured, local development is restricted to:

- `http://localhost`
- `http://127.0.0.1`

A development wildcard requires an explicit opt-in:

```dotenv
ALLOW_DEV_CORS_WILDCARD=true
CORS_ORIGINS=*
```

The wildcard opt-in is ignored for detected deployed runtimes.

## Failure behavior

The policy fails closed rather than silently dropping a bad member from an allowlist. For example, `https://good.example,not-an-origin` rejects the complete configured list instead of accepting only the valid member.

Deployment checks should verify the effective allowlist for the target environment and keep `ALLOW_DEV_CORS_WILDCARD` unset in production.
