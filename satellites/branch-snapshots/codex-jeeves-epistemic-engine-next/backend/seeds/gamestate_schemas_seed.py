"""
Game-state & persistence schema knowledge base.

Collection: `gamestate_schemas`

For every common save-system shape we record:
  • the WIRE format (JSON / SQLite / protobuf / msgpack / yaml),
  • the schema TREE (top-level keys + nested types),
  • versioning + migration recipe,
  • sample minimal snapshot,
  • anti-cheat / integrity hint.
— cross-product engine × genre × persistence-kind → ~600 schemas.
"""
from __future__ import annotations
import hashlib, logging, itertools
from datetime import datetime, timezone

log = logging.getLogger("knowledge.gamestate")

ENGINES = ["Unity", "Unreal", "Godot", "Bevy", "Phaser", "Three.js", "LÖVE", "Pygame", "GameMaker", "Cocos"]
GENRES  = ["rpg", "fps", "moba", "arpg", "rts", "survival", "mmo", "roguelike", "platformer", "sandbox", "sim", "racing", "fighter", "horror", "strategy"]
KINDS   = ["snapshot-json", "snapshot-binary", "event-sourced", "sqlite-wal", "protobuf", "msgpack", "yaml"]

WIRE_FORMATS = {
    "snapshot-json":   {"ext": "json", "mime": "application/json", "compression": "gzip"},
    "snapshot-binary": {"ext": "sav",  "mime": "application/octet-stream", "compression": "zstd"},
    "event-sourced":   {"ext": "log",  "mime": "application/x-ndjson", "compression": "lz4"},
    "sqlite-wal":      {"ext": "db",   "mime": "application/x-sqlite3", "compression": "none"},
    "protobuf":        {"ext": "pb",   "mime": "application/x-protobuf", "compression": "none"},
    "msgpack":         {"ext": "msgpk","mime": "application/msgpack", "compression": "zstd"},
    "yaml":            {"ext": "yaml", "mime": "application/x-yaml", "compression": "none"},
}

BASE_TREE = {
    "version": "int (schema version)",
    "saved_at": "isoformat utc",
    "player": {
        "id": "uuid",
        "name": "str",
        "level": "int",
        "xp": "int",
        "stats": {"hp": "int", "mp": "int", "stam": "int"},
        "position": {"x": "f32", "y": "f32", "z": "f32"},
        "inventory": "list[{item_id, qty, slot}]",
        "equipped": "dict[slot:item_id]",
        "quests": "list[{quest_id, stage, flags}]",
        "unlocks": "set[flag]",
    },
    "world": {
        "seed": "u64",
        "day": "int",
        "time_of_day": "f32",
        "weather": "enum",
        "discovered_regions": "list[region_id]",
        "npcs": "dict[npc_id:{hp, position, schedule_idx, mood}]",
        "loot_drops": "list[{id, pos, items}]",
    },
    "meta": {
        "playtime_seconds": "int",
        "achievements": "set[ach_id]",
        "settings": "dict",
    },
}

MIGRATION_HINT = (
    "On load: read `version` first. If older than current, run migrators[old..current] in order. "
    "Each migrator: takes dict in, returns dict + new version. Never overwrite original until migrate + verify succeed."
)

INTEGRITY_HINT = (
    "Compute HMAC-SHA256(payload, server_secret) and store alongside. On load, recompute and reject mismatch. "
    "For client-only saves, switch to CRC32 to detect corruption, not tamper."
)


def _gid(*p): return "gss_" + hashlib.md5("|".join(p).encode()).hexdigest()[:14]


def build_gamestate_schemas() -> list[dict]:
    out = []
    for engine, genre, kind in itertools.product(ENGINES, GENRES, KINDS):
        wire = WIRE_FORMATS[kind]
        out.append({
            "id": _gid(engine, genre, kind),
            "engine": engine,
            "genre": genre,
            "kind": kind,
            "wire": wire,
            "tree": BASE_TREE,
            "sample_minimum": {
                "version": 1,
                "saved_at": "2026-01-01T00:00:00Z",
                "player": {"id": "<uuid>", "name": "Hero", "level": 1, "xp": 0,
                            "stats": {"hp": 100, "mp": 50, "stam": 100},
                            "position": {"x": 0, "y": 0, "z": 0},
                            "inventory": [], "equipped": {}, "quests": [], "unlocks": []},
                "world": {"seed": 1234, "day": 1, "time_of_day": 0.0, "weather": "clear",
                           "discovered_regions": [], "npcs": {}, "loot_drops": []},
                "meta": {"playtime_seconds": 0, "achievements": [], "settings": {}},
            },
            "migration_hint": MIGRATION_HINT,
            "integrity_hint": INTEGRITY_HINT,
            "tags": [engine.lower(), genre, kind, "gamestate", "persistence"],
        })
    return out


async def seed_gamestate_schemas(db) -> dict:
    docs = build_gamestate_schemas()
    try:
        await db.gamestate_schemas.create_index("id", unique=True)
        await db.gamestate_schemas.create_index("engine")
        await db.gamestate_schemas.create_index("genre")
        await db.gamestate_schemas.create_index("kind")
        await db.gamestate_schemas.create_index([("tags", 1)])
    except Exception:
        pass
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    for d in docs:
        d["indexed_at"] = now
        try:
            r = await db.gamestate_schemas.update_one({"id": d["id"]}, {"$set": d}, upsert=True)
            if r.upserted_id is not None: inserted += 1
        except Exception: pass
    total = await db.gamestate_schemas.count_documents({})
    log.info(f"[gamestate_schemas] inserted={inserted} total={total}")
    return {"inserted": inserted, "total": total, "combinations": len(docs)}
