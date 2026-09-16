# Repository Bots

Skeleton can run bounded maintenance bots against a configurable chat-model API.
The bots are designed for free-tier/self-hosted model endpoints, but provider
limits and model availability are controlled by the provider and are not
assumed to be unlimited.

## Base bots

| Bot | Job |
| --- | --- |
| `triage` | Reads open issues and proposes a focused repair. |
| `ci` | Reads recent Actions runs and proposes a focused CI repair. |
| `security` | Looks for concrete security regressions and regression tests. |
| `cleanup` | Finds safe cleanup opportunities in code, tests, and docs. |

## Secretary + specialist fleet

The repository secretary maintains awareness of every registered specialist
and routes due work from the current backlog/PR plan. The specialist fleet is:

`root-cause`, `dependency-guardian`, `regression-hunter`,
`architecture-reviewer`, `security-auditor`, `performance-sentinel`,
`release-guardian`, `documentation-guardian`, `integration-sentinel`,
`pr-reviewer`, `test-gap`, and `api-contract`.

The secretary selects specialists from explicit plan signals. The selected
specialist receives that plan as task context and uses the model to determine
what concrete work is justified by the evidence. This is plan-driven runtime
adaptation, not model training or unrestricted autonomous execution.

## Change boundary

Every proposed change is:

1. generated outside `main`;
2. restricted to `skeleton/`, `tests/`, or `docs/`;
3. prevented from touching workflows, deployment files, secrets, or env files;
4. checked with a fixed allowlist of safe local test commands;
5. pushed to an isolated bot branch; and
6. opened as a normal pull request so the repository's existing CI and security gates remain authoritative.

The bots cannot merge their own work or disable/weaken repository gates.

## Model configuration

Set repository variables:

- `MODEL_API_URL` — an OpenAI-compatible chat-completions endpoint.
- `MODEL_NAME` — the selected model identifier.

Set repository secret:

- `MODEL_API_KEY` — API credential for the chosen provider.

A free-tier provider may be used here. The bot does not assume that an API is
free forever or that rate limits are unlimited.

## Manual operation

Run **Actions → Repository Bots → Run workflow** for the base fleet, or
**Actions → Repository Secretary** to let the secretary route specialists.
Scheduled runs keep both lanes unattended.

## Security boundary

The model receives bounded repository context and redacted issue/PR signals,
but no GitHub secrets. Model output is treated as untrusted input. Path
traversal, workflow changes, deployment changes, environment files, oversized
files, excessive file counts, and unsafe test commands are rejected before a
branch is created.
