# Original-content provenance claim inspection (not rights certification)

`python -m skeleton app inspect-original-provenance` verifies that an
independently pinned, private JSON claim inventory matches actual original
browser and Godot source bytes in a canonical replay-verified project.

Required flags: `--installed`, `--claims`,
`--expected-manifest-sha256`, `--expected-claim-sha256` and
`--trusted-local-operator`. The claims file is a bounded, owner-private
JSON file (maximum 8192 bytes), using schema
`skeleton.app.original_content_provenance_claims.v1`, with exact fields
`schema`, `project_id`, `manifest_sha256`,
`rights_review_status: "unreviewed"` and a sorted unique `files`
array of 2–24 entries. Each entry has `path`, `sha256` and
`origin` (`ai_generated_original` or `human_authored_original`).
Both `index.html` and `godot/project.godot` must be present.

Source reads are nofollow, descriptor-bound and size-bounded. Both file
digests and inodes are rechecked across a second canonical replay proof.
The inventory is **not** exhaustive by default. Claim strings do not
prove authorship, license grants or plagiarism clearance. The inspector
never marks rights, publisher identity, native devices or consumer release
as certified.

Focused acceptance:
`python -m pytest skeleton/testing/test_app_offline_original_content_provenance.py -q`.
