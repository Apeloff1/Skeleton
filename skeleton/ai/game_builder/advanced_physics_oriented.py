"""Authored, deterministic 2D oriented-box SAT contacts in the physics reference.

Angles are integer millidegrees and evaluated on a fixed one-degree lookup,
without runtime platform-libm dependence. In 3D these are Z-extruded boxes,
not arbitrary 3-axis quaternion rigid bodies. CCD remains axis-aligned and
separate; rotational SAT here resolves post-integration manifolds.
"""
from __future__ import annotations

from math import isqrt

from .advanced_physics_dynamics import transfer_collision_spin

Q = 10000
SIN_0_90 = (0, 175, 349, 523, 698, 872, 1045, 1219, 1392, 1564, 1736, 1908, 2079, 2250, 2419, 2588, 2756, 2924, 3090, 3256, 3420, 3584, 3746, 3907, 4067, 4226, 4384, 4540, 4695, 4848, 5000, 5150, 5299, 5446, 5592, 5736, 5878, 6018, 6157, 6293, 6428, 6561, 6691, 6820, 6947, 7071, 7193, 7314, 7431, 7547, 7660, 7771, 7880, 7986, 8090, 8192, 8290, 8387, 8480, 8572, 8660, 8746, 8829, 8910, 8988, 9063, 9135, 9205, 9272, 9336, 9397, 9455, 9511, 9563, 9613, 9659, 9703, 9744, 9781, 9816, 9848, 9877, 9903, 9925, 9945, 9962, 9976, 9986, 9994, 9998, 10000)
MAX_MANIFOLDS = 16


def _sine(degree):
    deg = degree % 360
    if deg <= 90:
        return SIN_0_90[deg]
    if deg <= 180:
        return SIN_0_90[180-deg]
    if deg <= 270:
        return -SIN_0_90[deg-180]
    return -SIN_0_90[360-deg]


def sin_cos(angle):
    # Authored physics state uses millidegrees; integer rounding is specified.
    degree = (angle + 500) // 1000
    return _sine(degree), _sine(degree+90)


def box_vertices(position, half_size, angle):
    sine, cosine = sin_cos(angle)
    cx, cy = position[:2]
    hx, hy = half_size[:2]
    vertices = []
    for dx, dy in ((-hx,-hy),(hx,-hy),(hx,hy),(-hx,hy)):
        vertices.append([
            cx + (dx*cosine-dy*sine)//Q,
            cy + (dx*sine+dy*cosine)//Q,
        ])
    return vertices


def sat_manifold(shape_a, shape_b):
    """Return a conservative integer contact normal, depth and point.

    SAT uses all four face normals; ties resolve deterministically by axis
    order and source object order. No false client-supplied penetration values.
    """
    a = box_vertices(shape_a["position"], shape_a["half_size"],
                     shape_a["orientation"])
    b = box_vertices(shape_b["position"], shape_b["half_size"],
                     shape_b["orientation"])
    if ("z_radius" in shape_a and "z_radius" in shape_b and
        abs(shape_a["position"][2]-shape_b["position"][2]) >=
        shape_a["z_radius"]+shape_b["z_radius"]):
        return None
    best_depth = None
    best_axis = None
    for v in (a,b):
        for i in (0,1):
            e=[v[i+1][j]-v[i][j] for j in (0,1)]
            axis=[-e[1],e[0]]
            if not any(axis):
                continue
            proj_a=[p[0]*axis[0]+p[1]*axis[1] for p in a]
            proj_b=[p[0]*axis[0]+p[1]*axis[1] for p in b]
            # Distance to the nearest separating face, including containment.
            overlap=min(max(proj_a)-min(proj_b),
                        max(proj_b)-min(proj_a))
            if overlap <= 0:
                return None
            length=isqrt(axis[0]**2+axis[1]**2)
            depth=max(1,(overlap + length - 1)//length)
            if best_depth is None or depth<best_depth:
                delta=[shape_b["position"][j]-shape_a["position"][j]
                       for j in (0,1)]
                direction=1 if delta[0]*axis[0]+delta[1]*axis[1]>=0 else -1
                best_axis=[direction*axis[0]*Q//length,
                           direction*axis[1]*Q//length]
                best_depth=depth
    if best_depth is None:
        return None
    # Midpoint of closest opposing support vertices, from reviewed geometry.
    support_a=max(a,key=lambda p:p[0]*best_axis[0]+p[1]*best_axis[1])
    support_b=min(b,key=lambda p:p[0]*best_axis[0]+p[1]*best_axis[1])
    return {"normal":best_axis,"depth":best_depth,
            "point":[(support_a[i]+support_b[i])//2 for i in (0,1)]}


def _body_shape(body,state):
    result={
        "position":body["position"],
        "half_size":body["shape_half"],
        "orientation":body["orientation"],
    }
    if state["depth"]>1:
        result["z_radius"]=body["radius"]
    return result


def _fixture_shape(fixture,state):
    result={
        "position":fixture["position"],
        "half_size":fixture["half_size"],
        "orientation":fixture["orientation"],
    }
    if state["depth"]>1:
        result["z_radius"]=fixture["half_size"][2]
    return result


def _record(state,kind,normal,depth,point,events):
    state["oriented_contacts"]+=1
    record={"frame":state["frame"],"kind":kind,"normal":normal,
            "penetration":depth,"point":point}
    state["contact_manifolds"].append(record)
    if len(state["contact_manifolds"])>MAX_MANIFOLDS:
        state["contact_manifolds"].pop(0)
    events.append("oriented_"+kind+"_manifold_resolved")


def oriented_world(body,state,config,events):
    """Bound all four rotated corners, even with non-square boxes."""
    verts=box_vertices(body["position"],body["shape_half"],body["orientation"])
    axes=((0,0,(state["width"]-1)*100),
          (1,0,state["floor_y"]*100))
    for axis,lo,hi in axes:
        lower=min(vertex[axis] for vertex in verts)
        upper=max(vertex[axis] for vertex in verts)
        move = lo-lower if lower<lo else hi-upper if upper>hi else 0
        if move:
            body["position"][axis]+=move
            if body["velocity"][axis]*move<0:
                body["velocity"][axis]=-body["velocity"][axis]*config["wall_restitution"]//100
            state["contacts"]+=1
            _record(state,"world",[Q if axis==0 else 0,
                                    Q if axis==1 else 0],abs(move),
                    body["position"][:2],events)
            verts=box_vertices(body["position"],body["shape_half"],
                               body["orientation"])
    if state["depth"]>1:
        z=body["position"][2]
        lo=body["radius"];hi=(state["depth"]-1)*100-body["radius"]
        if z<lo or z>hi:
            body["position"][2]=max(lo,min(hi,z))
            body["velocity"][2]=-body["velocity"][2]*config["wall_restitution"]//100
            state["contacts"]+=1
            events.append("bounded_oriented_world_depth_contact")


def oriented_static(body,state,config,events):
    for fixture in state["fixtures"]:
        if not (body["mask"]&fixture["layer"]):
            continue
        m=sat_manifold(_body_shape(body,state),_fixture_shape(fixture,state))
        if not m:
            continue
        n=m["normal"]
        depth=m["depth"]
        for j in (0,1):
            body["position"][j]-=n[j]*(depth+1)//Q
        projected=sum(body["velocity"][j]*n[j] for j in (0,1))//Q
        if projected>0:
            bounce=projected*(100+config["wall_restitution"])//100
            for j in (0,1):
                body["velocity"][j]-=bounce*n[j]//Q
        for j in (0,1):
            tangent=body["velocity"][j]-(sum(body["velocity"][k]*n[k]
                         for k in (0,1))//Q)*n[j]//Q
            body["velocity"][j]-=tangent*config["contact_friction"]//100
        state["contacts"]+=1
        _record(state,"fixture",n,depth,m["point"],events)
        oriented_world(body,state,config,events)


def oriented_pairs(state,config,events):
    bodies=state["bodies"]
    for i,first in enumerate(bodies):
        if first["broken"]:
            continue
        for second in bodies[i+1:]:
            if second["broken"] or not (
                first["mask"]&second["layer"] and
                second["mask"]&first["layer"]):
                continue
            m=sat_manifold(_body_shape(first,state),_body_shape(second,state))
            if not m:
                continue
            n=m["normal"];depth=m["depth"]
            total=first["mass"]+second["mass"]
            moved_first=max(1,depth*second["mass"]//total)
            moved_second=max(1,depth-moved_first)
            for j in (0,1):
                first["position"][j]-=n[j]*moved_first//Q
                second["position"][j]+=n[j]*moved_second//Q
            relative=sum((first["velocity"][j]-second["velocity"][j])*n[j]
                         for j in (0,1))//Q
            if relative>0:
                restitution=min(config["wall_restitution"],
                    config["material_restitution"])
                impulse=relative*(100+restitution)//100
                amount_a=impulse*second["mass"]//total
                amount_b=impulse-amount_a
                for j in (0,1):
                    first["velocity"][j]-=amount_a*n[j]//Q
                    second["velocity"][j]+=amount_b*n[j]//Q
                spin_axis=0 if abs(n[0])>=abs(n[1]) else 1
                transfer_collision_spin(first,second,spin_axis,1,
                                        impulse,range(2),config)
                for body in (first,second):
                    if not body["broken"] and impulse>=body["break_threshold"]:
                        body["broken"]=True
                        state["fractures"]+=1
            state["contacts"]+=1
            _record(state,"dynamic",n,depth,m["point"],events)
            oriented_world(first,state,config,events)
            oriented_world(second,state,config,events)


__all__=["sin_cos","box_vertices","sat_manifold","oriented_world",
         "oriented_static","oriented_pairs"]
