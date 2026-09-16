# Copilot repository instructions

Follow the root `AGENTS.md` contract for every build-affecting change.

Before editing, run `make repo-intel` and read `.cache/repo-intel/notes.md`, the relevant gap entries, and `repo-intel/batches.json`. Identify the batch IDs advanced by the change.

Before handoff, add/update a note under `repo-intel/notes/` using `TEMPLATE.md`, including validation, security, quality/performance, dependency/Dependabot impact and remaining gaps. Run `make repo-intel-check`.

Do not equate a discovered file/module with feature readiness. Competitive/SOTA claims require explicit eval or benchmark evidence.
