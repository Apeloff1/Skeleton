# Studio A — source-bound temporal windows

This is a deterministic editorial temporal constraint compiler, **not** physical
travel simulation, AI model inference, native game execution or release approval.
It consumes the canonical quest, scene and dialogue staging source and binds each
operator-authored window to the current source and replay session.

## Operator flow

1. Obtain `source_digest` from the canonical canon audit.
2. Run `python -m scripts.studio_temporal_windows_cli --project studio_arena_fighting_glacial_fjord --expected-source DIGEST --prompt "plan source-bound temporal windows" --handoff-manifest`.
3. Copy the typed `proposal.authoring` object and edit `schedule_request`,
   `windows` and `exclusive_groups` deliberately. Every scene must have a
   nonempty `earliest/latest` window. Recompile using `--authoring JSON`.
4. Use `--publish EXISTING_PRIVATE_DIRECTORY` to save an immutable private
   receipt; use `--restore` with the same canonical source to verify it.
5. The playable handoff embeds the actual HTML5 quest in `index.html` and a
   separate read-only timing proof in `timeline.html` and `timeline.json`.
   Native engine timing integration remains unqualified.

Windows reject unsatisfiable starts/deadlines. Exclusive groups reject any
overlap among their scenes, including scenes featuring different NPCs. Source
and session leases, duplicate-key JSON, nonfinite values, nonregular receipt
files, symlinks, insecure file permissions, oversized input and stale replay
fail closed. All receipt publication is exclusive, private and fsynced.

Jeeves static router tool: `studio_original_temporal_windows`. No arbitrary
tool import or model-provided authorization is accepted. A model provider may
propose authoring separately, but this compiler never claims inference.

Focused regression fixture:
`pytest -q tests/test_studio_ecosystem_temporal_windows.py`.
Required exact-head security and CI gates remain release holds.
