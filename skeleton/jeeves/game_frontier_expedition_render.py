"""Source-bound adaptive LOD streaming planner and performance budget checks.

Actual camera/waypoint distances, polygon counts and finite draw budgets
determine the geometry loaded for each game frame; no claim of sampled FPS.
Plans provide deterministic per-frame receipts suitable for native engine
integration and adversarial QA.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import sqrt,isfinite
from typing import Mapping,Sequence
from .game_frontier_expedition import ExpeditionWorld,ExpeditionError,_digest


@dataclass(frozen=True,slots=True)
class LODPolicy:
    near_m:float=80.0
    far_m:float=240.0
    triangle_budget:int=25000
    max_visible:int=512
    hysteresis_m:float=12.
    max_updates_per_frame:int=128

    def __post_init__(self):
        for name in ("near_m","far_m","hysteresis_m"):
            value=getattr(self,name)
            if type(value) not in (int,float) or not isfinite(value) or value<0 or value>1e6:
                raise ExpeditionError("render LOD distance must be bounded")
        if not 0<self.near_m<self.far_m or self.hysteresis_m>=self.near_m/2:
            raise ExpeditionError("render LOD transition bands overlap")
        for name,bound in (("triangle_budget",10_000_000),("max_visible",8192),
                           ("max_updates_per_frame",2048)):
            val=getattr(self,name)
            if type(val) is not int or not 1<=val<=bound:
                raise ExpeditionError("LOD frame capacity invalid")


@dataclass(frozen=True,slots=True)
class View:
    frame:int
    x_m:float
    y_m:float
    altitude_m:float
    visibility_m:float=1000.

    def __post_init__(self):
        if type(self.frame) is not int or not 0<=self.frame<=10**10:
            raise ExpeditionError("render frame counter out of bounds")
        for attr in ("x_m","y_m","altitude_m","visibility_m"):
            val=getattr(self,attr)
            if type(val) not in (int,float) or not isfinite(val) or not -1e6<=val<=1e6:
                raise ExpeditionError("render camera coordinates invalid")
        if self.visibility_m<=0:
            raise ExpeditionError("visibility distance must be positive")


def _distance(node,view):
    return sqrt((node.x_m-view.x_m)**2+(node.y_m-view.y_m)**2+
                (node.altitude_m-view.altitude_m)**2)


def plan_game_lod(world:ExpeditionWorld,view:View,asset_manifest:Mapping, *,
                  policy:LODPolicy=LODPolicy(), prior:Mapping[str,int]|None=None)->dict:
    if not isinstance(world,ExpeditionWorld) or not isinstance(view,View) or not isinstance(policy,LODPolicy):
        raise ExpeditionError("LOD planner requires original source world and camera")
    if not isinstance(asset_manifest,Mapping) or (
            asset_manifest.get("schema")!="skeleton.game.original_3d_assets.v1" or
            asset_manifest.get("world_digest")!=world.digest):
        raise ExpeditionError("LOD mesh inventory belongs to another source")
    records=asset_manifest.get("assets")
    if not isinstance(records,list) or len(records)>32768:
        raise ExpeditionError("LOD geometry inventory invalid")
    by_waypoint:dict[str,dict[int,dict]]={}
    for item in records:
        if not isinstance(item,dict) or item.get("waypoint") not in world.by_id:
            raise ExpeditionError("LOD record has foreign waypoint")
        lod=item.get("lod")
        triangles=item.get("triangles")
        if type(lod) is not int or not 0<=lod<=8 or type(triangles) is not int or not 1<=triangles<=1_000_000:
            raise ExpeditionError("LOD geometry topology invalid")
        if lod in by_waypoint.setdefault(item["waypoint"],{}):
            raise ExpeditionError("ambiguous geometry level for one asset")
        by_waypoint[item["waypoint"]][lod]=item
    if set(by_waypoint)!=set(world.by_id):
        raise ExpeditionError("LOD inventory missing authored world locations")
    levels=set(by_waypoint[next(iter(by_waypoint))])
    if not levels or len(levels)>8 or any(set(lod_map)!=levels for lod_map in by_waypoint.values()):
        raise ExpeditionError("LOD inventory inconsistent across geometry sources")
    if prior is not None and (
        not isinstance(prior,Mapping) or any(
            key not in world.by_id or type(v) is not int or v not in levels
            for key,v in prior.items()
        )
    ):
        raise ExpeditionError("previous LOD state has foreign or altered geometry")
    prior={} if prior is None else dict(prior)
    choices=[]
    far=max(levels)
    middle=sorted(levels)[len(levels)//2]
    nearest=min(levels)
    for node in world.waypoints:
        dist=_distance(node,view)
        if dist>view.visibility_m:
            continue
        level=(nearest if dist<=policy.near_m else
               middle if dist<=policy.far_m else far)
        previous=prior.get(node.waypoint_id)
        # Stable camera movement should not cause repeated LOD swaps
        # inside a small distance hysteresis band.
        if previous is not None and previous!=level and (
            abs(dist-policy.near_m)<policy.hysteresis_m or
            abs(dist-policy.far_m)<policy.hysteresis_m
        ):
            level=previous
        item=by_waypoint[node.waypoint_id][level]
        choices.append({
            "waypoint":node.waypoint_id,"distance_m":round(dist,4),
            "lod":level,"mesh_path":item["mesh_path"],
            "mesh_sha256":item["sha256"],"triangles":item["triangles"],
        })
    choices.sort(key=lambda x:(x["distance_m"],x["waypoint"]))
    selected=choices[:policy.max_visible]
    budget=0
    result=[]
    for item in selected:
        if budget+item["triangles"]<=policy.triangle_budget:
            result.append(item)
            budget+=item["triangles"]
        else:
            # Skip overdraw, rather than silently exceeding the frame budget.
            continue
    updates=sum(item["lod"]!=prior.get(item["waypoint"]) for item in result)
    if updates>policy.max_updates_per_frame:
        accepted=0
        for item in result:
            if item["lod"]!=prior.get(item["waypoint"]):
                accepted+=1
                if accepted>policy.max_updates_per_frame:
                    item["deferred"]=True
    ready=[item for item in result if not item.get("deferred")]
    payload={
        "schema":"skeleton.game.render_lod_plan.v1",
        "world_digest":world.digest,"frame":view.frame,
        "camera":{"x_m":view.x_m,"y_m":view.y_m,
                  "altitude_m":view.altitude_m,
                  "visibility_m":view.visibility_m},
        "requested_visible":len(choices),
        "budgeted_visible":len(ready),
        "deferred":len(result)-len(ready),
        "triangle_count":sum(x["triangles"] for x in ready),
        "meshes":ready,
        "measured_native_fps":None,
        "native_render_executed":False,
    }
    payload["receipt_digest"]=_digest(payload)
    return payload


def render_lod_timeline(
    world:ExpeditionWorld,asset_manifest:Mapping,views:Sequence[View], *,
    policy:LODPolicy=LODPolicy(),
)->dict:
    if (not isinstance(views,(tuple,list)) or not 1<=len(views)<=256
            or any(not isinstance(v,View) for v in views)
            or any(b.frame<=a.frame for a,b in zip(views,views[1:]))):
        raise ExpeditionError("render frame timeline must increase and stay bounded")
    records=[]
    state={}
    previous=_digest({"world":world.digest,"render_genesis":True})
    for view in views:
        plan=plan_game_lod(world,view,asset_manifest,policy=policy,prior=state)
        state={p["waypoint"]:p["lod"] for p in plan["meshes"]}
        receipt=_digest({"previous":previous,"plan":plan["receipt_digest"],
                         "frame":view.frame})
        records.append({"frame":view.frame,"plan":plan,
                        "receipt":receipt,"prior_receipt":previous})
        previous=receipt
    report={
        "schema":"skeleton.game.render_frame_timeline.v1",
        "world_digest":world.digest,"frames":len(records),
        "records":records,"receipt_head":previous,
        "native_performance_qualified":False,
    }
    report["receipt_digest"]=_digest(report)
    return report
