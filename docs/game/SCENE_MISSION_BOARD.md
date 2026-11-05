# Replay-derived scene mission objective board

Use `python -m skeleton scene-mission-board --demo` to inspect the original
Harbor Lantern mission. Supply `--source-json` for an authored source or
`--session-json` for a canonical saved session. The output contains
available legal actions, mission prerequisites, earned reputation, current
scene, inventory and completed choices. It does not grant rewards.

Use `--export` to create a portable bundle with the full canonical session
and its read-only board. `--bundle-json` replays the session and recomputes
every board field; changing an objective or recomputing a checksum cannot
forge a reward or completion proof. Digest receipts detect corruption,
not trusted author identity. Keep original source provenance separately.

Objective status is earned, blocked (missing dependencies), available
(prerequisites met, trigger pending) or trigger_ready (trigger already
satisfied but not yet granted by canonical progression). This status
does not change the runtime. Legal moves are filtered through the
real director rather than inferred from author-supplied descriptions.

Focused validation:
`python -m pytest skeleton/testing/test_scene_mission_board.py skeleton/testing/test_scene_mission_interactive.py -q`.
All final-head CI gates remain required before promotion or release.
