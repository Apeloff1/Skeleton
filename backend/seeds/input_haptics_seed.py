"""
Controller, Input-Device & Haptic Feedback knowledge base.
Collection: `input_haptics`
"""
import hashlib, logging, itertools
from datetime import datetime, timezone
log = logging.getLogger("knowledge.input_haptics")

DEVICES = ["xbox-series-x","dualsense","dualshock4","switch-pro","joycon","steam-deck","steam-controller","keyboard-mouse","touch-mobile","vr-quest","vr-index","vr-vive","flight-stick","wheel-pedals","midi-pad","arcade-stick","gyro-imu","eye-tracker","haptic-glove","backbone-mobile"]
BINDINGS = ["jump","crouch","sprint","shoot","aim","reload","interact","inventory","map","melee","throw","ability1","ability2","ultimate","dodge","parry","block","camera-reset","emote","chat","ping","vehicle-enter","weapon-swap","pause"]
HAPTIC_PATTERNS = [
    ("hit-light",   {"freq_hz": 120, "amp": 0.35, "dur_ms": 60}),
    ("hit-heavy",   {"freq_hz": 80,  "amp": 0.85, "dur_ms": 180}),
    ("reload",      {"freq_hz": 200, "amp": 0.25, "dur_ms": 320}),
    ("footstep",    {"freq_hz": 60,  "amp": 0.15, "dur_ms": 40}),
    ("low-health",  {"freq_hz": 40,  "amp": 0.50, "dur_ms": 600, "pulse": True}),
    ("trigger-pull",{"freq_hz": 150, "amp": 0.45, "dur_ms": 100, "adaptive": True}),
    ("engine-rumble",{"freq_hz": 35, "amp": 0.30, "dur_ms": 0, "continuous": True}),
    ("explosion",   {"freq_hz": 25,  "amp": 1.00, "dur_ms": 450}),
    ("heal",        {"freq_hz": 220, "amp": 0.20, "dur_ms": 220, "ramp": True}),
    ("ui-confirm",  {"freq_hz": 320, "amp": 0.18, "dur_ms": 25}),
]

def _hid(*p): return "input_" + hashlib.md5("|".join(p).encode()).hexdigest()[:14]

def build_input_haptics():
    out = []
    for dev, bind in itertools.product(DEVICES, BINDINGS):
        out.append({
            "id": _hid(dev, bind, "binding"),
            "category": "binding",
            "device": dev,
            "action": bind,
            "description": f"Default {bind} binding for {dev}",
            "tags": [dev, bind, "input", "binding"],
        })
    for dev, (name, params) in itertools.product(DEVICES, HAPTIC_PATTERNS):
        out.append({
            "id": _hid(dev, name, "haptic"),
            "category": "haptic",
            "device": dev,
            "pattern_name": name,
            "params": params,
            "description": f"{name} haptic preset for {dev}",
            "tags": [dev, name, "haptic", "feedback"],
        })
    return out

async def seed_input_haptics(db):
    docs = build_input_haptics()
    try:
        await db.input_haptics.create_index("id", unique=True)
        await db.input_haptics.create_index("device")
        await db.input_haptics.create_index("category")
        await db.input_haptics.create_index([("tags", 1)])
    except Exception: pass
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    for d in docs:
        d["indexed_at"] = now
        try:
            r = await db.input_haptics.update_one({"id": d["id"]}, {"$set": d}, upsert=True)
            if r.upserted_id is not None: inserted += 1
        except Exception: pass
    return {"inserted": inserted, "total": await db.input_haptics.count_documents({})}
