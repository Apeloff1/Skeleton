# First playable app journey — source qualification, not release

The canonical application CLI can now run a real, offline original-game
production path: typed intent → Jeeves/Dragon studio orchestration → compiled
winning game → adversarial mirror review → browser and Godot source export →
independent in-process SHA-256 pin → canonical source re-read and replay.

```sh
python -m skeleton app studio-journey \
  --intent original-intent.json \
  --output ./new-original-game \
  --trusted-local-operator
```

The intent uses the existing `GameBuildIntent` JSON contract. The destination
must be new and under an operator-controlled directory. The command refuses
existing outputs, malformed source, unapproved local operation and unsafe
POSIX publication. A failed post-export verification leaves the directory
**unqualified** for explicit operator inspection; it does not delete an
untrusted or concurrently replaced path.

A successful receipt proves actual canonical Python replay of the generated
game's winning actions and byte-for-byte source identity. The trusted digest
is taken from the in-memory package before export, not from a mutable file
after publication. For independent later verification, distribute the digest
separately and use the canonical `verify-export` command. This is not a
publisher signature, consumer install, native Godot run, legal clearance,
hardware test, or release approval.

The app command intentionally does not invoke a provider SDK or claim local
model inference. The guarded AI readiness and provider activation boundary
remain separate; a user can still author an original typed game and obtain
a playable source package while offline. Device, rights, security, malware,
accessibility and platform gates remain held until independently qualified.

Focused regression:
`python -m pytest -q skeleton/testing/test_app_studio_journey.py
skeleton/testing/test_secure_export_publication.py
skeleton/testing/test_dual_runtime_verify.py`.

## Durable independently inspectable verification receipt

Add `--receipt ./private-replay.json` to publish the canonical replay receipt
outside the exported game directory. The receipt is written through the
existing POSIX descriptor-safe, fsynced, no-clobber publisher and its SHA-256
pin is returned in `independent_receipt_sha256`. The verifier can later
inspect it with `python -m skeleton.ai.game_builder.offline_receipt_inspect_cli
--receipt ./private-replay.json --expected-sha256 <pin>
--trusted-local-operator`. Keep the pin in a separate trusted channel.
A stored receipt proves historical replay evidence and source integrity at
the time of verification; re-inspection does not reexecute the game or grant
release authorization. A receipt inside the source package is rejected.

## Offline recovery and independent replay of an existing game

A new build is not required to prove that a previously exported game is still
intact. Keep the independently distributed SHA-256 of its original release.json
outside the game package, then run the app-owned read-only verification path:

```sh
python -m skeleton app studio-journey --verify-existing \
  --output ./existing-original-game \
  --expected-manifest-sha256 <trusted-64-character-sha256> \
  --receipt ./private-reverification.json \
  --trusted-local-operator
```

This path rejects absent or forged pins, modified package bytes, symlinked
source roots, unsafe receipt parents, receipt collisions, and attempts to
combine build parameters with re-verification. The source directory is never
modified by the verifier; receipt publication is optional and is no-clobber.
A receipt destination inside the package is rejected **before** game creation,
avoiding an otherwise predictable partial handoff. If a concurrent filesystem
change occurs after preflight, the final publisher still fails closed; a
post-export verification failure leaves the source unqualified for inspection.

Verification reexecutes the canonical winning actions on the actual package
bytes. It does not perform model inference, native Godot execution, hardware
qualification, publisher identity attestation, rights clearance, or release.

## First-run export admission and failure recovery

Before allocating mirror/compilation work, the app checks the new export
destination through a pinned POSIX directory descriptor. Existing output,
symlinked ancestors, unowned or group/world-writable parents, unsupported
hosts, and malformed names fail before generating a game. Receipt destination
admission runs in the same preconstruction phase. These are preflights, not
locks: the final source and receipt publishers independently enforce no-clobber
and owner custody even if a competing process changes the filesystem.

After publication, any replay or receipt failure remains an explicit blocked
result. Never treat a leftover source directory as a qualified game; use
`--verify-existing` with the separately held manifest pin to requalify
without destroying or overwriting owner files.

## Inspect archived replay evidence from the app

For an already archived owner-private receipt, use the app entrypoint:

```sh
python -m skeleton app studio-journey --inspect-receipt \
  --receipt ./private-reverification.json \
  --expected-receipt-sha256 <independently-stored-receipt-pin> \
  --trusted-local-operator
```

The app delegates to the canonical descriptor-safe receipt inspector, validates
the independent SHA-256 and schema, and reports receipt integrity without
opening or executing the game. A historical replay record is not proof of
present gameplay, native hardware, legal rights, or release qualification.
The inspection mode rejects build/verify options and never writes a receipt.

## First-run offline game onboarding

Operators no longer need to hand-author JSON to create their first original
playable game. The app validates a typed canonical intent in memory, compiles
and adversarially reviews the original game, exports browser/Godot source
without clobbering files, then reexecutes the winning trace from disk:

```sh
python -m skeleton app studio-journey --onboard \
  --project-id my-first-original-game --title "Moonlit Compass" \
  --seed 1729 --output ./first-original-game \
  --receipt ./private-first-replay.json --trusted-local-operator
```

Optional `--subtitle`, `--theme`, `--width`, `--height`, and `--levels`
are validated by the canonical `GameBuildIntent` contract; defaults use a
small, offline-friendly one-level puzzle. The same first-run security and
verification pipeline is used as JSON-based builds. This is deterministic
source authoring, **not** evidence that a model was invoked or that a consumer
device, native Godot binary, rights, or release were qualified.

## Secure first-run JSON intent import

The existing `--intent` route now reads original game JSON through pinned
POSIX directory/file descriptors, rejecting symlinked parents, final symlinks,
hardlinks, unstable or oversized input files, duplicate object members,
nonfinite JSON, and malformed canonical `GameBuildIntent` records. This closes
the stat/read replacement window of a pathname-only import. Unsupported hosts
remain fail-closed; a Windows consumer install is not certified by POSIX tests.
`--onboard` avoids file import entirely by constructing the same typed intent
in memory, then runs the same game build, export and replay verification path.

## Independently pinned historical receipt → live game reconciliation

The archived receipt inspector alone only authenticates the historical bytes;
it does not prove that the receipt belongs to a game currently on disk. For a
read-only source-to-receipt handoff, independently retain **both** the game
release.json SHA-256 and the receipt SHA-256 in a trusted channel, then run:

```sh
python -m skeleton app studio-journey --reconcile-receipt \\
  --output ./existing-original-game --receipt ./private-first-replay.json \\
  --expected-manifest-sha256 <independent-game-pin> \\
  --expected-receipt-sha256 <independent-receipt-pin> \\
  --trusted-local-operator
```

The app replays the source with the canonical verifier, opens the historical
receipt through the existing descriptor-safe bounded inspector, compares the
complete original game/replay/source identity (not just the project name), and
replays the game **again** to detect intervening source mutation. Foreign
receipts, missing fields, type-confused booleans/integers, modified source,
symlinked receipt paths and conflicting CLI modes fail closed. Neither source
nor receipt is modified. This provides point-in-time source/receipt consistency,
not an immutable filesystem snapshot, publisher signature, model execution,
rights clearance, native Godot test or consumer release qualification.

Focused canonical regression:
`python -m pytest -q skeleton/testing/test_app_receipt_reconciliation.py`.

## Play, save and resume a verified offline game without network or model access

The application can now run actual canonical player moves on an existing
independently pinned original game source package. This does **not** execute
untrusted browser JavaScript or Godot GDScript; the canonical typed Python
gameplay engine performs each state transition and produces a hash-chained
replay. It first verifies the package and reconstructs the original world from
its pinned manifest, then verifies source again before handing it to gameplay.

```sh
python -m skeleton app studio-journey --play-existing \\
  --output ./existing-original-game \\
  --expected-manifest-sha256 <independent-game-pin> \\
  --moves up,right,down --save ./private-save.json \\
  --trusted-local-operator
```

A new save is published atomically and without clobbering an existing file,
through POSIX owner-controlled, nofollow directory descriptors. Store the
returned `independent_save_sha256` separately from the save file. To resume
and append new player actions:

```sh
python -m skeleton app studio-journey --play-existing \\
  --output ./existing-original-game \\
  --expected-manifest-sha256 <independent-game-pin> \\
  --load-save ./private-save.json \\
  --expected-save-sha256 <independent-save-pin> \\
  --moves left,up --trusted-local-operator
```

Restore rejects unpinned, changed, symlinked or hardlinked save files and
foreign-world replay histories. The canonical deserializer independently
reexecutes the entire action chain and checks every transition before adding
moves. Source is reverified after save publication; if a concurrent source
mutation is found, the save remains **unqualified**, not silently deleted.
This is deterministic reference gameplay and private local save/recovery,
not native Godot device qualification, multiplayer security, rights clearance,
AI inference or consumer release certification. No network access is required.

Focused tests: `python -m pytest -q
skeleton/testing/test_app_offline_gameplay.py`.

### Reversible original-game replay branches

Use `--fork-at N` together with `--load-save` and its independent pin to
replay the first N canonical actions, then append alternative moves and publish
a **new** no-clobber save. The original save remains unchanged. A fork beyond
the verified action history, a negative step, or a fork without a loaded save
is rejected before a new save is published. This is deterministic local
choice exploration, not a networked save synchronization service.

### Stable owner-controlled first-run intent import

JSON onboarding now requires the opened source intent to be owner-controlled
and not writable by group or other users. Two bounded descriptor reads must
agree, and the original parent path must still resolve to the pinned directory
inode before typed intent construction. A changed, swapped or concurrently
rewritten source is blocked before the costly game build or export.


### Read-only comparison of private offline playthroughs

After creating two owner-private saves with `studio-journey --play-existing --save`,
compare their reexecuted histories using `studio-journey --compare-saves
--output GAME_DIR --expected-manifest-sha256 MANIFEST_PIN --left-save LEFT.json
--left-sha256 LEFT_PIN --right-save RIGHT.json --right-sha256 RIGHT_PIN
--trusted-local-operator`. The manifest and both save hashes must be held
independently. Comparison rejects foreign-world, modified, non-private or
ambiguous saves, never writes to source or save paths, and reports the first
zero-based action index at which two canonical replay histories diverge.
An identical history returns null for the divergent index. A strict prefix
diverges at the first absent action. This only verifies offline source-level
gameplay, not AI inference, native Godot execution, device qualification,
rights certification, or release readiness. Saving a new replay now verifies
the original source again before publishing any new private save.

### Deterministic offline source delivery archive

After the exported source passes canonical gameplay verification, publish a
private reproducible browser/Godot source ZIP with `studio-journey
--package-existing --output GAME_DIR --expected-manifest-sha256 MANIFEST_PIN
--archive DELIVERY.zip --trusted-local-operator`. The archive contains only
independently verified source files and `release.json`, in deterministic
uncompressed ZIP format. Publication uses an owner-private, descriptor-safe,
no-clobber destination; no existing operator file is overwritten. Preserve the
returned archive SHA-256 outside the archive.

Read-only inspection uses `studio-journey --inspect-archive --archive
DELIVERY.zip --expected-archive-sha256 ARCHIVE_PIN
--expected-manifest-sha256 MANIFEST_PIN --trusted-local-operator`. Inspection
requires both pins, rejects ambiguous ZIPs, unsafe entries and mismatched
content, and never extracts or executes archive members. Inspection does not
reexecute source gameplay. A ZIP is **not** a signed installer, verified native
Godot build, device qualification, rights clearance or release certification.

### Pinned offline source installation and first playable after delivery

A separately pinned ZIP can be installed into a **new** owner-controlled
directory with `studio-journey --install-archive --archive DELIVERY.zip
--expected-archive-sha256 ARCHIVE_PIN --expected-manifest-sha256 MANIFEST_PIN
--output NEW_GAME_DIR --trusted-local-operator`. The archive is validated
without executing or trusting its members, then each source file is written
through private nofollow descriptors. The new destination is reserved with
no-clobber mkdir and verified by the canonical source/gameplay verifier
before a success receipt. Use `--verify-existing` and `--play-existing`
against the installed directory with the same independent manifest pin to
replay or save the actual original game offline. An interrupted install leaves
a nonqualified directory for explicit operator quarantine; it is never
mistaken for a completed consumer installation. This is source-level
installation, not a signed package, native device test or release approval.


### First-run original intent custody

The app first-run importer now pins the original intent file's device, inode,
size, link count, ownership, mode and nanosecond timestamps across two
bounded nofollow descriptor reads. Identical JSON bytes from a substituted
inode are not accepted as continuous source custody. The parent directory
remains independently re-opened and checked before the intent can reach the
canonical game builder. Excessively nested JSON is a typed fail-closed input
rejection, never a partially exported game. This is a POSIX source-custody
contract, not hardware or consumer-device qualification.

Focused acceptance: `python -m pytest -q skeleton/testing/test_app_studio_journey.py`.


### Independently pinned original JSON input

For an operator-supplied first-run JSON intent, `studio-journey` now accepts
`--expected-intent-sha256 <64-lowercase-hex>`. The digest must be acquired
independently of the input file, not copied from a field inside that file.
The importer checks its owner-controlled nofollow descriptor reads, file inode
continuity and independently supplied digest before the canonical game builder
is invoked. Wrong or malformed pins fail without exporting game source.

The resulting source-level receipt explicitly distinguishes pinned from
unpinned JSON input. Inline `--onboard` does not accept a file pin because
there is no external input file to authenticate. This feature does not sign
a game, establish intellectual-property rights, or qualify a consumer device.

Focused acceptance: `python -m pytest -q skeleton/testing/test_app_studio_journey.py`.
