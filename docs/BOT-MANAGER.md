# Repository Bot Manager

The bot manager is the control plane for repository maintenance agents.

## Advanced bot roster

- triage — issue clustering and bounded repair proposals
- ci — failure diagnosis and regression repair
- security — security regression review
- cleanup — safe repository cleanup
- dependency — dependency/lockfile maintenance
- test — missing regression coverage
- review — PR risk and contract review
- docs — documentation drift
- performance — bounded performance regression analysis
- release — release-readiness checks

## Safety model

The manager does not grant bots new permissions, merge PRs, disable checks,
or modify protected control-plane files. It limits concurrent work, applies a
cooldown, and opens a circuit after repeated failures. Bot changes continue to
flow through ordinary branches, PRs, and repository gates.

The model layer remains provider-neutral and can use a free-tier
OpenAI-compatible endpoint configured through CI secrets/variables.
