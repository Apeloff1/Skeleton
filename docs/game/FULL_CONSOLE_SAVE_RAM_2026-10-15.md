# Native console SRAM custody and cold-resume qualification

This implements the *real* libretro RETRO_MEMORY_SAVE_RAM region (ID 0) in Skeleton's already-sandboxed native emulator worker. It does not fabricate game saves or certify any of the 169 catalog platforms.

## Implemented interfaces

- save_ram_export: obtains a bounded 1–8 MiB memory region from a running approved libretro core and returns exact-size, SHA-256-checked bytes through the private host/worker protocol.
- save_ram_import: imports only into the same pinned content/core/firmware/registry before the first native reset; actual worker memory size, exact bytes and post-write readback must match. An invalid or partial native operation fails closed.
- The host includes core and content identity, pinned binary and firmware hashes, RAM region identity, byte count and SHA-256 in a separate receipt. The imported RAM hash is included in the resumed environment digest.
- Raw bytes remain in user-owned local .srm files rather than in GitHub, report JSON, network HTTP or production AI weights. A separate JSON receipt supports independent verification.
- Optional cold-resume qualification starts a second isolated native core, imports the checkpoint, verifies it in memory, runs actual retro_reset, then verifies the SRAM remained present. This checks a narrow memory-retention property; it does not prove game-save compatibility or fidelity.

## Operator commands

From a rights-cleared study manifest and approved Linux Bubblewrap core:

    python3 scripts/qualify_full_console_save_ram.py \
      --study /private/study.json --game my_game \
      --registry /private/approved_cores.json \
      --steps 4 --output-dir /private/evidence \
      --verify-fresh-resume --rights-acknowledged

Restore the saved RAM into a different native worker and capture new evidence:

    python3 scripts/qualify_full_console_save_ram.py \
      --study /private/study.json --game my_game \
      --registry /private/approved_cores.json \
      --resume-metadata /private/evidence/my_game.sram.metadata.json \
      --resume-save-ram /private/evidence/my_game.srm \
      --steps 4 --output-dir /private/resumed-evidence \
      --rights-acknowledged

Supported **only** for cores that expose RETRO_MEMORY_SAVE_RAM; disc-based memory cards or file-based battery saves may require other core-specific arrangements. Unsupported cores fail honestly.

## Remaining gates

The added regression cases use constructed memory and fake worker callbacks; real installed cores, multi-disc media, controller/input timing, audiovisual accuracy, actual game-save recognition, rights status and model training are not claimed as verified. The focused source-contract workflow is intentionally manual-only, to avoid congesting push/PR queues.
