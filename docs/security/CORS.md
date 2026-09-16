# CORS deployment policy

The API fails closed for cross-origin access when running in a detected deployed environment.

## Production

Set `CORS_ORIGINS` to a comma-separated list of complete HTTP(S) origins, for example:

```dotenv
CORS_ORIGINS=https://app.example.com,https://admin.example.com
```

Origins are normalized and invalid entries are rejected. A missing, blank, malformed, or wildcard-only production value resolves to a non-routable sentinel origin, so the API does not emit permissive CORS headers.

Do not use `CORS_ORIGINS=*` in production.

## Local development

Without a configured value, local development defaults to:

- `http://localhost`
- `http://127.0.0.1`

A local wildcard requires an explicit opt-in:

```dotenv
ALLOW_DEV_CORS_WILDCARD=true
CORS_ORIGINS=*
```

The wildcard opt-in is ignored in detected deployed environments.

## Deployment checklist

- Configure the exact frontend/admin origins in the deployment environment.
- Keep `ALLOW_DEV_CORS_WILDCARD` unset in production.
- Never put credentials, paths, queries, or fragments in `CORS_ORIGINS` values.
- Validate CORS behavior as part of deployment/security regression tests.
