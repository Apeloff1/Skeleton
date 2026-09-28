# Large artifact archive

B006 of issue #807 removes legacy payloads larger than 10 MiB from the current
working tree without erasing historical evidence.

The authoritative map is `machine/large_artifact_archive.json`. Every entry
pins the exact baseline commit, Git blob object ID, byte count, classification,
and any maintained replacement reference. None of these archived payloads is a
supported build, deploy, test, or dependency-management input.

## Recovery

Historical bytes remain in Git history. Recover an entry only for forensic or
migration work by checking out the pinned baseline commit and reading the
recorded path. Do not commit a recovered payload back to normal Git.

If an asset becomes a maintained input, promote it through
`docs/ARTIFACT_POLICY.md`: Git LFS, CI/release storage, or immutable external
storage with provenance.

## Validation

```bash
python scripts/check_large_artifact_archive.py
python scripts/check_large_artifact_archive.py --verify-history
```

Normal validation fails if any regular blob over 10 MiB remains in the current
tree. `--verify-history` additionally checks every archived path against the
pinned baseline's exact Git blob ID and size and is intended for a full-history
checkout.
