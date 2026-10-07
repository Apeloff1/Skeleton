"""Deterministic serialization of spine chains (JSON-friendly dicts)."""

from __future__ import annotations

from typing import Any

from skeleton.spine.chain import SpineChain, default_chain, rebind_segments
from skeleton.spine.segment import Segment, SegmentId, DiscProps, build_segments
from skeleton.spine.vertebra import Pose6, Vertebra, make_vertebra, ZERO_POSE


def pose_to_dict(p: Pose6) -> dict[str, float]:
    return {"rx": p.rx, "ry": p.ry, "rz": p.rz, "tx": p.tx, "ty": p.ty, "tz": p.tz}


def pose_from_dict(d: dict[str, float]) -> Pose6:
    return Pose6(d["rx"], d["ry"], d["rz"], d["tx"], d["ty"], d["tz"])


def vertebra_to_dict(v: Vertebra) -> dict[str, Any]:
    return {
        "label": v.label,
        "pose": pose_to_dict(v.pose),
        "fused": v.fused,
        "tags": list(v.tags),
        "dims": {
            "height_mm": v.dims.height_mm,
            "depth_mm": v.dims.depth_mm,
            "width_mm": v.dims.width_mm,
            "pedicle_mm": v.dims.pedicle_mm,
        },
    }


def segment_to_dict(s: Segment) -> dict[str, Any]:
    return {
        "label": s.label,
        "cranial": s.sid.cranial,
        "caudal": s.sid.caudal,
        "index": s.sid.index,
        "relative": pose_to_dict(s.relative),
        "locked": s.locked,
        "disc": {
            "height_mm": s.disc.height_mm,
            "radius_mm": s.disc.radius_mm,
            "young_mpa": s.disc.young_mpa,
            "shear_mpa": s.disc.shear_mpa,
        },
    }


def chain_to_dict(chain: SpineChain) -> dict[str, Any]:
    return {
        "name": chain.name,
        "vertebrae": [vertebra_to_dict(v) for v in chain.vertebrae],
        "segments": [segment_to_dict(s) for s in chain.segments],
    }


def chain_from_dict(d: dict[str, Any]) -> SpineChain:
    vertebrae = []
    for vd in d["vertebrae"]:
        v = make_vertebra(vd["label"], pose_from_dict(vd["pose"]), fused=vd.get("fused"))
        if vd.get("tags"):
            v = v.with_tags(*vd["tags"])
        vertebrae.append(v)
    segs_in = d["segments"]
    # rebuild then overlay relatives
    base = tuple(vertebrae)
    segs = list(build_segments(base))
    by_label = {sd["label"]: sd for sd in segs_in}
    out_segs = []
    for s in segs:
        sd = by_label[s.label]
        out_segs.append(
            Segment(
                sid=s.sid,
                disc=DiscProps(
                    sd["disc"]["height_mm"],
                    sd["disc"]["radius_mm"],
                    sd["disc"]["young_mpa"],
                    sd["disc"]["shear_mpa"],
                ),
                relative=pose_from_dict(sd["relative"]),
                locked=sd["locked"],
            )
        )
    return SpineChain(vertebrae=base, segments=tuple(out_segs), name=d.get("name", "loaded"))


def roundtrip_ok(chain: SpineChain | None = None) -> bool:
    from skeleton.spine.digest import chain_digest

    c = chain or default_chain()
    d = chain_to_dict(c)
    c2 = chain_from_dict(d)
    return chain_digest(c) == chain_digest(c2)


def compact_relatives(chain: SpineChain) -> dict[str, list[float]]:
    return {s.label: list(s.relative.as_tuple()) for s in chain.segments}
