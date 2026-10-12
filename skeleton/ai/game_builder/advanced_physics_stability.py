"""Deterministic low-energy support/sleep state for authored physical cargo.

Resting bodies settle only on real floor or horizontal signed platforms, with
finite speed/spin thresholds and consecutive-frame evidence. Any new player
impulse, torque, motor operation or dynamic collision must wake them.
"""
from __future__ import annotations

from .advanced_physics_oriented import box_vertices


def has_support(body,state):
    if body["broken"]:
        return False
    corners=box_vertices(body["position"],body["shape_half"],body["orientation"])
    bottom=max(point[1] for point in corners)
    if abs(state["floor_y"]*100-bottom)<=2:
        return True
    for fixture in state["fixtures"]:
        # An inclined or moving-looking surface is not a certified standing
        # support; this reference supports only original level platforms.
        if fixture["orientation"]!=0 or not body["mask"] & fixture["layer"]:
            continue
        ceiling=fixture["position"][1]-fixture["half_size"][1]
        if abs(bottom-ceiling)>2:
            continue
        left=fixture["position"][0]-fixture["half_size"][0]
        right=fixture["position"][0]+fixture["half_size"][0]
        if any(left<=point[0]<=right for point in corners):
            return True
    return False


def is_sleeping(body,state,config):
    return (
        body["sleep"]>=config["sleep_frames"] and
        max(abs(v) for v in body["velocity"])==0 and
        body["angular_velocity"]==0 and
        not ((state["fan"] or state["magnet"]) and state["battery"]>0) and
        has_support(body,state)
    )


def settle(state,config,events):
    sleepers=0
    for body in state["bodies"]:
        if body["broken"]:
            body["sleep"]=0
            continue
        stable=(not ((state["fan"] or state["magnet"]) and state["battery"]>0) and
                max(abs(v) for v in body["velocity"])<=config["rest_speed"] and
                abs(body["angular_velocity"])<=config["rest_spin"] and
                has_support(body,state))
        if stable:
            before=body["sleep"]
            body["sleep"]=min(config["sleep_frames"],before+1)
            if body["sleep"]>=config["sleep_frames"]:
                body["velocity"]=[0,0,0]
                body["angular_velocity"]=0
                sleepers+=1
                if before<config["sleep_frames"]:
                    state["rest_stabilizations"]+=1
                    events.append("original_body_earned_stable_floor_rest")
        else:
            body["sleep"]=0
    state["sleeping_bodies"]=sleepers


__all__=["settle","has_support","is_sleeping"]
