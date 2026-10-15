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
