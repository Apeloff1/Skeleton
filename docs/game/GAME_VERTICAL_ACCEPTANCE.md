# Playable game vertical acceptance

The installed command `python -m skeleton game-vertical-accept` verifies a complete
original game path, not just a structural source manifest. It supports the
canonical `quest` chapter campaign and `forge` tactical crafting adventure.

`demo --kind quest` plays both original Lantern Harbor quest chapters, checks
earned ending flags and verifies a checkpoint replay. `demo --kind forge`
plays original arena salvage, spends earned materials on equipment, equips it,
wins the next fight and checks the exact same deterministic replay.

`run --kind forge --source-json JSON --actions-json JSON` accepts an authored
source and player actions. The optional `--checkpoint-at N` selects a replay
boundary. The engine runs the full session and independently resumes the
checkpoint, rejects differences, verifies canonical event history and round-trips
the real portable save through the existing engine import/export contract.
A run that does not earn a victory is rejected rather than marked accepted.

`verify --acceptance-json JSON` replays source and actions instead of trusting
the supplied report. `export --acceptance-json JSON` creates a bounded
offline evidence bundle; `import --bundle-json JSON` checks the checksum,
source identity and re-executes gameplay. These JSON arguments are intentionally
bounded, strict and contain no filesystem path or remote provider access.

This is **functional acceptance evidence only**. Checksums detect accidental
corruption, not a hostile author's ability to forge new content. The caller must
separately authorize source provenance. No physical-device, installer, payment,
network, platform, rights or release qualification is implied.
