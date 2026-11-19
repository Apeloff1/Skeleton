"""Bounded supplied-frame acceptance with exact palette and temporal witnesses.

The caller supplies untrusted RGB/mask data; nothing here captures a renderer,
authenticates a screenshot, evaluates 3D deformation or certifies art direction.
Canonical GF-I per-frame acceptance remains authoritative.
"""
from __future__ import annotations

from dataclasses import asdict
import re

from skeleton.app.recovered_evidence import (
    EvidenceError, array, fields, identifier, integer, digest, seal, pin,
)
from skeleton.game.art_acceptance import evaluate_frame, hex_to_rgb
from skeleton.ai.agents.jeeves.design_bible_assets_extended import (
    asset_quality_checklist, bible_section_template, era_style_notes,
)
from skeleton.ai.agents.jeeves.production_planning_extended import (
    risk_matrix, resource_outline, milestone_template,
)

MAX_PIXELS=900_000
MAX_FRAMES=128
HEX_RGB=re.compile(r"[0-9a-f]{6}\Z")
HEX_BYTES=re.compile(r"[0-9a-f]+\Z")


def _palette(raw,expected):
    if type(raw) is not dict or not 2<=len(raw)<=64:
        raise EvidenceError("palette size bound")
    for key,value in raw.items():
        identifier(key)
        if type(value) is not str or not HEX_RGB.fullmatch(value):
            raise EvidenceError("canonical RGB hex required")
    pin(digest(raw),expected)
    return {key:hex_to_rgb(value) for key,value in sorted(raw.items())}


def _decode(row,count):
    fields(row,{"index","rgb","mask"})
    rgb,mask=row["rgb"],row["mask"]
    if type(rgb) is not str or len(rgb)!=count*6 or not HEX_BYTES.fullmatch(rgb):
        raise EvidenceError("invalid RGB plane")
    if type(mask) is not str or len(mask)!=count or set(mask)-{"0","1"}:
        raise EvidenceError("invalid subject mask")
    return bytes.fromhex(rgb),mask


def _reference(raw,mask,width,height):
    image=[]
    subject=[]
    for y in range(height):
        start=y*width
        image.append([tuple(raw[3*i:3*i+3]) for i in range(start,start+width)])
        subject.append([mask[i]=="1" for i in range(start,start+width)])
    return image,subject


def _temporal(first,second):
    old,old_mask=first
    new,new_mask=second
    changed=sum(a!=b for a,b in zip(old_mask,new_mask,strict=True))
    overlap=sum(a==b=="1" for a,b in zip(old_mask,new_mask,strict=True))
    union=sum(a=="1" or b=="1" for a,b in zip(old_mask,new_mask,strict=True))
    count=len(old_mask)
    absolute=sum(abs(a-b) for a,b in zip(old,new,strict=True))
    return {"mask_change_ppm":changed*1_000_000//count,
            "mask_iou_ppm":overlap*1_000_000//union if union else 0,
            "rgb_mean_abs_change_ppm":absolute*1_000_000//(255*len(old))}


def qualify_frames(order,*,authorized):
    if authorized is not True:
        raise PermissionError("explicit frame qualification operator required")
    fields(order,{"schema","subject","era","tier","weeks","width","height","palette",
                  "expected_palette_digest","frames","max_mask_change_ppm","max_rgb_change_ppm"})
    if order["schema"]!="skeleton.studio-frame-qualification.order.v1":
        raise EvidenceError("unsupported sequence order")
    subject=identifier(order["subject"])
    era=order["era"]
    tier=order["tier"]
    if era not in ("8bit","16bit","handheld","32bit") or tier not in ("basic","polished","premium"):
        raise EvidenceError("unknown reviewed era or tier")
    weeks=integer(order["weeks"],1,260)
    width=integer(order["width"],2,512)
    height=integer(order["height"],2,512)
    count=width*height
    frames=array(order["frames"],2,MAX_FRAMES)
    if count*len(frames)>MAX_PIXELS:
        raise EvidenceError("sequence pixel ceiling")
    max_mask=integer(order["max_mask_change_ppm"],0,1_000_000)
    max_rgb=integer(order["max_rgb_change_ppm"],0,1_000_000)
    palette=_palette(order["palette"],order["expected_palette_digest"])
    results=[]
    transitions=[]
    previous=None
    for index,row in enumerate(frames):
        rgb,mask=_decode(row,count)
        if integer(row["index"],0,MAX_FRAMES-1)!=index:
            raise EvidenceError("frame index gap or reordering")
        frame,subject_mask=_reference(rgb,mask,width,height)
        report=evaluate_frame(frame,subject_mask,palette)
        results.append({"index":index,"frame_digest":digest(row),"passed":report.passed,
                        "metrics":report.metrics,"failure_labels":report.failures,
                        "supports":list(report.supports),"not_claimed":list(report.not_claimed)})
        if previous is not None:
            measured=_temporal(previous,(rgb,mask))
            passed=(measured["mask_change_ppm"]<=max_mask and measured["rgb_mean_abs_change_ppm"]<=max_rgb)
            transitions.append({"from":index-1,"to":index,"metrics":measured,"passed":passed})
        previous=(rgb,mask)
    all_frames=all(row["passed"] for row in results)
    all_transitions=all(row["passed"] for row in transitions)
    # The archived planning owners provide guidance only. Measured findings
    # create explicit follow-up items, never mark the original milestone done.
    followups=[]
    for row in results:
        if not row["passed"]:
            followups.append({"kind":"frame_acceptance","index":row["index"],
                              "action":"review supplied reference and canonical failure labels"})
    for row in transitions:
        if not row["passed"]:
            followups.append({"kind":"temporal_discontinuity","index":row["to"],
                              "action":"review capture continuity and subject transition"})
    return seal({"schema":"skeleton.studio-frame-qualification.report.v1",
                 "order_digest":digest(order),"subject":subject,
                 "palette_digest":order["expected_palette_digest"],"dimensions":[width,height],
                 "frames":results,"transitions":transitions,
                 "all_reference_frames_passed":all_frames,"all_transition_limits_passed":all_transitions,
                 "reference_sequence_passed":all_frames and all_transitions,
                 "production_guidance":{"bible":bible_section_template("visual acceptance"),
                     "asset_checklist":asset_quality_checklist(tier),"era_notes":era_style_notes(era),
                     "risks":risk_matrix(subject),"resources":resource_outline(weeks),
                     "milestones":milestone_template(),"followups":followups},
                 "supplied_frames_only":True,"renderer_executed":False,
                 "animation_quality_certified":False,"rights_certified":False,
                 "native_engine_executed":False,"release_certified":False})
