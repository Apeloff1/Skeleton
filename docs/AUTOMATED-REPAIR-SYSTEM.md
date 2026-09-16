# Automated repair system

Skeleton uses pull-request-based repair automation with explicit trust boundaries. Automated repair must never treat an issue, pull request description, repository file, model response, generated patch, dependency update, or workflow output as permission to bypass security controls.

## Current layers

1. **Dependabot security updates** raise pull requests when patched dependency versions are available.
2. **Dependabot version updates** use `.github/dependabot.yml` to keep supported ecosystems current.
3. **Fail-closed Dependabot merge worker** evaluates trusted Dependabot pull requests from the repository default branch without checking out or executing pull-request code.
4. **Code-scanning remediation** may propose fixes through supported GitHub security tooling, but those fixes remain pull requests subject to repository validation.
5. **Repository backlog automation** may gather deterministic evidence and advisory model output, but model output is not policy or mutation authority.

## Dependabot automatic-merge boundary

The scheduled merge worker verifies its own safety conditions before every merge attempt instead of assuming repository settings or branch protection will always remain unchanged.

A Dependabot pull request is eligible only when all of the following hold:

- the author is exactly `dependabot[bot]`;
- the head branch begins with `dependabot/`;
- the head belongs to the same repository;
- the target is the repository default branch;
- the pull request is open, non-draft, and GitHub reports it as mergeable;
- the changed-file set is non-empty and contains only explicitly allowlisted live dependency manifests or lockfiles;
- archived `satellites/**/branch-snapshots/**` manifests are rejected even when their filenames otherwise resemble supported dependency files;
- every required workflow has a completed successful `pull_request` run for the exact current head SHA;
- no required workflow is missing, pending, cancelled, skipped, neutral, stale, or successful only for another head SHA;
- the candidate head contains the observed current default-branch head;
- immediately before mutation, the worker re-fetches pull-request identity, files, workflow runs, and the default-branch head and repeats the policy evaluation;
- the pull-request identity, file set, required workflow set, head SHA, and observed base head remain stable across the mutation boundary;
- the squash merge request is bound to the exact validated head SHA.

If any condition cannot be proved, the worker does nothing. A workflow rename, missing workflow run, merge conflict, moved base or head, ambiguous file path, unsupported dependency surface, failed security gate, or API error leaves the pull request for normal review.

## Trusted-code execution boundary

The merge workflow runs only from the repository default branch on `schedule` or `workflow_dispatch`. It checks out that trusted branch explicitly with persisted checkout credentials disabled.

It does **not**:

- use `pull_request_target` to execute pull-request content;
- check out a Dependabot head ref;
- import Python from a Dependabot branch;
- execute changed package scripts, installers, tests, build steps, or repository code from the candidate pull request;
- read workflow logs as instructions;
- accept model output as merge authority;
- force-push `main` or bypass repository policy.

The worker reads GitHub metadata, changed filenames, and workflow-run metadata for the candidate head. Project validation remains in the normal pull-request workflows.

## Dependency-file allowlist

Eligible files are limited to canonical live dependency manifests and lockfiles such as `pyproject.toml`, `package.json`, supported lockfiles, and `requirements*.txt` paths. Non-canonical or traversal paths fail closed.

Workflow files, Dockerfiles, scripts, source files, security-control files, and archived branch-snapshot manifests are outside the automatic-merge boundary even when a basename resembles an allowlisted dependency file.

## Required workflow baseline

The default policy always requires successful exact-head evidence for:

- `CI/CD`
- `Merge Readiness`
- `Secret scanning`
- `Malware Gate`
- `Repository Hygiene Gate`
- `Artifact Policy`
- `Provenance Policy`
- `PR Hygiene`
- `Dependency Review`

Additional gates are required when their live path filters apply. `Dependency Surface Guard` is added for `pyproject.toml`, and `Backend Quality` is added for dependency files under the broad backend/source roots covered by that workflow.

`DEPENDABOT_REQUIRED_WORKFLOWS` may add validation requirements but cannot remove the built-in baseline. An empty or incomplete environment override therefore cannot weaken policy.

## Merge-cap and failure behavior

The worker has a bounded per-run merge cap. Configuration may reduce operational throughput, but it cannot expand beyond the hard safety limit encoded in policy.

A failed or missing check, ambiguous dependency change, unsupported ecosystem, merge conflict, stale or moved base/head, cross-repository candidate, repository-policy change, malformed API response, or security scanner disagreement stops automatic merging for that candidate. The pull request remains open for diagnosis and normal review.

Branch protection and repository rulesets remain defense in depth; the worker's own fail-closed validation is bound to the exact candidate head and current default-branch state immediately before mutation.
