# Owner-side GitHub security controls

Some repository guarantees live in GitHub settings rather than in source control. The connected automation app can maintain code, pull requests, issues, and CI, but it may not expose repository `Administration: write`. Repository ownership alone does not grant that permission to the app connection.

This repository therefore keeps the desired owner controls executable and auditable through the repository owner's own GitHub CLI authentication instead of weakening CI to compensate for a connector permission boundary.

## Required owner controls

The source-controlled security model expects:

- `main` is protected;
- the stable `Merge Readiness` check is required in strict/up-to-date mode;
- branch protection applies to administrators;
- changes flow through pull requests, while a single-maintainer repository may use zero mandatory approving reviews;
- review conversations must be resolved;
- force pushes and branch deletion are blocked;
- the default GitHub Actions token permission is read-only;
- GitHub Actions cannot approve pull requests;
- environment/provider/registry controls are reviewed separately because their correct policy depends on the actual deployment topology.

## Bootstrap branch protection

After `scripts/configure_main_protection.sh` is present on the branch you are operating from:

```bash
REPO=Apeloff1/Skeleton bash scripts/configure_main_protection.sh --dry-run
REPO=Apeloff1/Skeleton bash scripts/configure_main_protection.sh --apply
REPO=Apeloff1/Skeleton bash scripts/configure_main_protection.sh --verify
```

## Bootstrap GitHub Actions defaults

The Actions owner bootstrap is deliberately independent of workflow files. Individual jobs may still request narrow explicit write permissions where their reviewed behavior requires them; the repository-wide default remains read-only.

```bash
REPO=Apeloff1/Skeleton bash scripts/configure_actions_permissions.sh --dry-run
REPO=Apeloff1/Skeleton bash scripts/configure_actions_permissions.sh --apply
REPO=Apeloff1/Skeleton bash scripts/configure_actions_permissions.sh --verify
```

The script sets only:

```text
default_workflow_permissions=read
can_approve_pull_request_reviews=false
```

It does not modify secrets, environments, collaborators, webhooks, deploy keys, or workflow source.

## Audit external controls

Run the read-only owner audit after bootstrapping and periodically after repository-setting changes:

```bash
REPO=Apeloff1/Skeleton BRANCH=main \
  bash scripts/audit_owner_security_controls.sh
```

The audit reads and reports:

- owner/admin permission for the active `gh` identity;
- branch protection and the expected merge-gate invariants;
- Actions default token and PR-approval settings;
- repository ruleset count;
- GitHub `security_and_analysis` metadata when exposed;
- deployment environment names and protection-rule *types* only.

The audit intentionally never requests or prints repository/environment secret values.

## What remains topology-specific

Do not blindly automate these controls without first defining the deployment model:

- environment names and required reviewers;
- provider IAM and credential lifetime;
- registry/package immutability and retention;
- production deployment permissions;
- external audit-log retention;
- emergency administrator/break-glass identities.

Those controls should be added only when the repository has a real environment/provider to bind them to. A source-only placeholder is not equivalent to external enforcement.

## Permission boundary

If an owner script receives `403 Resource not accessible by integration`, confirm it is being run with the owner's local `gh` authentication rather than through a GitHub App installation token. These scripts exist specifically so the repository can use the owner's legitimate administration authority without granting broad administration rights to routine automation.
