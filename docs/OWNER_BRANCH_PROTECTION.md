# Owner branch-protection bootstrap

`main` must be protected by GitHub repository settings; source-controlled CI cannot make that guarantee by itself. The connected automation app can manage repository content and pull requests, but does not expose the separate **Administration: write** permission required by GitHub's branch-protection endpoint.

This repository therefore keeps an owner-side bootstrap at `scripts/configure_main_protection.sh`. It uses the repository owner's authenticated GitHub CLI session and applies the real GitHub branch-protection control rather than emulating it with another workflow.

## Policy applied

The script protects `main` with these invariants:

- require the canonical `Merge Readiness` check and require the branch to be current before merge;
- bind `Merge Readiness` to the GitHub Actions app (`app_id: 15368`);
- enforce required checks for repository administrators too;
- require changes to arrive through a pull request, while allowing zero mandatory approving reviewers for a single-maintainer repository;
- dismiss stale approvals if approval requirements are increased later;
- require pull-request conversation resolution;
- forbid force pushes and branch deletion.

The API payload keeps the legacy `contexts` array empty and uses the modern `checks` array for the exact context/app binding.

## Run as the repository owner

Authenticate `gh` with the owner account or a fine-grained token that has **Administration: write** for this repository. Do not place the token in this repository or command history.

Preview without changing GitHub:

```bash
REPO=Apeloff1/Skeleton bash scripts/configure_main_protection.sh --dry-run
```

Apply:

```bash
REPO=Apeloff1/Skeleton bash scripts/configure_main_protection.sh --apply
```

Verify:

```bash
REPO=Apeloff1/Skeleton bash scripts/configure_main_protection.sh --verify
```

The script exits non-zero if the active identity is not an administrator, `main` is unprotected, the required check is missing, or the resulting protection policy is weaker than expected.

## Tracking

Issues #127, #540, and #784 remain open until GitHub itself reports `main` as protected and the required merge gate is enforced. Landing this script removes the tooling dead end; running it with an owner-authorized `gh` session completes the external/admin-only step.
