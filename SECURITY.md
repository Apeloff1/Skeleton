# Security Policy

## Supported code

Security fixes target the active `main` branch and the most recent release line. Older snapshots, forks, and abandoned branches may not receive security updates.

## Reporting a vulnerability

Please report suspected vulnerabilities privately through GitHub's **Security** tab using **Report a vulnerability** / a private security advisory when that option is available.

Do **not** open a public issue for an unpatched vulnerability, and do not include passwords, API keys, access tokens, private customer data, or other secrets in a report.

A useful report includes:

- affected component, route, workflow, or commit;
- impact and realistic attack preconditions;
- minimal reproduction steps or a proof of concept that avoids destructive actions;
- suggested remediation, if known.

If private GitHub reporting is unavailable, disclose only the minimum non-sensitive information needed to establish contact with the repository owner. Do not publish exploitation details before a fix is available.

## Deployment security defaults

Production deployments should preserve the repository's fail-closed defaults:

- `TRUSTED_PROXY_CIDRS` is empty unless exact ingress/proxy networks are explicitly configured;
- `RATE_LIMIT_EXEMPT` is empty unless a narrowly scoped exemption is operationally required;
- `CORS_ORIGINS` is an explicit comma-separated allowlist; use `*` only as a deliberate development choice;
- `HEALTH_DIAGNOSTICS_VERBOSE` remains disabled unless the detailed endpoint is protected by an internal or authenticated ingress;
- `FORCE_HSTS` is enabled only when the authority is guaranteed to be HTTPS-only;
- production secrets are supplied by the deployment secret store and are never committed to the repository.

## Security-sensitive changes

Changes to authentication/authorization, middleware, CI workflows, dependency manifests and lockfiles, container definitions, execution/sandbox code, or deployment configuration should receive explicit security review. Required CI security checks should pass before merge.
