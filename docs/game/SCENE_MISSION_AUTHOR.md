# Transactional authored mission editor

Run `python -m skeleton scene-mission-author demo` to preview the original
Harbor Lantern mission through canonical gameplay and portable export.
`new --source-json JSON` initializes a source-bound editor. The returned
editor contains a revision and digest; supply both with every
`apply --editor-json JSON --edits-json JSON --expected-revision N
--expected-digest HASH` operation. A stale lease fails closed.

Supported typed edits adjust choice and mission reputation, ending
thresholds, scene step limits, exit item requirements and pickup items.
Each edit is replayed from the original source, re-normalizes the entire
mission/world graph and records a digest-chained receipt. A batch is atomic:
one invalid reference, impossible exit item or no-op rejects the entire
batch without modifying the prior editor. Maximum 16 edits per batch and
64 per editor. No authored scripts or filesystem effects are accepted.

`verify --editor-json JSON` replays the entire journal.
`preview --editor-json JSON --actions-json JSON` executes the edited
source through the canonical mission runtime, verifies its portable
save roundtrip and computes earned consequences. The preview does not
grant rewards or certify an unplayed ending. Digests are integrity
checks, not signatures; source provenance remains the caller's duty.

Focused validation:
`python -m pytest skeleton/testing/test_scene_mission_author.py skeleton/testing/test_scene_mission.py -q`.
Final-head CI and release policy must still pass.
