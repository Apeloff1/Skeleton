# Repository Bots

Skeleton can run bounded maintenance bots against a configurable chat-model API.
The bots are designed for free-tier/self-hosted model endpoints, but provider
limits and model availability are controlled by the provider and are not
assumed to be unlimited.

## Bots

| Bot | Job |
| --- | --- |
| `triage` | Reads open issues and proposes a focused repair. |
| `ci` | Reads recent Actions runs and proposes a focused CI repair. |
| `security` | Looks for concrete security regressions and regression tests. |
| `cleanup` | Finds safe cleanup opportunities in code, tests, and docs. |

Every proposed change is:

1. generated outside `main`;
2. restricted to `skeleton/`, `tests/`, or `docs/`;
3. prevented from touching workflows, deployment files, secrets, or env files;
4. checked with model-supplied local test commands that pass a conservative command filter;
5. pushed to a bot branch; and
6. opened as a normal pull request so the repository's existing CI and security gates remain authoritative.

The bot cannot merge its own work and cannot disable or weaken repository gates.

## Model configuration

Set repository variables:

- `MODEL_API_URL` — an OpenAI-compatible chat-completions endpoint.
- `MODEL_NAME` — the selected model identifier.

Set repository secret:

- `MODEL_API_KEY` — API credential for the chosen provider.

A free-tier provider may be used here. The bot does not assume that an API is
free forever or that rate limits are unlimited.

## Manual operation

Run **Actions → Repository Bots → Run workflow** and choose one bot or `all`.
The scheduled workflow runs hourly. If model configuration is missing, the bot
stops without modifying the repository.

## Security boundary

The model receives repository context and issue/Actions signals, but no GitHub
secrets. Model output is treated as untrusted input. Path traversal, workflow
changes, deployment changes, environment files, oversized files, excessive file
counts, and unsafe test commands are rejected before a branch is created.
