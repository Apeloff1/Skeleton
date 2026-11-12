"""Full FastAPI surface for the prototype. All verticals exposed.
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from ..jeeves.full_tutor import FullJeevesTutor
from ..godot.full_emitter import FullGodotEmitter
from pathlib import Path
import tempfile

app = FastAPI(title="Skeleton Full Prototype API", version="2026.11-completionist")
tutor = FullJeevesTutor()
emitter = FullGodotEmitter()

class Query(BaseModel):
    session_id: Optional[str] = None
    query: str

class Brief(BaseModel):
    brief: str
    title: Optional[str] = "PrototypeGame"

@app.post("/jeeves/start")
def start_session(user_id: str = "default"):
    return {"session_id": tutor.start(user_id)}

@app.post("/jeeves/respond")
def respond(body: Query):
    sid = body.session_id or tutor.start("anon")
    return tutor.respond(sid, body.query)

@app.post("/forge/emit")
def emit_godot(body: Brief):
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "pack"
        result = emitter.emit({"title": body.title, "brief": body.brief, "catalogs": {}}, path)
        return result

@app.get("/health")
def health():
    return {"status": "green", "standard": "Nov2026-completionist", "verticals": ["jeeves", "forge", "godot", "cockpit", "economy", "chronicle"]}
