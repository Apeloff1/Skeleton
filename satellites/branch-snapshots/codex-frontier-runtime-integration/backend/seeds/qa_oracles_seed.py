"""
Quality-Assurance Oracles knowledge base.

Collection: `qa_oracles`

Property-based, invariant, and behavioural test ORACLES the agent can
instantiate against any generated game. Each oracle defines:
  • invariant_name + free-form description
  • applicable_genres / engines
  • check_kind (smoke / property / behaviour / load / soak / fuzz / regression)
  • pseudo-code assertion
  • severity (warn / error / blocker)
  • suggested fix when it fails

Generates ~1500 oracles via (invariant × genre).
"""
from __future__ import annotations
import hashlib, logging, itertools
from datetime import datetime, timezone

log = logging.getLogger("knowledge.qa_oracles")

INVARIANTS = [
    ("player-hp-non-negative",        "smoke",       "blocker",  "assert player.hp >= 0",                                                "clamp hp to 0 floor"),
    ("player-hp-leq-max",             "smoke",       "error",    "assert player.hp <= player.maxHp",                                     "clamp hp at maxHp"),
    ("xp-monotone",                   "property",    "error",    "forall t: xp(t+1) >= xp(t)",                                            "prevent xp loss except on death-penalty path"),
    ("save-load-roundtrip",           "property",    "blocker",  "save(state) then load() == state (modulo timestamps)",                  "normalize datetimes + floats before compare"),
    ("deterministic-physics",         "property",    "error",    "replay(input_log) yields identical final state",                       "fix accumulator drift / non-deterministic RNG seeds"),
    ("no-orphan-entities",            "property",    "error",    "every entity has a parent scene OR is in pool",                         "sweep unparented entities in ECS at frame end"),
    ("frame-time-under-budget",       "behaviour",   "error",    "P95(frame_ms) <= 16.67 at target_fps=60",                               "profile + cull hot paths"),
    ("memory-no-leak-1hr",            "soak",        "error",    "working_set_growth(60min) < 50MB",                                      "verify pool returns + listener cleanup"),
    ("network-bandwidth-bound",       "behaviour",   "warn",     "avg_bytes/sec/client < 64 KB during match",                             "delta-compress entity sync"),
    ("input-latency-bound",           "behaviour",   "error",    "input_to_render_ms < 33",                                               "reduce buffer; use predict+reconcile"),
    ("inventory-no-dup-stack",        "property",    "error",    "stackable items collapse to single stack per cell",                     "merge stacks on insert"),
    ("economy-no-arb",                "property",    "warn",     "buy(a)->sell(a) <= 0 net per cycle",                                    "adjust shop spread"),
    ("quest-no-deadlock",             "behaviour",   "blocker",  "every quest has a reachable terminal stage",                            "add fallback dialogue path"),
    ("dialogue-no-empty-line",        "smoke",       "warn",     "no NPC line is empty string",                                           "strip + fallback to '...'" ),
    ("asset-references-valid",        "smoke",       "error",    "every asset_id referenced exists in asset registry",                    "build asset manifest check"),
    ("localization-coverage",         "behaviour",   "warn",     "every key has translation in primary locale",                           "flag untranslated keys CI gate"),
    ("crash-on-corrupt-save",         "fuzz",        "error",    "corrupting random byte does NOT crash loader",                          "wrap loader in try/except + return new-game fallback"),
    ("matchmaking-fair",              "behaviour",   "warn",     "avg_skill_delta(match) <= 200 mmr",                                     "tighten mmr bucket"),
    ("server-tickrate-stable",        "load",        "error",    "std(server_tick_ms) over 5 min < 1.5",                                  "profile + isolate noisy systems"),
    ("ecs-no-component-leak",         "property",    "error",    "entity destroy removes ALL components",                                 "ensure destroy hook iterates all archetypes"),
    ("physics-no-tunneling",          "property",    "error",    "fast bodies never overlap > shape.radius after step",                    "enable CCD on fast bodies"),
    ("audio-no-clip",                 "behaviour",   "warn",     "output sample peak <= -1 dBFS",                                         "apply limiter on master bus"),
    ("ui-no-overlap-mobile",          "behaviour",   "error",    "no two clickable UI rects overlap at 360x640",                          "refit safe-area + bottom inset"),
    ("random-no-bias",                "property",    "warn",     "chi-squared(N=1e5 rolls) p>0.01",                                       "replace seed/RNG — use xoshiro256**"),
    ("animation-no-tposeb-on-spawn",  "behaviour",   "error",    "first-frame mesh != bind-pose for animated chars",                      "force LateUpdate animator before render frame 1"),
    ("shader-compiles-on-target",     "smoke",       "blocker",  "all shaders compile on min-spec GPU",                                   "add fallback shader variants"),
    ("loot-table-sums-to-1",          "smoke",       "error",    "sum(weights) - 1.0 < 1e-6 per table",                                   "normalize at load"),
    ("ladder-no-cheese",              "behaviour",   "warn",     "no single strategy > 65% winrate at top elo",                           "propose balance pass"),
    ("loading-screen-time",           "behaviour",   "warn",     "P90(level_load_ms) < 6000",                                             "preload assets + texture streaming"),
    ("controller-rumble-bounded",     "behaviour",   "warn",     "rumble does not run > 1.5 s continuously",                              "clamp rumble durations"),
]

GENRES = ["rpg","fps","moba","arpg","rts","survival","mmo","roguelike","platformer","sandbox","sim","racing","fighter","horror","strategy","4x","gacha","ccg","co-op","extraction"]


def _oid(name, genre): return "oracle_" + hashlib.md5(f"{name}|{genre}".encode()).hexdigest()[:14]


def build_qa_oracles() -> list[dict]:
    out = []
    for (name, kind, severity, assertion, fix), genre in itertools.product(INVARIANTS, GENRES):
        out.append({
            "id": _oid(name, genre),
            "invariant_name": name,
            "genre": genre,
            "kind": kind,
            "severity": severity,
            "assertion": assertion,
            "fix_hint": fix,
            "description": f"{name} oracle for {genre} games — a {kind}-class {severity}.",
            "tags": [name, kind, severity, genre, "oracle", "qa"],
        })
    return out


async def seed_qa_oracles(db) -> dict:
    docs = build_qa_oracles()
    try:
        await db.qa_oracles.create_index("id", unique=True)
        await db.qa_oracles.create_index("invariant_name")
        await db.qa_oracles.create_index("genre")
        await db.qa_oracles.create_index("kind")
        await db.qa_oracles.create_index("severity")
        await db.qa_oracles.create_index([("tags", 1)])
    except Exception:
        pass
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    for d in docs:
        d["indexed_at"] = now
        try:
            r = await db.qa_oracles.update_one({"id": d["id"]}, {"$set": d}, upsert=True)
            if r.upserted_id is not None: inserted += 1
        except Exception: pass
    total = await db.qa_oracles.count_documents({})
    log.info(f"[qa_oracles] inserted={inserted} total={total}")
    return {"inserted": inserted, "total": total, "combinations": len(docs)}
