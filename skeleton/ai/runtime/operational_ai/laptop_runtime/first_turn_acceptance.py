"""Actual installed model -> live inference -> idempotent replay acceptance.

This function performs real model generation. Never invoke on unapproved model
bytes or for a test that has not explicitly allocated its real resource budget.
"""
from __future__ import annotations
import secrets
from .contracts import refuse
from .session_adapter import create
from .turn_bridge import TurnBridge
from .replay_probe import inspect_replay

def run(worker,*,prompt,approved=False):
    if approved is not True:refuse("real end-to-end inference approval required")
    session=create(worker)
    request="r_"+secrets.token_hex(16)
    bridge=TurnBridge(worker)
    first=bridge.turn(session,request,prompt,seed=17,temperature=0.8)
    replay=inspect_replay(worker,session,request,prompt,seed=17,temperature=0.8)
    if not replay["committed"] or replay["output_sha256"]!=first["output_sha256"]:
        refuse("native first-turn durable replay disagrees")
    return {"schema":"laptop-real-first-turn-e2e.v1","session_id":session,
            "request_id":request,"output_sha256":first["output_sha256"],
            "replayed_without_generation":True,
            "native_model_observed":True,
            "release_certified":False}
