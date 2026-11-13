# Player-controlled offline combat campaign

Run: python -m skeleton combat-campaign-player demo

The original two-encounter Lantern Harbor patrol uses canonical turn combat.
The player directly chooses attack, guard or rest for the hero; only opposing
actors use the deterministic tactical policy. Surviving hero HP carries into
the next authored encounter. Credits are earned only from verified victories.

CLI subcommands: demo, simulate, resume, verify, export, import and play.
Interactive play accepts one strict JSON action per hero turn and emits a
source-bound replayable checkpoint. EOF or repeated invalid input emits the
last verified checkpoint and exits nonzero. Imported rewards, combat states
and checkpoints are never trusted without reconstructing the complete player
journal and deterministic opponent turns.

Focused regression: python -m pytest skeleton/testing/test_combat_campaign_player.py

Checksum digests detect corruption, not author signatures. This is offline
single-source gameplay evidence, not consumer/device/release certification.
