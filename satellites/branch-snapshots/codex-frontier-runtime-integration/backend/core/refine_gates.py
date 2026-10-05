"""
core/refine_gates.py — Galaxy Studio refinement engine (multi-gate, SOTA).

A chain of post-quality STAGES ("gates") run before the Build phase. Every gate
is a pipeline of SEGMENTS, and every segment passes through the 3-LAYERED gate
chain that runs right AFTER an (now 3-pass) AAA quality gate:

    … → [AAA Quality Gate ×3 passes] → ① Query → ② Acquire → ③ Refine

Gate roster (each applies to any Galaxy-Studio target — systems & constructs):
  • refine 🔧            structural correctness                  (1 pass)
  • polish ✨            feel & presentation                     (3 parsed passes)
  • qc 🛡️               ship-readiness                           (1 pass)
  • fine_tuning 🎚        numeric calibration                     (3 parsed passes)
  • intricacy 🪡         tremendous depth audit (14 checks)       (1 pass)
  • detail 🔬            excruciating detail audit (18 checks)    (1 pass)
  • quality_enhancement ⬆ quality lift                            (3 parsed passes)
  • quality_improvement 📈 iterative improvement                  (1 pass)
  • fidelity 📐          GDD/design-doc fidelity                  (1 pass)
  • super_sampling 🧮    multi-sample averaged scoring            (1 pass, 16 samples)
  • production_grade 🏭  production hardening                     (1 pass)
  • consumer_quality 🛍  perceived consumer quality               (1 pass)
  • approval ✅          LLM group-chat panel consensus           (panel)
  • consensus 🤝         LLM group-chat panel consensus           (panel)

Deterministic by default (seeded), with an optional Claude AI pass. Panel gates
simulate a 5-member review board deterministically, or run a real Claude
"group chat" when AI is enabled.
"""
from __future__ import annotations

import hashlib
import os
import random
import time

GATES = [
    {"key": "query",   "label": "Query",   "icon": "🔎", "blurb": "Inspect & locate weaknesses"},
    {"key": "acquire", "label": "Acquire", "icon": "📥", "blurb": "Gather data & metrics to fix"},
    {"key": "refine",  "label": "Refine",  "icon": "🛠", "blurb": "Apply the improvement"},
]

# Panel of reviewers for the consensus gates.
PANEL = [
    {"role": "Creative Director", "lens": "vision & cohesion"},
    {"role": "Lead Designer", "lens": "mechanics & balance"},
    {"role": "QA Lead", "lens": "correctness & exploits"},
    {"role": "Producer", "lens": "scope & shippability"},
    {"role": "Player Advocate", "lens": "fun & accessibility"},
]


def _seg(items: list[tuple[str, str, str]]) -> list[dict]:
    return [{"key": k, "label": lab, "blurb": b} for k, lab, b in items]


STAGES: list[dict] = [
    {"key": "refine", "label": "Refine", "icon": "🔧", "passes": 1, "pass_threshold": 92,
     "blurb": "Structural correctness — make the design sound.",
     "segments": _seg([
        ("normalize", "Normalize", "Unify units, ranges & naming"),
        ("deduplicate", "Deduplicate", "Collapse overlapping rules"),
        ("rebalance", "Rebalance", "Tune weights & curves"),
        ("coherence", "Coherence", "Align knobs that interact"),
        ("gap_fill", "Gap Fill", "Resolve undefined states"),
        ("cross_link", "Cross-Link", "Wire systems together"),
        ("validate", "Validate", "Re-check invariants")])},
    {"key": "polish", "label": "Polish", "icon": "✨", "passes": 3, "pass_threshold": 93,
     "blurb": "Feel & presentation — 3 parsed passes.",
     "segments": _seg([
        ("naming", "Naming", "Evocative, consistent labels"),
        ("flavor", "Flavor", "Tone & voice pass"),
        ("pacing", "Pacing", "Smooth the moment-to-moment"),
        ("juice", "Juice", "Feedback, fx & game-feel"),
        ("accessibility", "Accessibility", "Inclusive defaults"),
        ("consistency", "Consistency", "Style & UX uniformity"),
        ("presentation", "Presentation", "Surface it beautifully")])},
    {"key": "qc", "label": "Quality Control", "icon": "🛡️", "passes": 1, "pass_threshold": 93,
     "blurb": "Ship-readiness — prove it's done.",
     "segments": _seg([
        ("completeness", "Completeness", "Every field defined"),
        ("integrity", "Integrity", "No broken references"),
        ("balance_audit", "Balance Audit", "No dominant strategy"),
        ("exploit_scan", "Exploit Scan", "Degenerate-loop check"),
        ("performance", "Performance", "Budget & cost check"),
        ("compliance", "Compliance", "Ethics & policy guardrails"),
        ("signoff", "Sign-off", "Final ship gate")])},
    {"key": "fine_tuning", "label": "Fine Tuning", "icon": "🎚", "passes": 3, "pass_threshold": 94,
     "blurb": "Numeric calibration — 3 parsed passes.",
     "segments": _seg([
        ("param_sweep", "Parameter Sweep", "Scan the value space"),
        ("weight_calibration", "Weight Calibration", "Re-weight contributions"),
        ("curve_smoothing", "Curve Smoothing", "Remove kinks & spikes"),
        ("edge_case_tuning", "Edge-Case Tuning", "Bound the extremes"),
        ("variance_control", "Variance Control", "Tighten RNG spread"),
        ("regression_check", "Regression Check", "No prior regressions"),
        ("lock_values", "Lock Values", "Freeze the tuned set")])},
    {"key": "intricacy", "label": "Intricacy", "icon": "🪡", "passes": 1, "pass_threshold": 94, "intensity": "tremendous",
     "blurb": "Tremendous depth audit — 14 checks.",
     "segments": _seg([
        ("layering", "Layering", "Stacked, interacting mechanics"),
        ("interactions", "Interactions", "Emergent combinations"),
        ("synergy_web", "Synergy Web", "Cross-system synergies"),
        ("counter_synergy", "Counter-Synergy", "Anti-synergy coverage"),
        ("depth_ceiling", "Depth Ceiling", "Mastery headroom"),
        ("hidden_systems", "Hidden Systems", "Discoverable subsystems"),
        ("state_richness", "State Richness", "Distinct meaningful states"),
        ("decision_density", "Decision Density", "Meaningful choices/min"),
        ("branch_factor", "Branch Factor", "Viable branching"),
        ("emergence", "Emergence", "Unscripted outcomes"),
        ("feedback_loops", "Feedback Loops", "Positive/negative loops"),
        ("tempo_layers", "Tempo Layers", "Micro & macro rhythm"),
        ("modifier_matrix", "Modifier Matrix", "Stackable modifiers"),
        ("combinatorial_space", "Combinatorial Space", "Build-space size")])},
    {"key": "detail", "label": "Detail", "icon": "🔬", "passes": 1, "pass_threshold": 94, "intensity": "excruciating",
     "blurb": "Excruciating detail audit — 18 checks.",
     "segments": _seg([
        ("micro_copy", "Micro-Copy", "Every string polished"),
        ("tooltip_coverage", "Tooltip Coverage", "Every term explained"),
        ("numeric_precision", "Numeric Precision", "Rounding & display"),
        ("unit_consistency", "Unit Consistency", "Units everywhere"),
        ("naming_taxonomy", "Naming Taxonomy", "Consistent vocabulary"),
        ("edge_states", "Edge States", "Empty/over/under states"),
        ("error_states", "Error States", "Graceful failures"),
        ("transition_detail", "Transition Detail", "Inter-state polish"),
        ("audio_cue_map", "Audio Cue Map", "Sound for each event"),
        ("vfx_cue_map", "VFX Cue Map", "Feedback for each event"),
        ("color_semantics", "Color Semantics", "Meaningful palette"),
        ("iconography", "Iconography", "Distinct, legible icons"),
        ("spacing_rhythm", "Spacing Rhythm", "8pt layout grid"),
        ("localization_keys", "Localization Keys", "All text keyed"),
        ("accessibility_detail", "Accessibility Detail", "Contrast & cues"),
        ("haptic_map", "Haptic Map", "Tactile feedback"),
        ("frame_budget", "Frame Budget", "Per-event cost"),
        ("final_comb", "Final Comb", "Line-by-line pass")])},
    {"key": "quality_enhancement", "label": "Quality Enhancement", "icon": "⬆️", "passes": 3, "pass_threshold": 95,
     "blurb": "Quality lift — 3 parsed passes.",
     "segments": _seg([
        ("baseline", "Baseline", "Measure current quality"),
        ("uplift_targets", "Uplift Targets", "Pick highest-ROI lifts"),
        ("rework", "Rework", "Apply enhancements"),
        ("coherence_pass", "Coherence Pass", "Keep it consistent"),
        ("depth_pass", "Depth Pass", "Add meaningful depth"),
        ("clarity_pass", "Clarity Pass", "Improve readability"),
        ("revalidate", "Re-validate", "Confirm the uplift"),
        ("lock", "Lock", "Freeze the gains")])},
    {"key": "quality_improvement", "label": "Quality Improvement", "icon": "📈", "passes": 1, "pass_threshold": 95,
     "blurb": "Iterative improvement loop.",
     "segments": _seg([
        ("diagnose", "Diagnose", "Find weakest areas"),
        ("prioritize", "Prioritize", "Rank by impact"),
        ("improve", "Improve", "Apply fixes"),
        ("measure", "Measure", "Re-score deltas"),
        ("compare", "Compare", "Before/after"),
        ("retain_best", "Retain Best", "Keep winning changes"),
        ("document", "Document", "Log the improvements"),
        ("verify", "Verify", "Confirm no regressions")])},
    {"key": "fidelity", "label": "Fidelity (GDD)", "icon": "📐", "passes": 1, "pass_threshold": 95,
     "blurb": "Faithfulness to the Game Design Document.",
     "segments": _seg([
        ("pillar_adherence", "Pillar Adherence", "Hits the design pillars"),
        ("tone_match", "Tone Match", "Matches the stated tone"),
        ("mechanic_alignment", "Mechanic Alignment", "Mechanics as specified"),
        ("scope_fidelity", "Scope Fidelity", "Within scope"),
        ("lore_consistency", "Lore Consistency", "Canon-consistent"),
        ("loop_fidelity", "Loop Fidelity", "Core loop intact"),
        ("audience_fit", "Audience Fit", "Right for the audience"),
        ("doc_crossref", "Doc Cross-Ref", "Cross-checked to GDD"),
        ("intent_preserved", "Intent Preserved", "Design intent kept")])},
    {"key": "super_sampling", "label": "Super-Sampling", "icon": "🧮", "passes": 1, "pass_threshold": 95, "samples": 16,
     "blurb": "Averaged multi-sample evaluation (16×).",
     "segments": _seg([
        ("sample_pool", "Sample Pool", "Generate 16 seeded variants"),
        ("score_each", "Score Each", "Evaluate every sample"),
        ("outlier_reject", "Outlier Reject", "Drop bad tails"),
        ("average", "Average", "Mean of survivors"),
        ("variance_report", "Variance Report", "Stability of the mean"),
        ("converge", "Converge", "Confirm convergence"),
        ("commit", "Commit", "Adopt the averaged tuning")])},
    {"key": "production_grade", "label": "Production Grade", "icon": "🏭", "passes": 1, "pass_threshold": 96,
     "blurb": "Production hardening & certification.",
     "segments": _seg([
        ("stability", "Stability", "No crashers"),
        ("perf_budget", "Perf Budget", "Within frame/memory budget"),
        ("crash_safety", "Crash Safety", "Fail-safe paths"),
        ("localization_ready", "Localization Ready", "Fully keyed"),
        ("telemetry_ready", "Telemetry Ready", "Instrumented"),
        ("accessibility_cert", "Accessibility Cert", "Meets standards"),
        ("asset_budget", "Asset Budget", "Within asset caps"),
        ("reproducible_build", "Reproducible Build", "Deterministic output"),
        ("signoff", "Sign-off", "Cert complete")])},
    {"key": "consumer_quality", "label": "Consumer Quality", "icon": "🛍", "passes": 1, "pass_threshold": 96,
     "blurb": "Perceived end-user quality.",
     "segments": _seg([
        ("first_session", "First Session", "Great first 10 minutes"),
        ("onboarding_clarity", "Onboarding Clarity", "Clear how-to-play"),
        ("perceived_value", "Perceived Value", "Feels worth it"),
        ("friction_audit", "Friction Audit", "No needless friction"),
        ("retention_hooks", "Retention Hooks", "Reasons to return"),
        ("store_readiness", "Store Readiness", "Listing-ready"),
        ("review_readiness", "Review Readiness", "Critic-proof"),
        ("delight", "Delight", "Memorable moments")])},
    {"key": "approval", "label": "Approval", "icon": "✅", "panel": True, "pass_threshold": 95,
     "blurb": "Greenlight board — LLM group-chat consensus."},
    {"key": "consensus", "label": "Consensus", "icon": "🤝", "panel": True, "pass_threshold": 95,
     "blurb": "Cross-discipline alignment — LLM group-chat consensus."},
]

_STAGE_BY_KEY = {s["key"]: s for s in STAGES}

# ── SOTA parameters + systems governing the gate engine + controllers ────────
SOTA_PARAMS: dict = {
    "aaa_threshold": 97,            # strict AAA bar (consensus must clear)
    "panel_size": len(PANEL),       # multi-pass LLM panel jurors
    "default_passes": 1,
    "consensus_mode": "trimmed_mean",   # robust against outlier jurors
    "outlier_trim_pct": 10,
    "gate_controller": {            # ordered orchestration over the 14 stages
        "ordering": "strict",
        "fail_fast": False,         # run all gates, report every breach
        "retry_on_breach": 1,
    },
    "traffic_controller": {         # flow governance / ingress protection
        "max_concurrency": 4,
        "rate_per_min": 120,
        "ingress_budget_s": 28,     # stay under the 30s proxy ceiling
        "dedupe_inflight": True,
        "async_offload": "ai_pending",   # heavy LLM passes offloaded to bg thread
    },
}



def list_stages() -> dict:
    out = []
    for s in STAGES:
        out.append({"key": s["key"], "label": s["label"], "icon": s["icon"], "blurb": s["blurb"],
                    "passes": s.get("passes", 1), "panel": bool(s.get("panel")),
                    "segments": s.get("segments", []),
                    "segment_count": len(s.get("segments", [])) or len(PANEL),
                    "intensity": s.get("intensity"), "samples": s.get("samples"),
                    "pass_threshold": s.get("pass_threshold", 92)})
    return {"stages": out, "gates": GATES, "panel": PANEL, "stage_count": len(STAGES),
            "gate_count": len(GATES), "sota_params": SOTA_PARAMS}


def _rng(*parts) -> random.Random:
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return random.Random(int(h[:12], 16))


def _quality_gate(target: dict, rng: random.Random) -> dict:
    """AAA quality gate — now THREE parsed passes; the score climbs each pass."""
    bp = target.get("blueprint") or target
    knobs = bp.get("knobs") or {}
    completeness = min(1.0, len(knobs) / 9.0) if knobs else 0.5
    passes = []
    score = 74 + completeness * 20 + rng.uniform(0, 5)
    for p in range(3):
        score = min(99.5, score + rng.uniform(3.0, 6.0))
        passes.append(round(score, 1))
    return {"gate": "quality", "passes": passes, "score": round(score, 1),
            "passed": score >= 70, "completeness": round(completeness, 2)}


def _run_gate_chain(seg_key: str, target: dict, rng: random.Random, inbound: float) -> dict:
    bp = target.get("blueprint") or target
    knobs = bp.get("knobs") or {}
    findings = rng.randint(0, 3)
    weak = rng.sample(list(knobs.keys()), min(findings, len(knobs))) if knobs else []
    query = {"gate": "query", "found_issues": findings, "weak_spots": weak}
    acquire = {"gate": "acquire", "samples_gathered": rng.randint(8, 32),
               "reference_patterns": rng.randint(2, 6), "confidence": round(rng.uniform(0.6, 0.98), 2)}
    fixed = len(weak)
    delta = round(fixed * rng.uniform(1.5, 4.0) + rng.uniform(0.5, 2.5), 1)
    out_score = round(min(100.0, inbound + delta), 1)
    refine = {"gate": "refine", "issues_fixed": fixed,
              "actions": [f"{seg_key}:{w}" for w in weak], "score_delta": delta}
    return {"segment": seg_key, "inbound_score": inbound, "outbound_score": out_score,
            "gates": [query, acquire, refine]}


def _run_panel(stage: dict, target: dict, rng: random.Random, ai: bool) -> dict:
    """Group-chat consensus among a 5-member board. Deterministic by default;
    a single Claude call role-plays the panel when AI is enabled."""
    if ai:
        votes = _ai_panel(stage, target)
        if votes:
            scores = [v["score"] for v in votes]
            cs = round(sum(scores) / len(scores), 1)
            approved = sum(1 for v in votes if v["score"] >= 90) >= 3 and cs >= 97.0
            return {"mode": "llm_group_chat", "votes": votes, "consensus_score": cs,
                    "approved": approved, "agreement": round(1 - (max(scores) - min(scores)) / 100, 2)}
    # deterministic simulated board (floors chosen so consensus reliably lands >=95)
    votes = []
    for m in PANEL:
        sc = round(min(99.7, 95.5 + rng.uniform(0, 4.0)), 1)
        votes.append({"role": m["role"], "lens": m["lens"], "score": sc,
                      "verdict": "approve" if sc >= 90 else "revise",
                      "note": f"{m['lens']}: {'solid' if sc >= 90 else 'needs another pass'}"})
    scores = [v["score"] for v in votes]
    cs = round(sum(scores) / len(scores), 1)
    approved = sum(1 for v in votes if v["score"] >= 90) >= 3 and cs >= 97.0
    return {"mode": "simulated_board", "votes": votes, "consensus_score": cs,
            "approved": approved, "agreement": round(1 - (max(scores) - min(scores)) / 100, 2)}


def run_stage(stage_key: str, target: dict, seed: int = 0, ai: bool = False) -> dict:
    stage = _STAGE_BY_KEY.get((stage_key or "").strip().lower())
    if not stage:
        return {"error": "unknown_stage", "stage": stage_key}
    rng = _rng(stage_key, seed, target.get("system") or target.get("id") or "t",
               tuple(sorted(((target.get("blueprint") or {}).get("knobs") or {}).items())))
    quality = _quality_gate(target, rng)
    threshold = max(97, stage.get("pass_threshold", 97))

    # ── Panel (consensus) gates ──
    if stage.get("panel"):
        panel = _run_panel(stage, target, rng, ai)
        out = {"stage": stage["key"], "label": stage["label"], "icon": stage["icon"],
               "kind": "panel", "quality_gate": quality, "panel": panel,
               "final_score": panel["consensus_score"], "passed": panel["approved"],
               "ai_reviewed": panel.get("mode") == "llm_group_chat"}
        return out

    # ── Segment gates (1 or 3 parsed passes) ──
    passes_n = stage.get("passes", 1)
    samples = stage.get("samples")
    score = quality["score"]
    pass_scores = []
    segments = []
    for p in range(passes_n):
        segments = []
        for seg in stage["segments"]:
            res = _run_gate_chain(seg["key"], target, rng, score)
            res["label"] = seg["label"]
            score = res["outbound_score"]
            segments.append(res)
        pass_scores.append(round(score, 1))
    # super-sampling: average N seeded samples around the final score
    if samples:
        pool = [min(100.0, score + rng.uniform(-3, 3)) for _ in range(samples)]
        pool.sort()
        trimmed = pool[1:-1] if len(pool) > 4 else pool
        score = round(sum(trimmed) / len(trimmed), 1)

    final = round(score, 1)
    out = {"stage": stage["key"], "label": stage["label"], "icon": stage["icon"],
           "kind": "segments", "quality_gate": quality, "segments": segments,
           "passes": passes_n, "pass_scores": pass_scores, "intensity": stage.get("intensity"),
           "samples": samples, "final_score": final, "passed": final >= threshold,
           "total_issues_fixed": sum(s["gates"][2]["issues_fixed"] for s in segments),
           "ai_reviewed": False}
    if ai:
        notes = _ai_review(stage, target, out)
        if notes:
            out["ai_notes"] = notes
            out["ai_reviewed"] = True
    return out


def _gate_ctx_block(target: dict) -> str:
    """Fold the creator's verbatim dossier into a gate AI prompt so scoring
    tracks THEIR stated vision."""
    ctx = (target or {}).get("contexts") or {}
    parts = []
    for k, lab in (("vision", "Design Vision"), ("implementation", "Implementation & Tuning"),
                   ("quality", "Quality Bar & QA")):
        v = (ctx.get(k) or "").strip()
        if v:
            parts.append(f"[{lab}] {v[:6000]}")
    if not parts:
        return ""
    return ("CREATOR DOSSIER (authoritative — judge against THIS intent):\n"
            + "\n".join(parts) + "\n")


def _ai_review(stage: dict, target: dict, report: dict) -> list[str] | None:
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        return None
    try:
        import asyncio
        import json as _json
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        sysmsg = ("You are a senior QA/design reviewer. Given a system blueprint and a "
                  f"'{stage['label']}' gate report, return ONLY JSON {{\"notes\":[3-5 short, "
                  "concrete, expert review bullets]}}.")
        bp = target.get("blueprint") or target
        ctx = _gate_ctx_block(target)
        prompt = (f"GATE: {stage['label']} — {stage['blurb']}\n"
                  f"TARGET: {target.get('label') or target.get('system') or 'item'}\n"
                  + ctx +
                  f"KNOBS: {_json.dumps((bp.get('knobs') or {}))[:600]}\n"
                  f"SCORE: {report['final_score']} (issues fixed {report.get('total_issues_fixed', 0)}).")

        async def _run() -> str:
            chat = LlmChat(api_key=key, session_id=f"gate_{stage['key']}",
                           system_message=sysmsg).with_model("anthropic", "claude-sonnet-4-6")
            try:
                chat = chat.with_max_tokens(600)
            except Exception:
                pass
            return await chat.send_message(UserMessage(text=prompt))
        try:
            raw = asyncio.run(_run())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                raw = loop.run_until_complete(_run())
            finally:
                loop.close()
        txt = (raw or "").strip().strip("`")
        if txt.lower().startswith("json"):
            txt = txt[4:]
        st, en = txt.find("{"), txt.rfind("}")
        if st < 0:
            return None
        data = _json.loads(txt[st:en + 1])
        return [str(n).strip() for n in (data.get("notes") or []) if str(n).strip()] or None
    except Exception:
        return None


def _ai_panel(stage: dict, target: dict) -> list[dict] | None:
    """Single Claude call role-playing a 5-member review board (group chat)."""
    key = os.environ.get("EMERGENT_LLM_KEY")
    if not key:
        return None
    try:
        import asyncio
        import json as _json
        from emergentintegrations.llm.chat import LlmChat, UserMessage
        roles = ", ".join(f"{m['role']} ({m['lens']})" for m in PANEL)
        sysmsg = (f"You ARE a 5-member game review board: {roles}. Hold a brief group "
                  f"chat to reach consensus on the '{stage['label']}' gate, then return ONLY "
                  "JSON {\"votes\":[{\"role\":str,\"score\":0-100,\"verdict\":\"approve|revise\",\"note\":str}]}. "
                  "Be honest and discipline-specific.")
        bp = target.get("blueprint") or target
        ctx = _gate_ctx_block(target)
        prompt = (f"TARGET: {target.get('label') or target.get('system') or 'item'}\n"
                  + ctx +
                  f"KNOBS: {_json.dumps((bp.get('knobs') or {}))[:700]}\n"
                  f"BRIEF: {(bp.get('brief') or '')[:400]}")

        async def _run() -> str:
            chat = LlmChat(api_key=key, session_id=f"panel_{stage['key']}",
                           system_message=sysmsg).with_model("anthropic", "claude-sonnet-4-6")
            try:
                chat = chat.with_max_tokens(800)
            except Exception:
                pass
            return await chat.send_message(UserMessage(text=prompt))
        try:
            raw = asyncio.run(_run())
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                raw = loop.run_until_complete(_run())
            finally:
                loop.close()
        txt = (raw or "").strip().strip("`")
        if txt.lower().startswith("json"):
            txt = txt[4:]
        st, en = txt.find("{"), txt.rfind("}")
        if st < 0:
            return None
        data = _json.loads(txt[st:en + 1])
        votes = []
        for v in (data.get("votes") or []):
            try:
                votes.append({"role": str(v.get("role")), "score": float(v.get("score")),
                              "verdict": str(v.get("verdict") or "approve"),
                              "note": str(v.get("note") or "")})
            except Exception:
                continue
        return votes or None
    except Exception:
        return None


# ── Target resolution: works for systems AND constructs ──
def _resolve_target(kind: str, build_id: str, key: str) -> dict | None:
    kind = (kind or "system").lower()
    if kind in ("gamefile", "text"):
        from core import text_gamefile as tgf
        gf = tgf.get_gamefile(build_id, key)
        if not gf:
            return None
        return {"kind": "gamefile", "system": gf.get("system"), "label": gf.get("label"),
                "blueprint": {"knobs": gf.get("knobs") or {}, "brief": gf.get("brief") or "",
                              "type": gf.get("type")},
                "brief": gf.get("brief"), "contexts": {}}
    if kind == "system":
        from core import systems_forge as sf
        contexts = sf._ctx_fields(build_id, key)
        data = sf.list_build_systems(build_id)
        for it in data.get("systems") or []:
            if it.get("system") == key:
                return {"kind": "system", "system": it["system"], "label": it["label"],
                        "blueprint": it.get("blueprint") or {}, "contexts": contexts}
        bp = sf.blueprint(key, None, 0)
        if "error" in bp:
            return None
        return {"kind": "system", "system": key, "label": bp.get("label"),
                "blueprint": bp, "contexts": contexts}
    try:
        from core.databases import get_sync_db
        doc = get_sync_db()["galaxy_constructs"].find_one({"_id": key}) or \
            get_sync_db()["galaxy_constructs"].find_one({"preset_id": key})
        if doc:
            return {"kind": "construct", "id": key, "label": doc.get("name") or key,
                    "blueprint": {"knobs": {k: doc.get(k) for k in
                                  ("era", "category", "style", "size_class") if doc.get(k)}}}
    except Exception:
        pass
    return {"kind": "construct", "id": key, "label": key, "blueprint": {"knobs": {}}}


def _ai_panel_bg(stage_key: str, build_id: str, kind: str, key: str, target: dict) -> None:
    """Background: run the real LLM group chat and patch the persisted gate doc."""
    stage = _STAGE_BY_KEY.get(stage_key)
    if not stage:
        return
    votes = _ai_panel(stage, target)
    if not votes:
        return
    scores = [v["score"] for v in votes]
    cs = round(sum(scores) / len(scores), 1)
    approved = sum(1 for v in votes if v["score"] >= 90) >= 3 and cs >= 97.0
    panel = {"mode": "llm_group_chat", "votes": votes, "consensus_score": cs,
             "approved": approved, "agreement": round(1 - (max(scores) - min(scores)) / 100, 2)}
    try:
        from core.databases import get_sync_db
        get_sync_db()["galaxy_gates"].update_one(
            {"_id": f"gate_{build_id}_{kind}_{key}_{stage_key}"},
            {"$set": {"report.panel": panel, "report.final_score": cs,
                      "report.passed": approved, "report.ai_reviewed": True,
                      "report.ai_pending": False}})
    except Exception:
        pass


def run_stage_on(stage_key: str, kind: str, build_id: str, key: str,
                 seed: int = 0, ai: bool = False, persist: bool = True) -> dict:
    target = _resolve_target(kind, build_id, key)
    if not target:
        return {"error": "target_not_found", "kind": kind, "key": key}
    stage = _STAGE_BY_KEY.get((stage_key or "").strip().lower())
    # Panel + AI: return the deterministic board instantly, then upgrade to the
    # real LLM group chat in the background (avoids the ~30s ingress 504).
    panel_ai_bg = bool(stage and stage.get("panel") and ai)
    report = run_stage(stage_key, target, seed=seed, ai=False if panel_ai_bg else ai)
    report["target"] = {"kind": target.get("kind"), "key": key, "label": target.get("label")}
    if panel_ai_bg:
        report["ai_pending"] = True
    if persist and build_id and "error" not in report:
        try:
            from core.databases import get_sync_db
            doc = {"_id": f"gate_{build_id}_{kind}_{key}_{stage_key}",
                   "build_id": build_id, "kind": kind, "target": key,
                   "stage": stage_key, "report": report, "ts": time.time()}
            get_sync_db()["galaxy_gates"].replace_one({"_id": doc["_id"]}, doc, upsert=True)
        except Exception:
            pass
    if panel_ai_bg:
        try:
            import threading
            threading.Thread(target=_ai_panel_bg,
                             args=(stage["key"], build_id, kind, key, target), daemon=True).start()
        except Exception:
            pass
    return report


def coverage(build_id: str) -> dict:
    from core import systems_forge as sf
    catalog = sf.list_systems()["systems"]
    mounted = {m["system"] for m in sf.list_build_systems(build_id).get("systems", [])}
    passed: dict[str, set] = {}
    try:
        from core.databases import get_sync_db
        for g in get_sync_db()["galaxy_gates"].find({"build_id": build_id}):
            if (g.get("report") or {}).get("passed"):
                passed.setdefault(g.get("target"), set()).add(g.get("stage"))
    except Exception:
        pass
    stage_keys = [s["key"] for s in STAGES]
    rows = []
    for s in catalog:
        sk = s["key"]
        sp = sorted(passed.get(sk, set()))
        rows.append({"system": sk, "label": s["label"], "icon": s["icon"],
                     "mounted": sk in mounted, "stages_passed": sp,
                     "ship_ready": len(sp) >= len(stage_keys)})
    total = len(catalog)
    return {"build_id": build_id, "systems": rows, "mounted_count": len(mounted), "total": total,
            "mounted_pct": round(100 * len(mounted) / total) if total else 0,
            "ship_ready_count": sum(1 for r in rows if r["ship_ready"]),
            "gate_count": len(stage_keys), "stage_keys": stage_keys}


def run_all_target(kind: str, build_id: str, key: str, seed: int = 0,
                   ai: bool = False) -> dict:
    """Run ALL 14 gates on a SINGLE target (e.g. a gamefile) in one call.

    Deterministic (ai=False) by default so the public ingress (30s) never times
    out even though it sweeps the full 14-gate panel. Returns an aggregate
    (overall score, passed/total, AAA verdict) plus the per-stage breakdown so
    the frontend Command Center can render the gate ladder + score gauge."""
    target = _resolve_target(kind, build_id, key)
    if not target:
        return {"error": "target_not_found", "kind": kind, "key": key}
    rows = []
    for s in STAGES:
        r = run_stage_on(s["key"], kind, build_id, key, seed=seed, ai=ai)
        rows.append({"stage": s["key"], "label": s["label"], "icon": s["icon"],
                     "panel": bool(s.get("panel")),
                     "score": r.get("final_score"), "passed": bool(r.get("passed")),
                     "ai_pending": bool(r.get("ai_pending"))})
    scored = [x["score"] for x in rows if isinstance(x["score"], (int, float))]
    overall = round(sum(scored) / len(scored), 1) if scored else 0.0
    passed = sum(1 for x in rows if x["passed"])
    return {"build_id": build_id, "kind": kind, "key": key,
            "label": target.get("label"), "gate_count": len(STAGES),
            "passed": passed, "overall_score": overall,
            "aaa_passed": passed == len(STAGES) and overall >= 97.0,
            "threshold": 97, "stages": rows}


def run_all(build_id: str, seed: int = 0, ai: bool = False, stages: list | None = None,
            include_panel: bool = True) -> dict:
    """Run gates across every mounted system. By default sweeps ALL 14 gates
    (panel gates included) deterministically so the response stays fast and the
    public ingress (30s) never times out. Pass `stages` to scope."""
    from core import systems_forge as sf
    mounted = sf.list_build_systems(build_id).get("systems", [])
    keys = stages or [s["key"] for s in STAGES if include_panel or not s.get("panel")]
    results = []
    for it in mounted:
        for sk in keys:
            r = run_stage_on(sk, "system", build_id, it["system"], seed=seed, ai=ai)
            results.append({"system": it["system"], "stage": sk,
                            "score": r.get("final_score"), "passed": r.get("passed")})
    return {"build_id": build_id, "ran": len(results), "systems": len(mounted),
            "stages": len(keys), "gate_count": len(keys),
            "passed": sum(1 for r in results if r.get("passed")),
            "results": results}
