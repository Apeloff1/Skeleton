# Source-Bound Mission Assistance

`python -m skeleton scene-mission-assist --demo` provides a non-mutating,
replay-proven hint for an authored mission ending. Supply `--session-json`
for a checkpoint, `--ending-id` for the target and optional bounded
`--max-states` / `--max-depth`. A `found` result contains the next
canonical legal action, complete route witness, state digest and a portable
save checksum for the previewed move. Use `--verify-json` to recompute the
search and reject forged hints.

The advisor does not play on behalf of the user. It never invents quest
rewards, choices, teleportation, mission completion or ending unlocks. If
search is exhausted, status is `inconclusive` and no action is suggested.
Already completed checkpoints are not advanced again. Checksums are
corruption detectors, not proof of authorship or permission to execute
untrusted sources.
