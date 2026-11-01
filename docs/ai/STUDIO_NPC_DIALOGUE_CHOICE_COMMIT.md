# NPC dialogue choice — canonical playable-to-quest handoff

The operator first compiles a playable walk receipt, verifies a source-bound NPC
contact, then previews an available authored NPC scene with
`studio_npc_dialogue_contact_cli.py`. This feature accepts that exact contact
receipt and its SHA-256 digest lease, plus the original source, walk and quest
leases, and one authored alternative. It independently recomputes the contact
proof, source and quest replay before constructing the next canonical quest
history. Unknown, stale, locked, completed or forged alternatives fail closed.

The output is a deterministic **quest-choice receipt**. It proves the authored
choice can be replayed against the original game source and that a valid NPC
contact preceded it. It does **not** claim the dialogue was spoken, a native
runtime executed it, external evidence was obtained, or a release was qualified.

Use `scripts/studio_npc_dialogue_choice_commit_cli.py` with
`--project`, `--expected-contact`, `--expected-source`,
`--expected-walk`, `--expected-quest`, `--contact-json`, and
`--alternative`. Optional `--publish` writes an exclusive 0600 receipt into
an existing private directory; `--restore` independently verifies it. No
existing file is overwritten. Symlink, FIFO, duplicate-key, nonfinite,
wrong-owner, over-budget and replay-forgery cases are rejected.

The typed Jeeves tool is
`studio_original_npc_dialogue_choice_commit`, explicitly marked as
**authoring** by the static world router. The caller must supply out-of-band
`authorized=True, allow_authoring=True`; model-supplied flags cannot grant
authority. The tool itself does not write files.

Follow-on engine work must consume the verified `quest_actions` and
`next_quest_session_digest` and run the authoritative playable handoff; it
must not infer spoken dialogue or native-device qualification from this receipt.
