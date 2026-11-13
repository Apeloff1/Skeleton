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


### Same-byte source replacement custody

The read-only provenance inspector pins each claimed file's original device,
inode, size, ownership, permissions and timestamps. It now rechecks these
identities after the initial content read **and again after the final canonical
playable-source replay**. A same-byte replacement of a claimed source file
cannot be mistaken for uninterrupted source custody merely because the SHA-256
and gameplay replay still match. Hostile inode replacement fails closed; it
does not delete, quarantine, repair, sign, approve rights or certify release.
This is point-in-time inspection, not a claim of exclusive filesystem locking
or durable rollback protection against a privileged concurrent attacker.


The custody identity also binds every intermediate claimed-source directory.
Replacing a parent directory while moving the original child file inodes into
it is rejected, even when all file hashes, source manifests, and gameplay
replays remain identical. This check is descriptor-relative and read-only.
