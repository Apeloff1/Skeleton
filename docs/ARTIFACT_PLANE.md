# Artifact plane — Godot binary

GB-9. Companion to `docs/ARTIFACT_POLICY.md` (10 MiB git cap).

## Law

`backend/godot` (~103 MB Linux x86_64 editor) is **not** a git blob.
Git holds `backend/godot.artifact.json` only.

Acquire via:

1. `GODOT_BINARY` pointing at a local editor
2. `godot` on `PATH`
3. Download from Godot releases, `chmod +x`, drop at `backend/godot` (gitignored)

Clone without LFS / without the binary must still `import skeleton` and
`import gameforge.godot_engine.binary`.

## Locate

```
from gameforge.godot_engine.binary import locate
# or
from skeleton.godot_engine.binary import locate

card = locate()
# {kind:godot-binary, found:0|1, hint, stored_prose:0}
```

`locate()` never raises. Missing binary is `found=0` plus a hint.
`get_binary()` still raises `FileNotFoundError` for callers that want a hard miss.

## Git

- tracked: `backend/godot.artifact.json`
- ignored: `backend/godot`
- LFS optional if a future maintainer re-tracks the blob. Preferred is external URL + env.
