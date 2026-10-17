# Archived GitHub Actions workflows

CI queue reduction: 411 specialized workflows were moved from
`.github/workflows/` to `.github/workflows-archive/`.

Archived YAML files are **inactive**. They cannot be dispatched or scheduled
until a specific workflow is moved back to `.github/workflows/`.

16 canonical YAML workflows remain active. Merge Readiness now runs a
bounded Python syntax smoke test. Existing backend/security checks remain
in their own targeted workflows; heavyweight emulation, E2E, assembly,
Windows installer and experimental P0-P3 validations are not automatic.

To recover a specialized validation, restore only that file to
`.github/workflows/` in a reviewed change and choose a narrow trigger
(prefer `workflow_dispatch` for expensive tests).

Archive is not evidence that retired gates passed. Before making a release,
run the relevant deeper validation and review any regressions separately.

See the original Git history before this commit for the pre-slim CI design.

## Restored

- `ci.yml` — restored to `.github/workflows/ci.yml` by #4104 as a reusable
  workflow called from the required **Merge Readiness** aggregate (one run per
  head, per-ref cancel-in-progress, change-scoped job skips). The copy in this
  folder is the inactive pre-restore snapshot.
