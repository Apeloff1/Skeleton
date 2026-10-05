# Owner-side GitHub security controls

Some repository guarantees live in GitHub settings rather than source control. Routine automation may not have repository `Administration: write`, so these controls remain owner-operated and auditable instead of weakening CI around the permission boundary.

## Required owner controls

- `main` is protected.
- Stable `Merge Readiness` is required in strict/up-to-date mode.
- Protection applies to administrators.
- Changes flow through pull requests.
- Review conversations must be resolved.
- Force pushes and branch deletion are blocked.
- The default GitHub Actions token permission is read-only.
- GitHub Actions cannot approve pull requests.
- Environment/provider/registry controls are reviewed against the actual deployment topology.

## Actions defaults

```bash
REPO=Apeloff1/Skeleton bash scripts/configure_actions_permissions.sh --dry-run
REPO=Apeloff1/Skeleton bash scripts/configure_actions_permissions.sh --apply
REPO=Apeloff1/Skeleton bash scripts/configure_actions_permissions.sh --verify
```

The bootstrap changes only the repository-wide Actions defaults and never reads or modifies secret values.

## External-control audit

```bash
REPO=Apeloff1/Skeleton BRANCH=main bash scripts/audit_owner_security_controls.sh
```

The audit reports protection metadata, Actions defaults, ruleset count, security-analysis metadata when available, and deployment environment names/protection-rule types only. It does not request secret values.

## Permission boundary

If an owner script receives `403 Resource not accessible by integration`, run it with the repository owner's authenticated `gh` session rather than a GitHub App installation token. This preserves least privilege for routine automation.
