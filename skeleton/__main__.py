"""python -m skeleton — run, intake, eras, check.

Fix (2026-08-29): two subparsers were both registered under the name
``plan`` (``pl`` and ``pb``), so argparse raised ``conflicting subparser``
at startup — no CLI command could run at all. The builder-plan command is
now ``build-plan``; ``plan`` keeps the live-Jeeves plan_build path.
"""
from __future__ import annotations

import argparse
import json
import sys


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m skeleton")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="vision → Godot project")
    r.add_argument("vision", nargs="?", default="")
    r.add_argument("--era")
    r.add_argument("--out", dest="out")
    r.add_argument("--overwrite", action="store_true")
    r.add_argument("--json", action="store_true")
    r.add_argument("--blend", nargs=2, metavar=("ERA_A", "ERA_B"))
    r.add_argument("--t", dest="t", type=float, default=0.5)
    r.add_argument("--generation")

    i = sub.add_parser("intake", help="12-beat answers → project")
    i.add_argument("pairs", nargs="*", help="id=option")
    i.add_argument("--out")
    i.add_argument("--overwrite", action="store_true")

    sub.add_parser("eras", help="list era dialects")
    sub.add_parser("generations", help="list hardware generations")
    c = sub.add_parser("check", help="static-check a files dict or a project dir")
    c.add_argument("path")

    pl = sub.add_parser("plan", help="Jeeves BuildPlan for a vision / era")
    pl.add_argument("vision", nargs="?", default="")
    pl.add_argument("--era")
    pl.add_argument("--blend", nargs=2, metavar=("ERA_A", "ERA_B"))
    pl.add_argument("--t", dest="t", type=float, default=0.5)

    ck = sub.add_parser("cockpit", help="apply one cockpit command")
    ck.add_argument("command")

    th = sub.add_parser("think", help="Jeeves neocortex think (the model in training)")
    th.add_argument("stimulus", nargs="?", default="")
    th.add_argument("--bind", nargs=2, metavar=("SLOT", "BACKEND"))
    th.add_argument("--acquire")
    th.add_argument("--surpass")
    th.add_argument("--recall", action="store_true")

    trn = sub.add_parser("train", help="run GameForge curriculum epochs on the own-system")
    trn.add_argument("--epochs", type=int, default=1)

    sub.add_parser("metrics", help="score the live neocortex against untrained baselines")
    sub.add_parser("merkle", help="print the live cortex merkle card")
    dk = sub.add_parser("deck", help="command deck snapshot / speak / walk")
    dk.add_argument("stimulus", nargs="?", default="")
    dk.add_argument("--walk", type=int, default=0)
    ct = sub.add_parser("cut", help="seven-axis perpendicular cut")
    ct.add_argument("stimulus", nargs="?", default="like Elden Ring")
    ct.add_argument("--rounds", type=int, default=3)
    ct.add_argument("--live-parse", action="store_true")
    gx = sub.add_parser("galaxy", help="five-brain Hoag knowledge pulse")
    gx.add_argument("stimulus", nargs="?", default="")
    gx.add_argument("--sleep", action="store_true")
    og = sub.add_parser("organismer", help="10x organism step over galaxy+social")
    og.add_argument("stimulus", nargs="?", default="")
    og.add_argument("--sleep", action="store_true")
    og.add_argument("--cdx", action="store_true", help="opt-in Wayback CDX header probe")
    so = sub.add_parser("social", help="social SOTA card / ArchiveX pointers")
    so.add_argument("stimulus", nargs="?", default="")
    sub.add_parser("product", help="operator product card for the living organism")
    ctact = sub.add_parser("contact", help="teacher contact + distill the rule")
    ctact.add_argument("stimulus", nargs="?", default="plan tensor ttk")
    wq = sub.add_parser("wiki", help="SPARQL-shaped wiki query")
    wq.add_argument("q", nargs="?", default="SELECT topic WHERE kind=principle")
    gr = sub.add_parser("graph", help="cue-tag reconstruction forest")
    gr.add_argument("cue", nargs="?", default="memory graph")
    cx = sub.add_parser("context", help="rot-guard + reconstruction forest")
    cx.add_argument("cue", nargs="?", default="memory graph")
    sub.add_parser("banks", help="common vs long-tail memory banks")
    sub.add_parser("caps", help="hardware-aware multi-cap table")
    sub.add_parser("kernels", help="multi-kernel profile (mobile/tight/desktop)")
    sub.add_parser("lattice", help="Hoag lattice + gated KV handles")
    sub.add_parser("health", help="operator health card")
    dc = sub.add_parser("doctor", help="laws + health + caps + field")
    dc.add_argument("--fix", action="store_true")
    sub.add_parser("laws", help="live stored_prose scan")
    sl = sub.add_parser("sleep", help="gated NREM+REM consolidation")
    sl.add_argument("--force", action="store_true")
    sl.add_argument("cue", nargs="?", default="")
    fg = sub.add_parser("forget", help="decay / retire / reconsolidate")
    fg.add_argument("cue", nargs="?", default="")
    sub.add_parser("helix", help="dual-helix eidetic heads")
    sat = sub.add_parser("satellites", help="jeeves + vault + retrieve")
    sub.add_parser("nervous", help="SLO + intelligence roster")
    ch = sub.add_parser("chronicle", help="journals, rolodex, itinerary, annals, index")
    ch.add_argument("cue", nargs="?", default="memory graph")
    dp = sub.add_parser("dump", help="rotate hot books into decade backup")
    dp.add_argument("--force", action="store_true")
    sub.add_parser("scope", help="multi-horizon queue beyond one next code")
    sub.add_parser("enact", help="run the head of the scope queue")
    sub.add_parser("standin", help="bind a local teacher copy (no HF)")
    sat.add_argument("cue", nargs="?", default="")
    rc = sub.add_parser("recall", help="recall from helix snapshots")
    rc.add_argument("cue", nargs="?", default="")
    sub.add_parser("next", help="coded operator next hint")
    sub.add_parser("seed", help="file field pointers into the wiki")
    sub.add_parser("field", help="list SOTA field pointers")
    rd = sub.add_parser("ready", help="seed if empty, then health+next+caps")
    rd.add_argument("--walk", action="store_true")
    rd.add_argument("--fix", action="store_true")
    rd.add_argument("-n", type=int, default=2)
    pu = sub.add_parser("pulse", help="obey the next code")
    pu.add_argument("stimulus", nargs="?", default="")
    wk = sub.add_parser("walk", help="bounded pulse walk (not gameforge run)")
    wk.add_argument("stimulus", nargs="?", default="")
    wk.add_argument("-n", type=int, default=4)
    sub.add_parser("zaibatsu", help="tournament the three mouths; print the family seal")

    sp = sub.add_parser("speak", help="neo transformer decode")
    sp.add_argument("prefix", nargs="?", default="plan tensor ttk")
    sp.add_argument("-n", type=int, default=12)
    sp.add_argument("--seed", type=int, default=0)
    sp.add_argument("--mouth", default="gelu", help="gelu | rms")

    bm = sub.add_parser("beam", help="beam-search the neo mouth")
    bm.add_argument("prefix", nargs="?", default="plan tensor ttk")
    bm.add_argument("-n", type=int, default=8)
    bm.add_argument("--width", type=int, default=4)
    bm.add_argument("--mouth", default="gelu", help="gelu | rms")

    lr = sub.add_parser("lora", help="attach or merge LoRA on the live neo")
    lr.add_argument("--rank", type=int, default=2)
    lr.add_argument("--merge", action="store_true")

    gs = sub.add_parser("gossip", help="α-mix live neo with a fresh peer")
    gs.add_argument("--alpha", type=float, default=0.25)
    gs.add_argument("--mouths", action="store_true", help="mix neo_rms into primary")
    gs.add_argument("--direction", default="rms-into-gelu")

    hf = sub.add_parser("bind-hf", help="bind a HuggingFace teacher into a slot")
    hf.add_argument("slot", choices=["pfc", "midbrain", "left", "right"])
    hf.add_argument("--model", default="sshleifer/tiny-gpt2")

    km = sub.add_parser("bind-kimi", help="bind a Kimi/Moonshot teacher into a slot")
    km.add_argument("slot", choices=["pfc", "midbrain", "left", "right"])
    km.add_argument("--model", default="kimi-k2-0711-preview")

    ds = sub.add_parser("distill", help="teacher speaks; neo SGD on that text")
    ds.add_argument("slot", choices=["pfc", "midbrain", "left", "right"])
    ds.add_argument("prefix", nargs="?", default="plan tensor ttk")

    ct = sub.add_parser("contact", help="write Jeeves adapters onto a teacher copy")
    ct.add_argument("slot", choices=["pfc", "midbrain", "left", "right"])
    ct.add_argument("prefix", nargs="?", default="plan tensor ttk")

    gn = sub.add_parser("genos", help="pulse the genos trajectory engine")
    gn.add_argument("prefix", nargs="?", default="plan tensor ttk lattice soulslike")

    ac = sub.add_parser("acquire-game", help="parse a Steam app on demand; store pointer only")
    ac.add_argument("--appid", type=int, default=1245620)
    ac.add_argument("--title", default="Elden Ring")

    sub.add_parser("spree", help="write the 12-title reference index")

    rf = sub.add_parser("refer", help="lookup a game reference from a stimulus")
    rf.add_argument("prefix", nargs="?", default="elden ring")
    rf.add_argument("--live", action="store_true")

    im = sub.add_parser("improve", help="like <game>: raise house quality under law")
    im.add_argument("prefix", nargs="?", default="like elden ring")
    im.add_argument("--rounds", type=int, default=16)

    asd = sub.add_parser("ascend", help="improve + elect + sleep + evaluate under law")
    asd.add_argument("prefix", nargs="?", default="like elden ring")
    asd.add_argument("--rounds", type=int, default=8)

    pb = sub.add_parser("build-plan", help="Jeeves builder plan; like <game> resolves era")
    pb.add_argument("vision", nargs="?", default="like elden ring")

    ew = sub.add_parser("erawalk", help="prove spawn→extract on the emitted door graph")
    ew.add_argument("--era", default="extraction_now")
    ew.add_argument("--blend", nargs=2, metavar=("ERA_A", "ERA_B"))
    ew.add_argument("--t", dest="t", type=float, default=0.5)
    ew.add_argument("--json", action="store_true")
    ow = sub.add_parser("octwalk", help="octahedral face walk on the neo")
    ow.add_argument("-n", type=int, default=1)

    args = p.parse_args(argv)

    if args.cmd == "eras":
        from skeleton.forge.eras import list_eras, compile_era
        for era in list_eras():
            pack = compile_era(era)
            print(f"{era:22} dps={pack['primary_dps']:<7} speed={pack['player']['speed']}")
        return 0

    if args.cmd == "generations":
        from skeleton.forge.hardware import catalog
        for g in catalog():
            print(f"{g['key']:10} {g['label']:16} {g['viewport'][0]}x{g['viewport'][1]}  {g['tagline']}")
        return 0

    if args.cmd == "check":
        from pathlib import Path
        from skeleton.forge.gdscript_check import check_files
        root = Path(args.path)
        files = {str(f.relative_to(root)): f.read_text() for f in root.rglob("*") if f.is_file() and f.suffix in {".gd", ".tscn", ".godot", ".cfg", ".json"}}
        problems = check_files(files)
        if problems:
            print("FAIL")
            for x in problems:
                print(" -", x)
            return 2
        print(f"OK {len(files)} files")
        return 0

    if args.cmd == "cockpit":
        from skeleton.context.cockpit import Cockpit
        cpit = Cockpit()
        out = cpit.apply(args.command)
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "train":
        from skeleton.cortex.live import live_cortex, persist
        out = live_cortex().train(epochs=args.epochs)
        out["saved"] = persist()
        print(json.dumps(out, indent=2, default=str))
        return 0 if out.get("held_rate", 0) >= 0.5 else 1

    if args.cmd == "metrics":
        from skeleton.cortex.live import live_cortex
        from skeleton.cortex.metrics import evaluate
        print(json.dumps(evaluate(live_cortex()), indent=2, default=str))
        return 0

    if args.cmd == "deck":
        from skeleton.cortex.deck import live_deck
        from skeleton.cortex.live import persist
        deck = live_deck()
        if args.stimulus:
            out = deck.speak(args.stimulus)
        elif args.walk:
            out = deck.walk(args.walk)
        else:
            out = deck.snapshot()
        persist()
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "cut":
        from skeleton.cortex.deck import live_deck
        from skeleton.cortex.live import persist
        out = live_deck().cut(args.stimulus, rounds=args.rounds, live=args.live_parse)
        persist()
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "galaxy":
        from skeleton.cortex.deck import live_deck
        out = live_deck().galaxy(args.stimulus, sleep=args.sleep)
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "organismer":
        from skeleton.cortex.deck import live_deck
        out = live_deck().organismer(args.stimulus, sleep=args.sleep, live_cdx=bool(getattr(args, "cdx", False)))
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "social":
        from skeleton.cortex.deck import live_deck
        out = live_deck().social(args.stimulus)
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "product":
        from skeleton.cortex.deck import live_deck
        out = live_deck().product()
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "contact":
        from skeleton.cortex.deck import live_deck
        out = live_deck().contact(args.stimulus)
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "wiki":
        from skeleton.cortex.deck import live_deck
        out = live_deck().wiki(args.q)
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "graph":
        from skeleton.cortex.deck import live_deck
        out = live_deck().graph(args.cue)
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "context":
        from skeleton.cortex.deck import live_deck
        out = live_deck().context(args.cue)
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "banks":
        from skeleton.cortex.deck import live_deck
        out = live_deck().banks()
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "kernels":
        from skeleton.cortex.deck import live_deck
        out = live_deck().kernels()
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "caps":
        from skeleton.cortex.deck import live_deck
        out = live_deck().caps()
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "lattice":
        from skeleton.cortex.deck import live_deck
        out = live_deck().lattice()
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "sleep":
        from skeleton.cortex.deck import live_deck
        out = live_deck().sleep(force=bool(getattr(args, "force", False)), cue=str(getattr(args, "cue", "") or ""))
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "forget":
        from skeleton.cortex.deck import live_deck
        out = live_deck().forget(str(getattr(args, "cue", "") or ""))
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "helix":
        from skeleton.cortex.deck import live_deck
        out = live_deck().helix()
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "nervous":
        from skeleton.cortex.deck import live_deck
        out = live_deck().nervous()
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "scope":
        from skeleton.cortex.deck import live_deck
        out = live_deck().scope()
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "standin":
        from skeleton.cortex.deck import live_deck
        out = live_deck().standin()
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "enact":
        from skeleton.cortex.deck import live_deck
        out = live_deck().enact()
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "chronicle":
        from skeleton.cortex.deck import live_deck
        out = live_deck().chronicle(str(getattr(args, "cue", "") or "memory graph"))
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "dump":
        from skeleton.cortex.deck import live_deck
        out = live_deck().dump(force=bool(getattr(args, "force", False)))
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "satellites":
        from skeleton.cortex.deck import live_deck
        out = live_deck().satellites(str(getattr(args, "cue", "") or ""))
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "recall":
        from skeleton.cortex.deck import live_deck
        out = live_deck().recall(str(getattr(args, "cue", "") or ""))
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "health":
        from skeleton.cortex.deck import live_deck
        out = live_deck().health()
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "doctor":
        from skeleton.cortex.deck import live_deck
        out = live_deck().doctor(fix=bool(getattr(args, "fix", False)))
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "laws":
        from skeleton.cortex.deck import live_deck
        out = live_deck().laws()
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "next":
        from skeleton.cortex.deck import live_deck
        out = live_deck().next()
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "seed":
        from skeleton.cortex.deck import live_deck
        out = live_deck().seed()
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "field":
        from skeleton.cortex.deck import live_deck
        out = live_deck().field()
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "ready":
        from skeleton.cortex.deck import live_deck
        out = live_deck().ready(walk=bool(getattr(args, "walk", False)), n=int(getattr(args, "n", 2) or 2), fix=bool(getattr(args, "fix", False)))
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "pulse":
        from skeleton.cortex.deck import live_deck
        out = live_deck().pulse(args.stimulus)
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "walk":
        from skeleton.cortex.deck import live_deck
        out = live_deck().walk(args.stimulus, n=args.n)
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "merkle":
        from skeleton.cortex.hive import merkle_card
        from skeleton.cortex.live import live_cortex
        print(json.dumps(merkle_card(live_cortex()), indent=2, default=str))
        return 0

    if args.cmd == "zaibatsu":
        from skeleton.cortex.live import live_cortex
        from skeleton.cortex.zaibatsu import tournament
        print(json.dumps(tournament(live_cortex()), indent=2, default=str))
        return 0

    if args.cmd == "speak":
        from skeleton.cortex.live import live_cortex, persist
        text = live_cortex().speak(args.prefix, n=args.n, seed=args.seed, mouth=args.mouth)
        persist()
        print(text)
        return 0

    if args.cmd == "beam":
        from skeleton.cortex.live import live_cortex, persist
        out = live_cortex().beam(args.prefix, n=args.n, width=args.width, mouth=args.mouth)
        persist()
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "lora":
        from skeleton.cortex.live import live_cortex, persist
        neo = live_cortex()
        out = neo.merge_lora() if args.merge else neo.attach_lora(rank=args.rank)
        persist()
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "bind-hf":
        from skeleton.cortex.live import live_cortex, persist
        out = live_cortex().bind_hf(args.slot, args.model)
        persist()
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "bind-kimi":
        from skeleton.cortex.live import live_cortex, persist
        out = live_cortex().bind_kimi(args.slot, args.model)
        persist()
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "genos":
        from skeleton.cortex.live import live_cortex, persist
        out = live_cortex().genos(args.prefix)
        persist()
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "acquire-game":
        from skeleton.cortex.live import live_cortex, persist
        out = live_cortex().acquire_gaming(appid=args.appid, title=args.title)
        persist()
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "ascend":
        from skeleton.cortex.live import live_cortex, persist
        out = live_cortex().ascend(args.prefix, rounds=args.rounds)
        persist()
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "improve":
        from skeleton.cortex.live import live_cortex, persist
        out = live_cortex().improve(args.prefix, rounds=args.rounds)
        persist()
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "refer":
        from skeleton.cortex.live import live_cortex, persist
        out = live_cortex().refer(args.prefix, live=args.live)
        persist()
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "spree":
        from skeleton.cortex.live import live_cortex, persist
        out = live_cortex().acquire_spree()
        persist()
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "contact":
        from skeleton.cortex.live import live_cortex, persist
        out = live_cortex().contact(args.slot, args.prefix)
        persist()
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "distill":
        from skeleton.cortex.live import live_cortex, persist
        out = live_cortex().distill(args.slot, args.prefix)
        persist()
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "gossip":
        from skeleton.cortex import JeevesCortex
        from skeleton.cortex.live import live_cortex, persist
        neo = live_cortex()
        if args.mouths:
            out = neo.gossip_mouths(alpha=args.alpha, direction=args.direction)
        else:
            out = neo.gossip_with(JeevesCortex(), alpha=args.alpha)
        persist()
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "octwalk":
        from skeleton.cortex.deck import live_deck
        out = live_deck().octwalk(int(getattr(args, "n", 1) or 1))
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "erawalk":
        from skeleton.forge.eras import blend_eras, compile_era
        from skeleton.forge.walk import walk_from_pack
        from skeleton.jeeves.builder import BuilderBrain
        from skeleton.context.tensor import ContextTensor
        from skeleton.context.dodeca import Dodecahedron
        from skeleton.context.oracle import Magic8Ball
        if args.blend:
            pack = blend_eras(args.blend[0], args.blend[1], args.t)
            tensor = ContextTensor.from_era(args.blend[0]).lerp(
                ContextTensor.from_era(args.blend[1]), args.t
            )
        else:
            pack = compile_era(args.era)
            tensor = ContextTensor.from_era(args.era)
        reading = Magic8Ball(Dodecahedron.from_tensor(tensor)).roll(tensor)
        from skeleton.cortex.live import live_cortex, persist
        plan = BuilderBrain().plan(pack, tensor=tensor, reading=reading, cortex=live_cortex())
        persist()
        wr_i = walk_from_pack(pack, plan=plan.to_dict(), mode="ideal")
        wr = walk_from_pack(pack, plan=plan.to_dict(), mode="thermal")
        payload = wr.to_dict()
        payload["ideal"] = {"t": round(wr_i.t, 4), "extracted": wr_i.extracted}
        payload["plan"] = {"bias": plan.room_bias, "extract_late": plan.extract_late, "era": plan.era}
        if args.json:
            print(json.dumps(payload, indent=2, default=str))
        else:
            print(
                f"extracted={wr.extracted} thermal={wr.t:.2f}s ideal={wr_i.t:.2f}s "
                f"hops={wr.hops} heat_peak={wr.heat_peak:.1f} cores={wr.cores}/{wr.required_cores}"
            )
        return 0 if wr.passed and wr.t + 0.2 >= wr_i.t else 1

    if args.cmd == "think":
        from skeleton.cortex.live import live_cortex, persist
        neo = live_cortex()
        if args.bind:
            slot, how = args.bind
            if how == "echo":
                neo.bind_echo(slot)
            else:
                neo.bind_local(slot)
        trace = neo.think(args.stimulus)
        if args.acquire:
            neo.acquire(args.acquire)
        if args.surpass:
            neo.surpass(args.surpass)
            if args.stimulus:
                trace = neo.think(args.stimulus)
        persist()
        payload = trace.to_dict()
        if args.recall:
            payload["recall"] = neo.recall(args.stimulus)
        print(json.dumps(payload, indent=2, default=str))
        return 0

    if args.cmd == "plan":
        from skeleton.cortex.live import live_jeeves, persist
        out = live_jeeves().plan_build(vision=args.vision)
        persist()
        print(json.dumps(out, indent=2, default=str))
        return 0

    if args.cmd == "build-plan":
        from skeleton.context.tensor import ContextTensor, detect_era
        from skeleton.forge.eras import blend_eras, compile_era
        from skeleton.jeeves.builder import BuilderBrain
        from skeleton.context.dodeca import Dodecahedron
        from skeleton.context.oracle import Magic8Ball
        if args.blend:
            pack = blend_eras(args.blend[0], args.blend[1], args.t)
            tensor = ContextTensor.from_era(args.blend[0]).lerp(
                ContextTensor.from_era(args.blend[1]), args.t
            )
            object.__setattr__(tensor, "era", pack["era"])
        elif args.era:
            pack = compile_era(args.era)
            tensor = ContextTensor.from_era(args.era)
        else:
            era, _ = detect_era(args.vision or "")
            pack = compile_era(era)
            tensor = ContextTensor.from_era(era)
        reading = Magic8Ball(Dodecahedron.from_tensor(tensor)).roll(tensor)
        from skeleton.cortex.live import live_cortex, persist
        plan = BuilderBrain().plan(pack, tensor=tensor, reading=reading, cortex=live_cortex())
        persist()
        print(json.dumps(plan.to_dict(), indent=2))
        return 0

    from skeleton.context.pipeline import GameForgeRun

    answers = None
    vision = ""
    era = None
    out = None
    overwrite = False
    if args.cmd == "run":
        vision = args.vision
        era = args.era
        out = args.out
        overwrite = args.overwrite
        as_json = args.json
        blend = tuple(args.blend) + (args.t,) if args.blend else None
        generation = args.generation
    else:
        answers = {}
        for pair in args.pairs:
            if "=" not in pair:
                print("answers must be id=option", file=sys.stderr)
                return 2
            k, v = pair.split("=", 1)
            answers[k] = v
        out = args.out
        overwrite = args.overwrite
        as_json = False
        blend = None
        generation = None

    payload = GameForgeRun.live().execute(
        vision, era=era, answers=answers, project_root=out, overwrite=overwrite, target="godot",
        blend=blend, generation=generation,
    )
    if args.cmd == "run" and as_json:
        slim = {k: payload[k] for k in ("succeeded", "era", "mass", "complete", "sim", "project", "forge") if k in payload}
        print(json.dumps(slim, indent=2, default=str))
        return 0 if payload["succeeded"] else 1
    print(f"era={payload.get('era')} mass={payload.get('mass')} sim={payload.get('sim', {}).get('passed')} files={payload.get('forge', {}).get('file_count')}")
    if payload.get("project"):
        print("wrote", payload["project"]["root"])
    return 0 if payload.get("succeeded") else 1


if __name__ == "__main__":
    raise SystemExit(main())
