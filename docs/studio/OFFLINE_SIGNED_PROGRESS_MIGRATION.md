# Signed offline progress migration (source-level only)

The `python -m skeleton app migrate-signed-progress` command composes
independent archive, manifest, save and Ed25519 public-key SHA-256 pins.
It verifies the detached signature and archived replay compatibility **before**
reserving either output. The canonical installer creates a fresh original
source directory; the canonical private-save publisher creates a distinct
no-clobber replay file. Final acceptance independently checks the signature,
installed source, replay digest, key pin and saved actions.

Example:

```sh
python -m skeleton app migrate-signed-progress \
  --archive /private/source.zip --destination /private/new-game \
  --original-save /private/old-save.json --migrated-save /private/new-save.json \
  --public-key /private/trusted.pub --signature /private/source.sig \
  --expected-archive-sha256 '<independent-archive-pin>' \
  --expected-manifest-sha256 '<independent-manifest-pin>' \
  --expected-save-sha256 '<independent-save-pin>' \
  --expected-public-key-sha256 '<independent-key-pin>' \
  --trusted-local-operator
```

The pins must be obtained from a trusted independent source; self-discovered
hashes do not establish authenticity. POSIX owner-private, nofollow descriptor
custody is required. This operation does not execute a native Godot binary,
certify a consumer device, sign an executable, prove publisher identity or
establish rights. A failure after publication leaves the new source/save
for operator quarantine, never automatically deletes potentially replaced
paths, and never claims atomic migration across two destinations.

Focused acceptance: `pytest -q skeleton/testing/test_app_offline_signed_progress_migration.py`.
Full exact-head CI/security gates and device testing remain mandatory.

Read-only admission: add `--preflight-only` to the same command. It verifies
all independent pins, detached signature, replay compatibility and destination
availability without creating directories or saves. Its receipt is not a
reservation; the publication command repeats every gate and identity fence.
