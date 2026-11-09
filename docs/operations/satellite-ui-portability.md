# Archived satellite UI portability and integrity audit

The archived `satellites/branch-snapshots/` trees are historical evidence and are **not** deployable frontend roots. The currently adopted rename scheme uses `frontend/components/ui-archive/` for the formerly uppercase `UI/` components, preserving the original blob identities, as recorded in `satellites/branch-snapshots/PORTABILITY_RENAMES.json` (merged in #4042). Existing lower-case `frontend/components/ui/` remains independent.

The competing draft #4043 proposed moving those same files into `ui/`; that variant must not be merged on top of the adopted `ui-archive/` mapping without a deliberate, import-verified migration.

Run the read-only Git-object audit from a source checkout:

```bash
python -m unittest tests.test_satellite_integrity_audit
python scripts/audit_satellite_integrity.py --ref HEAD --max-examples 200 > satellite-audit.json
```

The audit checks tracked paths for Windows-incompatible names, excessive component/path lengths and case/Unicode collisions, and reviews small source blobs for stale `UI/` imports, TODO/FIXME/not-implemented markers, truncation markers and invalid JSON. The report has bounded cache and per-file scan sizes. Findings are candidates for review; a marker does **not** itself prove broken functionality. `--fail-on-ui-refs` also exits nonzero on stale frontend UI references, which must be repaired before promoting archived code into a build.

For historical paths or consumers, use the preserved Git blob identifiers and the `PORTABILITY_RENAMES.json` mapping. Do not silently replace `ui-archive/` with a conflicting rename or delete archival material as a shortcut. Production UI and full archived TypeScript builds have not been certified by this static audit.
