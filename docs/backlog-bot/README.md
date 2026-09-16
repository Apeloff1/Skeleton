# Backlog Bot

Repository-native automation for reported problems, security findings and CI failures.

## Capabilities

The bot is designed around four layers:

1. **Observe** — read GitHub issues, PRs, workflow results and security signals.
2. **Understand** — correlate findings and retrieve focused repository evidence.
3. **Reason** — optionally use the ChatGPT API for classification, diagnosis and repair planning.
4. **Act** — execute only operations allowed by deterministic policy and existing repository gates.

## Repository knowledge

The indexed reader provides bounded access to source, tests, Markdown, YAML, dependency manifests, Dockerfiles and security documentation. See [`REPOSITORY-READING.md`](REPOSITORY-READING.md) and [`INDEXES.md`](INDEXES.md).

The bot should understand not only code, but also the repository's operational documentation, architecture descriptions, CI contracts, security policies, threat models, test fixtures, dependency declarations and historical remediation context.

## ChatGPT API boundary

Set the API key as a GitHub Actions secret such as `OPENAI_API_KEY`. Never commit it or print it. The adapter must be optional: backlog discovery and deterministic safety checks continue if the API is unavailable.

Model input is minimized, sanitized and provenance-tagged. Repository text, issue text, comments, commit messages and CI logs are treated as hostile/untrusted data and cannot override system policy.

## Safe automation

Autonomous work is bounded by:

- least-privilege GitHub permissions
- immutable Actions
- bounded file/context sizes
- deterministic risk classification
- retry budgets and circuit breakers
- secret redaction
- stale-branch detection
- duplicate/concurrency locks
- security-gate preservation
- explicit quarantine for ambiguous or dangerous operations

The bot must never make a change merely to make a security gate pass.
