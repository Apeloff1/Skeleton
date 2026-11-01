# Offline game progress migration — source-level contract

This operation connects a real first-run game, private hash-chained replay
save, deterministic original browser/Godot source ZIP and fresh installation.
It does **not** claim native Godot execution, device qualification, AI inference,
package signing, content rights clearance or consumer release readiness.

The operator must independently preserve three SHA-256 pins: the archive,
the source release manifest and the private replay save. A digest printed
from the same untrusted file during restoration is not an independent pin.

## Workflow

Build an original source game with `studio-journey --onboard`, play with
`--play-existing --moves up,right --save <new-private-save>`, and publish
the deterministic source archive with `--package-existing`. Preserve the
three pins out of band. On the destination host, use:

```sh
python -m skeleton app studio-journey --migrate-progress \
  --archive ./original-source.zip \
  --expected-archive-sha256 "$ARCHIVE_PIN" \
  --expected-manifest-sha256 "$SOURCE_PIN" \
  --load-save ./old-private-save.json \
  --expected-save-sha256 "$SAVE_PIN" \
  --output ./new-original-game \
  --save ./new-private-save.json \
  --trusted-local-operator
```

The source installer creates a private no-clobber directory and replays the
canonical game proof. The migration then reconstructs the canonical world,
reexecutes the private replay, publishes a separate owner-private save,
reads it back, reexecutes again, and rechecks both archive and installed
source. A successful receipt binds the replay and source digests.

This is **not** a cross-directory atomic transaction. If a late verification
fails, the newly reserved source directory and/or private save can remain.
Do not delete or overwrite those paths by guesswork; quarantine them for
explicit owner inspection. No existing source or save is modified.

Tests cover the complete source-build → gameplay/save → deterministic ZIP →
fresh installation → migrated replay → resumed play journey, wrong independent
pins, foreign save histories, existing destination collisions, symlinks,
and mode-mixing. CI and physical-device qualification remain separate holds.

## Read-only recovery and reconciliation

After a migration, use `--reconcile-migration` with the installed source
directory, the new private save and their two independent pins. Optionally
provide both the original archive and its independently held SHA-256. The
command verifies source, reexecutes the save, reopens the private save and
source, and optionally rechecks the archive. It never writes, cleans up or
certifies that a prior multi-destination migration was atomic.

```sh
python -m skeleton app studio-journey --reconcile-migration \
  --output ./new-original-game \
  --expected-manifest-sha256 "$SOURCE_PIN" \
  --load-save ./new-private-save.json \
  --expected-save-sha256 "$NEW_SAVE_PIN" \
  --archive ./original-source.zip \
  --expected-archive-sha256 "$ARCHIVE_PIN" \
  --trusted-local-operator
```

If the archive is omitted, archive integrity is explicitly **not** verified.
If either the archive or its pin is provided alone, the command fails closed.
