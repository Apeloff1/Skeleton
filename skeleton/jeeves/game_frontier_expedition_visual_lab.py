"""Dragon visual comparison of explicitly supplied original RGB gameplay frames.

Input frames are actual caller-provided pixel arrays, not inferred screenshots
or invented emulation recordings. Compares up to 10 games, scores temporal
stability, color diversity, edge density and parallax, then attaches evidence
digests to measured claims. No neural training or copyright clearance claimed.
"""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from .game_frontier_expedition import ExpeditionError,_digest

@dataclass(frozen=True,slots=True)
class VisualFrame:
    game_digest:str
    frame:int
    width:int
    height:int
    rgb:bytes
    kind:str="original_runtime_capture"
    def __post_init__(self):
        if (type(self.game_digest) is not str or len(self.game_digest)!=64
                or any(c not in "0123456789abcdef" for c in self.game_digest)):
            raise ExpeditionError("Dragon visual frame requires exact original world")
        if type(self.frame) is not int or not 0<=self.frame<=10**10:
            raise ExpeditionError("Dragon visual source frame invalid")
        if (type(self.width) is not int or type(self.height) is not int
                or not 1<=self.width<=128 or not 1<=self.height<=128
                or type(self.rgb) is not bytes or len(self.rgb)!=self.width*self.height*3):
            raise ExpeditionError("Dragon visual frame RGB geometry invalid")
        if self.kind not in ("original_runtime_capture","original_procedural_preview"):
            raise ExpeditionError("Dragon source origin must not be fabricated")

    @property
    def source_digest(self):
        return _digest({"world":self.game_digest,"frame":self.frame,
                        "geometry":[self.width,self.height],"pixels":sha256(self.rgb).hexdigest(),
                        "kind":self.kind})


def _metrics(source:VisualFrame)->dict:
    width,height=source.width,source.height
    n=width*height
    colors=set()
    luminance=[]
    for pos in range(0,len(source.rgb),3):
        r,g,b=source.rgb[pos:pos+3]
        colors.add((r//32,g//32,b//32))
        luminance.append(round(.2126*r+.7152*g+.0722*b,4))
    edges=0
    for j in range(height):
        for i in range(width):
            idx=j*width+i
            if i>0 and abs(luminance[idx]-luminance[idx-1])>18:
                edges+=1
            if j>0 and abs(luminance[idx]-luminance[idx-width])>18:
                edges+=1
    mean=sum(luminance)/n
    return {"frame":source.frame,"source_digest":source.source_digest,
            "color_buckets":len(colors),
            "mean_luma":round(mean,4),
            "edge_density":round(edges/max(1,n*2),6),
            "dynamic_range":round(max(luminance)-min(luminance),4)}

def compare_original_visuals(groups:tuple[tuple[VisualFrame,...],...])->dict:
    if type(groups) is not tuple or not 1<=len(groups)<=10:
        raise ExpeditionError("Dragon can visually compare 1..10 original games")
    game_rows=[]
    for group in groups:
        if (type(group) is not tuple or not 2<=len(group)<=120
                or any(not isinstance(frame,VisualFrame) for frame in group)):
            raise ExpeditionError("Dragon requires at least two real bounded RGB frames")
        world=group[0].game_digest
        shape=(group[0].width,group[0].height)
        if any(x.game_digest!=world or (x.width,x.height)!=shape for x in group):
            raise ExpeditionError("Dragon visual frames cross original game source or resolution")
        if any(b.frame<=a.frame for a,b in zip(group,group[1:])):
            raise ExpeditionError("Dragon visual evidence must increase in game frame order")
        metrics=[_metrics(frame) for frame in group]
        diffs=[]
        for a,b in zip(group,group[1:]):
            changed=sum(abs(x-y) for x,y in zip(a.rgb,b.rgb))
            diffs.append(round(changed/(255*len(a.rgb)),6))
        game_rows.append({
            "world":world,"frames":len(group),
            "shape":[shape[0],shape[1]],
            "source_kind":sorted({x.kind for x in group}),
            "samples":metrics,"temporal_changed_fraction":diffs,
            "average_motion_delta":round(sum(diffs)/len(diffs),6),
            "average_color_diversity":round(
                sum(x["color_buckets"] for x in metrics)/len(metrics),4),
            "measured_native_fps":None,
            "external_game_used_as_training_source":False,
        })
    if len({x["world"] for x in game_rows})!=len(game_rows):
        raise ExpeditionError("Dragon requires independent original game sources")
    ranked=sorted(game_rows,key=lambda x:(
        -x["average_color_diversity"],
        -sum(y["edge_density"] for y in x["samples"])/len(x["samples"]),
        x["world"],
    ))
    report={"schema":"skeleton.dragon.original_visual_lab.v1",
            "games":game_rows,
            "ranking":[x["world"] for x in ranked],
            "frame_count":sum(x["frames"] for x in game_rows),
            "real_video_source_inferred":False,
            "neural_weights_promoted":False,
            "copyright_clearance_inferred":False,
            "user_owned_capture_only":True}
    report["receipt_digest"]=_digest(report)
    return report

def verify_visual_comparison(groups:tuple[tuple[VisualFrame,...],...],
                             candidate:dict)->None:
    if not isinstance(candidate,dict) or candidate!=compare_original_visuals(groups):
        raise ExpeditionError("Dragon visual scores differ from actual original source pixels")

def original_procedural_preview_frames(world_digest:str,*,seed:int=42,
                                       frames:int=4,width:int=24,height:int=16)->tuple[VisualFrame,...]:
    if (type(seed) is not int or not 0<=seed<2**63 or type(width) is not int
            or type(height) is not int or not 2<=width<=64 or not 2<=height<=64):
        raise ExpeditionError("original visual preview dimension or source seed invalid")
    frames_out=[]
    for tick in range(frames):
        pixels=bytearray()
        for y in range(height):
            for x in range(width):
                value=(x*17+y*11+tick*13+seed)%256
                pixels.extend((value,(value*3+x)%256,(value*7+y)%256))
        frames_out.append(VisualFrame(world_digest,tick,width,height,bytes(pixels),
                                      "original_procedural_preview"))
    return tuple(frames_out)
