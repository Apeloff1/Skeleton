# Repository Consolidation — August 2026

**Skeleton is now the single canonical repo for the Tutolage platform.**

## What was surveyed

| Repo | State | Action |
|------|-------|--------|
| **Skeleton** (this repo) | Most developed — full backend, frontend, tests, docs | **Canonical repo** |
| Prood | Byte-for-byte duplicate of Skeleton (same 79 root files) | Redundant — safe to delete or archive |
| Tutolage | Older iteration of the same app | Salvaged: fuller `docker-compose.yml` (healthchecks, Mongo auth, ChromaDB profile, Expo ports) merged in |
| 2dv0.4, 2dv0.3, 2dv0.2, 2dv1, 2d | Old 2D game prototypes (JavaScript) | Superseded — no salvageable app code |
| Openworld*, Newmove*, Hotday*, Summer, lage, tolage, etc. | Early experiments | Superseded |
| Prod, gameforge-rs, Ai-gamestudio, Piper, Restorepoint, resting-22, Ieresting-22 | Empty repositories | Nothing to salvage |

## Fixes applied in the consolidation pass

- Added `LICENSE` (MIT) — the README referenced it but it didn't exist.
- Added `.env.example`, `backend/.env.example`, `frontend/.env.example` — the README's setup steps referenced files that weren't in the repo.
- Fixed `.gitignore` self-contradiction: it both required and ignored `.env` files. Real env files are now ignored; only `.env.example` is tracked.
- Slimmed `backend/requirements.txt` from a full machine freeze (~190 packages incl. CUDA toolkits, PyInstaller, kubernetes client) to actual production dependencies; fixed the `bcrypt 5.0.0` / `passlib 1.7.4` incompatibility by pinning `bcrypt==4.0.1`.
- Corrected README clone URL (pointed at a nonexistent `tutolage/tutolage` repo).
- Merged the stronger `docker-compose.yml` from the Tutolage repo.
- Gitignored `test_result.md` (2MB committed test-output dump), `*.bak*` editor backups, and the 103MB `backend/godot` binary.

## Known remaining issue

Two files should be deleted from git history but the GitHub API currently returns
`GitRPC::BadObjectState` on tree creation for this repo (likely related to the
103MB `backend/godot` blob). To remove them locally:

```bash
git clone https://github.com/Apeloff1/Skeleton.git
cd Skeleton
git rm --cached test_result.md backend_test.py.bak_1779283310 backend/godot
git commit -m "chore: untrack test dump, backup file, and godot binary"
git push
```

If the push also fails with a bad-object error, the repo's object store needs
repair: contact GitHub support, or migrate by pushing a fresh local clone to a
new repo and archiving this one.
