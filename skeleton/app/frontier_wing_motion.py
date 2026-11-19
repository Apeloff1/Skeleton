"""Continuous three-axis stroke, twist and extension envelope for wing anchors."""
from __future__ import annotations
import math
from skeleton.jeeves.game_frontier_production import Vec3
from skeleton.app.frontier_wing_model import landmarks


def smoothstep(x):
    x=max(0.,min(1.,x))
    return x*x*x*(x*(x*6-15)+10)


def phase_weight(previous,target,offset,transition):
    # Quintic interpolation has zero first and second derivatives at both ends.
    return previous+(target-previous)*smoothstep(offset/transition)


def rotate_x(v,a):
    c,s=math.cos(a),math.sin(a)
    return Vec3(v.x,v.y*c-v.z*s,v.y*s+v.z*c)


def rotate_y(v,a):
    c,s=math.cos(a),math.sin(a)
    return Vec3(v.x*c+v.z*s,v.y,-v.x*s+v.z*c)


def rotate_z(v,a):
    c,s=math.cos(a),math.sin(a)
    return Vec3(v.x*c-v.y*s,v.x*s+v.y*c,v.z)


def pose_landmarks(order,side,phase,weight):
    root,elbow,*tips=landmarks(order,side)
    stroke=order.amplitude*math.sin(phase)*weight
    # Distal response lags the shoulder. Wing twist changes sign across a beat,
    # while a gliding wing remains extended with a small fixed dihedral.
    distal=order.amplitude*.22*math.sin(phase-.48)*weight
    sweep=.13*weight*(1-math.cos(phase))*.5
    twist=.20*weight*math.sin(phase-.35)
    def proximal(v):
        return rotate_y(rotate_z(v,-side*sweep),-side*(stroke+.045))
    moved_elbow=root+proximal(elbow-root)
    points=[]
    for tip in tips:
        direction=tip-elbow
        local=rotate_x(direction,twist)
        local=rotate_y(local,-side*distal)
        points.append(moved_elbow+proximal(local))
    return root,tuple(points)


def anchors(order,geometry,phase,weight):
    all_points={side:pose_landmarks(order,side,phase,weight) for side in (-1,1)}
    result=[]
    n=order.subdivisions
    for side,weights in geometry.coordinates:
        root,tips=all_points[side]
        value=root.scaled((n-sum(weights))/n)
        for tip,k in zip(tips,weights,strict=True):
            value=value+tip.scaled(k/n)
        # Small continuous camber goes to zero on every constrained radial edge.
        nonzero=[k for k in weights if k]
        if len(nonzero)==2 and sum(weights)<n:
            i,j=nonzero
            fraction=27*(i/n)*(j/n)*(1-sum(weights)/n)
            camber=order.chord*.045*fraction*(1+.3*math.cos(phase)*weight)
            value=value+Vec3(0,0,camber)
        result.append(value)
    return tuple(result)
