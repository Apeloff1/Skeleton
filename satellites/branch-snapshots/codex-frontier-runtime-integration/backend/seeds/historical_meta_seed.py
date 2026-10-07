"""
Historical Meta & Nostalgia Frameworks.
Collection: `historical_meta`
"""
import hashlib, logging, itertools
from datetime import datetime, timezone

ERAS = [
    ("arcade-golden",   1972, 1985, ["Pong","Space Invaders","Pac-Man","Donkey Kong","Galaga"], ["CRT scanlines","side-scroll arcade","hi-score chase","limited palette"]),
    ("home-8bit",        1983, 1989, ["Super Mario Bros","Zelda","Mega Man","Castlevania"],    ["NES palette","chiptune sound","linear levels","password saves"]),
    ("16bit-mascot",     1989, 1995, ["Sonic","Donkey Kong Country","Earthworm Jim"],          ["parallax","Mode 7","FM synth","sprite scaling"]),
    ("early-3d",         1995, 2000, ["Mario 64","Quake","Tomb Raider","Crash"],               ["low-poly","PS1 vertex wobble","fixed cameras","texture warping"]),
    ("y2k-shooter",      2000, 2007, ["Halo","Half-Life 2","Doom 3","Far Cry"],                 ["normal maps","bloom + lens flare","crouch button","limited weapons"]),
    ("hd-cinematic",     2007, 2013, ["Uncharted","Mass Effect","GTA IV","Skyrim"],             ["motion capture","set-piece","regenerating health","quick-time events"]),
    ("indie-renaissance",2008, 2018, ["Braid","Limbo","Hollow Knight","Celeste","Stardew"],     ["pixel-art","narrative-driven","one-author","music-led mood"]),
    ("live-service",     2014, 2024, ["Fortnite","Destiny 2","Genshin","Apex"],                 ["battle-pass","seasons","crossplay","in-game shops"]),
    ("cloud-streaming",  2019, 2026, ["GeForce Now","xCloud","Stadia (rip)","Luna"],            ["no install","60+ FPS streaming","controller-on-mobile","server-side render"]),
    ("AI-generative",    2023, 2026, ["AI Dungeon","Inworld NPCs","Roblox AI"],                 ["runtime LLM dialogue","procedural quests","infinite worlds"]),
]

NOSTALGIA_FILTERS = [
    ("crt-scanlines",     {"shader":"crt-easymode","strength":0.6}),
    ("vhs-grain",         {"strength":0.35,"chromatic":True,"jitter":0.04}),
    ("chiptune-music",    {"sound_chip":"NES-2A03"}),
    ("low-poly-style",    {"poly_budget":1024,"vertex_snap":True}),
    ("pixel-grid",        {"target_res":320,"scale":"nearest"}),
    ("film-grain",        {"strength":0.15,"animated":True}),
    ("sepia-tone",        {"saturation":0.0,"tint_r":1.0,"tint_g":0.85,"tint_b":0.6}),
    ("polaroid-frame",    {"frame_width_px":24}),
]

def _hid(*p): return "hist_" + hashlib.md5("|".join(p).encode()).hexdigest()[:14]

def build_historical_meta():
    out = []
    for era, start, end, games, conventions in ERAS:
        out.append({"id":_hid(era,"era"),"category":"era","era":era,"start_year":start,"end_year":end,
                    "signature_games":games,"design_conventions":conventions,
                    "description":f"{era}: {start}-{end}. Conventions: {', '.join(conventions[:3])}.",
                    "tags":[era,"era","history","nostalgia"]})
    for name, params in NOSTALGIA_FILTERS:
        out.append({"id":_hid(name,"filter"),"category":"nostalgia-filter","filter_name":name,"params":params,
                    "description":f"Nostalgia filter: {name}","tags":[name,"filter","nostalgia"]})
    return out

async def seed_historical_meta(db):
    docs = build_historical_meta()
    try:
        await db.historical_meta.create_index("id", unique=True)
        await db.historical_meta.create_index("category")
        await db.historical_meta.create_index("era")
        await db.historical_meta.create_index([("tags", 1)])
    except Exception: pass
    now = datetime.now(timezone.utc).isoformat(); inserted = 0
    for d in docs:
        d["indexed_at"] = now
        try:
            r = await db.historical_meta.update_one({"id":d["id"]},{"$set":d},upsert=True)
            if r.upserted_id is not None: inserted += 1
        except Exception: pass
    return {"inserted": inserted, "total": await db.historical_meta.count_documents({})}
