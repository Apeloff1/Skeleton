# Backlog Bot

Repository-native automation for reported problems, security findings and CI failures.

## Operating loop

1. **Observe** — read GitHub issues, PRs, workflow results and security signals.
2. **Correlate** — fingerprint duplicate reports and retain every source of evidence.
3. **Retrieve** — use deterministic repository indexes to select focused source, tests, docs, workflows and dependency context.
4. **Reason** — optionally use the ChatGPT API for classification, diagnosis and repair planning.
5. **Validate** — apply deterministic policy, risk checks, stale-state checks and security invariants.
6. **Act** — make only permitted changes, normally through a PR and existing repository gates.
7. **Verify** — inspect CI/security results and invalidate stale plans when the repository changes.

## Repository knowledge

The indexed reader provides bounded access to source, tests, Markdown, YAML, dependency manifests, Dockerfiles and security documentation. The index layer also records symbols, references, dependencies, workflows, tests and provenance. See [`REPOSITORY-READING.md`](REPOSITORY-READING.md) and [`INDEXES.md`](INDEXES.md).

The bot should understand not only code, but also the repository's operational documentation, architecture descriptions, CI contracts, security policies, threat models, test fixtures, dependency declarations and historical remediation context.

## ChatGPT API boundary

Set the API key as a GitHub Actions secret such as `OPENAI_API_KEY`. Never commit it or print it. The adapter is optional: backlog discovery and deterministic safety checks continue if the API is unavailable.

Model input is minimized, sanitized and provenance-tagged. Repository text, issue text, comments, commit messages and CI logs are treated as hostile/untrusted data and cannot override system policy.

## Safe automation

Autonomous work is bounded by least-privilege GitHub permissions, immutable Actions, bounded file/context sizes, deterministic risk classification, retry budgets, circuit breakers, secret redaction, stale-branch detection, duplicate/concurrency locks, security-gate preservation, explicit quarantine, and durable state.

The bot must never make a change merely to make a security gate pass. Model output is advisory and cannot directly authorize a merge, permission change, gate bypass, secret access, or destructive operation.

## Failure behavior

A missing model API, GitHub rate limit, malformed response, stale index, conflicting scanner result, merge conflict, repeated failed repair, or infrastructure-only CI failure must stop only the affected operation while preserving durable backlog state. Repeated unsafe or ambiguous work is quarantined rather than retried forever.
