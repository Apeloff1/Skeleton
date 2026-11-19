"""Deterministic glTF 2.0 binary morph animation for explicit sampled wing geometry.

Open-format candidate asset only. Coordinates are converted from the internal
right-handed Z-up reference to glTF's right-handed Y-up. Each morph target
stores relative POSITION and NORMAL deltas with a one-hot weight animation.
"""
from __future__ import annotations
import json
import math
import struct
from skeleton.app.recovered_evidence import EvidenceError

MAX_PAGE_FRAMES=25
MAX_GLB_BYTES=16*1024*1024


def _vec(p):
    return (float(p.x),float(p.z),-float(p.y))


def _sub(a,b):
    return tuple(x-y for x,y in zip(a,b,strict=True))


def _cross(a,b):
    x,y,z=a
    u,v,w=b
    return (y*w-z*v,z*u-x*w,x*v-y*u)


def _normal(v):
    length=math.sqrt(sum(x*x for x in v))
    if not math.isfinite(length) or length<1e-12:
        raise EvidenceError("degenerate or disconnected mesh normal")
    return tuple(x/length for x in v)


def normals(positions,triangles):
    accum=[[0.,0.,0.] for _ in positions]
    for a,b,c in triangles:
        normal=_cross(_sub(positions[b],positions[a]),_sub(positions[c],positions[a]))
        if sum(x*x for x in normal)<1e-20:
            raise EvidenceError("degenerate animation triangle cannot be exported")
        for i in (a,b,c):
            for k,value in enumerate(normal):
                accum[i][k]+=value
    return tuple(_normal(row) for row in accum)


class Buffer:
    def __init__(self):
        self.data=bytearray()
        self.views=[]
        self.accessors=[]

    def add(self,values,*,kind,component=5126,target=None,bounds=False):
        width={"SCALAR":1,"VEC3":3}[kind]
        rows=list(values)
        if not rows:
            raise EvidenceError("empty glTF accessor")
        flat=[]
        for row in rows:
            row=(row,) if width==1 else tuple(row)
            if len(row)!=width:
                raise EvidenceError("glTF accessor dimension mismatch")
            flat.extend(row)
        if component==5126:
            if any(type(n) not in (int,float) or not math.isfinite(n) or abs(n)>1e7 for n in flat):
                raise EvidenceError("nonfinite animation accessor")
            raw=struct.pack("<"+"f"*len(flat),*flat)
            flat=list(struct.unpack("<"+"f"*len(flat),raw))
        elif component==5125:
            if any(type(n) is not int or not 0<=n<2**32 for n in flat):
                raise EvidenceError("invalid glTF index")
            raw=struct.pack("<"+"I"*len(flat),*flat)
        else:
            raise EvidenceError("unsupported accessor component")
        self.data.extend(b"\0"*((-len(self.data))%4))
        view={"buffer":0,"byteOffset":len(self.data),"byteLength":len(raw)}
        if target is not None:
            view["target"]=target
        self.data.extend(raw)
        self.views.append(view)
        accessor={"bufferView":len(self.views)-1,"componentType":component,
                  "count":len(rows),"type":kind}
        if bounds:
            accessor["min"]=[min(flat[k::width]) for k in range(width)]
            accessor["max"]=[max(flat[k::width]) for k in range(width)]
        self.accessors.append(accessor)
        if len(self.data)>MAX_GLB_BYTES:
            raise EvidenceError("GLB page byte ceiling")
        return len(self.accessors)-1


def encode_page(triangles,frames,*,name):
    """Frames are pairs of exact presentation nanoseconds and vertex tuples."""
    if not 2<=len(frames)<=MAX_PAGE_FRAMES:
        raise EvidenceError("GLB frame page ceiling")
    n=len(frames[0][1])
    if not 3<=n<=4096 or not triangles or len(triangles)>65536:
        raise EvidenceError("invalid export geometry budget")
    if any(len(face)!=3 or len(set(face))!=3 or any(type(i) is not int or not 0<=i<n for i in face)
           for face in triangles):
        raise EvidenceError("invalid triangle indices")
    if any(len(frame)!=n for _,frame in frames) or any(a[0]>=b[0] for a,b in zip(frames,frames[1:])):
        raise EvidenceError("sampled timeline is not coherent")
    converted=[tuple(_vec(p) for p in row) for _,row in frames]
    all_normals=[normals(row,triangles) for row in converted]
    base=converted[0]
    base_normals=all_normals[0]
    buffer=Buffer()
    pos=buffer.add(base,kind="VEC3",target=34962,bounds=True)
    nor=buffer.add(base_normals,kind="VEC3",target=34962)
    indices=buffer.add((i for face in triangles for i in face),kind="SCALAR",component=5125,target=34963)
    targets=[]
    for points,ns in zip(converted[1:],all_normals[1:],strict=True):
        targets.append({"POSITION":buffer.add((_sub(a,b) for a,b in zip(points,base,strict=True)),
                                               kind="VEC3",target=34962,bounds=True),
                        "NORMAL":buffer.add((_sub(a,b) for a,b in zip(ns,base_normals,strict=True)),
                                             kind="VEC3",target=34962)})
    duration=[(time-frames[0][0])/1e9 for time,_ in frames]
    times=buffer.add(duration,kind="SCALAR",bounds=True)
    weights=buffer.add((float(i==k+1) for i in range(len(frames)) for k in range(len(targets))),
                       kind="SCALAR")
    scene={"asset":{"version":"2.0","generator":"Skeleton reference wing exporter"},
           "scene":0,"scenes":[{"nodes":[0]}],"nodes":[{"name":name,"mesh":0}],
           "meshes":[{"name":name,"weights":[0.]*len(targets),"primitives":[{
              "attributes":{"POSITION":pos,"NORMAL":nor},"indices":indices,
              "material":0,"mode":4,"targets":targets}]}],
           "materials":[{"name":"reference_ruby_membrane","doubleSided":True,
                         "pbrMetallicRoughness":{"baseColorFactor":[.42,.035,.065,1.],
                                                "metallicFactor":0.,"roughnessFactor":.65}}],
           "animations":[{"name":"source_frame_morph","samplers":[{"input":times,"output":weights,
                                 "interpolation":"LINEAR"}],
                          "channels":[{"sampler":0,"target":{"node":0,"path":"weights"}}]}],
           "buffers":[{"byteLength":len(buffer.data)}],"bufferViews":buffer.views,
           "accessors":buffer.accessors}
    raw=json.dumps(scene,ensure_ascii=True,sort_keys=True,separators=(",",":"),allow_nan=False).encode("ascii")
    raw+=b" "*((-len(raw))%4)
    binary=bytes(buffer.data)+b"\0"*((-len(buffer.data))%4)
    size=12+8+len(raw)+8+len(binary)
    if size>MAX_GLB_BYTES:
        raise EvidenceError("GLB page byte ceiling")
    return (struct.pack("<4sII",b"glTF",2,size)+struct.pack("<I4s",len(raw),b"JSON")+raw+
            struct.pack("<I4s",len(binary),b"BIN\0")+binary)
