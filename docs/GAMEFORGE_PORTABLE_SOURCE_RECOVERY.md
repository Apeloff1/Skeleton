# Portable GameForge source recovery

The Forge run panel exposes the complete source-manifest SHA-256. Retain it
separately from the ZIP; a truncated filename or a hash supplied by an
untrusted archive is not an independent identity.

From the repository root, with the application Python environment installed:

```bash
python -m scripts.verify_gameforge_source_zip project.zip --expected-sha256 FULL_SHA256
```

The report separates exact source identity, current native template
compatibility, Galaxy profile and control receipts, and launch/return portal
custody. It does not execute Godot or establish device acceptance.

Reopen the unchanged files in an absent directory under a trusted local parent:

```bash
python -m scripts.verify_gameforge_source_zip project.zip --expected-sha256 FULL_SHA256 --output reopened
```

Open that directory's `project.godot` only after reviewing the source. For a
current-template-only workflow, add `--require-current-template`.
Historical projects remain recoverable without that flag; no silent migration
or automatic overwrite takes place. An I/O failure during reopening may leave
a partial new directory, which should be reviewed before removal or retry.

Compare independently retained versions:

```bash
python -m scripts.verify_gameforge_source_zip old.zip --expected-sha256 OLD_SHA256 --compare-zip new.zip --compare-sha256 NEW_SHA256
```

Comparison is read-only and shows sorted added, removed, modified and
unchanged source counts. When both versions contain verified current tuning
for the same playable mode, it also reports changed native scalar values.
It neither infers file renames nor claims gameplay behavior from source changes.
The CLI accepts the stored UTF-8 source ZIP format produced by GameForge,
not arbitrary compressed, encrypted, linked or executable archive containers.
