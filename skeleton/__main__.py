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

    GameForge (CI / unit thin wrappers):
    python -m skeleton eras
    python -m skeleton generations
    python -m skeleton plan "soulslike extraction with bonfire rest"
    python -m skeleton cockpit "BLEND ERA arcade_golden_age soulslike 0.5"
    python -m skeleton walk --era soulslike
    python -m skeleton run "vision text" --out /tmp/out --overwrite --json
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



def cmd_eras(args) -> int:
    from skeleton.forge.eras import list_eras, compile_era
    for era in list_eras():
        pack = compile_era(era)
        print(f"{era:22} dps={pack['primary_dps']:<7} speed={pack['player']['speed']}")
    return 0


def cmd_generations(args) -> int:
    from skeleton.forge.hardware import catalog
    for g in catalog():
        print(f"{g['key']:10} {g['label']:16} {g['viewport'][0]}x{g['viewport'][1]}  {g['tagline']}")
    return 0


def cmd_plan(args) -> int:
    from skeleton.cortex.live import live_jeeves, persist
    out = live_jeeves().plan_build(vision=args.vision)
    persist()
    print(json.dumps(out, indent=2, default=str))
    return 0


def cmd_cockpit(args) -> int:
    from skeleton.context.cockpit import Cockpit
    out = Cockpit().apply(args.cockpit_cmd)
    print(json.dumps(out, indent=2, default=str))
    return 0


def cmd_walk(args) -> int:
    """Prove spawn→extract on the emitted door graph (CI GameForge walk)."""
    from skeleton.forge.eras import blend_eras, compile_era
    from skeleton.forge.walk import walk_from_pack
    from skeleton.jeeves.builder import BuilderBrain
    from skeleton.context.tensor import ContextTensor
    from skeleton.context.dodeca import Dodecahedron
    from skeleton.context.oracle import Magic8Ball
    if getattr(args, "blend", None):
        pack = blend_eras(args.blend[0], args.blend[1], args.t)
        tensor = ContextTensor.from_era(args.blend[0]).lerp(
            ContextTensor.from_era(args.blend[1]), args.t
        )
    else:
        pack = compile_era(args.era)
        tensor = ContextTensor.from_era(args.era)
    reading = Magic8Ball(Dodecahedron.from_tensor(tensor)).roll(tensor)
    plan = BuilderBrain().plan(pack, tensor=tensor, reading=reading)
    wr = walk_from_pack(pack, plan=plan.to_dict())
    payload = wr.to_dict()
    payload["plan"] = {"bias": plan.room_bias, "extract_late": plan.extract_late, "era": plan.era}
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, default=str))
    else:
        print(f"extracted={wr.extracted} t={wr.t:.2f} hops={wr.hops} cores={wr.cores}/{wr.required_cores}")
    return 0 if wr.passed else 1


def cmd_run(args) -> int:
    from skeleton.context.pipeline import GameForgeRun
    vision = args.vision
    era = getattr(args, "era", None)
    out = getattr(args, "out", None)
    overwrite = bool(getattr(args, "overwrite", False))
    as_json = bool(getattr(args, "json", False))
    blend = tuple(args.blend) + (args.t,) if getattr(args, "blend", None) else None
    generation = getattr(args, "generation", None)
    payload = GameForgeRun.live().execute(
        vision, era=era, answers={}, project_root=out, overwrite=overwrite, target="godot",
        blend=blend, generation=generation,
    )
    if as_json:
        slim = {k: payload[k] for k in ("succeeded", "era", "mass", "complete", "sim", "project", "forge") if k in payload}
        print(json.dumps(slim, indent=2, default=str))
    else:
        print(f"era={payload.get('era')} mass={payload.get('mass')} sim={(payload.get('sim') or {}).get('passed')} files={(payload.get('forge') or {}).get('file_count')}")
        if payload.get("project"):
            print("wrote", payload["project"]["root"])
    return 0 if payload.get("succeeded") else 1


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

    # GameForge thin wrappers (CI + tests/run_unit TestCLI)
    sub.add_parser("eras", help="List era dialects")
    sub.add_parser("generations", help="List hardware generations")
    pl = sub.add_parser("plan", help="Jeeves BuildPlan for a vision / era")
    pl.add_argument("vision", nargs="?", default="")
    pl.add_argument("--era")
    pl.add_argument("--blend", nargs=2, metavar=("ERA_A", "ERA_B"))
    pl.add_argument("--t", dest="t", type=float, default=0.5)
    ck = sub.add_parser("cockpit", help="Apply one cockpit command")
    ck.add_argument("cockpit_cmd", metavar="COMMAND", help="Cockpit command line")
    wk = sub.add_parser("walk", help="Prove spawn→extract on the emitted door graph")
    wk.add_argument("--era", default="extraction_now")
    wk.add_argument("--blend", nargs=2, metavar=("ERA_A", "ERA_B"))
    wk.add_argument("--t", dest="t", type=float, default=0.5)
    wk.add_argument("--json", action="store_true")
    rn = sub.add_parser("run", help="Vision → Godot project via GameForgeRun")
    rn.add_argument("vision", nargs="?", default="")
    rn.add_argument("--era")
    rn.add_argument("--out", dest="out")
    rn.add_argument("--overwrite", action="store_true")
    rn.add_argument("--json", action="store_true")
    rn.add_argument("--blend", nargs=2, metavar=("ERA_A", "ERA_B"))
    rn.add_argument("--t", dest="t", type=float, default=0.5)
    rn.add_argument("--generation")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        # Keep unit tests / embedded callers from being killed by argparse.
        code = exc.code
        return int(code) if isinstance(code, int) else (1 if code else 0)
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
        "eras": cmd_eras,
        "generations": cmd_generations,
        "plan": cmd_plan,
        "cockpit": cmd_cockpit,
        "walk": cmd_walk,
        "run": cmd_run,
    }
    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        return 1
    rc = handler(args)
    return int(rc) if rc is not None else 0


if __name__ == "__main__":
    sys.exit(main())
