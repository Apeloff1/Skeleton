# Native ROM and emulator implementation ledger (15 October 2026)

The app has two distinct execution paths. The **experimental in-process DMG
interpreter** in `skeleton/jeeves/game_rom_runtime.py` executes LR35902
instructions and supports limited ROM-only, MBC1, RTC-free MBC3 and
non-rumble MBC5 cartridges. Its grayscale raster has approximate timing;
audio, CGB-only hardware, RTC, rumble, and arbitrary commercial game
compatibility remain out of scope. It is not a substitute for native cores.

The **libretro path** uses `skeleton/jeeves/game_emulator_catalog.py`,
`game_emulator_host.py` and `game_emulator_worker.py`. It requires a
locally built, exact-sha approved native core and a safely materialized
rights-cleared content bundle. This path does not silently replace missing
console emulation with a reference game simulation.

## Newly pinned optional build recipes

| Core | Hardware target | Exact source pin | Availability |
| --- | --- | --- | --- |
| SameBoy | GB, GBC, Pocket, Light | `aa158a889a48b538a0302873704a34577c8eb67d` | recipe only |
| Nestopia | NES | `06a8949e0b3cf60e3a38a374b1426bf40fccb9a0` | recipe only |
| Mesen | NES | `0102910c39ad1a62bc3f784466f3f67ca9eae335` | recipe only |
| Snes9x2010 | SNES | `fe690dd321fa5a46b5234a2bde089d2518c62b0e` | recipe only |
| Beetle Saturn | Saturn | `faef2779a7568c1734addc4fe63cc76e9fa2566b` | recipe only |

These five are added to `PINNED_CORES` as opt-in alternatives. The six
original default build selections have **not** changed. An upstream source
pin is reproducibility provenance, not evidence that the target host has
the compiler, headers, source submodules, licensed firmware or functioning
software-rendering path.

## Operator procedure

On a supported Linux host, use private absolute directories on a filesystem
you control. Review upstream licenses and source first. The following is an
**example command**; it has not been run by this change:

```bash
python scripts/install_game_emulator_cores.py \
  --source-root /private/emulator-source \
  --install-root /private/emulator-installed \
  --fetch-sources \
  --core sameboy --core nestopia --core mesen --core snes9x2010 \
  --core mednafen_saturn \
  --jobs 2
```

For bulk build orchestration, an **explicit** `--fleet` request attempts all
currently pinned recipes rather than stopping at the first failure. Each core
uses the same source, static ABI, firmware and license gates; individual
failures are retained in the returned `failures` ledger. The CLI returns a
nonzero exit code if any selected core failed or remains unapproved, even when
some binaries were successfully installed:

```bash
python scripts/install_game_emulator_cores.py \
  --source-root /private/emulator-source \
  --install-root /private/emulator-installed \
  --fetch-sources --fleet --jobs 2
```

Use `--fleet --core sameboy --core nestopia` for a failure-isolated subset.
These commands are operator examples, **not** a report of completed builds.
Dependencies such as unsupported GPU contexts and unavailable firmware will
continue to fail closed rather than be represented as supported machines.

The installer uses declared exact upstream revisions, independently inspects
the produced shared libraries, stores immutable digest-named artifacts,
retains license and build identity records, and writes a private approval
registry. A Saturn build without legitimately operator-supplied
`sega_101.bin` and `mpr-17933.bin` is explicitly left unapproved.
The first install does not acquire or distribute those copyrighted files,
game ROMs, DRM keys or BIOS images. Snes9x2010 source has noncommercial
restrictions requiring independent legal review.

After an approved local install, the application must be pointed at its
operator-registry file, for example:

```bash
export SKL_GAME_EMULATOR_REGISTRY=/private/emulator-installed/cores.json
```

The actual host additionally requires its declared Linux bubblewrap and
runtime policy support. `approved` means static core/firmware admission,
**not** ROM/game compatibility, human playability or successful startup.

## Operational completion gates

For each target independently, record the exact approved core commit and
library SHA256; source/license review; any lawful BIOS identity; isolated
libretro ABI startup; rights-cleared homebrew ROM header/disc content
admission; real frame/audio production; controller replay;
snapshot/restore/reboot; termination and crash behaviour; and independently
reviewed actual acceptance evidence.

The mapping catalog lists substantially more historical target IDs than
installed cores. Unsupported targets (including many modern hardware
platforms), systems needing GPU/hardware contexts, firmware-heavy
platforms, and those with missing binary toolchains remain unavailable.
No result in this change should be read as those machines being emulated.
Do not count a platform catalog row, emitted native source, compiler receipt,
or emulator-compatible agent interface as a booted executable game.

## Evidence status

- Native cores compiled/installed by this branch: **zero**.
- ROM compatibility certification by this branch: **zero**.
- Tests authored here: in-memory synthetic cartridge banking regressions.
- Tests, native boot sessions, installer execution or hardware runs performed
  during this change: **none**.
- Current status: implementation on a review branch; release authority false.


## Native first boot and rewind acceptance gate

The new `scripts/audit_game_emulator_first_boot.py` audits only operator-approved
native cores with privately provided, hash-pinned, lawfully owned single-file
ROMs. **It does not download or distribute game data, build ROMs, approve
firmware, trust reference simulation, or auto-promote a newly compiled core.**

Example `/private/research/first-boot-cases.json`:

```json
{
  "schema_version": "skeleton.game.native_emulator_first_boot_matrix.v1",
  "cases": [
    {
      "core_id": "gambatte",
      "target_id": "game_boy",
      "rom_path": "/private/roms/owned-original.gb",
      "filename": "owned-original.gb",
      "rom_sha256": "<replace with 64-hex actual SHA-256 of your owned ROM>"
    },
    {
      "core_id": "sameboy",
      "target_id": "game_boy",
      "rom_path": "/private/roms/owned-original.gb",
      "filename": "owned-original.gb",
      "rom_sha256": "<replace with the same actual SHA-256>"
    }
  ]
}
```

Once each native core has been independently compiled and approved in the
operator registry, execute:

```bash
python scripts/audit_game_emulator_first_boot.py \
  --manifest-file /private/research/first-boot-cases.json \
  --evidence-file /private/research/first-boot-evidence.json \
  --rights-acknowledged --timeout 5
```

The gate requires an actual native boot frame, a real idle action and button
action, an opaque source savestate, and exact observation, reward-component,
transition-digest and final savestate equality after rewinding and repeating
the same action. Failure of one core does not falsely mark other cores as
operational. Missing approval, emulator sandbox, firmware, savestate
capability, legal content, native callbacks or deterministic replay is a
failed case; the command returns a nonzero status if any case failed.

The operator report distinguishes **per-core actual native first-boot and
replay acceptance** from the much larger independent hardware accuracy,
reliability, licensing and AI-training acceptance requirements. No core has
been accepted by this new gate during this source authoring pass.

See [advanced emulator training and research](ROM_EMULATOR_ADVANCED_RESEARCH.md)
for neural parameter fitting, source-confirmed action planning and controlled
game-objective hypotheses.


## Operator-authorized optical disc, playlist and multi-file native first boot

The standard cartridge gate handles one hash-pinned original ROM up to
the native host's 16-MiB inline capacity. Larger original/lawful content
requires a **different**, governed source-content route. The new
`scripts/audit_game_emulator_disc_first_boot.py` uses the existing
`GameContentBundle` and `GameContentReference` native-host transport.
That transport already validates CUE/BIN, GDI, M3U and other supported
disc descriptors and requires an approved native core, valid BIOS and
actual sandboxed libretro execution. The new audit does not implement,
download, grant permission for or emulate BIOS/game media.

Example private operator manifest `/private/media/source-discs.json`:

```json
{
  "schema_version": "skeleton.game.approved_native_disc_first_boot_matrix.v1",
  "cases": [
    {
      "core_id": "mednafen_saturn",
      "target_id": "sega_saturn",
      "entrypoint": "original-disc.cue",
      "files": [
        {
          "name": "original-disc.cue",
          "path": "/private/media/original-disc.cue",
          "size_bytes": 71,
          "sha256": "replace-with-exact-64-character-lowercase-sha256"
        },
        {
          "name": "original-track.bin",
          "path": "/private/media/original-track.bin",
          "size_bytes": 123456789,
          "sha256": "replace-with-exact-64-character-lowercase-sha256"
        }
      ]
    }
  ]
}
```

The illustrative filenames, sizes and SHA fields above must be replaced
with **actual** locally held media metadata; the referenced CUE text must
name the actual supplied track filename. An arbitrary JSON manifest
is not evidence that Saturn or any other console booted.

```bash
python scripts/audit_game_emulator_disc_first_boot.py \
  --manifest-file /private/media/source-discs.json \
  --evidence-file /private/media/native-disc-first-boot.json \
  --rights-acknowledged --timeout 5
```

The operator gate enforces at most eight cases, 16 exact local files per
case, and the native-host's actual referenced-file and aggregate size
limits. It rejects symlinks, duplicate aliases, malformed descriptors,
missing dependencies, changed length and SHA256, and unsupported BIOS/
core approval. Source files are consumed in bounded streaming chunks,
not copied into an in-memory Python ROM blob. A source hash is checked
again while streaming, and the existing materializer checks its actual
private output before the native core can load any content.

A valid core must then actually produce a native frame, execute idle
and A, produce an opaque savestate and return the identical observation,
reward, action digest and **source state after rewind/replay**. The output
retains independent per-core failures; one failing native disc never
inflates another platform's readiness. This audit is **operator-invoked
only** and is not a new automatic push/PR action.

**Known limits:** This is an acceptance gate, not a promise that any
specific disc/core will load. Runtime savestate capability, proprietary
firmware, media format, worker sandbox, OS support and core accuracy remain
separate gates. The initial test uses only basic controller inputs; it
does not establish complete game functionality, victory, legal ownership
or independent emulator hardware cycle accuracy. No native multi-file
disc was boot-verified during this source authoring pass.


## On-demand native compilation, without CI congestion

`.github/workflows/on-demand-libretro-core-build.yml` is a
**manual-dispatch-only**, single-job Linux build/inspect entrypoint.
It has no push, PR, schedule or merge triggers. Once present on the
repository's default branch and enabled by GitHub Actions, select
**Actions → On-demand pinned libretro core build → Run workflow**
and choose exactly one of:

- SameBoy (`sameboy`): Game Boy family
- Nestopia (`nestopia`): NES
- Mesen (`mesen`): NES
- Snes9x2010 (`snes9x2010`): SNES, independent upstream licensing review
- Beetle Saturn (`mednafen_saturn`): Sega Saturn; required legal firmware
  is **not** supplied by this workflow

The workflow checks out the requested commit, validates a fixed core
allowlist, fetches the corresponding **exact upstream pinned revision**,
attempts a bounded local Linux compilation, inspects the ELF/libretro
library through the existing approved catalog, and writes
`source-build-receipt.json`. This JSON deliberately separates:

- `compiled_native_binary_sha256`: the actual candidate library built
  and inspected in that workflow run, **only if** the installer succeeded.
- `operator_approval_status`: the installer/registry's *separate*
  approval or candidate designation, including blocked firmware.
- `real_libretro_core_execution_verified=false` and
  `rom_boot_verified=false`: no native game was executed in the build job.
- `production_model_weights_modified=false`: source builds are not
  neural parameter training.

The artifact retains small receipts and diagnostics for three days,
not core binaries, third-party ROMs, proprietary BIOS, build trees or
long-term mutable shared libraries. The job is serialized per ref, has a
45-minute outer timeout, and cancels superseded work on that ref.
A failed build remains a GitHub Actions failure and cannot be reported
as an operational console.

**Important limitation:** The workflow was authored on draft
PR #3935 and has not executed. GitHub generally requires manually
dispatchable workflow files on the repository default branch before
they appear in the normal Actions run-workflow UI. It must be merged
and explicitly dispatched before obtaining any verified native build
receipts. The separate operator-controlled first-boot gates remain
required afterward for actual emulator functionality.
