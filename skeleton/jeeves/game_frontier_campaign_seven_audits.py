"""Seven independent campaign QA instruments on existing Jeeves game authorities.

The reports are source-bound build evidence, never release certification, real
GNSS measurements, native frame capture, or provider-model attestations.
"""
from __future__ import annotations

from collections import deque
from dataclasses import replace
from hashlib import sha256
from math import atan2, degrees, hypot
from typing import Mapping

from .game_frontier_expedition import (
    ExpeditionError, ExpeditionWorld, Traveler, _digest,
    find_route, verify_route,
)

AXES=("topology","instruments","objectives","weather","frames","assets","delivery")


def _reachable(graph:dict, start:str)->set[str]:
    seen={start}
    queue=deque([start])
    while queue:
        for target in graph[queue.popleft()]:
            if target not in seen:
                seen.add(target)
                queue.append(target)
    return seen


def audit_topology(world:ExpeditionWorld)->dict:
    """M1: directed graph, dead ends, destination cuts, no invented reverse edges."""
    if not isinstance(world,ExpeditionWorld):
        raise ExpeditionError("topology needs canonical expedition")
    graph={key:[] for key in world.by_id}
    for edge in world.edges:
        graph[edge.source].append(edge.target)
    graph={key:tuple(sorted(values)) for key,values in graph.items()}
    seen=_reachable(graph,world.arrival)
    cuts=[]
    if len(world.edges)<=512:
        for edge in world.edges:
            reduced={start:tuple(target for target in targets
                     if start!=edge.source or target!=edge.target)
                     for start,targets in graph.items()}
            remainder=_reachable(reduced,world.arrival)
            if any(target in seen and target not in remainder
                   for target in world.destinations):
                cuts.append(edge.edge_id)
    return _seal({
        "schema":"skeleton.game.campaign_topology_audit.v1",
        "world":world.digest,"node_count":len(world.waypoints),
        "directed_edges":len(world.edges),
        "unreachable_waypoints":sorted(set(graph)-seen),
        "unreachable_destinations":sorted(set(world.destinations)-seen),
        "non_goal_sinks":sorted(v for v in seen if not graph[v] and v not in world.destinations),
        "destination_cut_edges":sorted(cuts),
        "cut_analysis_complete":len(world.edges)<=512,
        "not_an_ability_gated_playthrough":True,
    })


def audit_instruments(world:ExpeditionWorld, *, cap:int=64)->dict:
    """M2: virtual compass, game altimeter, slant-range and sextant readings."""
    if not isinstance(world,ExpeditionWorld) or type(cap) is not int or not 2<=cap<=128:
        raise ExpeditionError("game-only instruments require typed bounded input")
    start=world.by_id[world.arrival]
    points=sorted(world.waypoints,key=lambda n:n.waypoint_id)
    if len(points)>cap:
        picks={round(i*(len(points)-1)/(cap-1)) for i in range(cap)}
        points=[p for i,p in enumerate(points) if i in picks
                or p.waypoint_id in world.destinations
                or p.waypoint_id==world.arrival]
    readings=[]
    for point in points:
        dx=point.x_m-start.x_m
        dy=point.y_m-start.y_m
        dz=point.altitude_m-start.altitude_m
        flat=hypot(dx,dy)
        readings.append({
            "waypoint":point.waypoint_id,
            "xyz_m":[point.x_m,point.y_m,point.altitude_m],
            "game_compass_degrees":round((degrees(atan2(dx,dy))+360)%360,6),
            "slant_range_m":round(hypot(flat,dz),6),
            "sextant_elevation_degrees":round(degrees(atan2(dz,flat)),6),
            "altimeter_m":point.altitude_m,
            "bubble_level_reference_degrees":0.,
        })
    return _seal({
        "schema":"skeleton.game.campaign_virtual_instruments.v1",
        "world":world.digest,"origin":world.arrival,
        "coordinate_system":"fictional_world_XYZ_metres",
        "observations":readings,
        "physical_sensor_or_real_gps_verified":False,
    })


def audit_objectives(world:ExpeditionWorld,player:Traveler)->dict:
    """M3: execute real fastest/safest/energy/scenic routes, compare Pareto paths."""
    if not isinstance(world,ExpeditionWorld) or not isinstance(player,Traveler):
        raise ExpeditionError("objective playthrough requires typed game owners")
    rows=[]
    for destination in sorted(world.destinations)[:8]:
        for objective in ("fastest","safest","energy","scenic"):
            try:
                route=find_route(world,player,destination,objective=objective)
            except ExpeditionError as exc:
                if str(exc)!="no traversable route under current abilities and stamina":
                    raise
                rows.append({"destination":destination,"objective":objective,"blocked":True})
                continue
            proof=verify_route(world,player,route)
            if not proof["verified"] or not proof["final_state"]["won"]:
                raise ExpeditionError("game state rejected proposed objective route")
            rows.append({
                "destination":destination,"objective":objective,"blocked":False,
                "route":route.digest,"edges":list(route.edge_ids),
                "seconds":route.seconds,"stamina":route.stamina,
                "damage":route.damage,"scenery":route.scenic_score,
                "actual_game_receipt":proof["receipt_head"],
            })
    completed=[v for v in rows if not v["blocked"]]
    if not completed:
        raise ExpeditionError("campaign has no won objective")
    pareto=[]
    for candidate in completed:
        rivals=[v for v in completed if v["destination"]==candidate["destination"]]
        dominated=any(
            v["seconds"]<=candidate["seconds"] and
            v["stamina"]<=candidate["stamina"] and
            v["damage"]<=candidate["damage"] and
            v["scenery"]>=candidate["scenery"] and (
            v["seconds"]<candidate["seconds"] or
            v["stamina"]<candidate["stamina"] or
            v["damage"]<candidate["damage"] or
            v["scenery"]>candidate["scenery"]) for v in rivals)
        if not dominated:
            pareto.append({"destination":candidate["destination"],
                           "objective":candidate["objective"],"route":candidate["route"]})
    return _seal({
        "schema":"skeleton.game.campaign_objective_playthrough.v1",
        "world":world.digest,"cases":rows,"played_routes":len(completed),
        "unique_routes":len({tuple(v["edges"]) for v in completed}),
        "pareto":pareto,"native_game_executed":False,
    })


def audit_weather(world:ExpeditionWorld,player:Traveler)->dict:
    """M4: weather/equipment perturbations executed against canonical route logic."""
    if not isinstance(world,ExpeditionWorld) or not isinstance(player,Traveler):
        raise ExpeditionError("weather audit requires canonical game and traveler")
    scenarios=(
        ("baseline",{},True),("severe_headwind",{"wind_x_mps":-35.},True),
        ("strong_updraft",{"vertical_mps":25.},True),
        ("rain",{"rain":1.},True),("turbulence",{"turbulence":1.},True),
        ("instrument_fog",{"visibility":0.02},True),
        ("unassisted_fog",{"visibility":0.02},False),
    )
    rows=[]
    for name,changes,equipped in scenarios:
        modified=replace(world,weather=replace(world.weather,**changes))
        gear=player.equipment if equipped else player.equipment-frozenset(("instrument_navigation",))
        traveler=replace(player,equipment=gear)
        try:
            route=find_route(modified,traveler,modified.destinations[0])
        except ExpeditionError as exc:
            if str(exc)!="no traversable route under current abilities and stamina":
                raise
            rows.append({"name":name,"world":modified.digest,"won":False,
                         "reason":"authoritatively_not_traversable"})
            continue
        proof=verify_route(modified,traveler,route)
        if not proof["final_state"]["won"]:
            raise ExpeditionError("weather scenario did not win executed game")
        rows.append({"name":name,"world":modified.digest,"won":True,
                     "route":route.digest,"receipt":proof["receipt_head"]})
    if not rows[0]["won"]:
        raise ExpeditionError("baseline world gameplay cannot complete")
    return _seal({
        "schema":"skeleton.game.campaign_weather_stress.v1",
        "world":world.digest,"scenarios":rows,
        "wins":sum(row["won"] for row in rows),
        "blocked":sum(not row["won"] for row in rows),
        "environmental_sensor_evidence":False,
    })


def audit_frames(world:ExpeditionWorld,player:Traveler, *, subdivisions:int=8)->dict:
    """M5: source-bound between-frame journal; authoritative gameplay replay."""
    if (not isinstance(world,ExpeditionWorld) or not isinstance(player,Traveler)
            or type(subdivisions) is not int or not 2<=subdivisions<=32):
        raise ExpeditionError("invalid authored frame chunk scope")
    route=find_route(world,player,world.destinations[0])
    proof=verify_route(world,player,route)
    if not proof["final_state"]["won"]:
        raise ExpeditionError("frame timeline must be derived from winning game")
    head=_digest({"world":world.digest,"route":route.digest,"genesis":True})
    frames=[]
    for edge_id in route.edge_ids:
        edge=world.by_edge[edge_id]
        a,b=world.by_id[edge.source],world.by_id[edge.target]
        for n in range(1,subdivisions+1):
            if len(frames)>=4096:
                raise ExpeditionError("too many authored frame chunks")
            t=n/subdivisions
            blend=t*t*(3-2*t)
            xyz=[round(v+(w-v)*blend,6) for v,w in zip(
                (a.x_m,a.y_m,a.altitude_m),(b.x_m,b.y_m,b.altitude_m))]
            row={"frame":len(frames),"edge":edge_id,"segment":n,
                 "xyz_m":xyz,"previous":head,
                 "gameplay_receipt":proof["receipt_head"]}
            row["receipt_digest"]=_digest(row)
            head=row["receipt_digest"]
            frames.append(row)
    return _seal({
        "schema":"skeleton.game.campaign_frame_continuity.v1",
        "world":world.digest,"route":route.digest,
        "gameplay_receipt":proof["receipt_head"],
        "subdivisions":subdivisions,"count":len(frames),
        "frames":frames,"head":head,
        "native_rendered_frames_recorded":0,
    })


def audit_assets(world:ExpeditionWorld, forged:Mapping, *, max_triangles:int=25000)->dict:
    """M6: validate actual OBJ hashes and complete coarse/fine LOD budgets."""
    if (not isinstance(world,ExpeditionWorld) or not isinstance(forged,Mapping)
            or type(max_triangles) is not int or not 256<=max_triangles<=10_000_000):
        raise ExpeditionError("asset QA requires finite budget and canonical source")
    manifest=forged.get("manifest")
    files=forged.get("files")
    if not isinstance(manifest,Mapping) or not isinstance(files,Mapping):
        raise ExpeditionError("missing original mesh manifest")
    if (manifest.get("world_digest")!=world.digest or
            manifest.get("receipt_digest")!=_digest({
                k:v for k,v in manifest.items() if k!="receipt_digest"})):
        raise ExpeditionError("mesh manifest is not bound to original world")
    by_node={}
    entries=manifest.get("assets",())
    if not isinstance(entries,list) or len(entries)>8192:
        raise ExpeditionError("mesh catalog exceeds bounded source scope")
    for entry in entries:
        if not isinstance(entry,Mapping):
            raise ExpeditionError("mesh inventory row invalid")
        waypoint,lod,tri,path,sha=(entry.get(k) for k in
                                  ("waypoint","lod","triangles","mesh_path","sha256"))
        if (waypoint not in world.by_id or type(lod) is not int or not 0<=lod<=3
                or type(tri) is not int or tri<=0 or type(path) is not str
                or type(sha) is not str):
            raise ExpeditionError("mesh row has invalid authored geometry")
        content=files.get(path)
        if type(content) is not str or sha256(content.encode()).hexdigest()!=sha:
            raise ExpeditionError("mesh byte digest does not match original OBJ")
        lods=by_node.setdefault(waypoint,{})
        if lod in lods:
            raise ExpeditionError("duplicate waypoint mesh LOD")
        lods[lod]=tri
    expected=set(range(len(manifest.get("lod_segments",()))))
    if (len(entries)!=manifest.get("count") or set(by_node)!=set(world.by_id)
            or any(set(levels)!=expected for levels in by_node.values())):
        raise ExpeditionError("LOD coverage incomplete for original world")
    high=sum(levels[0] for levels in by_node.values())
    low=sum(levels[max(levels)] for levels in by_node.values())
    return _seal({
        "schema":"skeleton.game.campaign_original_asset_budget.v1",
        "world":world.digest,"manifest_receipt":manifest["receipt_digest"],
        "checked_objs":len(entries),"checked_nodes":len(by_node),
        "full_quality_triangles":high,"low_detail_triangles":low,
        "triangle_budget":max_triangles,
        "full_quality_fits":high<=max_triangles,
        "low_detail_fits":low<=max_triangles,
        "native_gpu_profiled":False,
    })


def _seal(record:dict)->dict:
    record["receipt_digest"]=_digest(record)
    return record


def compile_seven_campaign_audits(world:ExpeditionWorld,player:Traveler,
                                 forged:Mapping)->dict:
    """M7: independently regenerate receipts; unsigned releases remain blocked."""
    sources={
        "topology":audit_topology(world),
        "instruments":audit_instruments(world),
        "objectives":audit_objectives(world,player),
        "weather":audit_weather(world,player),
        "frames":audit_frames(world,player),
        "assets":audit_assets(world,forged),
    }
    for value in sources.values():
        if value["world"]!=world.digest or value["receipt_digest"]!=_digest({
                k:v for k,v in value.items() if k!="receipt_digest"}):
            raise ExpeditionError("campaign audit failed independent hash replay")
    blocked=[]
    if sources["topology"]["unreachable_destinations"]:
        blocked.append("authored_graph_destination")
    if not sources["assets"]["low_detail_fits"]:
        blocked.append("low_detail_resource_budget")
    delivery=_seal({
        "schema":"skeleton.game.campaign_seven_audits.v1",
        "world":world.digest,"axes":list(AXES),
        "source_receipts":{k:v["receipt_digest"] for k,v in sorted(sources.items())},
        "source_checks_passed":not blocked,"source_blockers":blocked,
        "production_blockers":[
            "native_playthrough_not_attested",
            "independent_rights_review_missing",
            "physical_controller_not_qualified",
            "long_term_uptime_not_measured",
        ],
        "production_release_approved":False,
        "legal_review_signed":False,
    })
    return {**sources,"delivery":delivery}


def verify_seven_campaign_audits(world:ExpeditionWorld,player:Traveler,
                                 forged:Mapping,record:Mapping)->None:
    if not isinstance(record,Mapping) or dict(record)!=compile_seven_campaign_audits(
        world,player,forged):
        raise ExpeditionError("seven original-campaign audit receipts are forged or stale")
