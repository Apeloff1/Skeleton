# B001 — contributor, agent, bot, and automation provenance

- **Batch IDs:** B001
- **Area:** repository intelligence / provenance / agent handoff
- **Author/agent:** ai:chatgpt
- **Contribution mode:** authored
- **Intent:** Make human, AI-agent, bot, automation, and orchestrator participation visible without conflating Git identity, explicit handoff declarations, operational surfaces, or user-declared tools.

## What changed

- Added `repo-intel/contributors.json` as the canonical identity/evidence contract.
- Added `scripts/repo_intel_contributions.py` to scan bounded Git history, direct contribution trailers, instruction/workflow surfaces, augmentation-note attribution, and unknown identities.
- Added `scripts/check_repo_intel_contribution_gate.py` so build-affecting work must leave at least one changed handoff note with a recognized canonical actor; explicitly named unregistered actors fail closed.
- Added focused regressions in `tests/test_repo_intel_contributions.py` for multiline commit messages, Copilot direct trailers versus Grok surface references, declared handoff participation, unknown bot identities, and gate behavior.
- Updated `Makefile` so normal repo-intelligence refresh/check paths also refresh contribution provenance.
- Updated the augmentation-note template with contribution mode and provenance edge-case guidance.

## Validation evidence

Focused CI regression wiring is added in this batch and the repository intelligence / merge-readiness workflows remain authoritative once they execute on the final head. The contribution implementation is Python 3.11 stdlib-only and bounded by `history_commit_limit`.

## Security impact

- Generated provenance output never emits raw Git email addresses.
- Unknown identities are represented by stable truncated SHA-256 IDs and are not guessed into a named AI/vendor.
- A branch name, instruction file, commit-message mention, or model catalog entry is not promoted to authorship evidence.
- Shared human/connector identities require an explicit handoff declaration or Git trailer to preserve AI participation.
- New explicitly named actors fail the contribution gate until registered.

## Quality/performance impact

- History scanning is bounded to 3,000 commits rather than unbounded repository traversal.
- The provenance layer reuses the existing index file surface instead of independently walking the tree.
- Git author, committer, direct trailer, declared handoff, and operational-surface evidence remain distinct so counts are interpretable rather than blended into a misleading score.

## Dependabot/dependency note

No dependency additions, removals, or upgrades. Dependabot remains represented separately as a repository-observed dependency bot when Git identity or explicit trailers provide evidence.

## Contribution/provenance note

This work is being written through an authenticated GitHub connector, so the resulting Git commits are owned by the repository account rather than a distinct ChatGPT Git identity. The explicit `ai:chatgpt` handoff declaration is therefore the contribution evidence for this work unit. Existing repository evidence separately identifies Copilot App co-authorship, Dependabot, GitHub Actions, Grok/Codex/Claude/Gemini surfaces, and other registered actors according to the evidence rules in `repo-intel/contributors.json`.

## Noticeable gaps / next augmentation

- GitHub PR/review/issue authorship is not yet joined into the local contribution graph.
- Per-file historical ownership/contribution lineage is not yet emitted; current direct evidence is commit-level.
- Model/version identity is intentionally unknown unless explicitly recorded; vendor/tool identity must not imply a model version.
- Squash/rebase/cherry-pick/imported-history losses can only be reported from observable Git/handoff evidence, not reconstructed reliably.
- Existing legacy B001 notes are not retroactively rewritten solely for attribution; the new gate requires a valid canonical handoff in each build-affecting change series and rejects explicit unknown identities.

## Build handoff

- [ ] `make repo-intel`
- [ ] focused contribution provenance regressions
- [ ] `make repo-intel-check`
- [x] canonical Author/agent provenance recorded
- [x] B001 evidence note added
