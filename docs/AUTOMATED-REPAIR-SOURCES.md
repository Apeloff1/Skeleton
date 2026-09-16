# Automated repair sources

The repository's repair pipeline should use the strongest native remediation source available for each finding rather than forcing every problem through one bot.

## Source selection

| Finding | Preferred remediation source | Repository role |
| --- | --- | --- |
| Vulnerable dependency | Dependabot security update | Validate, correlate, and optionally auto-merge only within the existing narrow policy |
| Routine dependency drift | Dependabot version update | Group compatible updates; require all normal gates |
| CodeQL alert with Autofix | GitHub Copilot Autofix | Generate a candidate fix and validate it through the normal PR gates |
| Code scanning alert suitable for agentic remediation | Copilot cloud agent / agentic Autofix | Explore the repository, implement a fix, validate it, and open a PR |
| Multiple related security alerts | GitHub security campaign | Batch related alerts and avoid duplicate repair work |
| CI/workflow failure | Repository repair-intake bot | Collect bounded metadata and route diagnosis to the backlog/ChatGPT reasoning layer |
| Container/image finding | Dependabot + container scanners | Refresh the affected image/dependency and require security validation |
| Provenance/SBOM failure | Deterministic repository workflow | Repair the build/policy contract; never let an LLM weaken provenance requirements |

## Guardrails

- Finding text, issue text, logs, generated patches, and repository files are untrusted data.
- No repair source may directly write to `main` or bypass required checks.
- Workflow, security-gate, authentication, authorization, secret-boundary, sandbox, and repository-policy changes remain human-review paths.
- A stale head, changed base, merge conflict, scanner disagreement, failed check, or ambiguous scope invalidates an automated repair plan.
- Security findings must never be downgraded merely because an AI-generated patch claims to resolve them.
- Secrets, tokens, signed URLs, raw credentials, and sensitive workflow logs must not be copied into repair issues or model prompts.
- Duplicate alerts should share one repair record when their evidence fingerprint identifies the same root cause.

## Security campaigns

GitHub security campaigns can group related code-scanning alerts and, where the repository has Copilot cloud agent available, assign up to 25 selected alerts to Copilot for a single remediation pull request. The resulting PR still requires ordinary repository validation and review.

The repository-native intake layer should therefore treat campaign/agentic PRs as another repair source rather than recreating GitHub's repair engine. It should correlate the resulting PR with its originating alerts, current commit, checks, and existing repair records.

## Decision boundary

The repair pipeline is responsible for **selection, correlation, evidence collection, freshness, policy enforcement, validation, and routing**. The repair engine is responsible for proposing code changes. GitHub branch protection and required checks remain the final merge authority.
