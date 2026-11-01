# Source-bound NPC knowledge and dialogue provenance

Studio A compiles a deterministic NPC knowledge transfer rehearsal from the
canonical original cast, scene, narrative and quest source. It cannot invent
facts, voice lines, witnesses, gameplay authority or verified native behavior.

A reveal identifies a fact by `scene_id:npc_knowledge` or
`scene_id:scene_consequence`, a later recipient scene, and optionally an
exact authored choice. The fact is available to the recipient only when the
canonical quest replay completes both scenes and matches the required choice.
Forward reveals, missing facts, duplicates and stale source/session leases fail
closed. Locked and unplayed scenes remain **pending**, not evidence.

The editor flow is:

1. Read an original registered project and obtain its canon source digest.
2. Propose a bounded source-derived transfer using
   `python -m scripts.studio_npc_knowledge_cli --project PROJECT
   --expected-source SHA256 --prompt "share knowledge across scenes"`.
3. Review/edit the returned typed `authoring` JSON, then compile it using
   `--authoring-json` and the exact same source/session lease.
4. Publish into an **existing** private directory with
   `--publish-directory DIRECTORY`. Publication is exclusive, immutable,
   fsynced and replay-verified; no symlinked parent or final-file replacement.
5. Restore with `--verify-directory DIRECTORY` and the same authoring input.
   Verification replays source and quest state and rejects altered receipts.
6. Use `--include-html` to render a script-free accessible companion showing
   only earned source-authored cues. This is an editor handoff for the playable
   director, not a claim that dialogue has been spoken or a native game built.

Jeeves exposes the reviewed `studio_original_npc_knowledge` typed tool through
`scripts.studio_world_tool_cli`. The router never trusts authorization
fields in model-provided JSON. The proposal uses deterministic source-token
overlap, not LLM inference. The CLI and Jeeves share the canonical compiler.

Focused regressions: `pytest -q tests/test_studio_npc_knowledge.py`.
Full release and device qualification remain independently required.
