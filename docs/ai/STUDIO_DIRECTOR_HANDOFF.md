# Original offline playable director handoff — Studio A

This is an integrated original game creation flow, not a design catalog.
An operator submits a typed scene schedule and explicit source-to-visual
asset recipe bindings, with exact canon, visual and quest-session digests.

The canonical scene scheduler verifies NPC turnaround and quest causality.
The canonical asset binding compiler verifies that every scene asset and
interactive object resolves to a registered original design recipe. The
existing game builder compiles an actual standalone offline HTML5 game and
replays a winning trace. The director verifies all three identities and
creates a deterministic ZIP containing `index.html`, `scene_schedule.json`,
`scene_asset_bindings.json`, and `director_manifest.json`, with per-file
SHA-256 receipts and a deterministic ZIP SHA-256.

CLI: `python -m scripts.studio_director_handoff_cli --project PROJECT
--expected-source CANON_DIGEST --expected-visual VISUAL_DIGEST
--schedule SCHEDULE_JSON --assignments ASSIGNMENTS_JSON
--publish-directory EXISTING_DIR`

A separate `--verify-directory` re-compiles from the same exact source and
compares the published ZIP byte-for-byte. Publication is private, exclusive,
atomic and fsynced. Existing bundles cannot be overwritten. The static
Jeeves `studio_original_director_handoff` tool returns only the manifest
and does not write to disk or grant itself publication authority.

The playable HTML5 maze is real, but original NPC dialogues, temporal
duration, visual design recipes and native genre runtime are **not**
implemented by that HTML5 compiler. All unverified claims remain false.

The bundle also includes an accessible offline `director_editor.html` with
source-leased timing and recipe selection controls. It exports one `studio_director_authoring.json` containing the exact
source, visual and quest-session leases plus the edited scene schedule and
asset assignments. The operator recompiles that file with:
```bash
python -m scripts.studio_director_handoff_cli \
  --project PROJECT --expected-source CANON_DIGEST \
  --expected-visual VISUAL_DIGEST --expected-session QUEST_SESSION_DIGEST \
  --editor-export EXISTING_DIR/studio_director_authoring.json \
  --publish-directory EXISTING_PRIVATE_DIR
```
The CLI also accepts `--verify-directory EXISTING_PRIVATE_DIR` with the
same export and source leases. The original inline `--schedule` and
`--assignments` arguments remain available but cannot be combined with
`--editor-export`. Even without `--expected-session`, importing an export
requires the embedded session digest to match the current canonical quest
replay. No browser-supplied hash or lease is treated as a signature.

The import opens each ancestor with directory-descriptor `O_NOFOLLOW`,
requires a regular bounded leaf file, rejects symlinks, FIFOs, duplicate JSON
keys, nonfinite values and unexpected fields, and checks file identity
before/after the read. Canonical scene/quest/visual owners then recompile
every edit; neither the import nor its hash alone authorizes publication.

The static Jeeves `studio_original_director_authoring` tool accepts the
same typed export in memory, requires explicit `allow_authoring=True` on
the world router and returns a deterministic playable manifest without
writing files. It cannot self-grant authorization. Browser edits and
design recipes do not establish native asset, rights, dialogue or release
qualification. It never silently edits canonical
source, grants model permissions, or asserts that an exported JSON file is a
playable runtime. The editor uses text-only DOM construction and exact CSP
hashes, with no external scripts, network requests, or dynamic code evaluation.
