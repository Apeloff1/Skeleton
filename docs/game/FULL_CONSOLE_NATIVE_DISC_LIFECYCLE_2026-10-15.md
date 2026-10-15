# Full-console libretro media lifecycle — native multidisc v0/v1

This pass advances Skeleton from “core listed in a registry” toward operator-verifiable, whole-console runtime behavior. The existing Bubblewrap-isolated native host already provides core boot, controller input, video, audio and savestates. This addition supplies a controlled multi-disc media lifecycle.

## Concrete runtime changes

- Native worker: libretro command 13 (legacy disk interface), 57 (interface version query), and 58 (extended disk interface). Five mandatory function pointers from the ABI-compatible first seven fields are admitted. Paths, media insertion from new files, arbitrary append/replace operations and callback addresses never cross the host boundary.
- Core status: zero to 32 registered images, current index, tray-ejected flag and interface version. Empty image tables are treated as unavailable rather than breaking conventional cartridge boots; malicious or impossible counts fail closed.
- Swap transaction: eject, verify, select registered image, insert, verify. Re-selecting the active image is a no-op. Native callback failures terminate the worker, avoiding unacknowledged partial media state.
- Host: disc_status(), swap_disc(index), and disc_receipts() methods with exact response schemas, maximum 32 accepted changes, SHA-256 receipts, and per-core/per-content/per-environment provenance. Disc operations and savestate operations are serialized.
- Savestate: a disc-bearing snapshot captures the active index, tray state and media-change chain. Restore refuses incompatible disc context. Cartridge/other no-disc snapshot formats remain unchanged.
- Operator CLI: scripts/qualify_full_console_disc_cycle.py performs real, rights-gated native multi-file console boot, bounded controller steps before and after swapping, audiovisual frame receipt collection, and optional savestate roundtrip.
- Source-only regressions: tests/test_game_emulator_disc_control.py uses fake ABI callbacks and mocked host authority; it does not certify real console compatibility. Existing manual-only focused qualification workflow now includes these tests and command compilation, without enabling any new push, pull-request or schedule triggers.

## Operator procedure

Prepare a rights-cleared, validated comparison study with the selected game's governed multi-file bundle (e.g., a supported M3U entrypoint with two verified disc images), an installed and approved libretro core, exact content hashes, and operator-controlled firmware. Run from the repository root:

    python3 scripts/qualify_full_console_disc_cycle.py \
      --study /private/console-study.json \
      --game my_multidisc_game \
      --registry /private/approved-cores.json \
      --disc-index 1 \
      --before-steps 2 --after-steps 2 \
      --output-dir /private/console-evidence \
      --rights-acknowledged --check-savestate

A successful invocation writes a small JSON report with real native boot, input, audio/video and media-change receipts. No game ROM/BIOS bytes or copyrighted captured frames are exported. No core is fetched or installed and no Dragon/Jeeves model weights are changed.

## Hard boundaries still open

1. The source edits were not tested against any real approved core/media pair. Console boot and swap compatibility must be qualified on lawful homebrew/test media.
2. Software-frame-only native host currently lacks OpenGL/Vulkan hardware render contexts required by some contemporary cores. Unsupported cores fail, not silently fall back to pretend execution.
3. Specialized physical peripherals, light guns, motion/haptics and multitap subdevice modes remain nonqualified.
4. Durable save RAM, console memory cards and independent per-game governed persistence remain a separate capability from temporary sandbox state.
5. The dual-screen live comparison desk has not been wired to invoke disc swapping; this operator CLI is the full native disc lifecycle path in this slice.
6. The 169-target matrix still distinguishes declared mappings, approved installations and real observed boots. A listed target is not a completed emulator.

Real native execution, physical-console timing accuracy, gameplay completion, source rights, and production AI training gains are not inferred from these code changes.
