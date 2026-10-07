# Repository Bot Manager + Secretary

The bot manager is the control plane for repository maintenance agents. The
secretary sits above it and routes concrete repository plans/signals to the
registered specialist bots.

## Specialist roster

| Specialist | Trigger / specialty | Risk |
| --- | --- | --- |
| `root-cause` | repeated CI failures | medium |
| `dependency-guardian` | dependency/security alerts | high |
| `regression-hunter` | new failing tests or flaky jobs | medium |
| `architecture-reviewer` | large PR or subsystem drift | low |
| `security-auditor` | security/code-scanning signal | high |
| `performance-sentinel` | benchmark or timeout regression | medium |
| `release-guardian` | release readiness | high |
| `documentation-guardian` | docs/code drift | low |
| `integration-sentinel` | cross-subsystem integration failures | high |
| `pr-reviewer` | opened or updated PRs | low |
| `test-gap` | coverage gaps without behavior change | medium |
| `api-contract` | API/schema contract drift | high |

The secretary knows the complete roster and only dispatches registered,
currently-due specialists. It reads the current backlog/PR plan and routes by
explicit signals; the plan is untrusted data, not executable instructions.
Specialists use that plan as their task context and determine at run time
whether there is enough evidence to propose a change.

## Night Shift / Idle integration

The specialist fleet is designed to run unattended at the same operational
level as the existing Night Shift and Idle automation. It is bounded by the
manager's cooldown, concurrency limit, and circuit breaker rather than creating
unlimited parallel agents.

## Safety model

The manager/secretary does not grant bots new permissions, merge PRs, disable
checks, or modify protected control-plane files. Specialist proposals are
restricted to source/tests/docs and continue through ordinary branches, PRs,
CI, and security gates. High-risk specialists remain subject to the same
fail-closed policy as other automated repairs.

The model layer remains provider-neutral and can use a free-tier or
self-hosted OpenAI-compatible endpoint configured through CI variables/secrets.
No GitHub secret is included in the specialist plan sent to the model.
