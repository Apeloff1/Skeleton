# Archived satellite UI portability and reference audit

## Scope and status

The three historical snapshots in `satellites/branch-snapshots/` are **archival evidence**, not supported build/deployment roots. Each previously contained separate `frontend/components/UI/` and `frontend/components/ui/` trees. On case-insensitive filesystems those directories collided at checkout.

This change combines their contents into the existing lowercase `frontend/components/ui/`. Nine `.tsx` paths are renamed (three per snapshot), retaining their **original Git blob IDs and source code**:

| Former component in `UI/` | Current path in each snapshot | Preserved blob |
| --- | --- | --- |
| `ErrorBanner.tsx` | `frontend/components/ui/ErrorBanner.tsx` | `f3b04f165fabf989a570fd017186b7e01c4312b8` |
| `LoadingScreen.tsx` | `frontend/components/ui/LoadingScreen.tsx` | `96aabc81fcd11e96f11fe680ac8e5f2dbc2bb11c` |
| `Toast.tsx` | `frontend/components/ui/Toast.tsx` | `b7da7cf99f893516fc4fe489a5cdb58c44edf225` |

The existing thirteen lowercase component files remain intact. Each lower-case `ui/index.ts` now exports the three relocated components. There was already a separate `frontend/components/Toast.tsx`; it is **not** replaced by the archived `ui/Toast.tsx`.

## Compatibility

A consumer promoting source out of these historical snapshots must update any import of `components/UI/{ErrorBanner,LoadingScreen,Toast}` (including `../UI/` relative variants) to its lowercase `components/ui/` equivalent. In JavaScript/TypeScript, case-only path mismatches can fail on Linux even when they seem to work on Windows. Git history preserves the old archived filenames if a legacy reference must be researched.

Run the read-only audit from the repository root:

```bash
python scripts/audit_satellite_integrity.py --ref HEAD --fail-on-ui-refs
```

The audit reads Git objects directly, so it does not need to materialize the archived trees on a case-insensitive checkout. It reports:
- portable path limits, Windows-invalid paths, and normalized case/Unicode directory collisions;
- stale case-sensitive frontend `UI/` string references;
- source `TODO`, `FIXME`, unimplemented-operation and truncated-output markers;
- malformed small `.json` files.

Stub, truncation and JSON findings are **candidate reviews**, not confirmed incomplete functionality. Results are emitted as JSON for an evidence-driven remediation queue; source files above the reported per-file byte limit are deliberately excluded from the content inspection.

## Release criteria

- [x] Moved all nine named component files without altering their blobs.
- [x] Preserved the thirteen lowercase `ui/` component files.
- [x] Exposed moved default exports from each snapshot's `ui/index.ts`.
- [ ] Execute a complete static reference audit on the proposed Git head and resolve each stale reference.
- [ ] Execute an actual archived frontend TypeScript/Metro build **if** any snapshot is promoted to a supported application; do not claim archived builds passed without running them.
- [ ] Classify and remediate reported stub/truncation candidates separately, without changing historical evidence merely to clear a heuristic warning.

Do not rewrite archival snapshots for unrelated refactors and do not bypass repository provenance checks to land this change.
