# Multi-file and disc-game comparative admission — 2026-10-15

The comparative studio now accepts **large, lawful multi-file game media** through the existing verified `GameContentBundle` owner without reading disc images into Python memory. This extends studies beyond their earlier 16 MiB inline-ROM limit while keeping the canonical 30-game study / 10-concurrent-session ceiling.

## Optional manifest field

Existing single-file rows remain unchanged. For a disc game, keep the required `source_path` and `source_sha256` pinned to its **entrypoint file**, and add:

```json
{
  "content_bundle": {
    "entrypoint": "disc.cue",
    "files": [
      {
        "name": "disc.cue",
        "path": "/srv/owned-games/title/disc.cue",
        "sha256": "<exact SHA-256 for cue file>",
        "size_bytes": 128
      },
      {
        "name": "track.bin",
        "path": "/srv/owned-games/title/track.bin",
        "sha256": "<exact SHA-256 for actual track bytes>",
        "size_bytes": 524288000
      }
    ]
  }
}
```

The placeholder sizes/hash strings are illustrative, not a claim that these files exist. The `source_path` field of the enclosing game must exactly match the bundle entrypoint's `path`, and `source_sha256` must equal its SHA-256; optional top-level `rights_evidence_digest` remains the operator-supplied source-rights claim.

Game source files are opened with a no-follow path walk. The host checks type, exact inode/size/change metadata, and bounded descriptor contents. An immutable `GameContentReference` reader streams at most 1 MiB per chunk to `GameContentBundle.materialize_private` which verifies **complete real SHA-256 and sizes** before allowing the approved isolated core to load content. Missing companion tracks, invalid playlist/CUE/GDI files, unsupported image headers, changed files, symlinked components, invalid ownership or unapproved cores fail visibly; there is no reference-game substitution or silent truncation.

The existing limits still apply: 96 files, 2 GiB per referenced file, 4 GiB aggregate, 64 KiB per descriptor header, 256 KiB aggregate prefixes. CHD and ISO images require canonical structural prefixes; CUE/GDI/M3U dependencies are validated by the existing emulator catalog. Multiple concurrent disc sessions still consume real disk space because each prepared bundle is privately materialized. Operators should choose a suitably bounded `max_active` for their disks and hardware.

Each study report now distinguishes `source_sha256` (entrypoint) from `source_bundle_sha256` (full normalized source/bundle identity); the series ledger keeps both. No ROM, BIOS, disc image, game asset or source URL is embedded in the HTML comparison viewer or Dragon intake. Actual disc compatibility depends on a separately installed, operator-approved core and legally acquired data; native disc boot, timing, peripheral fidelity, video and game accuracy have **not** been exercised by this source commit.

Unit-contract tests are added in `tests/test_game_comparison_media.py` covering streaming CUE/track admission, source mutation, symlink denial and exact entrypoint identity; no real game ROM is included.
