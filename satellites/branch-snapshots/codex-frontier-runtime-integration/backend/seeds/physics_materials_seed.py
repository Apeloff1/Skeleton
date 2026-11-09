"""
Physics, Material-Science & Simulation Matrices.
Collection: `physics_materials_sim`
"""
import hashlib, logging, itertools
from datetime import datetime, timezone
log = logging.getLogger("knowledge.physics_materials")

MATERIALS = [
    ("wood",      {"density": 0.7, "friction": 0.6, "restitution": 0.3, "young_modulus_gpa": 11, "sound":"hollow-knock"}),
    ("steel",     {"density": 7.85, "friction": 0.45, "restitution": 0.55, "young_modulus_gpa": 200, "sound":"clang"}),
    ("aluminum",  {"density": 2.7, "friction": 0.5, "restitution": 0.6, "young_modulus_gpa": 69, "sound":"bright-clang"}),
    ("rubber",    {"density": 1.2, "friction": 1.0, "restitution": 0.85, "young_modulus_gpa": 0.05, "sound":"thud"}),
    ("glass",     {"density": 2.5, "friction": 0.2, "restitution": 0.1, "young_modulus_gpa": 70, "sound":"shatter"}),
    ("ice",       {"density": 0.92, "friction": 0.05, "restitution": 0.3, "young_modulus_gpa": 9, "sound":"crack"}),
    ("sand",      {"density": 1.6, "friction": 0.7, "restitution": 0.1, "young_modulus_gpa": 0.001, "sound":"swish"}),
    ("flesh",     {"density": 1.0, "friction": 0.8, "restitution": 0.05, "young_modulus_gpa": 0.01, "sound":"squish"}),
    ("concrete",  {"density": 2.4, "friction": 0.7, "restitution": 0.2, "young_modulus_gpa": 30, "sound":"thud-stone"}),
    ("plastic",   {"density": 1.0, "friction": 0.4, "restitution": 0.4, "young_modulus_gpa": 3, "sound":"hollow-plastic"}),
    ("water",     {"density": 1.0, "friction": 0.0, "restitution": 0.0, "young_modulus_gpa": 2.2, "sound":"splash"}),
    ("snow",      {"density": 0.3, "friction": 0.3, "restitution": 0.05, "young_modulus_gpa": 0.001, "sound":"crunch"}),
    ("cloth",     {"density": 0.4, "friction": 0.6, "restitution": 0.05, "young_modulus_gpa": 0.01, "sound":"flutter"}),
    ("jelly",     {"density": 1.0, "friction": 0.9, "restitution": 0.6, "young_modulus_gpa": 0.001, "sound":"slop", "soft_body": True}),
    ("magma",     {"density": 3.0, "friction": 0.5, "restitution": 0.0, "young_modulus_gpa": 0.01, "sound":"sizzle", "hot": True}),
]
SIM_KINDS = [
    ("rigid-body",     {"solver":"PGS","iterations":8}),
    ("soft-body",      {"solver":"XPBD","iterations":12,"compliance":1e-4}),
    ("cloth",          {"solver":"PBD","iterations":10,"bend_stiffness":0.4}),
    ("fluid-sph",      {"smoothing_radius":0.1,"rest_density":1000}),
    ("fluid-flip",     {"cell_size":0.05,"viscosity":0.001}),
    ("destruction-voronoi",{"fracture_threshold":1e5,"shards":24}),
    ("ragdoll",        {"joint_iter":6,"angular_damp":0.3}),
    ("vehicle",        {"wheel_friction":1.2,"sus_stiffness":24}),
    ("hair",           {"strands":64,"segments":12}),
    ("gas-cellular",   {"grid":128,"diffusion":0.0005}),
]
ENGINES = ["Bullet","PhysX","Havok","Box2D","Jolt","Rapier","Chaos","MuJoCo","ODE","Newton"]

def _pid(*p): return "phys_" + hashlib.md5("|".join(p).encode()).hexdigest()[:14]

def build_physics_materials():
    out = []
    for name, props in MATERIALS:
        out.append({"id": _pid(name,"material"),"category":"material","name":name,"properties":props,"tags":[name,"material"]})
    for (sim, params), engine in itertools.product(SIM_KINDS, ENGINES):
        out.append({"id": _pid(sim,engine,"sim"),"category":"simulation","sim_kind":sim,"engine":engine,"params":params,
                    "description":f"{sim} simulation on {engine}","tags":[sim,engine.lower(),"simulation"]})
    return out

async def seed_physics_materials(db):
    docs = build_physics_materials()
    try:
        await db.physics_materials_sim.create_index("id", unique=True)
        await db.physics_materials_sim.create_index("category")
        await db.physics_materials_sim.create_index("name")
        await db.physics_materials_sim.create_index("sim_kind")
        await db.physics_materials_sim.create_index([("tags", 1)])
    except Exception: pass
    now = datetime.now(timezone.utc).isoformat(); inserted = 0
    for d in docs:
        d["indexed_at"] = now
        try:
            r = await db.physics_materials_sim.update_one({"id":d["id"]},{"$set":d},upsert=True)
            if r.upserted_id is not None: inserted += 1
        except Exception: pass
    return {"inserted": inserted, "total": await db.physics_materials_sim.count_documents({})}
