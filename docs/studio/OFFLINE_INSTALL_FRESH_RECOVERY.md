# Fresh offline install recovery without destroying quarantine

A failed partial installation is not an installed game and must not be
silently adopted, repaired in place, deleted or treated as release-qualified.
The Studio D recovery command uses a separately pinned original ZIP to
reinstall into a **different, previously unused** owner-private directory.

```sh
python -m skeleton app recover-install \
  --quarantined /owner/private/failed-install \
  --archive /owner/private/original-source.zip \
  --destination /owner/private/new-install \
  --expected-archive-sha256 <independent-64-lowercase-hex> \
  --expected-manifest-sha256 <independent-64-lowercase-hex> \
  --trusted-local-operator
```

Before any publication, the command performs descriptor-bound, bounded
read-only inventory of the quarantined tree, canonical archive inspection,
and destination preflight. It checks the quarantine again, then invokes the
canonical no-clobber installer. After installation it independently verifies
the fresh tree against the pinned ZIP and repeats quarantine identity checks.

A late failure **does not** roll back or clear either directory. The operator
must quarantine any new destination that failed a later check. The original
partial source remains untouched even on success. No archived bytes are
executed by the installer. Python replay proof is not native Godot execution.

A successful diagnostic still explicitly reports no package signature,
rights certification, native-device qualification or consumer-release
certification. Required exact-head security and release gates remain held.
