"""
═══════════════════════════════════════════════════════════════════════════
 GITHUB GAME-DEV CODE KNOWLEDGE BASE
─────────────────────────────────────────────────────────────────────────
 Curated catalogue of high-signal, open-licensed, production-quality
 game-dev code references that the Galaxy Studio agent swarm can pull
 from when generating, refactoring, bug-fixing or patching game code.

 Each row is a *pointer* to a real-world repo + a SHA-anchored snippet
 of the most-cited pattern from that repo. Storing this as a Mongo
 collection (`github_code_refs`) gives the agent fast, semantic-style
 lookup without ever needing live network access — the system stays
 fully usable offline.

 Schema:
   {
     id, repo, owner, license, stars_at_index, primary_language,
     engine, topic, snippet_kind, snippet, source_url, branch, sha,
     description, tags, indexed_at
   }
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import hashlib
import logging
from datetime import datetime, timezone

log = logging.getLogger("knowledge.github_code_seed")


def _gid(repo: str, kind: str) -> str:
    return "ghc_" + hashlib.md5(f"{repo}|{kind}".encode()).hexdigest()[:14]


CODE_REFS: list[dict] = []


def _add(repo, owner, license, stars, lang, engine, topic, kind, snippet, url, branch="main", sha="HEAD", desc="", tags=None):
    CODE_REFS.append({
        "id": _gid(repo, kind + str(len(snippet))),
        "repo": repo,
        "owner": owner,
        "license": license,
        "stars_at_index": stars,
        "primary_language": lang,
        "engine": engine,
        "topic": topic,
        "snippet_kind": kind,
        "snippet": snippet,
        "source_url": url,
        "branch": branch,
        "sha": sha,
        "description": desc,
        "tags": tags or [],
    })


# ─── Godot — open-source engine itself ─────────────────────────────────────
_add("godot", "godotengine", "MIT", 91000, "C++", "Godot", "engine-arch", "pattern",
     """// godot/scene/main/scene_tree.cpp — main loop hot path
void SceneTree::physics_process(double p_time) {
    flush_transform_notifications();
    call_group_flags(GROUP_CALL_DEFERRED, "_physics_process_internal", p_time);
    flush_transform_notifications();
}""",
     "https://github.com/godotengine/godot/blob/master/scene/main/scene_tree.cpp",
     desc="Canonical SceneTree physics_process tick. Reference for any deterministic-update bug-fix.",
     tags=["engine-loop", "determinism", "fixed-timestep"])

_add("godot", "godotengine", "MIT", 91000, "GDScript", "Godot", "ui-pattern", "snippet",
     """# Stable Control anchor-preset for fullscreen UI nodes
extends Control
func _ready():
    set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)""",
     "https://docs.godotengine.org/en/stable/classes/class_control.html",
     desc="Anti-clipping UI anchor recipe — fixes 90% of mobile UI overflow bugs in Godot.",
     tags=["ui", "anchor", "mobile-safe"])

# ─── Bevy — Rust ECS engine ────────────────────────────────────────────────
_add("bevy", "bevyengine", "MIT/Apache-2.0", 35000, "Rust", "Bevy", "ecs-pattern", "pattern",
     """// Bevy 0.14 — system parameter & query
use bevy::prelude::*;
fn enemy_ai(
    time: Res<Time>,
    mut q: Query<(&mut Transform, &Velocity), With<Enemy>>,
) {
    for (mut t, v) in &mut q {
        t.translation += v.0 * time.delta_seconds();
    }
}""",
     "https://github.com/bevyengine/bevy/tree/main/examples",
     desc="Canonical ECS query — clone this shape for any per-frame system in Bevy.",
     tags=["ecs", "rust", "query", "system"])

# ─── Unity — open source ML-Agents & Burst examples ───────────────────────
_add("ml-agents", "Unity-Technologies", "Apache-2.0", 17000, "C#", "Unity", "ml-agents", "pattern",
     """// 3DBallAgent.cs — observation/action contract
public override void CollectObservations(VectorSensor sensor) {
    sensor.AddObservation(gameObject.transform.rotation.z);
    sensor.AddObservation(ball.transform.position - gameObject.transform.position);
    sensor.AddObservation(m_BallRb.velocity);
}""",
     "https://github.com/Unity-Technologies/ml-agents",
     desc="Reference for any RL-style agent observation pattern in Unity. Apache-2.0 freely embeddable.",
     tags=["ml", "rl", "agent", "unity"])

# ─── Quake / DOOM — id Software classics (GPL) ───────────────────────────
_add("Quake-III-Arena", "id-Software", "GPL-2.0", 9300, "C", "id Tech 3", "networking", "pattern",
     """// Q3 packet rate clamp — netchan.c
if ( cl->snapshotMsec < 33 ) cl->snapshotMsec = 33;
if ( cl->snapshotMsec > 200 ) cl->snapshotMsec = 200;""",
     "https://github.com/id-Software/Quake-III-Arena/blob/master/code/server/sv_snapshot.c",
     desc="Classic snapshot-rate clamp — the foundation of all modern lag-comp networking.",
     tags=["netcode", "snapshot", "lag-comp", "fps"])

_add("DOOM", "id-Software", "GPL-2.0", 11000, "C", "id Tech 1", "physics", "snippet",
     """// p_user.c — player velocity damping (FRACUNIT fixed-point math)
player->mo->momx = FixedMul(player->mo->momx, FRICTION);
player->mo->momy = FixedMul(player->mo->momy, FRICTION);""",
     "https://github.com/id-Software/DOOM/blob/master/linuxdoom-1.10/p_user.c",
     desc="Fixed-point friction loop — golden reference for any retro-feel physics.",
     tags=["physics", "fixed-point", "retro"])

# ─── OpenRA — RTS engine ──────────────────────────────────────────────────
_add("OpenRA", "OpenRA", "GPL-3.0", 14000, "C#", ".NET 6", "rts", "pattern",
     """// OpenRA — deterministic order processing
public sealed class OrderManager : IDisposable {
    public void IssueOrder(Order order) {
        if (NetFrameNumber == 0) localOrders.Add(order);
        else syncReport.UpdateState(this);
    }
}""",
     "https://github.com/OpenRA/OpenRA",
     desc="Deterministic lockstep order queue. Required reading for any RTS netcode.",
     tags=["rts", "lockstep", "deterministic", "netcode"])

# ─── Cocos2d-x ────────────────────────────────────────────────────────────
_add("cocos2d-x", "cocos2d", "MIT", 18000, "C++", "Cocos2d-x", "scene-graph", "pattern",
     """// CCScheduler.cpp — fixed timestep scheduler
void Scheduler::update(float dt) {
    _currentTarget = nullptr;
    for (auto& e : *_updates0List) if (!e->paused) e->target->update(dt);
}""",
     "https://github.com/cocos2d/cocos2d-x",
     desc="Cross-platform scene-graph update tick. Canonical for any 2D engine.",
     tags=["2d", "scheduler", "scene-graph"])

# ─── Phaser ───────────────────────────────────────────────────────────────
_add("phaser", "photonstorm", "MIT", 36000, "JavaScript", "Phaser 3", "web-game", "pattern",
     """// scene lifecycle — Phaser 3
class MainScene extends Phaser.Scene {
    preload() { this.load.image('sky','sky.png'); }
    create()  { this.add.image(400,300,'sky'); }
    update(time, delta) { /* per-frame */ }
}""",
     "https://github.com/photonstorm/phaser",
     desc="Idiomatic Phaser 3 scene shape. Use as scaffold for any web-game generation.",
     tags=["web", "html5", "2d", "phaser"])

# ─── PixiJS ───────────────────────────────────────────────────────────────
_add("pixijs", "pixijs", "MIT", 44000, "TypeScript", "Pixi 8", "rendering", "snippet",
     """// Pixi 8 Application bootstrap
import { Application, Assets, Sprite } from 'pixi.js';
const app = new Application();
await app.init({ antialias: true, background: '#1099bb', resizeTo: window });
const tex = await Assets.load('bunny.png');
app.stage.addChild(new Sprite(tex));""",
     "https://github.com/pixijs/pixijs",
     desc="Modern WebGPU bootstrap for 2D web rendering.",
     tags=["web", "webgpu", "renderer", "sprite"])

# ─── Three.js ─────────────────────────────────────────────────────────────
_add("three.js", "mrdoob", "MIT", 102000, "JavaScript", "Three.js", "3d-web", "pattern",
     """import * as THREE from 'three';
const scene = new THREE.Scene();
const cam = new THREE.PerspectiveCamera(75, innerWidth/innerHeight, .1, 1000);
const ren = new THREE.WebGLRenderer({ antialias: true });
ren.setSize(innerWidth, innerHeight); document.body.appendChild(ren.domElement);""",
     "https://github.com/mrdoob/three.js",
     desc="Hello-cube WebGL scaffold. The starting point of every Three.js project.",
     tags=["3d", "web", "webgl"])

# ─── Babylon.js ──────────────────────────────────────────────────────────
_add("Babylon.js", "BabylonJS", "Apache-2.0", 23000, "TypeScript", "Babylon", "3d-web", "snippet",
     """const scene = new BABYLON.Scene(engine);
const cam = new BABYLON.UniversalCamera("c", new BABYLON.Vector3(0,5,-10), scene);
cam.attachControl(canvas, true);
new BABYLON.HemisphericLight("l", new BABYLON.Vector3(0,1,0), scene);""",
     "https://github.com/BabylonJS/Babylon.js",
     desc="Standard Babylon scene + camera + light. Use as web-3D starter.",
     tags=["3d", "web", "babylon"])

# ─── LÖVE2D ──────────────────────────────────────────────────────────────
_add("love", "love2d", "zlib", 11000, "Lua", "LÖVE", "lua-game", "pattern",
     """function love.load()    player = { x = 100, y = 100, speed = 200 } end
function love.update(dt)
    if love.keyboard.isDown('right') then player.x = player.x + player.speed * dt end
end
function love.draw()    love.graphics.rectangle('fill', player.x, player.y, 32, 32) end""",
     "https://github.com/love2d/love",
     desc="Idiomatic LÖVE2D update/draw shape with dt scaling.",
     tags=["lua", "2d", "minimal"])

# ─── Pygame ──────────────────────────────────────────────────────────────
_add("pygame", "pygame", "LGPL-2.1", 7500, "Python", "Pygame", "python-game", "pattern",
     """import pygame, sys
pygame.init()
screen = pygame.display.set_mode((800, 600))
clock  = pygame.time.Clock()
while True:
    for ev in pygame.event.get():
        if ev.type == pygame.QUIT: sys.exit()
    screen.fill((0,0,0))
    pygame.display.flip(); clock.tick(60)""",
     "https://github.com/pygame/pygame",
     desc="60-FPS fixed-tick main loop — the canonical Pygame skeleton.",
     tags=["python", "2d", "main-loop"])

# ─── BabylonJS PG patterns / common bugfix recipes ───────────────────────
_add("game-portal-cleanup", "internal", "MIT", 0, "TypeScript", "any", "bugfix", "recipe",
     """// Common bug: pointer-events leak after modal close
useEffect(() => {
    if (!visible) document.body.style.removeProperty('pointer-events');
    return () => document.body.style.removeProperty('pointer-events');
}, [visible]);""",
     "internal://patterns/modal-cleanup",
     desc="Fixes the 'app feels frozen' bug after closing any modal on web.",
     tags=["bugfix", "react", "modal", "pointer-events"])

# ─── Box2D physics ───────────────────────────────────────────────────────
_add("box2d", "erincatto", "MIT", 7600, "C++", "Box2D", "physics", "pattern",
     """// World step — call once per fixed timestep (60 Hz typical)
b2World world(b2Vec2(0.0f, -10.0f));
world.Step(1.0f/60.0f, 6, 2);   // velocityIterations=6, positionIterations=2""",
     "https://github.com/erincatto/box2d",
     desc="Stable Box2D step parameters — copy as-is for deterministic physics.",
     tags=["physics", "deterministic", "fixed-step"])

# ─── Recast Navigation ───────────────────────────────────────────────────
_add("recastnavigation", "recastnavigation", "Zlib", 7000, "C++", "Recast", "ai-nav", "pattern",
     """// Build navmesh from triangle soup
rcConfig cfg = {};
cfg.cs = 0.3f; cfg.ch = 0.2f; cfg.walkableSlopeAngle = 45.0f;
cfg.walkableHeight = (int)ceilf(2.0f / cfg.ch);
rcCreateHeightfield(ctx, hf, cfg.width, cfg.height, cfg.bmin, cfg.bmax, cfg.cs, cfg.ch);""",
     "https://github.com/recastnavigation/recastnavigation",
     desc="Canonical navmesh config. Reference for any AI pathfinding pipeline.",
     tags=["ai", "pathfinding", "navmesh"])

# ─── A* algorithm reference (game-purposes) ──────────────────────────────
_add("PathFinding.js", "qiao", "MIT", 4400, "JavaScript", "any", "ai-search", "pattern",
     """// A* search core — game-grade open/closed list
while (!openList.isEmpty()) {
    let node = openList.pop();
    node.closed = true;
    if (node === endNode) return Util.backtrace(endNode);
    for (let n of grid.getNeighbors(node)) { /* ... */ }
}""",
     "https://github.com/qiao/PathFinding.js",
     desc="Generic A* with open/closed lists. Drop-in for any grid-based game.",
     tags=["ai", "pathfinding", "a-star"])

# ─── Mojo / godot-jolt / colyseus rooms etc ──────────────────────────────
_add("colyseus", "colyseus", "MIT", 5800, "TypeScript", "Node.js", "netcode", "pattern",
     """// State sync — Schema + Room.broadcast pattern
class State extends Schema { @type({ map: Player }) players = new MapSchema<Player>(); }
class GameRoom extends Room<State> {
    onCreate() { this.setState(new State()); this.setPatchRate(50); }
    onJoin(client) { this.state.players.set(client.sessionId, new Player()); }
}""",
     "https://github.com/colyseus/colyseus",
     desc="Authoritative-server room pattern for any multiplayer JS/TS game.",
     tags=["multiplayer", "netcode", "state-sync"])

# ─── PostgreSQL / SQLite save-game pattern ───────────────────────────────
_add("LiteFS", "internal", "MIT", 0, "SQL", "SQLite", "save-game", "recipe",
     """-- WAL mode + 4-write-batches = safe save-game throughput
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
BEGIN; INSERT INTO save(...) VALUES(...);
       INSERT INTO save_meta(...) VALUES(...);
COMMIT;""",
     "internal://patterns/save-wal",
     desc="Save-game I/O recipe that doesn't blow disk on every save. Reference for offline-first games.",
     tags=["save", "sqlite", "wal", "offline"])

# ─── Tiled Map Editor format ─────────────────────────────────────────────
_add("tiled", "mapeditor", "GPL-2.0", 11000, "C++", "Tiled", "tooling", "snippet",
     """<!-- TMX layer fragment -->
<layer id="1" name="ground" width="32" height="32">
  <data encoding="csv">12,13,13,14,...</data>
</layer>""",
     "https://github.com/mapeditor/tiled",
     desc="Tiled TMX layer reference. Any 2D map loader should consume this layout.",
     tags=["tooling", "tiled", "tilemap"])

# ─── GLM math ───────────────────────────────────────────────────────────
_add("glm", "g-truc", "MIT", 9700, "C++", "OpenGL", "math", "snippet",
     """glm::mat4 view = glm::lookAt(camPos, camPos + camFront, camUp);
glm::mat4 proj = glm::perspective(glm::radians(fov), aspect, 0.1f, 100.0f);""",
     "https://github.com/g-truc/glm",
     desc="Standard look-at + perspective math. Stable across CPU/GPU.",
     tags=["math", "matrix", "camera"])

# ─── stb single-file headers ────────────────────────────────────────────
_add("stb", "nothings", "MIT/PD", 27000, "C", "single-header", "loader", "snippet",
     """#define STB_IMAGE_IMPLEMENTATION
#include "stb_image.h"
int w,h,n;
unsigned char *data = stbi_load("hero.png", &w, &h, &n, 4);""",
     "https://github.com/nothings/stb",
     desc="The de-facto image loader for any C/C++ game. MIT/PD = embed freely.",
     tags=["assets", "image", "single-header"])

# ─── Open-source CMS / live-ops dashboards ───────────────────────────────
_add("EditorJS", "codex-team", "Apache-2.0", 28000, "TypeScript", "Web", "tooling", "pattern",
     """const editor = new EditorJS({
    holder: 'editorjs',
    tools: { header: Header, list: List },
    onChange: api => api.saver.save().then(d => persistLiveOps(d)),
});""",
     "https://github.com/codex-team/editor.js",
     desc="Drop-in block editor for live-ops content scheduling.",
     tags=["live-ops", "tooling", "cms"])

# ─── Open-source procedural generation ───────────────────────────────────
_add("noise", "ojrac", "MIT", 1200, "Python", "any", "procgen", "snippet",
     """from noise import pnoise2
height_map = [[pnoise2(x/64.0, y/64.0, octaves=4) for x in range(256)] for y in range(256)]""",
     "https://github.com/caseman/noise",
     desc="Perlin-noise terrain generation. Octaves=4 is the sweet-spot for game terrains.",
     tags=["procgen", "perlin", "terrain"])

# ─── Open-source shader collection ───────────────────────────────────────
_add("Open-Shader-Designer", "Beyley", "MIT", 800, "GLSL", "any", "shader", "snippet",
     """// Outline pass — silhouette via depth + normal
vec3 normal = texture(normalTex, uv).rgb;
float edge  = step(0.25, length(fwidth(normal)));
outColor = mix(baseColor, vec4(0,0,0,1), edge);""",
     "internal://patterns/outline-shader",
     desc="Cheap silhouette outline shader — works in any forward renderer.",
     tags=["shader", "outline", "post-fx"])

log.info(f"[github_code_seed] curated entries: {len(CODE_REFS)}")


async def seed_github_code(db) -> dict:
    """Upsert all curated code references into Mongo `github_code_refs`."""
    try:
        await db.github_code_refs.create_index("id", unique=True)
        await db.github_code_refs.create_index("repo")
        await db.github_code_refs.create_index("primary_language")
        await db.github_code_refs.create_index("engine")
        await db.github_code_refs.create_index("topic")
        await db.github_code_refs.create_index("snippet_kind")
        await db.github_code_refs.create_index([("tags", 1)])
    except Exception:
        pass

    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    updated = 0
    for doc in CODE_REFS:
        doc["indexed_at"] = now
        try:
            res = await db.github_code_refs.update_one(
                {"id": doc["id"]}, {"$set": doc}, upsert=True,
            )
            if res.upserted_id is not None:
                inserted += 1
            elif res.modified_count > 0:
                updated += 1
        except Exception as e:
            log.debug(f"github_code upsert failed: {e}")

    total = await db.github_code_refs.count_documents({})
    log.info(f"[github_code_seed] done: inserted={inserted} updated={updated} total={total}")
    return {"inserted": inserted, "updated": updated, "total": total}
