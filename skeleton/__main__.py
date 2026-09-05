"""CLI entry point for Skeleton operator commands.

Usage:
    python -m skeleton policy state
    python -m skeleton policy save --comment "before tuning"
    python -m skeleton policy rollback --version-id pv-abc123
    python -m skeleton policy rollback-surface --surface forge
    python -m skeleton policy versions
    python -m skeleton policy diff --a pv-abc --b pv-def
    python -m skeleton policy lineage --version-id pv-abc
    python -m skeleton policy rollback-preview --version-id pv-abc

    python -m skeleton verify forge --files file1.gd,file2.gd
    python -m skeleton verify plan --plan plan.json
    python -m skeleton verify pipeline --tree tree.json
    python -m skeleton verify npc --spec spec.json
    python -m skeleton verify dialogue --script script.json

    python -m skeleton repair orchestrate --surface forge --target-id main_scene
    python -m skeleton repair sessions --surface forge
    python -m skeleton repair effectiveness --surface forge
    python -m skeleton repair telemetry --surface forge
    python -m skeleton repair errors --surface forge
    python -m skeleton repair learned
    python -m skeleton repair strategy --surface forge --reason low_score

    python -m skeleton lattice hud
    python -m skeleton lattice editor
    python -m skeleton steering register --name mood_dark --strength 1.2
    python -m skeleton steering activate --name mood_dark --weight 0.8
    python -m skeleton steering deactivate --name mood_dark
    python -m skeleton steering composite
    python -m skeleton kv stats
    python -m skeleton mouth feed --phoneme AA --ts 12345
    python -m skeleton mouth current
    python -m skeleton lora card
    python -m skeleton decoder card
    python -m skeleton master
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from skeleton.cortex.deck import CommandDeck


def _out(data: Dict[str, Any]) -> None:
    print(json.dumps(data, indent=2, default=str))


def _deck(args) -> CommandDeck:
    return CommandDeck(root=getattr(args, "root", None))


def cmd_policy(args) -> None:
    deck = _deck(args)
    if args.subcmd == "state":
        _out(deck.policy_state())
    elif args.subcmd == "save":
        vid = deck.save_policy_version(comment=getattr(args, "comment", ""), author=getattr(args, "author", "cli"))
        _out({"kind": "policy-save-result", "version_id": vid})
    elif args.subcmd == "rollback":
        _out(deck.rollback_policy(args.version_id))
    elif args.subcmd == "rollback-surface":
        _out(deck.rollback_policy_surface(args.surface))
    elif args.subcmd == "versions":
        _out(deck.policy_versions(limit=getattr(args, "limit", 8)))
    elif args.subcmd == "diff":
        _out(deck.policy_diff(args.a, args.b))
    elif args.subcmd == "lineage":
        _out({"kind": "policy-lineage", "lineage": deck.policy_lineage(args.version_id)})
    elif args.subcmd == "rollback-preview":
        _out(deck.rollback_preview(args.version_id))


def cmd_verify(args) -> None:
    deck = _deck(args)
    if args.subcmd == "forge":
        files = {}
        for p in (getattr(args, "files", "") or "").split(","):
            if p.strip():
                files[Path(p.strip()).name] = Path(p.strip()).read_text(encoding="utf-8")
        _out(deck.verify_forge(files, request=getattr(args, "request", "")))
    elif args.subcmd == "plan":
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8")) if getattr(args, "plan", None) else {}
        _out(deck.verify_plan(plan))
    elif args.subcmd == "pipeline":
        tree = json.loads(Path(args.tree).read_text(encoding="utf-8")) if getattr(args, "tree", None) else {}
        _out(deck.verify_pipeline(tree))
    elif args.subcmd == "npc":
        spec = json.loads(Path(args.spec).read_text(encoding="utf-8")) if getattr(args, "spec", None) else {}
        _out(deck.verify_npc(spec))
    elif args.subcmd == "dialogue":
        script = json.loads(Path(args.script).read_text(encoding="utf-8")) if getattr(args, "script", None) else {}
        _out(deck.verify_dialogue(script))


def cmd_repair(args) -> None:
    deck = _deck(args)
    if args.subcmd == "orchestrate":
        _out(deck.repair_orchestrate(args.surface, args.target_id, max_passes=getattr(args, "max_passes", 3)))
    elif args.subcmd == "sessions":
        _out(deck.repair_sessions(getattr(args, "surface", "")))
    elif args.subcmd == "effectiveness":
        _out(deck.repair_effectiveness(getattr(args, "surface", "")))
    elif args.subcmd == "telemetry":
        _out(deck.repair_telemetry(getattr(args, "surface", "")))
    elif args.subcmd == "errors":
        _out(deck.repair_errors(getattr(args, "surface", "")))
    elif args.subcmd == "learned":
        _out(deck.repair_learned())
    elif args.subcmd == "strategy":
        _out(deck.repair_strategy(args.surface, args.reason))


def cmd_lattice(args) -> None:
    deck = _deck(args)
    if args.subcmd == "hud":
        _out(deck.lattice_hud())
    elif args.subcmd == "editor":
        _out(deck.lattice_editor())


def cmd_steering(args) -> None:
    deck = _deck(args)
    if args.subcmd == "register":
        _out(deck.steering_register(args.name, strength=getattr(args, "strength", 1.0)))
    elif args.subcmd == "activate":
        deck.steering_activate(args.name, getattr(args, "weight", 1.0))
        _out({"kind": "steering-activate", "name": args.name})
    elif args.subcmd == "deactivate":
        deck.steering_deactivate(args.name)
        _out({"kind": "steering-deactivate", "name": args.name})
    elif args.subcmd == "composite":
        _out(deck.steering_composite())


def cmd_kv(args) -> None:
    deck = _deck(args)
    if args.subcmd == "stats":
        _out(deck.kv_cache_stats())


def cmd_mouth(args) -> None:
    deck = _deck(args)
    if args.subcmd == "feed":
        _out(deck.mouth_feed(args.phoneme, float(args.ts), getattr(args, "confidence", 1.0)))
    elif args.subcmd == "current":
        _out(deck.mouth_current())


def cmd_lora(args) -> None:
    deck = _deck(args)
    if args.subcmd == "card":
        _out(deck.lora_card())


def cmd_decoder(args) -> None:
    deck = _deck(args)
    if args.subcmd == "card":
        _out(deck.decoder_card())


def cmd_master(args) -> None:
    _out(_deck(args).master_card())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="skeleton", description="Skeleton operator CLI")
    parser.add_argument("--root", default=None, help="Project root path")
    sub = parser.add_subparsers(dest="command")

    # Policy
    p = sub.add_parser("policy", help="Policy versioning and control")
    p_sub = p.add_subparsers(dest="subcmd")
    p_sub.add_parser("state", help="Show policy state")
    sp = p_sub.add_parser("save", help="Save policy version")
    sp.add_argument("--comment", default="")
    sp.add_argument("--author", default="cli")
    rp = p_sub.add_parser("rollback", help="Rollback to version")
    rp.add_argument("--version-id", required=True)
    rsp = p_sub.add_parser("rollback-surface", help="Rollback surface")
    rsp.add_argument("--surface", required=True)
    p_sub.add_parser("versions", help="List versions")
    dp = p_sub.add_parser("diff", help="Diff versions")
    dp.add_argument("--a", required=True)
    dp.add_argument("--b", required=True)
    lp = p_sub.add_parser("lineage", help="Version lineage")
    lp.add_argument("--version-id", required=True)
    rpp = p_sub.add_parser("rollback-preview", help="Preview rollback")
    rpp.add_argument("--version-id", required=True)

    # Verify
    v = sub.add_parser("verify", help="Verification commands")
    v_sub = v.add_subparsers(dest="subcmd")
    vf = v_sub.add_parser("forge", help="Verify forge output")
    vf.add_argument("--files", default="")
    vf.add_argument("--request", default="")
    vp = v_sub.add_parser("plan", help="Verify plan")
    vp.add_argument("--plan", default="")
    vpi = v_sub.add_parser("pipeline", help="Verify pipeline")
    vpi.add_argument("--tree", default="")
    vn = v_sub.add_parser("npc", help="Verify NPC spec")
    vn.add_argument("--spec", default="")
    vd = v_sub.add_parser("dialogue", help="Verify dialogue script")
    vd.add_argument("--script", default="")

    # Repair
    r = sub.add_parser("repair", help="Repair commands")
    r_sub = r.add_subparsers(dest="subcmd")
    ro = r_sub.add_parser("orchestrate", help="Orchestrate repair")
    ro.add_argument("--surface", required=True)
    ro.add_argument("--target-id", required=True)
    ro.add_argument("--max-passes", type=int, default=3)
    rs = r_sub.add_parser("sessions", help="Repair sessions")
    rs.add_argument("--surface", default="")
    re = r_sub.add_parser("effectiveness", help="Repair effectiveness")
    re.add_argument("--surface", default="")
    rt = r_sub.add_parser("telemetry", help="Repair telemetry")
    rt.add_argument("--surface", default="")
    rer = r_sub.add_parser("errors", help="Repair errors")
    rer.add_argument("--surface", default="")
    r_sub.add_parser("learned", help="Learned policy")
    rstr = r_sub.add_parser("strategy", help="Repair strategy")
    rstr.add_argument("--surface", required=True)
    rstr.add_argument("--reason", required=True)

    # Lattice
    l = sub.add_parser("lattice", help="Pixel lattice")
    l_sub = l.add_subparsers(dest="subcmd")
    l_sub.add_parser("hud", help="HUD lattice")
    l_sub.add_parser("editor", help="Editor lattice")

    # Steering
    s = sub.add_parser("steering", help="Operator steering")
    s_sub = s.add_subparsers(dest="subcmd")
    sr = s_sub.add_parser("register", help="Register vector")
    sr.add_argument("--name", required=True)
    sr.add_argument("--strength", type=float, default=1.0)
    sa = s_sub.add_parser("activate", help="Activate vector")
    sa.add_argument("--name", required=True)
    sa.add_argument("--weight", type=float, default=1.0)
    sd = s_sub.add_parser("deactivate", help="Deactivate vector")
    sd.add_argument("--name", required=True)
    s_sub.add_parser("composite", help="Composite vector")

    # KV
    kv = sub.add_parser("kv", help="KV cache")
    kv_sub = kv.add_subparsers(dest="subcmd")
    kv_sub.add_parser("stats", help="Cache stats")

    # Mouth
    m = sub.add_parser("mouth", help="Mouth binding")
    m_sub = m.add_subparsers(dest="subcmd")
    mf = m_sub.add_parser("feed", help="Feed phoneme")
    mf.add_argument("--phoneme", required=True)
    mf.add_argument("--ts", required=True)
    mf.add_argument("--confidence", type=float, default=1.0)
    m_sub.add_parser("current", help="Current mouth state")

    # LoRA
    lor = sub.add_parser("lora", help="LoRA adapter")
    lor_sub = lor.add_subparsers(dest="subcmd")
    lor_sub.add_parser("card", help="LoRA card")

    # Decoder
    dec = sub.add_parser("decoder", help="GPU decoder")
    dec_sub = dec.add_subparsers(dest="subcmd")
    dec_sub.add_parser("card", help="Decoder card")

    # Master
    sub.add_parser("master", help="Master deck card")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 1
    handlers = {
        "policy": cmd_policy,
        "verify": cmd_verify,
        "repair": cmd_repair,
        "lattice": cmd_lattice,
        "steering": cmd_steering,
        "kv": cmd_kv,
        "mouth": cmd_mouth,
        "lora": cmd_lora,
        "decoder": cmd_decoder,
        "master": cmd_master,
    }
    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        return 1
    handler(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
