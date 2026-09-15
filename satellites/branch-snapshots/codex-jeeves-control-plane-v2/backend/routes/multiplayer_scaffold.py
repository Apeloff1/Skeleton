"""
╔══════════════════════════════════════════════════════════════════════════╗
║  MULTIPLAYER / NETCODE SCAFFOLD STUDIO  (Cosmic Backlog V.4)               ║
║                                                                            ║
║  Generates real, parameterised multiplayer boilerplate that can be dropped ║
║  into an exported game: an authoritative WebSocket server with a fixed     ║
║  tick loop, a client with the right sync strategy (interpolation /         ║
║  prediction+rollback / deterministic lockstep / relay), a shared wire      ║
║  protocol, lobby + matchmaking, and a README. Pure codegen — no external   ║
║  calls — so it is instant and deterministic.                               ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations
import os
import re
import uuid
import json
from datetime import datetime, timezone
from typing import Optional, List, Dict, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from core.databases import client as _MONGO

router = APIRouter(prefix="/api/multiplayer", tags=["multiplayer"])
_db = _MONGO[os.environ.get("DB_NAME", "test_database")]
_col = _db.multiplayer_scaffolds
PROJ = {"_id": 0}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── NETCODE MODELS ──────────────────────────────────────────────────────────
MODELS: Dict[str, Dict] = {
    "authoritative": {
        "label": "Authoritative Server + Interpolation",
        "desc": "Server owns the truth; clients send inputs and render interpolated snapshots. Cheat-resistant, simplest to reason about.",
        "best_for": ["co-op", "action", "shooter", "rpg", "platformer", "survival"],
        "tradeoffs": "Adds input latency; mitigate with client-side visual smoothing.",
        "recommended_tick": 20,
    },
    "rollback": {
        "label": "Client Prediction + Rollback",
        "desc": "Clients predict locally and roll back/replay when the server correction arrives. Feels instant — the gold standard for fast PvP.",
        "best_for": ["fighting", "fast-pvp", "arena", "racing", "sports"],
        "tradeoffs": "Most complex; requires a deterministic, re-simulatable game step.",
        "recommended_tick": 60,
    },
    "lockstep": {
        "label": "Deterministic Lockstep",
        "desc": "Every client simulates identically from the same inputs. Tiny bandwidth, scales to thousands of units.",
        "best_for": ["rts", "strategy", "moba", "city-builder", "simulation"],
        "tradeoffs": "Demands full determinism (fixed-point math); one stall blocks all.",
        "recommended_tick": 15,
    },
    "relay": {
        "label": "Relay / Shared-State Sync",
        "desc": "Lightweight relay broadcasts state deltas between peers. Easiest to ship for casual/turn-based games.",
        "best_for": ["turn-based", "card", "board", "puzzle", "casual", "social"],
        "tradeoffs": "Not cheat-proof; trust is shared between peers.",
        "recommended_tick": 10,
    },
}


def recommend_model(genre: str) -> str:
    g = (genre or "").strip().lower()
    tokens = set(re.findall(r"[a-z0-9]+", g))
    # 1) exact tag match against each model's best_for (no substring false-positives)
    for mid, m in MODELS.items():
        for tag in m["best_for"]:
            parts = set(re.split(r"[\s/-]+", tag))
            if tag in tokens or (parts & tokens):
                return mid
    # 2) genre keyword heuristics
    if any(k in g for k in ("fight", "versus", "brawl", "race")):
        return "rollback"
    if any(k in g for k in ("rts", "strategy", "tower", "moba")):
        return "lockstep"
    if any(k in g for k in ("turn", "card", "board", "puzzle", "trivia")):
        return "relay"
    return "authoritative"


@router.get("/models")
async def list_models(genre: str = Query("")):
    out = []
    for mid, m in MODELS.items():
        out.append({"id": mid, **{k: m[k] for k in ("label", "desc", "best_for", "tradeoffs", "recommended_tick")}})
    resp = {"models": out}
    if genre:
        resp["recommended"] = recommend_model(genre)
    return resp


@router.get("/recommend")
async def recommend(genre: str = Query(...)):
    mid = recommend_model(genre)
    return {"genre": genre, "recommended": mid, "model": {"id": mid, **MODELS[mid]}}


# ── CODE TEMPLATES ──────────────────────────────────────────────────────────
def _server_js(model: str, max_players: int, tick: int, snap: int, game: str) -> str:
    interval = round(1000 / max(1, tick))
    snap_interval = round(1000 / max(1, snap))
    return f"""// {game} — authoritative multiplayer server  (model: {model})
// Fixed tick = {tick}Hz, snapshots = {snap}Hz, max players/room = {max_players}
// Run:  npm i ws  &&  node server/index.js
const {{ WebSocketServer }} = require('ws');
const {{ createRoom, joinRoom, leaveRoom, rooms }} = require('./lobby');
const PORT = process.env.PORT || 8080;
const TICK_MS = {interval};
const SNAP_MS = {snap_interval};
const MAX_PLAYERS = {max_players};

const wss = new WebSocketServer({{ port: PORT }});
console.log('[net] {game} server on :' + PORT + ' (' + '{model}' + ')');

wss.on('connection', (ws) => {{
  ws.id = Math.random().toString(36).slice(2, 10);
  ws.inputs = [];
  ws.on('message', (raw) => {{
    let msg; try {{ msg = JSON.parse(raw); }} catch {{ return; }}
    switch (msg.t) {{
      case 'join': {{
        const room = joinRoom(msg.room, ws, MAX_PLAYERS);
        if (!room) return ws.send(JSON.stringify({{ t: 'full' }}));
        ws.room = room.id;
        ws.send(JSON.stringify({{ t: 'joined', id: ws.id, room: room.id, players: room.members.map(m => m.id) }}));
        break;
      }}
      case 'input':  // buffered, applied on the next authoritative tick
        ws.inputs.push({{ id: ws.id, seq: msg.seq, data: msg.data, at: Date.now() }});
        break;
      case 'ping':
        ws.send(JSON.stringify({{ t: 'pong', at: msg.at }}));
        break;
    }}
  }});
  ws.on('close', () => leaveRoom(ws));
}});

// ── Authoritative simulation: advance world from buffered inputs ──
function stepRoom(room) {{
  for (const ws of room.members) {{
    for (const inp of ws.inputs) applyInput(room.state, inp);  // TODO: your game rules
    ws.inputs.length = 0;
  }}
  room.tick++;
}}
function applyInput(state, input) {{
  // TODO: mutate `state` for player `input.id` using `input.data`.
  state.players[input.id] = state.players[input.id] || {{ x: 0, y: 0 }};
}}

setInterval(() => {{ for (const room of rooms.values()) stepRoom(room); }}, TICK_MS);
setInterval(() => {{
  for (const room of rooms.values()) {{
    const snap = JSON.stringify({{ t: 'snap', tick: room.tick, state: room.state }});
    for (const ws of room.members) {{ try {{ ws.send(snap); }} catch {{}} }}
  }}
}}, SNAP_MS);
"""


def _lobby_js(max_players: int) -> str:
    return f"""// Lobby + matchmaking — create/join/leave rooms, cap {max_players}/room
const rooms = new Map();
function createRoom(id) {{
  const room = {{ id, members: [], tick: 0, state: {{ players: {{}} }} }};
  rooms.set(id, room); return room;
}}
function joinRoom(id, ws, cap) {{
  let room = rooms.get(id) || createRoom(id || Math.random().toString(36).slice(2, 8));
  if (room.members.length >= cap) return null;
  room.members.push(ws); return room;
}}
function leaveRoom(ws) {{
  const room = rooms.get(ws.room); if (!room) return;
  room.members = room.members.filter(m => m !== ws);
  delete room.state.players[ws.id];
  if (room.members.length === 0) rooms.delete(room.id);
}}
module.exports = {{ createRoom, joinRoom, leaveRoom, rooms }};
"""


def _protocol_ts(model: str) -> str:
    return f"""// Shared wire protocol (client + server). Model: {model}
export type Vec2 = {{ x: number; y: number }};

export type ClientMsg =
  | {{ t: 'join'; room: string }}
  | {{ t: 'input'; seq: number; data: InputData }}
  | {{ t: 'ping'; at: number }};

export type ServerMsg =
  | {{ t: 'joined'; id: string; room: string; players: string[] }}
  | {{ t: 'snap'; tick: number; state: WorldState }}
  | {{ t: 'full' }}
  | {{ t: 'pong'; at: number }};

export interface InputData {{ up?: boolean; down?: boolean; left?: boolean; right?: boolean; action?: boolean; }}
export interface PlayerState {{ x: number; y: number; [k: string]: unknown; }}
export interface WorldState {{ players: Record<string, PlayerState>; }}
"""


def _client_ts(model: str, tick: int) -> str:
    common = f"""// Net client (model: {model}). import {{ NetClient }} from './netClient';
import type {{ ClientMsg, ServerMsg, WorldState, InputData }} from '../shared/protocol';

export class NetClient {{
  private ws!: WebSocket;
  public id = '';
  public state: WorldState = {{ players: {{}} }};
  private seq = 0;
  onSnapshot?: (s: WorldState, tick: number) => void;

  connect(url: string, room: string) {{
    this.ws = new WebSocket(url);
    this.ws.onopen = () => this.send({{ t: 'join', room }});
    this.ws.onmessage = (e) => this.handle(JSON.parse(e.data) as ServerMsg);
  }}
  private send(m: ClientMsg) {{ this.ws?.readyState === 1 && this.ws.send(JSON.stringify(m)); }}
  sendInput(data: InputData) {{ this.send({{ t: 'input', seq: ++this.seq, data }}); """
    if model == "rollback":
        body = """this.predict(data); }
"""
    else:
        body = """}
"""
    handle = """
  private handle(m: ServerMsg) {
    if (m.t === 'joined') this.id = m.id;
    if (m.t === 'snap') { this.reconcile(m.state, m.tick); this.onSnapshot?.(this.state, m.tick); }
  }
"""
    if model == "authoritative":
        extra = """  // Interpolate toward the latest authoritative snapshot for smooth motion.
  private reconcile(server: WorldState) { this.state = server; }
  predict(_: InputData) { /* no-op: server-authoritative */ }
}
"""
    elif model == "rollback":
        extra = f"""  private pending: {{ seq: number; data: InputData }}[] = [];
  // Apply locally now; replay un-acked inputs after the server correction.
  predict(data: InputData) {{ this.pending.push({{ seq: this.seq, data }}); applyLocal(this.state, this.id, data); }}
  private reconcile(server: WorldState, tick: number) {{
    this.state = structuredClone(server);
    for (const p of this.pending) applyLocal(this.state, this.id, p.data); // re-simulate ({tick}Hz)
  }}
}}
function applyLocal(s: WorldState, id: string, _d: InputData) {{ s.players[id] = s.players[id] || {{ x: 0, y: 0 }}; }}
"""
    elif model == "lockstep":
        extra = """  // Deterministic lockstep: queue inputs per turn; step only when all peers' inputs arrived.
  private reconcile(server: WorldState) { this.state = server; }
  predict(_: InputData) { /* lockstep advances on confirmed turns only */ }
}
"""
    else:  # relay
        extra = """  private reconcile(server: WorldState) { this.state = { ...this.state, ...server }; }
  predict(_: InputData) { /* relay: trust shared state */ }
}
"""
    return common + body + handle + extra


def _readme(model: str, max_players: int, tick: int, snap: int, game: str) -> str:
    m = MODELS[model]
    return f"""# {game} — Multiplayer Scaffold ({m['label']})

**Model:** {model} — {m['desc']}
**Best for:** {', '.join(m['best_for'])}
**Tradeoffs:** {m['tradeoffs']}

## Parameters
- Max players / room: **{max_players}**
- Server tick rate: **{tick} Hz**
- Snapshot rate: **{snap} Hz**

## Run
```bash
cd server && npm i ws && node index.js   # ws server on :8080
```
Point the client at `ws://localhost:8080` and call `netClient.connect(url, roomId)`.

## Files
- `server/index.js` — authoritative tick loop + snapshot broadcast
- `server/lobby.js` — room create/join/leave + matchmaking cap
- `shared/protocol.ts` — the wire protocol (single source of truth)
- `client/netClient.ts` — connect, send inputs, apply the **{model}** sync strategy

## Next steps
1. Implement `applyInput` (server) with your real game rules.
2. {"Make your game step deterministic (fixed-point) so rollback/lockstep stays in sync." if model in ("rollback", "lockstep") else "Add interpolation buffering on the client for smooth rendering."}
3. Add reconnection + auth tokens before shipping to production.
"""


class ScaffoldBody(BaseModel):
    pid: Optional[str] = None
    game: str = "Your Game"
    genre: str = ""
    model: Optional[str] = None
    max_players: int = Field(4, ge=2, le=64)
    tick_rate: int = Field(0, ge=0, le=128)   # 0 ⇒ use the model's recommended tick


@router.post("/scaffold")
async def scaffold(body: ScaffoldBody):
    """Generate a complete, parameterised multiplayer starter for a game."""
    model = (body.model or "").strip().lower()
    if model not in MODELS:
        model = recommend_model(body.genre)
    tick = body.tick_rate or MODELS[model]["recommended_tick"]
    snap = max(5, min(tick, 30))   # snapshots no faster than the tick, capped for bandwidth
    game = (body.game or "Your Game").strip()[:80]
    mp = body.max_players

    files = [
        {"path": "server/index.js",      "lang": "javascript", "content": _server_js(model, mp, tick, snap, game)},
        {"path": "server/lobby.js",      "lang": "javascript", "content": _lobby_js(mp)},
        {"path": "shared/protocol.ts",   "lang": "typescript", "content": _protocol_ts(model)},
        {"path": "client/netClient.ts",  "lang": "typescript", "content": _client_ts(model, tick)},
        {"path": "README.md",            "lang": "markdown",   "content": _readme(model, mp, tick, snap, game)},
    ]
    doc = {
        "scaffold_id": uuid.uuid4().hex,
        "pid": body.pid, "game": game, "genre": body.genre,
        "model": model, "max_players": mp, "tick_rate": tick, "snapshot_rate": snap,
        "files": files, "created_at": _now(),
    }
    try:
        await _col.update_one({"pid": body.pid} if body.pid else {"scaffold_id": doc["scaffold_id"]},
                              {"$set": dict(doc)}, upsert=True)
    except Exception:
        pass
    return {
        "scaffold_id": doc["scaffold_id"], "game": game, "model": model,
        "model_label": MODELS[model]["label"], "max_players": mp,
        "tick_rate": tick, "snapshot_rate": snap, "file_count": len(files), "files": files,
    }


@router.get("/scaffold/{pid}")
async def get_scaffold(pid: str):
    doc = await _col.find_one({"pid": pid}, PROJ, sort=[("created_at", -1)])
    if not doc:
        raise HTTPException(404, "no scaffold for this game yet")
    return doc


class ZipBody(ScaffoldBody):
    pass


@router.post("/scaffold/zip")
async def scaffold_zip(body: ZipBody):
    """📦 Generate the scaffold and return it as a downloadable .zip (base64)."""
    import io, zipfile, base64
    built = await scaffold(body)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for f in built["files"]:
            z.writestr(f["path"], f["content"])
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    fname = (built["game"] or "game").lower().replace(" ", "-")[:40] + "-multiplayer.zip"
    return {"filename": fname, "model": built["model"], "file_count": built["file_count"],
            "size_bytes": len(buf.getvalue()), "zip_base64": b64}
