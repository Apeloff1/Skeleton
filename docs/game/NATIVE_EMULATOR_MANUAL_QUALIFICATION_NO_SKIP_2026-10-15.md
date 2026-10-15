# Native emulation qualification must execute, not skip — October 15, 2026

A green focused emulator CI workflow is not sufficient evidence of an actually exercised sandbox if optional native tests quietly skip for lack of Linux Bubblewrap or a C compiler. The manual-only qualification job already installed Bubblewrap, but its regression list accepted skipped tests.

The focused workflow now separates source-contract regressions from the **required** two-native-test qualification gate:

1. Compile and load a tiny original C libretro shared library, send controller inputs, observe native video/PCM callbacks and round-trip savestate state.
2. Install the actual sandbox dependency, start that homebrew fixture through Skeleton's isolated Bubblewrap native host, check real controller-affected video/audio output and ensure worker teardown.

The qualification command fails if either test errors, fails, or **skips**, and requires exactly two native contract tests to execute. This is a manually dispatched workflow—no new push/PR/scheduled trigger is added. No commercial ROM, proprietary firmware, licensed-game assets or model weights are involved.

The multimodal verified-ingestion test also now exercises the complete corpus staging/publication/reverification path, including deliberate tampering with its recorded issued decoder digest. The test enforces source-hash identity and a fail-closed record read.

**Meaningful distinctions:** Passing these two tests proves the minimal libretro ABI and executable Linux sandbox integration on the workflow runner. It does *not* validate 169 console emulators, proprietary platform firmware, legal rights to games, long-duration performance, or learned model weights.
