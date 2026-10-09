# Native Game Release Intake — Real Files, Not Assertions

## New execution-plane boundary

**Module:** `skeleton/ai/game_builder/native_release_intake.py`  
**Regression suite:** `skeleton/testing/test_game_builder_native_release_intake.py`  
**First supported scope:** independently authored Windows, Linux and macOS SDL2/C source projects generated through `compile_originality_gated_desktop` and `export_rights_aware_desktop`.

The existing `release_assurance.py` checks whether independent reviewers signed the **declared** game source, executable, provenance, rights, license notices and machine destination. An assertion about a file's hash is insufficient if no one reads the actual bytes. The new byte-intake gate adds this missing concrete step.

`verify_native_release_intake(...)` reads actual game files from a specified local directory, the actual compiled executable (or candidate binary), and the provided build/gameplay evidence. It verifies:

1. `game.c`, `CMakeLists.txt`, `manifest.json`, `legal_review.json` are all readable, regular files, opened with no-follow semantics where supported; none can be silently replaced by a symlink.
2. The generated C game and CMake source bytes, paired with `manifest.json`, recompute to the exact **content-addressed native source digest** in the signed release candidate.
3. The project ID, rights evidence, native target, world digest, legal assessment, originality scan, credit notice digest and other declaration fields match **across** the source manifest and legal receipt.
4. `rights/CREDITS.md`, `rights/THIRD_PARTY_NOTICES.txt`, and `rights/material_inventory.json` exist and match the actual reviewed `CreditsBundle` content byte-for-byte.
5. The externally provided *native binary* is a bounded regular file with a basic Windows MZ, Linux ELF or macOS Mach-O header appropriate to the selected destination, and its SHA-256 equals the exact review candidate's hash. **A correct magic header does not prove that the file is runnable or genuine.**
6. The actual build and gameplay evidence files match the separately identified evidence digests. These may still be unverified claims unless the independent technical reviewer validates their origins, build reproducibility, compiler execution and real gameplay.
7. Missing documents, altered C game source, changed credits, stale binary hashes, substituted build receipts, false legal authorization, mismatched jurisdictions or symlink redirection **stop the intake**.

The output is a deterministic `NativeIntakeReceipt` with the exact digests and names of ten files examined. It explicitly declares:

- `file_bytes_verified: true`;
- `compiler_execution_verified: false`;
- `emulator_or_hardware_execution_verified: false`;
- `copyrights_independently_verified: false`;
- `release_authorized: false`.

There is **no code path** that converts native byte identity into a legal copyright judgment, a recognized console publisher authorization, a verified simulator execution claim, or a license to distribute somebody else's commercial ROM, firmware or game asset.

## Compatibility and progression

This pass adds concrete file validation for the existing C/SDL2 desktop exporter. Do not infer that the same bytes or headers are applicable to NES, Game Boy, C64, Atari, DOS or a proprietary console package. Each platform needs its own trusted file format validator, reproducible build rules, emulator/hardware test receipts, toolchain availability and legally valid publication channels.

The staged pipeline now runs:

**Authored homebrew** → **eight-class provenance and plagiarism audit** → **originality-bound port** → **native source with author credits and third-party notices** → **actual compiled output + build/replay file intake** → **independent Ed25519 signed 10-domain review** → **separate responsible-publisher decision**.

The system distinguishes an *original homebrew game inspired by historical hardware ideas* from unauthorized copying of a protected game. A device license or technical exclusivity condition may affect publishing to particular hardware, without necessarily monopolizing its gameplay ideas on another independently built system. Whether a specific successor is infringing remains jurisdiction- and fact-dependent.

## CI and limitation

The dedicated `Homebrew Historical Archive` workflow exercises both successful byte identification and rejection of modified C code, altered manifests/credits, binary substitutions, malformed format, symlinked inputs, mismatched rights packet/territories and attempts to forge release states. Its test binaries are **synthetic**, not real runnable Windows builds. A passing unit test demonstrates validation logic, *not real hardware acceptance*.

The no-follow file opening method presently depends on operating-system support for `O_NOFOLLOW` and directory-handle operations. Where unavailable it fails closed instead of weakening the security boundary. Windows-hosted native validation will need a Windows-specific secure file-opening implementation.

No universal game history catalog or legal reference collection is currently exhaustive. The exact native release must still be independently built, executed, reviewed and authorized under relevant law and platform terms before any publication.
