"""
╔════════════════════════════════════════════════════════════════════════╗
║  SNOWBALL FORGE — escalating, parity-locked, quality-gated build.       ║
║  ────────────────────────────────────────────────────────────────────  ║
║  Walks the item-bearing stages in order. At EVERY stage it:             ║
║                                                                        ║
║    1. PARSES all accumulated GDD sections + gamefiles in the Vault       ║
║    2. BUILDS the next stage's gamefiles grounded on them (snowball)      ║
║    3. CLEARS escalating QUALITY GATES (grade floor + fidelity rise)      ║
║    4. Forges a 10× ASSET pack per accepted gamefile                      ║
║    5. ESCALATES the GDD (one new section per stage)                      ║
║    6. ENFORCES GDD PARITY — #GDD sections == #gamefile stages, always    ║
║                                                                        ║
║  The grade floor escalates each stage, so later gamefiles are graded     ║
║  strictly above earlier ones. Deterministic & seed-reproducible.        ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import time
from typing import Any

from core import asset_forge
from core import eras as eras_mod
from core import forge_quality as gates
from core import game_choices
from core import item_foundry as foundry
from core import swarm_planner as planner


def _escalation_floor(base_grade: int, stage_index: int) -> int:
    """Grade floor RISES each stage (capped so a higher grade is always
    reachable)."""
    return min(base_grade + stage_index, len(foundry._TIERS) - 2)


def _gdd_header(title: str, genre: str, build_id: str) -> list[str]:
    return [
        f"# 🎮 Escalating GDD — {title}",
        "",
        f"**Genre:** {genre} · **Build:** `{build_id}`",
        "",
        "> Snowball build: each stage below PARSES every prior GDD section + "
        "gamefile and builds on top, with an escalating grade floor and a "
        "GDD-parity lock (one section per built stage).",
        "",
    ]


def _gdd_stage_section(level: int, stage: str, items: list[dict],
                       floor: int, prior_stages: list[str]) -> list[str]:
    icon = {"world": "🌍", "narrative": "📖", "mechanics": "⚙️",
            "procedural": "🧬", "tileset": "🧱", "assets": "🎨"}.get(stage, "•")
    grounded = ", ".join(prior_stages) if prior_stages else "the Vault canon"
    L = [
        f"## Lv{level} · {icon} {stage.title()}",
        "",
        f"_Built on: {grounded}. Grade floor ≥ {floor}._",
        "",
    ]
    for it in sorted(items, key=lambda x: -int(x.get("grade", 0))):
        d = it.get("definition") or {}
        L.append(f"- **{it.get('name')}** · {d.get('tier')} (G{it.get('grade')}) · "
                 f"{d.get('archetype')} · {(it.get('skin') or {}).get('material')}")
    L.append("")
    return L


def escalate(build_id: str, genre: str = "rpg", seed: int = 0,
             platoon_size: int = 4, base_grade: int = 2, era: str | None = None,
             config: dict | None = None, persist: bool = True) -> dict:
    """Run the full escalating, parity-locked, quality-gated snowball build.

    Era-sensitive AND choice-sensitive: every Galaxy-Builder Advanced choice in
    ``config`` is stamped onto every item + asset and gated for reflection in
    every step. Every choice is logged to the per-game ledger."""
    from core import build_config, choice_gates
    era_spec = eras_mod.get_era(era)
    era_key = era_spec["key"]
    cfg = build_config.normalize(config)
    applied = build_config.derive(cfg)
    vault_ctx: dict[str, Any] = {"genre": genre, "base_grade": base_grade, "era": era_key,
                                 "config": cfg, "applied_choices": applied}
    regions = foundry._regions_for(vault_ctx)

    # Reset + log the game-level choices the agents stay aware of.
    if persist:
        game_choices.clear(build_id)
    game_choices.record(build_id, "setup", "game_setup", {
        "era": era_key, "era_label": era_spec["label"], "genre": genre,
        "seed": seed, "platoon_size": platoon_size, "base_grade": base_grade,
        "storage_cap_bytes": era_spec["storage_bytes"][1],
        "config": cfg, "applied_choices": applied,
    }, persist=persist)

    plan = planner.plan_build(build_id=build_id, phases=list(foundry.ITEM_STAGES),
                              seed=seed, platoon_size=platoon_size, game_ctx=vault_ctx)
    platoons = {n["phase_id"]: n["workers"] for n in plan["nodes"] if n["tier"] == "platoon"}

    title = vault_ctx.get("title") or f"{era_spec['label']} {genre.upper()}"
    gdd_lines = _gdd_header(title, genre, build_id)
    gdd_lines += [
        "## Era Envelope",
        "",
        f"- **Era:** {era_spec['label']} ({', '.join(era_spec['platforms'])})",
        f"- **Storage:** {era_spec['storage_label']} · **Colors:** {era_spec['color_label']} · "
        f"**Resolution:** {era_spec['resolution']}",
        f"- **Geometry:** {era_spec['poly_label']} · **Audio:** {era_spec['audio_format']}",
        f"- **Asset types this era:** {', '.join(era_spec['asset_types'])}",
        "",
    ]

    accepted_all: list[dict] = []
    assets_all: list[dict] = []
    stages_built: list[str] = []
    ladder: list[dict] = []
    universal_scenes: list[dict] = []  # per-scene universal asset forging
    parity_ok_every_step = True
    storage_used = 0
    storage_cap = era_spec["storage_bytes"][1]

    for idx, stage in enumerate(foundry.ITEM_STAGES):
        floor = _escalation_floor(base_grade, idx)
        # AWARENESS: parse all prior choices the agents must respect this step.
        awareness = game_choices.parse_context(build_id)
        vault_ctx["awareness"] = awareness
        forged, verdicts = [], []
        gdd_stage_set = set(stages_built) | {stage}
        stage_retries = 0
        for worker in platoons.get(stage, []):
            best_item, best_v = None, None
            # Quality control: retry / recall the forge until it clears the
            # 95 production bar, keeping the best attempt.
            for attempt in range(3):
                rseed = seed + attempt * 7919  # re-roll on recall
                item = foundry.forge_item(build_id, stage, worker, vault_ctx, rseed, floor)
                v = gates.evaluate(item, stage_index=idx, stage_floor_grade=floor,
                                   gdd_stages=gdd_stage_set, regions=regions, era=era_key)
                if best_v is None or v["production_score"] > best_v["production_score"]:
                    best_item, best_v = item, v
                if v["production_ready"]:
                    break
                stage_retries += 1
            best_item["quality"] = best_v
            best_item["forge_attempts"] = attempt + 1
            forged.append(best_item)
            verdicts.append(best_v)
        # Only PRODUCTION-READY (≥95 + all gates) gamefiles are folded in.
        accepted = [it for it in forged if it["quality"]["production_ready"]]
        accepted_all.extend(accepted)

        # 4: era-appropriate asset pack per accepted gamefile
        stage_assets: list[dict] = []
        for it in accepted:
            stage_assets.extend(asset_forge.forge_assets_for_item(it, seed, era_key))
        assets_all.extend(stage_assets)
        stage_bytes = sum(int(a["size_kb"]) * 1024 for a in stage_assets)
        storage_used += stage_bytes

        # PER-SCENE FORGING — agents forge universal assets for THIS scene,
        # correlated to what was built (more accepted gamefiles → more assets).
        # This starts at the FIRST scene (idx 0) and runs every scene after.
        if persist:
            try:
                from core import universal_forge as _uf
                _sc = _uf.seed_for_scene(build_id, era_key, stage,
                                         want=max(2, len(accepted) + 1),
                                         seed=seed + idx * 101, mount=True)
                universal_scenes.append({"stage": stage, "level": idx + 1,
                                         "assets": _sc.get("total", 0),
                                         "families": _sc.get("families", []),
                                         "planned": False})
            except Exception:
                universal_scenes.append({"stage": stage, "level": idx + 1, "assets": 0, "families": [], "planned": False})
        else:
            # Non-persistent (preview/compare) runs still report the per-scene
            # PLAN so callers can show the timeline without writing to the DB.
            try:
                from core import universal_forge as _uf
                cats = _uf.scene_families().get(stage, [])
                fams = sorted({_uf._CAT_BY_KEY[c]["family"] for c in cats if c in _uf._CAT_BY_KEY})
                universal_scenes.append({"stage": stage, "level": idx + 1,
                                         "assets": max(2, len(accepted) + 1),
                                         "families": fams, "planned": True})
            except Exception:
                universal_scenes.append({"stage": stage, "level": idx + 1, "assets": 0, "families": [], "planned": True})

        # 5: escalate the GDD (one new section)
        gdd_lines += _gdd_stage_section(idx + 1, stage, accepted, floor, list(stages_built))
        stages_built.append(stage)

        # 6: parity lock — #GDD stage sections must equal #gamefile stages built
        gdd_sections = sum(1 for ln in gdd_lines if ln.startswith("## Lv"))
        parity_ok = gdd_sections == len(stages_built)
        parity_ok_every_step = parity_ok_every_step and parity_ok

        qsum = gates.summarize(verdicts)
        # LOG this step's choices → the ledger the next steps parse.
        game_choices.record(build_id, f"stage:{stage}", "stage_forge", {
            "stage": stage, "level": idx + 1, "grade_floor": floor,
            "accepted": len(accepted), "rejected": len(forged) - len(accepted),
            "assets": len(stage_assets), "storage_bytes": stage_bytes,
            "era": era_key,
        }, persist=persist)

        ladder.append({
            "level": idx + 1,
            "stage": stage,
            "grade_floor": floor,
            "fidelity_floor": gates.fidelity_floor(idx),
            "forged": len(forged),
            "accepted": len(accepted),
            "rejected": len(forged) - len(accepted),
            "max_grade": max((it["grade"] for it in accepted), default=floor),
            "assets": len(stage_assets),
            "storage_bytes": stage_bytes,
            "retries": stage_retries,
            "production_ready": len(accepted) > 0,
            "storage_label": eras_mod.humanize_bytes(stage_bytes),
            "gdd_sections": gdd_sections,
            "parity_ok": parity_ok,
            "quality": qsum,
            "built_on": list(stages_built[:-1]),
        })

    gdd = "\n".join(gdd_lines)
    grades = [it["grade"] for it in accepted_all]
    escalating = all(ladder[i]["max_grade"] <= ladder[i + 1]["max_grade"]
                     for i in range(len(ladder) - 1)) if len(ladder) > 1 else True

    manifest = {
        "build_id": build_id,
        "seed": seed,
        "genre": genre,
        "era": era_key,
        "era_label": era_spec["label"],
        "era_spec": {k: era_spec[k] for k in (
            "platforms", "storage_label", "color_label", "resolution",
            "poly_label", "audio_format", "asset_types", "texture_res")},
        "title": title,
        "plan_hash": plan["plan_hash"],
        "stages": len(foundry.ITEM_STAGES),
        "ladder": ladder,
        "gdd": gdd,
        "gdd_chars": len(gdd),
        "gdd_sections": sum(1 for ln in gdd.splitlines() if ln.startswith("## Lv")),
        "parity_locked": parity_ok_every_step,
        "parity_pct": round(100 * sum(1 for r in ladder if r["parity_ok"]) / max(1, len(ladder))),
        "grade_escalating": escalating,
        "production_ready": all(r.get("production_ready") for r in ladder) and len(accepted_all) > 0,
        "total_retries": sum(r.get("retries", 0) for r in ladder),
        "avg_production_score": round(
            sum(r["quality"].get("avg_production_score", 0) for r in ladder) / max(1, len(ladder)), 1),
        "storage": {
            "used_bytes": storage_used,
            "used_label": eras_mod.humanize_bytes(storage_used),
            "cap_bytes": storage_cap,
            "cap_label": eras_mod.humanize_bytes(storage_cap),
            "used_pct": round(min(100.0, 100 * storage_used / max(1, storage_cap)), 2),
            "within_budget": storage_used <= storage_cap,
        },
        "balance_curve": [{"level": r["level"], "stage": r["stage"],
                           "grade_floor": r["grade_floor"], "max_grade": r["max_grade"]}
                          for r in ladder],
        "capacity": {
            "asset_capacity": era_spec["asset_capacity"],
            "usual_max_assets": era_spec["usual_max_assets"],
            "outshine_pct": era_spec["outshine_pct"],
            "assets_forged": len(assets_all),
            "utilization_pct": round(100 * len(assets_all) / max(1, era_spec["asset_capacity"]), 2),
        },
        "choices": game_choices.get_choices(build_id),
        "awareness": game_choices.parse_context(build_id),
        "config": build_config.summary(cfg),
        "applied_choices": applied,
        "choice_gates": choice_gates.build(cfg, accepted_all, assets_all),
        "universal_scenes": universal_scenes,
        "universal_assets_per_scene": sum(s.get("assets", 0) for s in universal_scenes),
        "totals": {
            "gamefiles": len(accepted_all),
            "assets": len(assets_all),
            "assets_per_item": len(era_spec["asset_types"]),
            "avg_grade": round(sum(grades) / max(1, len(grades)), 2),
            "min_grade": min(grades, default=0),
            "max_grade": max(grades, default=0),
            "quality_pass_rate": round(
                sum(r["quality"]["accepted"] for r in ladder)
                / max(1, sum(r["quality"]["count"] for r in ladder)), 3),
        },
        "created_at": time.time(),
    }

    if persist:
        try:
            from core.databases import get_sync_db
            db = get_sync_db()
            # gamefiles
            col = db["galaxy_build_items"]
            col.create_index([("build_id", 1), ("stage", 1)])
            for it in accepted_all:
                col.update_one({"build_id": build_id, "item_id": it["item_id"]},
                               {"$set": {**it, "build_id": build_id}}, upsert=True)
            # assets
            asset_forge.forge_build_assets(build_id, accepted_all, seed,
                                           persist=True, era=era_key)
            # ── Construct Forge + Material Forge (runs AFTER the phase ladder) ──
            # Mint a batch of era-correct large constructs + surface materials
            # and mount them onto the build's gamefiles (Vault connection), so
            # the final build ships buildings/cities/castles + materials too.
            try:
                from core import construct_forge as _cforge
                _cf = _cforge.forge_for_build(
                    build_id, era=era_key, seed=seed,
                    construct_count=24, material_count=24,
                    config=cfg, mount=True, seed_universal=False)
                manifest["constructs"] = {
                    "constructs": _cf["constructs"], "materials": _cf["materials"],
                    "mounted": _cf["mounted"],
                    "presets_available": _cf["presets_available"],
                }
            except Exception:
                manifest["constructs"] = {"constructs": 0, "materials": 0}
            # escalating GDD + parity mount (era + storage aware)
            db["galaxy_vault_mounts"].update_one(
                {"build_id": build_id},
                {"$set": {"build_id": build_id, "seed": seed, "title": title,
                          "genre": genre, "era": era_key, "era_label": era_spec["label"],
                          "gdd": gdd, "gdd_chars": len(gdd),
                          "escalation": {"ladder": ladder,
                                         "parity_locked": parity_ok_every_step,
                                         "parity_pct": manifest["parity_pct"],
                                         "grade_escalating": escalating,
                                         "era": era_key,
                                         "storage": manifest["storage"],
                                         "balance_curve": manifest["balance_curve"]},
                          "vault_gamefiles": len(accepted_all),
                          "total_assets": len(assets_all),
                          "coverage_pct": round(100 * len(stages_built) / len(foundry.ITEM_STAGES)),
                          "mounted_at": time.time()}}, upsert=True)
        except Exception:
            pass

    return manifest


def era_ladder(build_id: str, era_a: str, era_b: str, genre: str = "rpg",
               seed: int = 0) -> dict:
    """NEXT IMPROVEMENT — re-forge the SAME game across two eras and diff the
    asset counts / storage / capacity so the asset-growth story is visible.
    Non-persisting (comparison only)."""
    a = escalate(f"{build_id}__a", genre=genre, seed=seed, era=era_a, persist=False)
    b = escalate(f"{build_id}__b", genre=genre, seed=seed, era=era_b, persist=False)

    def _row(m: dict) -> dict:
        return {
            "era": m["era"], "era_label": m["era_label"],
            "assets": m["totals"]["assets"], "assets_per_item": m["totals"]["assets_per_item"],
            "gamefiles": m["totals"]["gamefiles"],
            "storage_used": m["storage"]["used_label"], "storage_bytes": m["storage"]["used_bytes"],
            "storage_cap": m["storage"]["cap_label"],
            "asset_capacity": m["capacity"]["asset_capacity"],
        }

    ra, rb = _row(a), _row(b)
    asset_x = round(rb["assets"] / max(1, ra["assets"]), 2)
    storage_x = round(rb["storage_bytes"] / max(1, ra["storage_bytes"]), 2)
    cap_growth_pct = round(100 * (rb["asset_capacity"] - ra["asset_capacity"])
                           / max(1, ra["asset_capacity"]))
    return {
        "build_id": build_id, "genre": genre, "seed": seed,
        "a": ra, "b": rb,
        "asset_multiplier": asset_x,
        "storage_multiplier": storage_x,
        "capacity_growth_pct": cap_growth_pct,
        "headline": f"{rb['era_label']} forges {asset_x}× the assets and "
                    f"{storage_x}× the storage of {ra['era_label']}.",
    }
