"""Read-only binary mesh/skin audit of original pinned GLB.
Reports sampled source data, never rendered or continuous collision evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import struct

from dragon_atelier_admit import PIN, unique_object, invalid_constant
from audit_emerald_animation import identity, integer, bounded_index, require

COMPONENT = {5120: ("b", 1), 5121: ("B", 1), 5122: ("h", 2),
             5123: ("H", 2), 5125: ("I", 4), 5126: ("f", 4)}
SHAPE = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
MAX_VERTICES = 30_000_000
MAX_VALUES = 200_000_000


def objects(doc, name, ceiling, allow_empty=False):
    value = doc.get(name, [])
    require(isinstance(value, list) and (allow_empty or bool(value)) and len(value) <= ceiling,
            "invalid " + name)
    require(all(isinstance(row, dict) for row in value), "invalid " + name + " object")
    return value


class GeometryReader:
    def __init__(self, stream, doc, start, size):
        self.stream = stream
        self.views = objects(doc, "bufferViews", 250_000)
        self.accessors = objects(doc, "accessors", 250_000)
        self.start, self.size = start, size
        self.total_values = 0

    def layout(self, index, shape, types):
        a = self.accessors[bounded_index(index, len(self.accessors), "accessor")]
        comp = a.get("componentType")
        require(a.get("type") == shape and comp in types and "sparse" not in a,
                "unsupported geometry accessor encoding")
        fmt, size = COMPONENT[comp]
        width = SHAPE[shape]
        normalize = a.get("normalized", False)
        require(type(normalize) is bool and (not normalize or comp in (5120,5121,5122,5123)),
                "invalid normalized accessor")
        count = integer(a.get("count"), 1, MAX_VERTICES, "geometry accessor count")
        v = self.views[bounded_index(a.get("bufferView"), len(self.views), "buffer view")]
        require(v.get("buffer") == 0, "external geometry buffer")
        base = integer(v.get("byteOffset", 0), 0, self.size, "buffer offset")
        length = integer(v.get("byteLength"), 1, self.size-base, "buffer view length")
        offset = integer(a.get("byteOffset",0), 0, length, "accessor offset")
        stride = integer(v.get("byteStride",width*size),width*size,252,"geometry stride")
        require((base+offset)%size==0 and stride%size==0, "unaligned geometry accessor")
        require(offset+(count-1)*stride+width*size<=length,"geometry accessor exceeds view")
        return count, width, size, fmt, comp, normalize, self.start+base+offset, stride

    def read(self, layout):
        count,width,size,fmt,comp,normalize,start,stride=layout
        self.total_values += count*width
        require(self.total_values <= MAX_VALUES,"geometry component budget exceeded")
        unpack=struct.Struct("<"+fmt*width)
        # Independent bounded buffers permit zip() over interleaved streams.
        chunk=max(1,1024*1024//stride)
        for first in range(0,count,chunk):
            n=min(chunk,count-first)
            self.stream.seek(start+first*stride)
            raw=self.stream.read((n-1)*stride+width*size)
            require(len(raw)==(n-1)*stride+width*size,"truncated geometry source")
            for ordinal in range(n):
                values=unpack.unpack_from(raw,ordinal*stride)
                if normalize:
                    divisor={5120:127,5121:255,5122:32767,5123:65535}[comp]
                    values=tuple(max(-1.0,v/divisor) for v in values)
                yield values


def finite(values):
    require(all(math.isfinite(v) for v in values),"non-finite mesh or skin component")
    return values


def audit_geometry(stream, doc, start, size):
    reader=GeometryReader(stream,doc,start,size)
    nodes=objects(doc,"nodes",8192)
    meshes=objects(doc,"meshes",4096)
    skins=objects(doc,"skins",128)
    skin_joints=[]
    for skin in skins:
        joints=skin.get("joints")
        require(isinstance(joints,list) and 0<len(joints)<=8192,"invalid skin joints")
        valid=[bounded_index(j,len(nodes),"joint node") for j in joints]
        require(len(set(valid))==len(valid),"duplicate skin joint")
        if "inverseBindMatrices" in skin:
            layout=reader.layout(skin["inverseBindMatrices"],"MAT4",(5126,))
            require(layout[0]>=len(valid),"missing inverse bind matrices")
            for matrix in reader.read(layout):
                finite(matrix)
        skin_joints.append(len(valid))
    # A mesh may be instanced by more than one skin. Validate its palette
    # against the smallest applicable palette without multiplying vertex work.
    palettes={}
    for node in nodes:
        if "skin" not in node:
            continue
        mesh=bounded_index(node.get("mesh"),len(meshes),"skinned mesh")
        count=skin_joints[bounded_index(node["skin"],len(skins),"skin")]
        palettes[mesh]=min(palettes.get(mesh,count),count)
    require(bool(palettes),"no skinned meshes")
    inventory=[]
    total_vertices=0
    total_indices=0
    for i,mesh in enumerate(meshes):
        primitives=objects(mesh,"primitives",4096)
        for j,primitive in enumerate(primitives):
            attr=primitive.get("attributes",{})
            require(isinstance(attr,dict) and "POSITION" in attr,"missing mesh positions")
            pos=reader.layout(attr["POSITION"],"VEC3",(5126,))
            n=pos[0]
            total_vertices += n
            require(total_vertices<=MAX_VERTICES,"geometry vertex budget exceeded")
            lo=[math.inf]*3; hi=[-math.inf]*3
            for values in reader.read(pos):
                for axis,v in enumerate(finite(values)):
                    lo[axis]=min(lo[axis],v);hi[axis]=max(hi[axis],v)
            normal_error=None
            if "NORMAL" in attr:
                normal=reader.layout(attr["NORMAL"],"VEC3",(5126,))
                require(normal[0]==n,"normal count differs from positions")
                normal_error=0.0
                for values in reader.read(normal):
                    normal_error=max(normal_error,abs(math.sqrt(sum(x*x for x in finite(values)))-1))
            weight_error=None
            max_influences=0
            if i in palettes:
                sets=sorted(int(k.split("_")[1]) for k in attr if k.startswith("JOINTS_") and k.split("_")[-1].isdigit())
                weight_sets=sorted(int(k.split("_")[1]) for k in attr if k.startswith("WEIGHTS_") and k.split("_")[-1].isdigit())
                require(sets==weight_sets and sets==list(range(len(sets))) and 1<=len(sets)<=4,
                        "missing or unmatched skin attribute sets")
                streams=[]
                for k in sets:
                    jl=reader.layout(attr["JOINTS_"+str(k)],"VEC4",(5121,5123))
                    wl=reader.layout(attr["WEIGHTS_"+str(k)],"VEC4",(5121,5123,5126))
                    require(jl[0]==wl[0]==n and not jl[5] and (wl[4]==5126 or wl[5]),
                            "invalid skin attribute counts or normalized weights")
                    streams.extend((reader.read(jl),reader.read(wl)))
                weight_error=0.0
                for row in zip(*streams,strict=True):
                    sum_weights=0.0; influences=0
                    for joints,weights in zip(row[::2],row[1::2],strict=True):
                        for joint,weight in zip(joints,finite(weights),strict=True):
                            require(type(joint) is int and 0<=joint<palettes[i],"joint palette index out of bounds")
                            require(0<=weight<=1,"invalid skin weight")
                            sum_weights+=weight
                            influences+=int(weight>0)
                    error=abs(sum_weights-1)
                    require(error<=0.025,"skin weights do not sum to one")
                    weight_error=max(weight_error,error)
                    max_influences=max(max_influences,influences)
            count=n
            repeated_triangle_indices=0
            mode=primitive.get("mode",4)
            require(type(mode) is int and 0<=mode<=6,"unknown mesh primitive mode")
            idx=primitive.get("indices")
            if idx is not None:
                layout=reader.layout(idx,"SCALAR",(5121,5123,5125))
                require(not layout[5],"normalized index accessor")
                count=layout[0]
                recent=[]
                for (value,) in reader.read(layout):
                    require(0<=value<n,"mesh index out of bounds")
                    if mode==4:
                        recent.append(value)
                        if len(recent)==3:
                            repeated_triangle_indices+=int(len(set(recent))<3)
                            recent=[]
            if mode==4:
                require(count%3==0,"incomplete triangle")
            total_indices+=count
            inventory.append({"mesh":i,"primitive":j,"vertices":n,"indexed":idx is not None,
                              "index_or_vertex_count":count,"mode":mode,"local_min":lo,"local_max":hi,
                              "max_normal_norm_error":normal_error,"max_weight_sum_error":weight_error,
                              "max_nonzero_skin_influences":max_influences,
                              "repeated_triangle_indices":repeated_triangle_indices})
    return {"primitives":inventory,"total_vertices_by_primitive":total_vertices,
            "total_index_or_vertex_count":total_indices,"skin_palette_sizes":skin_joints,
            "skinned_meshes":len(palettes),"components_examined":reader.total_values}


def audit_pinned(model,pin):
    require(model.name=="emerald_continuum.glb" and not model.is_symlink(),"original model path required")
    flags=os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_BINARY",0)|getattr(os,"O_NONBLOCK",0)
    with os.fdopen(os.open(model,flags),"rb") as stream:
        before=os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_size==pin["modelBytes"],"original size mismatch")
        require(hashlib.file_digest(stream,"sha256").hexdigest()==pin["modelSha256"],"original digest mismatch")
        stream.seek(0)
        magic,version,length,size,kind=struct.unpack("<4sIIII",stream.read(20))
        require(magic==b"glTF" and version==2 and length==before.st_size and kind==0x4e4f534a,"invalid GLB header")
        require(4<=size<=32*1024*1024 and size%4==0 and size+28<=length,"invalid JSON size")
        doc=json.loads(stream.read(size),object_pairs_hook=unique_object,parse_constant=invalid_constant)
        binary_size,marker=struct.unpack("<II",stream.read(8))
        require(marker==0x004e4942 and binary_size%4==0 and size+28+binary_size==length,"invalid embedded BIN")
        buffers=objects(doc,"buffers",1)
        require(len(buffers)==1 and "uri" not in buffers[0],"external mesh buffer")
        declared=integer(buffers[0].get("byteLength"),1,binary_size,"buffer size")
        require(binary_size-declared<=3,"invalid BIN padding")
        result=audit_geometry(stream,doc,28+size,declared)
        require(max(result["skin_palette_sizes"])==108,"wrong original joint count")
        require(identity(before)==identity(os.fstat(stream.fileno())),"asset changed during audit")
        return {"schema":"skeleton.emerald.mesh-skin-audit.v1","model_sha256":pin["modelSha256"],
                "model_bytes":before.st_size,**result,"continuous_collision_verified":False,
                "artistic_fidelity_verified":False,"gpu_skinning_verified":False,"physical_rtx_verified":False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model",type=Path)
    args=parser.parse_args()
    try:
        print(json.dumps(audit_pinned(args.model,json.loads(PIN.read_text(encoding="utf-8"))["native"]),indent=2))
    except (OSError,ValueError,TypeError,KeyError,AttributeError,struct.error,OverflowError) as exc:
        parser.exit(2,"Mesh/skin audit rejected: "+str(exc)+"\n")


if __name__=="__main__":
    main()
