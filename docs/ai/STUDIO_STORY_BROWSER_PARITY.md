# Studio A — Source-bound browser quest ending parity

The canonical browser story compiler previously projected quest stages and rewards
but omitted `choice_effects`, so authored endings requiring `choice:<stage>:<effect>`
were never eligible in the HTML5 interaction despite canonical quest replay
proving them eligible. This vertical carries the exact source-authored choice
effect map into the browser and applies only effects earned by the selected
alternative, without minting external evidence.

`python -m scripts.studio_story_browser_parity_cli --project PROJECT
--expected-source QUEST_SHA256 --expected-session INITIAL_SESSION_SHA256
--prompt --playable` deterministically rehearses the first legal choice at
each stage and produces a canonical receipt and HTML5 handoff manifest.

For an edited action sequence, create a private 0600 JSON file with
`{"actions":[["stage-id","authored-choice"]]}` and use
`--authoring-file PATH --publish EXISTING_PRIVATE_DIRECTORY`. The published
receipt is immutable and atomically linked, with bounded descriptor-anchored
restore using `--restore EXISTING_PRIVATE_DIRECTORY`. `--html-preview`
returns the real CSP-bound playable HTML for browser inspection; it never
asserts JavaScript was executed by the Python tool.

Jeeves tool `studio_original_story_browser_parity` is read-only, schema-bound,
operator-gated and registered in the static world tool router. All tool and
CLI requests are source/session leased, and receipt replay recomputes the
canonical quest outcome and HTML bytes. Browser parity is a projection proof,
not a browser runtime test, native game/device qualification, rights review or
release approval. Run the focused pytest module and exact-head security/CI
before promoting any source branch.

The playable HTML now includes a no-network, copy/paste checkpoint editor.
The user explicitly copies the displayed JSON into their own storage. Restore
validates the exact receipt fields, source and project digests, false external
and release claims, bounded action count, unique stage completion, legal
authored alternatives, and topological prerequisite order **before** changing
the current UI session. Invalid or stale checkpoints preserve the current
progress. The Python CLI remains the authoritative private-disk publication
path; browser copy/paste is an untrusted local convenience, not signed custody.

## Browser-to-CLI-to-playable handoff

The interactive HTML's `offline_story_choices.v1` JSON checkpoint can now
be saved as a private 0600 file and passed to
`--browser-checkpoint-file CHECKPOINT.json`. The importer rejects unknown
fields, stale source, non-false external/native/release claims, illegal choices,
and stale initial-session leases, then replays the authored quest engine.

`--publish-playable DIRECTORY` writes the actual CSP-bound interactive
`index.html` with exclusive descriptor-anchored, fsynced publication and
rollback on durability failure. The playable file is mode 0600 and never
overwrites an existing export. The manifest proves byte identity with the
replayed source, not browser/device execution. `--publish` for private receipt
and `--publish-playable` for HTML are deliberately separate operations.
