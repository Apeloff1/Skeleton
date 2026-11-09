# Focused emulator qualification workflow

The manually triggered `.github/workflows/focused-game-emulator-comparison.yml` is deliberately **not** wired to push, PR synchronization or daily schedules. It avoids the repository's already congested automation queue while providing an operator-driven exact-checkout regression suite for the high-risk emulator changes.

When selected in GitHub Actions (Focused Emulator Comparison Qualification > Run workflow), it compiles modified Python runtime/CLI sources, executes eleven focused unit/HTTP/source-contract modules and checks that the static 169-target audit does not invent emulator boots. It does not need game ROMs, emulator binaries or BIOS, and cannot prove actual game compatibility. Real native qualification remains a distinct operator process using rights-cleared sources and approved cores.

A passing manual source-only job is not a release sign-off. The live runtime also requires the local Bubblewrap syscall probe and actual native worker replay evidence. The workflow was committed but **not dispatched** during this source-editing pass.
