# Claude repository instructions

The authoritative model-agnostic rules are in `AGENTS.md`; follow them for every repository task.

Mandatory flow: `make repo-intel` before build-affecting edits, work against explicit `repo-intel/batches.json` IDs and current gaps, add/update `repo-intel/notes/` with evidence/security/quality/dependency effects, then run `make repo-intel-check` before handoff.

CI enforces the augmentation-note gate. Never convert structural presence into a claim of feature readiness or SOTA quality without the relevant tests/evals/benchmarks.
