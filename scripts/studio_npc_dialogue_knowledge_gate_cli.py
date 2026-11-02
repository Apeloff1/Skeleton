"""Private CLI for source-leased NPC dialogue knowledge gate authoring."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from skeleton.ai.game_builder.studio_ecosystem_catalog import read_blueprint
from skeleton.ai.game_builder.studio_ecosystem_quest import StudioQuestError
from skeleton.ai.game_builder.studio_npc_dialogue_knowledge_gate import (
    PROMPT, MAX_BYTES, propose_npc_dialogue_knowledge_gate,
    compile_npc_dialogue_knowledge_gate, replay_npc_dialogue_knowledge_gate,
    compile_npc_dialogue_gate_playable, publish_npc_dialogue_knowledge_gate,
    restore_npc_dialogue_knowledge_gate,
)
from scripts.studio_npc_knowledge_relay_cli import _private_json
from skeleton.ai.game_builder.studio_npc_dialogue_knowledge_gate_editor import (
    load_npc_dialogue_gate_editor_export, publish_npc_dialogue_gate_editor,
)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Source-bound NPC dialogue knowledge gate")
    ap.add_argument("--project", required=True)
    ap.add_argument("--expected-source", required=True)
    ap.add_argument("--relay-file", type=Path)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prompt", action="store_true")
    mode.add_argument("--authoring-file", type=Path)
    mode.add_argument("--editor-export-file", type=Path)
    mode.add_argument("--restore", type=Path)
    ap.add_argument("--publish", type=Path)
    ap.add_argument("--baseline-gate-file", type=Path)
    ap.add_argument("--render-editor", type=Path)
    ap.add_argument("--playable", action="store_true")
    args = ap.parse_args(argv)
    if args.restore is not None and (args.relay_file or args.publish or
                                     args.baseline_gate_file):
        ap.error("restore excludes new relay or publication")
    if args.restore is None and args.relay_file is None:
        ap.error("gate authoring requires a private relay receipt")
    if (args.editor_export_file is not None) != (args.baseline_gate_file is not None):
        ap.error("editor import requires a matching private baseline gate receipt")
    try:
        docs = read_blueprint(args.project)
        if args.restore is not None:
            result = restore_npc_dialogue_knowledge_gate(
                docs, args.restore, authorized=True,
                expected_source_digest=args.expected_source)
        else:
            relay = _private_json(args.relay_file, MAX_BYTES)
            kwargs = {"authorized": True,
                      "expected_source_digest": args.expected_source}
            if args.editor_export_file is not None:
                baseline = _private_json(args.baseline_gate_file, MAX_BYTES)
                replay_npc_dialogue_knowledge_gate(docs, baseline, authorized=True)
                if (baseline["relay_digest"] != relay["relay_digest"]
                        or baseline["source_digest"] != args.expected_source):
                    raise StudioQuestError("editor baseline differs from relay source")
                authoring = load_npc_dialogue_gate_editor_export(
                    args.editor_export_file, authorized=True,
                    expected_project_id=args.project,
                    expected_source_digest=args.expected_source,
                    expected_session_digest=baseline["session_digest"],
                    expected_relay_digest=baseline["relay_digest"],
                    expected_baseline_digest=baseline["gate_digest"])
                result = compile_npc_dialogue_knowledge_gate(
                    docs, relay, authoring, **kwargs)
            elif args.prompt:
                result = propose_npc_dialogue_knowledge_gate(
                    docs, relay, PROMPT, **kwargs)
            else:
                result = compile_npc_dialogue_knowledge_gate(
                    docs, relay, _private_json(args.authoring_file, 32768),
                    **kwargs)
            replay_npc_dialogue_knowledge_gate(docs, result, authorized=True)
        output = {
            "schema": "skeleton.cli.studio_npc_dialogue_knowledge_gate.v1",
            "gate": result, "file_write_performed": False,
            "release_certified": False,
        }
        if args.playable:
            output["playable_handoff"] = compile_npc_dialogue_gate_playable(
                docs, result, authorized=True)
        if args.render_editor is not None:
            output["editor"] = publish_npc_dialogue_gate_editor(
                docs, result, args.render_editor, authorized=True)
            output["file_write_performed"] = True
        if args.publish is not None:
            output["publication"] = publish_npc_dialogue_knowledge_gate(
                docs, result, args.publish, authorized=True)
            output["file_write_performed"] = True
        print(json.dumps(output, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=True, allow_nan=False))
    except (StudioQuestError, PermissionError, OSError, ValueError,
            UnicodeError, RecursionError) as exc:
        ap.exit(2, f"NPC dialogue knowledge gate rejected: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
