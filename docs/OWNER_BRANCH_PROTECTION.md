# Owner branch-protection bootstrap

`main` must be protected by GitHub repository settings; source-controlled CI cannot make that guarantee by itself. The connected automation app can manage normal repository content and pull requests, but its installation does not expose the separate **Administration: write** permission required by GitHub's branch-protection endpoint.

This repository therefore keeps an owner-side bootstrap at `scripts/configure_main_protection.sh`. It uses the repository owner's own authenticated GitHub CLI session and applies the real GitHub branch-protection control rather than emulating it with another workflow.

## Policy applied

The script protects `main` with these invariants:

- require the canonical `Merge Readiness` check and require the branch to be current before merge;
- enforce required checks for repository administrators too;
- require changes to arrive through a pull request, while allowing a single-maintainer repository to use zero mandatory approving reviewers;
- dismiss stale approvals if approval requirements are increased later;
- require pull-request conversation resolution;
- forbid force pushes and branch deletion;
- leave the branch writable through the normal protected pull-request path.

The GitHub UI may present the check as `CI/CD / Merge Readiness`; the branch-protection API consumes the check-run context name `Merge Readiness`. Historical repository check runs confirm that exact context is emitted by GitHub Actions.

## Run as the repository owner

Authenticate `gh` with the owner account or a fine-grained token that has **Administration: write** for this repository. Do not place the token in this repository or in command history.

Preview the exact policy without changing GitHub:

```bash
REPO=Apeloff1/Skeleton bash scripts/configure_main_protection.sh --dry-run
```

Apply it:

```bash
REPO=Apeloff1/Skeleton bash scripts/configure_main_protection.sh --apply
```

Verify it later without changing settings:

```bash
REPO=Apeloff1/Skeleton bash scripts/configure_main_protection.sh --verify
```

The script exits non-zero if the active GitHub identity is not a repository admin, if `main` is still unprotected, or if the resulting settings do not match the hardened policy.

## Emergency override

Do not keep an owner bypass permanently enabled merely to avoid CI friction. The emergency process in `docs/SECURITY_CI_POLICY.md` remains the authority for exceptional recovery: document the incident, keep the change minimal, preserve checks that can still run, restore protection immediately afterward, and validate the resulting `main` state.

## Tracking

Issues #127 and #540 remain open until GitHub itself reports `main` as protected and the required merge gate is enforced. Landing this script removes the tooling dead end; running it with an owner-authorized `gh` session completes the external/admin-only step.
