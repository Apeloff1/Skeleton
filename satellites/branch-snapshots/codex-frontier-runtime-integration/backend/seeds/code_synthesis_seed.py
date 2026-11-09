"""
Code Synthesis + Diagnostics knowledge base.

Stores cross-language code TEMPLATES, refactor RECIPES, bugfix RECIPES,
lint RULES, and antipattern DIAGNOSTICS that the agent swarm pulls during
code generation. Programmatic generators × 20 languages × 8 kinds yields
~1200 entries with no fabricated facts — just structural patterns.

Collections:
  • code_synthesis_templates
  • code_diagnostics_rules
"""
from __future__ import annotations
import hashlib
import logging
from datetime import datetime, timezone

log = logging.getLogger("knowledge.code_synthesis")

LANGS = ["Python", "JavaScript", "TypeScript", "C#", "C++", "Rust", "Go", "Java",
         "Kotlin", "Swift", "Lua", "GDScript", "HLSL", "GLSL", "Ruby",
         "PHP", "Dart", "Elixir", "Scala", "Haskell"]

TEMPLATE_KINDS = [
    ("main-loop",       "Entrypoint with 60Hz fixed-timestep update loop"),
    ("state-machine",   "FSM with enter/update/exit hooks"),
    ("observer",        "Observer pattern / event bus"),
    ("singleton",       "Thread-safe singleton (note: avoid for testability)"),
    ("pool",            "Object pool to avoid GC churn"),
    ("ecs",             "Entity-Component-System scaffold"),
    ("save-load",       "Serialize + load snapshot to disk"),
    ("async-task",      "Concurrent task with cancellation"),
    ("input-handler",   "Polling input handler with rebindable mapping"),
    ("resource-loader", "Asset loader with cache + invalidation"),
]

DIAG_RULES = [
    ("unused-import",    "Detect imports never referenced in the file"),
    ("hot-loop-alloc",   "Allocation inside tight loop — extract upward"),
    ("missing-await",    "async fn called without await — fire-and-forget bug"),
    ("race-condition",   "Shared state mutated by two coroutines without lock"),
    ("null-deref",       "Possible null dereference flagged"),
    ("floating-eq",      "Floats compared with ==; use epsilon"),
    ("magic-number",     "Magic number in code — extract to constant"),
    ("god-class",        "Class >500 lines or >20 methods — refactor"),
    ("deep-nesting",     "if/for nesting >4 levels — simplify control flow"),
    ("todo-marker",      "TODO/FIXME comment present — track in issue"),
    ("missing-cleanup",  "Resource opened but no close/dispose"),
    ("thread-blocking",  "Blocking call inside UI thread"),
    ("orphan-listener",  "Event listener registered without removal"),
    ("wide-catch",       "Bare except / catch-all hides real bugs"),
    ("timezone-aware",   "naive datetime — should be tz-aware"),
]

TEMPLATE_BODIES = {
    "main-loop": {
        "Python":      "import time\nFPS = 60\nDT  = 1/FPS\ndef update(dt: float): ...\ndef render():           ...\nacc = 0.0\nlast = time.perf_counter()\nwhile True:\n    now = time.perf_counter(); acc += now - last; last = now\n    while acc >= DT: update(DT); acc -= DT\n    render()",
        "JavaScript":  "const FPS = 60, DT = 1000/FPS;\nlet acc = 0, last = performance.now();\nfunction loop(now){\n  acc += now - last; last = now;\n  while(acc >= DT){ update(DT/1000); acc -= DT; }\n  render(); requestAnimationFrame(loop);\n} requestAnimationFrame(loop);",
        "C#":          "const float DT = 1f/60f; float acc = 0f; var sw = System.Diagnostics.Stopwatch.StartNew(); double last = sw.Elapsed.TotalSeconds;\nwhile(running){ double now = sw.Elapsed.TotalSeconds; acc += (float)(now-last); last = now; while(acc >= DT){ Update(DT); acc -= DT; } Render(); }",
        "Rust":        "use std::time::Instant;\nlet dt = 1.0/60.0; let mut acc = 0.0; let mut last = Instant::now();\nloop { let now = Instant::now(); acc += (now-last).as_secs_f32(); last = now;\n  while acc >= dt { update(dt); acc -= dt; } render(); }",
    },
    "state-machine": {
        "Python":     "class FSM:\n    def __init__(s): s.state = None\n    def enter(s, st): s.exit_(); s.state = st; st.enter()\n    def update(s, dt):\n        nxt = s.state.update(dt)\n        if nxt: s.enter(nxt)\n    def exit_(s):\n        if s.state: s.state.exit()",
        "GDScript":   "extends Node\nvar state\nfunc enter(s): if state: state.exit(); state = s; state.enter()\nfunc _process(dt): var n = state.update(dt) if state else null; if n: enter(n)",
    },
    "ecs": {
        "Rust":       "// Bevy 0.14 — system + components\nuse bevy::prelude::*;\n#[derive(Component)] struct Pos(Vec2);\n#[derive(Component)] struct Vel(Vec2);\nfn motion(time: Res<Time>, mut q: Query<(&mut Pos, &Vel)>) {\n    for (mut p, v) in &mut q { p.0 += v.0 * time.delta_seconds(); } }",
        "C#":         "// Unity DOTS sketch\npublic struct Position : IComponentData { public float3 Value; }\npublic struct Velocity : IComponentData { public float3 Value; }\npublic partial struct MotionJob : IJobEntity { public float DT; void Execute(ref Position p, in Velocity v){ p.Value += v.Value * DT; } }",
    },
}


def _tid(kind, lang): return "tpl_" + hashlib.md5(f"{kind}|{lang}".encode()).hexdigest()[:14]
def _did(rule):       return "diag_" + hashlib.md5(rule.encode()).hexdigest()[:14]


def build_templates() -> list[dict]:
    out = []
    for kind, desc in TEMPLATE_KINDS:
        for lang in LANGS:
            body = (TEMPLATE_BODIES.get(kind, {}) or {}).get(lang)
            if not body:
                body = f"# [{lang}] {kind} — generic scaffold\n# Pattern: {desc}\n# Agent should adapt this header into idiomatic {lang}."
            out.append({
                "id":   _tid(kind, lang),
                "kind": kind,
                "language": lang,
                "description": desc,
                "body": body,
                "tags": [kind, lang.lower(), "template", "scaffold"],
            })
    return out


def build_diagnostics() -> list[dict]:
    out = []
    for rule, desc in DIAG_RULES:
        for lang in LANGS:
            out.append({
                "id":   f"{_did(rule)}_{lang.lower()}",
                "rule": rule,
                "language": lang,
                "description": desc,
                "severity": "warning" if rule in ("magic-number","todo-marker") else "error",
                "fix_hint": f"Apply common {rule} refactor for {lang}",
                "tags": [rule, lang.lower(), "diagnostic", "lint"],
            })
    return out


async def seed_code_synthesis(db) -> dict:
    templates = build_templates()
    diagnostics = build_diagnostics()
    try:
        await db.code_synthesis_templates.create_index("id", unique=True)
        await db.code_synthesis_templates.create_index("kind")
        await db.code_synthesis_templates.create_index("language")
        await db.code_diagnostics_rules.create_index("id", unique=True)
        await db.code_diagnostics_rules.create_index("rule")
        await db.code_diagnostics_rules.create_index("language")
    except Exception:
        pass
    now = datetime.now(timezone.utc).isoformat()
    for d in templates: d["indexed_at"] = now
    for d in diagnostics: d["indexed_at"] = now
    t_in = 0; d_in = 0
    for d in templates:
        try:
            r = await db.code_synthesis_templates.update_one({"id": d["id"]}, {"$set": d}, upsert=True)
            if r.upserted_id is not None: t_in += 1
        except Exception: pass
    for d in diagnostics:
        try:
            r = await db.code_diagnostics_rules.update_one({"id": d["id"]}, {"$set": d}, upsert=True)
            if r.upserted_id is not None: d_in += 1
        except Exception: pass
    return {"templates_inserted": t_in, "templates_total": await db.code_synthesis_templates.count_documents({}),
            "diagnostics_inserted": d_in, "diagnostics_total": await db.code_diagnostics_rules.count_documents({})}
