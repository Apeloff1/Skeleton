# Dragon native compiler completion — 2026-10-10

This increment closes the missing Commodore 64 path in the existing native CLI
and compiler, and repairs artifact handling for every supported compiler target.
It does not mark the full game-builder vision or a masterplan volume complete.

## Completed behavior

- `python -m skeleton.ai.webcrawler.dragon_native_cli --target commodore_64
  --out /path/to/new/project --compile` now produces an actual cc65 C64 PRG.
  Local validation produced SHA-256
  `ddf971242fc66c15b163159b375173109fb719f4e2942c2ffae44a10423ddbe1`.
- Fixed argument vectors invoke the installed compiler. No generated Makefile is
  executed, no toolchain is downloaded, and compilation requires explicit consent.
- Every invocation checks the source inventory/digest, snapshots verified text,
  and compiles in a fresh private directory. Old objects and binaries cannot
  produce successful evidence for a new invocation.
- Compilation failures, missing tools, launch errors, timeout, oversized output,
  malformed binary and missing output return explicit unsuccessful outcomes.
  Failed builds preserve previous published binaries; success atomically replaces
  the binary and returns its SHA-256. Private build directories are removed.
- Compiler diagnostics are limited to 64 KiB of capture and 1,200 characters in
  the result. The total configured compiler deadline is 5–120 seconds. Sources
  are limited to 128 files of at most 120,000 UTF-8 bytes each. Binary size is
  checked before reading into memory.
- C64 checks require the expected load address, BASIC SYS entry, line termination,
  in-range machine-code entry and bounded payload. Game Boy checks now also
  enforce ROM size declarations and the global cartridge checksum. NES checks
  require the actual emitted NROM header, rejecting trainer/mapper/NES2 variants.
- CLI overwrite preflights all output paths before changing existing files.
  Symlinked roots/components are rejected and atomic replacement avoids writing
  through hard links to unrelated user files.
- The existing signed build-evidence ledger accepts validated C64 PRG bytes,
  binds them to the owner and canonical practice-source digest, and exposes
  the result in curriculum evidence. Duplicate signing is idempotent, earns
  no XP, and cannot imply GB/NES mastery or verified gameplay. Existing ROM
  receipt claims remain unchanged; C64 uses an explicit native-program claim.
- Existing hosted ROM workflow now builds and uploads C64 PRG output alongside
  GB, CGB, platformer and NES binaries. Hosted success must be observed separately.

## Construction evidence and operating limits

| Level | Implementation or explicit limit |
|---|---|
| L00–L01 | Existing crawler native-project/compiler/CLI owners; no new service or provider |
| L02 | Existing NativeBuildResult and source-generated state preserved; C64 uses compiled_native only after real compilation |
| L03 | Explicit local compilation permission; trusted operator-installed toolchain |
| L04 | Validate → snapshot → fixed compiler commands → binary checks → atomic publication |
| L05 | Source digest and binary digest remain distinct; output never changes source-generation status |
| L06 | Reject linked/traversing paths; no credentials, provider call or network acquisition |
| L07 | Cleanup and previous-artifact preservation for compiler failures and timeout |
| L08 | Result state, step count, duration, bytes, binary hash and bounded diagnostics |
| L09 | Source, diagnostic, binary and deadline limits; one sequential toolchain per call |
| L10 | Actual cc65/RGBDS builds plus stale-output, link, corruption, timeout and failed-publication regressions |
| L11 | Existing CI workflow and artifact retention; revert this increment to remove C64 CLI support without state migration |
| L12 | CLI --compile is opt-in; missing SDK returns failure; generated sources stay available for inspection |
| L13 | Native emulator play, original-device acceptance, other SDK adapters and full product qualification remain open |

This is a local trusted-toolchain helper, not an OS sandbox. A restricted runner
is still required for untrusted compilers or concurrent hostile filesystem
mutation. Source replacement is atomic per file, not a multi-file transaction;
a host crash during explicit overwrite can leave a mixed project, which the
compiler rejects until regenerated. Concurrent builds must use separate output
directories. File checks and hashes establish format/content evidence, not
playability, fun, original-hardware compatibility or legal release clearance.

Signed: Codex, 2026-10-10. Signature applies to this implementation increment
and its recorded local evidence; it does not confer enterprise qualification.
