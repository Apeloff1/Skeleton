# Exact-run Godot project ZIP export: historical source recovery

**Integration base:** PR #5320 at
`29c10a85ea80d0c0ee1aea8d108d03e758c91f54`.

**Historical original:** PR #5313 at
`85db3472bf9f656ea7e864eb2ae2d16afcff927c`, pinned at the precise
Git blobs for archive, sharing and offline account-epoch run custody.
Source and runtime are additive to modern GameForge; no wholesale replace
of questionnaire, native gameplay or local Jeeves internals.

## Practical user journey

1. Complete a GameForge brief, optional full Galaxy 14-matrix design and
   ten-axis instruments. Select Godot output.
2. Opt in to **Prepare portable Godot ZIP** (off by default).
3. Run the existing single GameForge pipeline. All eight native original
   mini-games, scene launcher, room quest, and two independent Godot
   qualifications remain available as before.
4. Only successful exact-run source manifests with at most **256 files**
   and **8 MiB UTF-8 text source** are eligible for export.
5. The returned source map must match a fully recomputed, sorted
   SHA-256 manifest, not an assertion copied from another run.
6. The run panel offers **Save or share Godot ZIP**, compiling only the
   exact returned source bytes into a deterministic stored ZIP capped at
   **9 MiB**. The original source file names, payload bytes and order are
   preserved without a remote service, another build or arbitrary paths.
7. Before sharing or browser downloading, validate every file SHA-256
   and recompute the manifest from current memory. Reject account epoch
   changes at every asynchronous boundary and verify that the original
   run is still the active run. Clear all private source from state on
   authentication changes and delete device cache ZIP in `finally`.

This is an editable **source project**, not an APK, installed game,
signed binary, tested live hardware performance or release certification.

## Historical source transplanted as original Git blobs

- `frontend/src/skeletonForge/sourceArchive.ts`: deterministic ZIP writer,
  Windows/device/path/Unicode/budget checks, CRC32
- `frontend/src/skeletonForge/shareSourceArchive.ts`: local web/native share
  with runtime SHA verification and device cleanup
- `frontend/src/skeletonForge/hooks.ts`: source/epoch invalidation,
  request-generation fencing, cancel/abort rejection
- `frontend/scripts/skeleton-forge/run-session-isolation.test.cjs`
- `skeleton/testing/test_gameforge_source_archive.py`

Backend, questionnaire, client, run-panel and cockpit adapters are
reconciled against the **newer** eight-mode GameForge source instead
of copying the older PR, preserving earlier cumulative changes.

## Focused exact-head verification

```sh
PYTHONPATH=.:backend python -m pytest -q --noconftest \
  skeleton/testing/test_gameforge_source_archive.py \
  backend/tests/test_native_eight_scene_api.py
cd frontend && node --test \
  scripts/skeleton-forge/source-archive.test.cjs \
  scripts/skeleton-forge/run-session-isolation.test.cjs \
  scripts/skeleton-forge/native-scene-qualification.test.cjs
cd frontend && yarn typecheck
```

Full required exact-head CI, security/CodeQL, local offline GGUF,
native Godot completion with admitted binary, device Windows/WSL2,
installer, artifact/dependency/hygiene/malware and provenance remain
mandatory. The source ZIP ability alone does not certify launch.
No merge, auto-merge, release or first-install signoff.
