"""Sigma, Omega, smash, Map. Lite combinatorial model."""

from __future__ import annotations

from skeleton.motive.space import Pointed, sphere


def smash(a: Pointed, b: Pointed) -> Pointed:
    pts = {"*"}
    for x in a.points:
        if x == a.base:
            continue
        for y in b.points:
            if y == b.base:
                continue
            pts.add(x + "#" + y)
    return Pointed("smash(%s,%s)" % (a.name, b.name), "*", frozenset(pts))


def suspend(x: Pointed) -> Pointed:
    return smash(x, sphere())


def mapping_space(src: Pointed, tgt: Pointed) -> Pointed:
    extras_src = sorted(p for p in src.points if p != src.base)
    extras_tgt = sorted(p for p in tgt.points if p != tgt.base)
    pts = {"*"}
    if extras_src and extras_tgt:
        for t in extras_tgt:
            pts.add("map:" + t)
    return Pointed("Map(%s,%s)" % (src.name, tgt.name), "*", frozenset(pts))


def loop_space(x: Pointed) -> Pointed:
    return mapping_space(sphere(), x)


def omega_sigma(x: Pointed) -> Pointed:
    return loop_space(suspend(x))


def omega_sigma_iso_id(x: Pointed) -> bool:
    back = omega_sigma(x)
    extra_x = len(x.points) - 1
    extra_back = len(back.points) - 1
    return extra_back == extra_x


def map_s_s_is_s() -> bool:
    s = sphere()
    m = mapping_space(s, s)
    return (len(m.points) - 1) == (len(s.points) - 1)
