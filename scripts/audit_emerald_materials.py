"""Inspect actual embedded image bytes and material references in the pinned GLB.
Header dimensions and hashes are not image decoding or artist approval.
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
import zlib

from dragon_atelier_admit import PIN, unique_object, invalid_constant, reject_external
from audit_emerald_animation import identity, integer, bounded_index, require
from audit_emerald_skin import objects

MAX_DIMENSION = 16384
MAX_IMAGE_BYTES = 128 * 1024 * 1024
MAX_HEADER = 1024 * 1024
MAX_PIXELS = 268435456
MAX_TOTAL_PIXELS = 536870912
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_SOF = {0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf}
ROLES = {
    "baseColorTexture": "srgb-base-color",
    "metallicRoughnessTexture": "linear-metallic-roughness",
    "normalTexture": "linear-normal",
    "occlusionTexture": "linear-occlusion",
    "emissiveTexture": "srgb-emissive",
}


def dimensions(header, mime):
    if mime == "image/png":
        require(len(header)>=33 and header[:8]==PNG_MAGIC and header[8:16]==b"\x00\x00\x00\x0dIHDR",
                "invalid PNG header")
        require(zlib.crc32(header[12:29])&0xffffffff==int.from_bytes(header[29:33],"big"),"bad PNG IHDR CRC")
        width,height,depth,kind,compression,filter_method,interlace=struct.unpack(">IIBBBBB",header[16:29])
        valid_depth={0:{1,2,4,8,16},2:{8,16},3:{1,2,4,8},4:{8,16},6:{8,16}}
        require(kind in valid_depth and depth in valid_depth[kind] and compression==filter_method==0 and interlace in (0,1),
                "invalid PNG format fields")
        return width,height,depth,kind
    require(mime=="image/jpeg" and header[:2]==b"\xff\xd8","unsupported or mismatched image format")
    at=2
    while at<len(header):
        require(header[at]==0xff,"invalid JPEG marker")
        while at<len(header) and header[at]==0xff:at+=1
        require(at<len(header),"truncated JPEG marker")
        marker=header[at];at+=1
        require(marker not in (0x00,0xd9,0xda),"JPEG frame header missing")
        if marker in (0x01,*range(0xd0,0xd8)):continue
        require(at+2<=len(header),"JPEG segment truncated")
        length=int.from_bytes(header[at:at+2],"big")
        require(length>=2 and at+length<=len(header),"JPEG segment exceeds header budget")
        if marker in JPEG_SOF:
            require(length>=8,"invalid JPEG frame")
            depth=header[at+2];height=int.from_bytes(header[at+3:at+5],"big");width=int.from_bytes(header[at+5:at+7],"big")
            components=header[at+7]
            require(components in (1,3,4) and length==8+3*components and depth in (8,12),"invalid JPEG frame fields")
            return width,height,depth,components
        at+=length
    raise ValueError("no JPEG frame in bounded header")


def embedded_image(stream, image, views, binary_start, size):
    require("uri" not in image,"external image denied")
    mime=image.get("mimeType")
    require(mime in ("image/png","image/jpeg"),"unsupported embedded image format")
    view=views[bounded_index(image.get("bufferView"),len(views),"image buffer view")]
    require(view.get("buffer")==0 and "byteStride" not in view,"invalid image buffer")
    offset=integer(view.get("byteOffset",0),0,size,"image offset")
    length=integer(view.get("byteLength"),1,min(size-offset,MAX_IMAGE_BYTES),"image size")
    stream.seek(binary_start+offset)
    header=stream.read(min(length,MAX_HEADER))
    require(len(header)==min(length,MAX_HEADER),"truncated embedded image")
    width,height,depth,color=dimensions(header,mime)
    require(1<=width<=MAX_DIMENSION and 1<=height<=MAX_DIMENSION and width*height<=MAX_PIXELS,
            "embedded image dimensions exceed bounds")
    sha=hashlib.sha256(header)
    remaining=length-len(header)
    last=header[-12:]
    while remaining:
        block=stream.read(min(1024*1024,remaining))
        require(bool(block),"truncated image payload")
        sha.update(block);remaining-=len(block);last=(last+block)[-12:]
    if mime=="image/png":
        require(last==b"\x00\x00\x00\x00IEND\xaeB\x60\x82","PNG IEND missing")
    else:
        require(last[-2:]==b"\xff\xd9","JPEG EOI missing")
    return {"mime":mime,"bytes":length,"sha256":sha.hexdigest(),"width":width,"height":height,
            "bit_depth":depth,"header_color_type_or_components":color}


def finite_factor(value, low, high, label):
    require(type(value) in (int,float) and math.isfinite(value) and low<=value<=high,"invalid "+label)
    return value


def texture_ref(value, textures, role):
    require(isinstance(value,dict),"invalid texture info")
    ref=bounded_index(value.get("index"),len(textures),"texture index")
    coord=integer(value.get("texCoord",0),0,15,"texture coordinate set")
    transform=value.get("extensions",{}).get("KHR_texture_transform",{})
    require(isinstance(transform,dict),"invalid texture transform")
    if "texCoord" in transform:coord=integer(transform["texCoord"],0,15,"transformed coordinate set")
    for field in ("offset","scale"):
        if field in transform:
            vector=transform[field]
            require(isinstance(vector,list) and len(vector)==2 and all(type(v) in (int,float) and math.isfinite(v) for v in vector),
                    "invalid texture transform vector")
    if "rotation" in transform:
        finite_factor(transform["rotation"],-1e6,1e6,"texture rotation")
    return {"role":role,"texture":ref,"image":textures[ref],"texcoord":coord}


def audit_materials(stream,doc,start,size):
    reject_external(doc)
    views=objects(doc,"bufferViews",250_000)
    images=objects(doc,"images",4096)
    textures=objects(doc,"textures",4096)
    materials=objects(doc,"materials",4096)
    samplers=objects(doc,"samplers",4096,allow_empty=True)
    mesh_rows=objects(doc,"meshes",4096)
    image_rows=[];pixels=0
    for image in images:
        record=embedded_image(stream,image,views,start,size)
        pixels+=record["width"]*record["height"]
        require(pixels<=MAX_TOTAL_PIXELS,"embedded texture pixel budget exceeded")
        image_rows.append(record)
    texture_sources=[]
    for texture in textures:
        require("source" in texture,"unqualified alternate texture source")
        texture_sources.append(bounded_index(texture["source"],len(images),"texture source"))
        if "sampler" in texture:
            sampler=samplers[bounded_index(texture["sampler"],len(samplers),"texture sampler")]
            for name,allowed in (("magFilter",{9728,9729}),("minFilter",{9728,9729,9984,9985,9986,9987}),
                                 ("wrapS",{33071,33648,10497}),("wrapT",{33071,33648,10497})):
                if name in sampler:require(sampler[name] in allowed,"invalid sampler mode")
    rows=[];usage={}
    for idx,material in enumerate(materials):
        pbr=material.get("pbrMetallicRoughness",{})
        require(isinstance(pbr,dict),"invalid PBR material")
        bindings=[]
        for key,role in ROLES.items():
            location=pbr if key in ("baseColorTexture","metallicRoughnessTexture") else material
            if key in location:
                binding=texture_ref(location[key],texture_sources,role)
                bindings.append(binding);usage.setdefault(binding["image"],set()).add(role)
        factor=pbr.get("baseColorFactor",[1,1,1,1])
        require(isinstance(factor,list) and len(factor)==4,"invalid base color factor")
        factor=[finite_factor(v,0,1,"base color factor") for v in factor]
        metallic=finite_factor(pbr.get("metallicFactor",1),0,1,"metallic factor")
        roughness=finite_factor(pbr.get("roughnessFactor",1),0,1,"roughness factor")
        alpha=material.get("alphaMode","OPAQUE")
        require(alpha in ("OPAQUE","MASK","BLEND"),"invalid alpha mode")
        rows.append({"index":idx,"bindings":bindings,"alpha_mode":alpha,
                     "base_color_factor":factor,"metallic_factor":metallic,"roughness_factor":roughness,
                     "extension_names":sorted(material.get("extensions",{}).keys())})
    bound=0
    unmaterialled=0
    for mesh in mesh_rows:
        for primitive in objects(mesh,"primitives",4096):
            if "material" not in primitive:
                unmaterialled+=1
                continue
            mat=rows[bounded_index(primitive["material"],len(rows),"primitive material")]
            attr=primitive.get("attributes",{})
            require(isinstance(attr,dict),"invalid UV attributes")
            for binding in mat["bindings"]:
                require("TEXCOORD_"+str(binding["texcoord"]) in attr,"material refers to missing UV coordinates")
            bound+=1
    for idx,row in enumerate(image_rows):
        row["core_roles"]=sorted(usage.get(idx,set()))
        row["multiple_color_interpretations"]=any(x.startswith("srgb-") for x in row["core_roles"]) and any(x.startswith("linear-") for x in row["core_roles"])
    return {"images":image_rows,"materials":rows,"total_header_pixels":pixels,
            "material_bound_primitives":bound,"primitives_without_material":unmaterialled,
            "unique_image_hashes":len({row["sha256"] for row in image_rows})}


def audit_pinned(model,pin):
    require(model.name=="emerald_continuum.glb" and not model.is_symlink(),"original model path required")
    flags=os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)|getattr(os,"O_NONBLOCK",0)|getattr(os,"O_BINARY",0)
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
        require(len(buffers)==1 and "uri" not in buffers[0],"external model buffer")
        declared=integer(buffers[0].get("byteLength"),1,binary_size,"buffer byte count")
        require(binary_size-declared<=3,"unexpected BIN padding")
        result=audit_materials(stream,doc,28+size,declared)
        require(identity(before)==identity(os.fstat(stream.fileno())),"asset changed during audit")
    return {"schema":"skeleton.emerald.material-byte-audit.v1","model_sha256":pin["modelSha256"],
            "model_bytes":before.st_size,**result,"fully_decoded_textures_verified":False,
            "handpainted_provenance_verified":False,"artist_approved":False,"physical_rtx_verified":False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("model",type=Path)
    args=parser.parse_args()
    try:
        print(json.dumps(audit_pinned(args.model,json.loads(PIN.read_text(encoding="utf-8"))["native"]),indent=2))
    except (OSError,ValueError,TypeError,KeyError,AttributeError,struct.error,OverflowError) as exc:
        parser.exit(2,"Material audit rejected: "+str(exc)+"\n")


if __name__=="__main__":
    main()
