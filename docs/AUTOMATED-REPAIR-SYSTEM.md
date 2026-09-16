# Automated repair system

Skeleton now has a layered automated-remediation strategy.

## Current layers

1. **Dependabot security updates** — GitHub automatically raises security-update PRs for vulnerable dependencies when a patched version is available.
2. **Dependabot version updates** — `.github/dependabot.yml` keeps Actions, Python, npm, and Docker dependencies current on a schedule.
3. **Dependabot Auto-Merge** — `.github/workflows/dependabot-automerge.yml` enables GitHub auto-merge only for Dependabot PRs whose changed files stay inside the explicitly allowlisted dependency/update surface. GitHub's required checks and branch rules remain authoritative.
4. **CodeQL/Copilot Autofix** — GitHub can generate fixes for supported code-scanning alerts; agentic autofix can explore the repository, validate the fix, and open a PR when the repository has the required GitHub security/Copilot capabilities enabled.
5. **Repository backlog bot** — the repository-native backlog reader/indexer provides deterministic evidence collection and an optional ChatGPT reasoning layer for issues that need broader diagnosis than dependency updates.

## Automatic merge boundary

Automation must not treat an issue, PR description, repository file, model response, or generated patch as permission to bypass security controls.

Dependabot auto-merge is deliberately narrow:

- only `dependabot[bot]` PRs;
- only `dependabot/*` heads;
- no repository checkout or execution of PR code;
- changed files must match the dependency/update allowlist;
- GitHub required checks and branch protections must still pass;
- merge is performed by GitHub auto-merge, not by force-pushing `main`;
- anything outside the allowlist is left for normal review/remediation.

## Why PR-based automation

Direct writes to `main` would make a failed automated repair immediately authoritative and could bypass required checks. PR-based auto-merge gives the repository's existing security, malware, dependency, CodeQL, quality, and merge-readiness gates the final authority.

## Additional systems worth enabling

- **GitHub Copilot Autofix / agentic autofix** for CodeQL and supported third-party code-scanning alerts. GitHub documents agentic autofix as a best-effort workflow that explores code, proposes a fix, validates it, and opens a draft PR.
- **Grouped Dependabot security updates** where compatible, to reduce repair-PR fragmentation.
- **Renovate** can be evaluated later if Dependabot's ecosystem coverage or grouping controls become insufficient; do not run two dependency-updaters against the same manifests without explicit ownership rules.

## Failure behavior

A failed check, ambiguous dependency change, unsupported ecosystem, merge conflict, stale base, scanner disagreement, or security-policy change must stop automatic merging. The item remains available to the backlog automation system for diagnosis and human review.
