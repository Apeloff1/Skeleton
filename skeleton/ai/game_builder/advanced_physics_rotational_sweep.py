"""Deterministic swept rotation and spatial-hash candidate selection for original physics.

This pipeline uses bounded temporal SAT sampling of authored XY oriented
rectangles, including static rotated fixtures and moving body pairs. Swept
envelopes conservatively include all intermediate orientations. It is not a
mathematically exact rotating-convex time-of-impact solver: contacts thinner
than the finite sample interval remain an explicit reference-engine limit.
"""
from __future__ import annotations

from .advanced_physics_contact_custody import record_fixture_contact

from math import isqrt

from .advanced_physics_oriented import (
    Q, _record, _body_shape, _fixture_shape, sat_manifold,
    oriented_world,
)
from .advanced_physics_dynamics import transfer_collision_spin


def _delta_angle(old, new):
    return (new-old+180000)%360000-180000


def _interpolate(start, end, step, total):
    return [a+(b-a)*step//total for a,b in zip(start,end)]


def _sample(body, old_position, old_angle, step, total, depth):
    angle = (old_angle + _delta_angle(old_angle,body["orientation"])*step//total)%360000
    shape = {
        "position":_interpolate(old_position,body["position"],step,total),
        "half_size":body["shape_half"],
        "orientation":angle,
    }
    if depth > 1:
        shape["z_radius"]=body["radius"]
    return shape


def _envelope(body, previous):
    radius=isqrt(sum(axis*axis for axis in body["shape_half"]))+2
    zrad=body["radius"]
    return (
        min(previous[0],body["position"][0])-radius,
        max(previous[0],body["position"][0])+radius,
        min(previous[1],body["position"][1])-radius,
        max(previous[1],body["position"][1])+radius,
        min(previous[2],body["position"][2])-zrad,
        max(previous[2],body["position"][2])+zrad,
    )


def _fixture_envelope(fixture):
    radial=isqrt(sum(axis*axis for axis in fixture["half_size"][:2]))+2
    x,y,z=fixture["position"]
    return (
        x-radial,x+radial,y-radial,y+radial,
        z-fixture["half_size"][2],z+fixture["half_size"][2],
    )


def _overlap(a,b,depth):
    return (a[0]<=b[1] and b[0]<=a[1] and a[2]<=b[3] and b[2]<=a[3]
            and (depth==1 or (a[4]<=b[5] and b[4]<=a[5])))


def _cells(rect,cell_size,depth):
    # Bounded original worlds; use source-backed integer grid, not a
    # platform-specific hash iteration order.
    for x in range(rect[0]//cell_size,rect[1]//cell_size+1):
        for y in range(rect[2]//cell_size,rect[3]//cell_size+1):
            if depth==1:
                yield (x,y,0)
            else:
                for z in range(rect[4]//cell_size,rect[5]//cell_size+1):
                    yield (x,y,z)


def candidates(state,previous,config):
    """Return stable candidate pairs and fixture indices (no false negatives).

    Expansion by a full circumscribing radius conservatively encloses any
    intermediate XY rotation, not just frame-end orientation.
    """
    bodies=state["bodies"]
    depth=state["depth"]
    step=config["broadphase_cell_size"]
    body_bounds=[_envelope(b,previous[b["id"]]) for b in bodies]
    static_bounds=[_fixture_envelope(f) for f in state["fixtures"]]
    buckets={}
    for i,(body,rect) in enumerate(zip(bodies,body_bounds)):
        if body["broken"]:
            continue
        for cell in _cells(rect,step,depth):
            buckets.setdefault(cell,[]).append(i)
    pairs=set()
    for items in buckets.values():
        for i,item in enumerate(items):
            for other in items[i+1:]:
                if item != other:
                    pairs.add((min(item,other),max(item,other)))
    pairs=tuple(sorted((i,j) for i,j in pairs if (
        bodies[i]["mask"] & bodies[j]["layer"] and
        bodies[j]["mask"] & bodies[i]["layer"] and
        _overlap(body_bounds[i],body_bounds[j],depth)
    )))
    fixture_pairs=[]
    for fi,(fixture,bounds) in enumerate(zip(state["fixtures"],static_bounds)):
        for bi,body in enumerate(bodies):
            if (not body["broken"] and body["mask"] & fixture["layer"]
                    and _overlap(body_bounds[bi],bounds,depth)):
                fixture_pairs.append((bi,fi))
    return pairs,tuple(fixture_pairs)


def _samples(config, body_a, before_a, angle_a, body_b=None,
             before_b=None,angle_b=None):
    axes=range(3 if config["dimension"]=="3d" else 2)
    motion=max(abs(body_a["position"][j]-before_a[j]) for j in axes)
    angle=abs(_delta_angle(angle_a,body_a["orientation"]))
    spin=(angle*max(body_a["shape_half"])+57299)//57300
    if body_b is not None:
        motion=max(abs((body_a["position"][j]-before_a[j]) -
                       (body_b["position"][j]-before_b[j])) for j in axes)
        turn=abs(_delta_angle(angle_b,body_b["orientation"]))
        spin+=(turn*max(body_b["shape_half"])+57299)//57300
    # A sample every ~3 original world units, with a minimum 8 samples
    # for moving/rotating objects and an absolute device-budget ceiling.
    return min(config["oriented_sweep_budget"],
               max(8,(motion+spin+2)//3))


def _collide_at(body,old_pos,old_angle,other_shape,tick,total,depth):
    return sat_manifold(_sample(body,old_pos,old_angle,tick,total,depth),
                        other_shape)


def _restore(body,old_pos,old_angle,sample,total):
    endpoint=body["position"][:]
    end_angle=body["orientation"]
    body["position"]=_interpolate(old_pos,endpoint,sample,total)
    body["orientation"]=(old_angle+_delta_angle(old_angle,end_angle)*sample//total)%360000


def _bounce_static(body,manifold,config):
    n=manifold["normal"]
    closing=sum(body["velocity"][j]*n[j] for j in (0,1))//Q
    if closing>0:
        restitution=min(config["wall_restitution"],
                        config["material_restitution"])
        impact=closing*(100+restitution)//100
        for j in (0,1):
            body["velocity"][j]-=impact*n[j]//Q
    tangent=sum(body["velocity"][j]*(-n[1] if j==0 else n[0])
                for j in (0,1))//Q
    for j,turn in enumerate((-n[1],n[0])):
        body["velocity"][j]-=tangent*turn*config["contact_friction"]//(100*Q)


def swept_fixtures(body,state,config,old_position,old_angle,indices,events):
    """Conservatively terminate movement at the last non-contact sample."""
    if not indices:
        return False
    depth=state["depth"]
    samples=_samples(config,body,old_position,old_angle)
    for index in indices:
        fixture=state["fixtures"][index]
        target=_fixture_shape(fixture,state)
        start=_sample(body,old_position,old_angle,0,samples,depth)
        state["oriented_sat_evaluations"]+=1
        if sat_manifold(start,target):
            # Existing discrete SAT is responsible for initially overlapping
            # dynamics; never mine a fresh swept collision from prior overlap.
            continue
        for tick in range(1,samples+1):
            state["oriented_sat_evaluations"]+=1
            hit=_collide_at(body,old_position,old_angle,target,tick,samples,depth)
            if hit is None:
                continue
            _restore(body,old_position,old_angle,tick-1,samples)
            _bounce_static(body,hit,config)
            state["contacts"]+=1
            state["rotating_swept_contacts"]+=1
            _record(state,"rotating_swept_fixture",
                    hit["normal"],hit["depth"],hit["point"],events)
            record_fixture_contact(state,body,index,"rotating_swept_fixture")
            oriented_world(body,state,config,events)
            return True
    return False


def swept_pairs(state,config,previous,old_angles,pairs,events):
    """Resolve swept rotational SAT for source-ordered moving body pairs.

    One earliest sampled contact per canonical pair per substep. Finite
    stepping and deterministic source ordering keep the replay bounded.
    """
    bodies=state["bodies"]
    depth=state["depth"]
    for i,j in pairs:
        a,b=bodies[i],bodies[j]
        if a["broken"] or b["broken"]:
            continue
        start_a=previous[a["id"]]
        start_b=previous[b["id"]]
        angle_a=old_angles[a["id"]]
        angle_b=old_angles[b["id"]]
        nsteps=_samples(config,a,start_a,angle_a,b,start_b,angle_b)
        initial=sat_manifold(
            _sample(a,start_a,angle_a,0,nsteps,depth),
            _sample(b,start_b,angle_b,0,nsteps,depth))
        state["oriented_sat_evaluations"]+=1
        if initial:
            continue
        for tick in range(1,nsteps+1):
            manifold=sat_manifold(
                _sample(a,start_a,angle_a,tick,nsteps,depth),
                _sample(b,start_b,angle_b,tick,nsteps,depth))
            state["oriented_sat_evaluations"]+=1
            if manifold is None:
                continue
            # Movement terminates at the last non-penetrating sample; the
            # manifold at collision still owns the normal and contact point.
            _restore(a,start_a,angle_a,tick-1,nsteps)
            _restore(b,start_b,angle_b,tick-1,nsteps)
            normal=manifold["normal"]
            closing=sum((a["velocity"][k]-b["velocity"][k])*normal[k]
                        for k in (0,1))//Q
            if closing>0:
                restitution=min(config["wall_restitution"],
                                config["material_restitution"])
                impulse=closing*(100+restitution)//100
                total=a["mass"]+b["mass"]
                impulse_a=impulse*b["mass"]//total
                impulse_b=impulse-impulse_a
                for k in (0,1):
                    a["velocity"][k]-=impulse_a*normal[k]//Q
                    b["velocity"][k]+=impulse_b*normal[k]//Q
                spin_axis=0 if abs(normal[0])>=abs(normal[1]) else 1
                transfer_collision_spin(a,b,spin_axis,1,impulse,
                                        range(2),config)
                for body in (a,b):
                    if not body["broken"] and impulse>=body["break_threshold"]:
                        body["broken"]=True
                        state["fractures"]+=1
            state["contacts"]+=1
            state["rotating_swept_contacts"]+=1
            _record(state,"rotating_swept_dynamic",normal,
                    manifold["depth"],manifold["point"],events)
            break


def solve_oriented_sweep(state,config,previous,old_angles,events):
    """Reconcile all reviewed swept contacts after fixed-step integration."""
    pairs,fixtures=candidates(state,previous,config)
    count_pairs=len(state["bodies"])*(len(state["bodies"])-1)//2
    count_static=len(state["bodies"])*len(state["fixtures"])
    state["broadphase_pairs"]+=len(pairs)
    state["broadphase_fixtures"]+=len(fixtures)
    state["broadphase_pruned"]+=max(
        0,count_pairs+count_static-len(pairs)-len(fixtures))
    selected={}
    for body_index,fixture_index in fixtures:
        selected.setdefault(body_index,[]).append(fixture_index)
    for i in sorted(selected):
        body=state["bodies"][i]
        if not body["broken"]:
            swept_fixtures(body,state,config,
                           previous[body["id"]],old_angles[body["id"]],
                           selected[i],events)
    swept_pairs(state,config,previous,old_angles,pairs,events)


__all__=["candidates","swept_fixtures","swept_pairs",
         "solve_oriented_sweep"]
