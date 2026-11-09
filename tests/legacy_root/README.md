# Legacy root harnesses

These scripts were moved out of the repository root during the September 2026 hygiene pass.

They are preserved for historical/manual diagnostics, but they are not part of the canonical automated test surface. Canonical pytest discovery is scoped to `skeleton/testing`, while CI invokes selected files under `tests/`, `skeleton/testing/`, and `backend/tests/` explicitly.

Treat these files as legacy snapshots. Prefer adding maintained regression coverage to the canonical test trees rather than extending these harnesses. Some scripts target historical preview services or assume repository-root execution and may require adaptation before manual use.
