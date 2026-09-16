# Automated repair system

Skeleton uses pull-request-based repair automation with explicit trust boundaries. Automated repair must never treat an issue, pull request description, repository file, model response, generated patch, or dependency update as permission to bypass security controls.

## Current layers

1. **Dependabot security updates** raise pull requests when patched dependency versions are available.
2. **Dependabot version updates** use `.github/dependabot.yml` to keep supported ecosystems current.
3. **Fail-closed Dependabot merge worker** evaluates trusted Dependabot pull requests from the repository's default branch without checking out or executing pull-request code.
4. **Code-scanning remediation** may propose fixes through supported GitHub security tooling, but those fixes remain pull requests subject to repository validation.
5. **Repository backlog automation** collects deterministic repository evidence and may use advisory reasoning; model output is not policy or mutation authority.

## Dependabot automatic-merge boundary

The repository cannot assume branch protection or required-status-check configuration will always be present. The scheduled merge worker therefore verifies its own safety conditions before every merge attempt.

A Dependabot pull request is eligible only when all of the following hold:

- the author is exactly `dependabot[bot]`;
- the head branch begins with `dependabot/`;
- the target is the repository default branch;
- the pull request is open, non-draft, and GitHub reports it as mergeable;
- the changed-file set is non-empty and contains only explicitly allowlisted dependency manifests or lockfiles;
- every configured required workflow has a completed successful `pull_request` run for the exact current head SHA;
- no required workflow is missing, pending, cancelled, skipped, neutral, stale, or successful only for a different head SHA;
- the current default-branch head must already be contained in the candidate head, so an out-of-date Dependabot branch cannot merge on stale validation;
- immediately before mutation, the worker re-fetches the pull request, default-branch head, file list, and workflow runs and repeats the complete policy evaluation;
- the pull request identity and head SHA must remain unchanged, and the default branch must not move across that final validation window;
- immediately before the merge API call, the default-branch head is checked once more; any observed movement fails closed;
- the merge mutation is bound to the exact validated candidate head SHA.

If any condition cannot be proved, the worker does nothing. A workflow rename, missing workflow run, merge conflict, moved head, moved base, stale candidate branch, ambiguous file path, unsupported dependency surface, failed security gate, or API error leaves the pull request for normal review.

## Trusted-code execution boundary

The merge workflow runs only from the repository's default branch on `schedule` or `workflow_dispatch`. It checks out that trusted default branch explicitly with persisted checkout credentials disabled.

It does **not**:

- use `pull_request_target` to execute pull-request content;
- check out a Dependabot head ref;
- import Python from a Dependabot branch;
- execute changed package scripts, installers, tests, build steps, or repository code from the candidate pull request;
- read workflow logs as instructions;
- accept model output as merge authority;
- force-push `main` or bypass repository policy.

The worker only reads GitHub metadata, changed filenames, workflow-run metadata, default-branch state, and compare metadata for the candidate head. The actual project validation remains in the normal pull-request workflows.

## Dependency-file allowlist

Eligible files are limited to dependency manifests/lockfiles such as `pyproject.toml`, `package.json`, common lockfiles, and `requirements*.txt` at repository-relative canonical paths. Workflow files, Dockerfiles, scripts, source files, configuration-control files, and non-canonical/traversal paths fail closed.

This intentionally excludes changes such as `.github/dependabot.yml`, Docker base-image updates, workflow-action updates, or arbitrary scripts from automatic merge. Those surfaces can change execution or trust policy and require the normal review path.

## Required workflow set

The default worker requires successful exact-head runs for:

- `CI/CD`
- `Backend Quality`
- `Merge Readiness`
- `Secret scanning`
- `Malware Gate`
- `Repository Hygiene Gate`
- `Artifact Policy`
- `Provenance Policy`

Operators can override this set with `DEPENDABOT_REQUIRED_WORKFLOWS`, but an empty required-workflow set is rejected by policy. Renaming a required workflow without updating the worker causes automatic merge to stop rather than silently weaken validation.

## Why explicit validation instead of relying only on branch protection

Branch protection and rulesets are still desirable, but repository settings can drift or be unavailable to a workflow. The auto-merge worker therefore treats them as defense in depth rather than its only safety mechanism. The worker requires the candidate to contain the current default-branch head, revalidates default-branch stability immediately before mutation, and binds the final mutation to the exact Dependabot head SHA.

GitHub's pull-request merge API exposes an expected head-SHA precondition but no expected base-SHA precondition. The worker therefore performs repeated base-head checks and fails closed on any base movement it can observe. Repository branch protection remains valuable defense in depth for the final API boundary.

## Failure behavior

A failed check, missing check, ambiguous dependency change, unsupported ecosystem, merge conflict, stale head, stale base, repository-policy change, GitHub API error, malformed response, or security scanner disagreement stops automatic merging. The pull request remains open for diagnosis and human review.
