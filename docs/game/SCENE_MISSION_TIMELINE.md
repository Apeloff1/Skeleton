# Offline mission timeline and checkpoint forks

Canonical entry point: python -m skeleton scene-mission-timeline demo

The command provides independently playable mission branches from authored
scene-mission sources. The canonical mission runtime validates all choices,
movement, inventory pickups, quest prerequisites, endings, save ancestry and
event receipts. Branches are source-bound, not user-granted entitlements.

Commands: demo, inspect, verify, session, compare, append, fork, checkout,
export, import. All input is bounded inline JSON; stdout is deterministic JSON
and invalid input returns code 2 with a JSON error on stderr.

Example workflow: obtain a demo timeline; inspect its revision and digest;
append a legal action batch to a named branch with --expected-revision and
--expected-digest; fork at a replay-verified turn; compare independent endings;
export the timeline and import it offline. Mutations require both revision and
digest leases and never publish partial action batches. A fork keeps the
canonical action prefix of its parent at the selected checkpoint.

Limits: 12 branches, 128 canonical actions per branch, 2 MiB JSON per value,
and 1,000,000 revisions. Duplicate keys and nonfinite numbers fail closed.
The entire branch graph is replayed on verification and import, including
parent-prefix, checkpoint, source and canonical head/save digests. JSON hashes
are corruption detectors, not author authentication or trusted signatures.
External creator rights require independent authorization and provenance.

Focused test entry: python -m pytest skeleton/testing/test_scene_mission_timeline.py -q
