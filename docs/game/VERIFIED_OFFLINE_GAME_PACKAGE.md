# Verified original offline game source package

`skeleton.game.build.offline_package` builds deterministic, source-bound ZIP
archives of original game source and assets. It uses the canonical
`PackageManifest` and build graph digest, with explicit **unsigned** and
**release_certified: false** receipts. This is not an installer, native executable,
asset-rights audit, signature, device qualification or release authorization.

```sh
python -m scripts.game.offline_package pack --input source.json --out original-game.zip
python -m scripts.game.offline_package verify --archive original-game.zip
python -m unittest skeleton.testing.test_offline_package -v
```

The source JSON object has `package_id`, `author`, `license` (CC0-1.0 or
CC-BY-4.0), and `files`: an array of `{"path":"game/scene.json",
"content_base64":"..."}` objects. Each original file is at most 1 MiB; 128
files and 8 MiB total uncompressed, 10 MB archive. Source names use
ASCII letters, digits, dots, underscores, hyphens and safe slash-separated
segments (at most eight segments). Reserved names, traversal, symlinks,
nonregular ZIP members, duplicates, encryption, compressed members, missing
members, digest/size mismatches, noncanonical manifests and false signature
claims are rejected before any extraction. **No extraction occurs.**

The builder sorts source paths, fixes ZIP metadata/timestamps and uses
stored entries for byte-for-byte reproducibility. The verifier rehashes
every member and recomputes the canonical build/package manifest. Input
reads are bounded and reject a symlink at the final path on O_NOFOLLOW
platforms; output uses exclusive no-clobber creation, restrictive permissions
and fsync. The caller must select a trusted destination parent and verify
asset rights independently; this is a safe source package, not a signed
release or a sandbox for executing untrusted game code.

Package member suffixes are intentionally limited to `.json`, `.txt`, `.md`,
`.csv`, and `.wav`. Git internals, GitHub workflow paths and executable/script
extensions are rejected at both build and verify. This is an additional
content admission boundary, **not** a malware scan or executable sandbox.
