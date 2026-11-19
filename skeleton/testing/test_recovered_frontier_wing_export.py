"""Binary glTF accessors, overlapping animation pages, source and publication custody."""
import json
import struct
from io import BytesIO
from hashlib import sha256
from zipfile import ZipFile
import pytest
from skeleton.app.recovered_evidence import EvidenceError
from skeleton.app.frontier_wing_glb import encode_page
from skeleton.app.frontier_wing_export import build_archive
from skeleton.app.frontier_wing_export_custody import operate
from skeleton.jeeves.game_frontier_production import Vec3
from skeleton.testing.test_recovered_frontier_wings import order


def unpack(raw):
    magic,version,total=struct.unpack_from("<4sII",raw)
    assert magic==b"glTF" and version==2 and total==len(raw)
    n,typ=struct.unpack_from("<I4s",raw,12)
    assert typ==b"JSON"
    doc=json.loads(raw[20:20+n])
    length,typ=struct.unpack_from("<I4s",raw,20+n)
    assert typ==b"BIN\0"
    binary=raw[28+n:]
    assert len(binary)==length
    return doc,binary


def accessor(doc,binary,index):
    acc=doc["accessors"][index]
    view=doc["bufferViews"][acc["bufferView"]]
    width={"SCALAR":1,"VEC3":3}[acc["type"]]
    fmt="f" if acc["componentType"]==5126 else "I"
    n=width*acc["count"]
    return struct.unpack_from("<"+fmt*n,binary,view["byteOffset"])


def test_glb_contains_actual_animation_and_y_up_geometry():
    first=(Vec3(0,0,0),Vec3(1,0,0),Vec3(0,1,0))
    second=tuple(Vec3(p.x,p.y,p.z+1) for p in first)
    data=encode_page(((0,1,2),),[(0,first),(10_000_000,second)],name="reference")
    doc,bin=unpack(data)
    primitive=doc["meshes"][0]["primitives"][0]
    delta=accessor(doc,bin,primitive["targets"][0]["POSITION"])
    assert delta==(0.,1.,0.)*3
    sampler=doc["animations"][0]["samplers"][0]
    assert accessor(doc,bin,sampler["output"])==(0.,1.)
    assert accessor(doc,bin,sampler["input"])==pytest.approx((0.,.01))


def build(doc):
    return build_archive(doc,sample_stride=2,page_frames=5,allow_reference_defects=True,authorized=True)


def test_full_simulation_pages_overlap_and_exact_bytes_reconstruct():
    raw,manifest=build(order())
    raw2,manifest2=build(order())
    assert raw==raw2 and manifest==manifest2
    with ZipFile(BytesIO(raw)) as z:
        rows=manifest["pages"]
        assert json.loads(z.read("manifest.json"))==manifest
        for row in rows:
            original=z.read(row["path"])
            assert sha256(original).hexdigest()==row["sha256"]
            doc,binary=unpack(original)
            assert len(doc["meshes"][0]["primitives"][0]["targets"])==row["samples"]-1
        for first,second in zip(rows,rows[1:]):
            assert first["last_frame"]==second["first_frame"]
            assert first["source_frames"][-1]==second["source_frames"][0]
    assert manifest["source_frames"]==48
    assert not manifest["native_import_verified"]


def test_publish_verify_and_no_clobber(tmp_path):
    p=tmp_path/"review.zip"
    doc=order()
    options=dict(sample_stride=2,page_frames=5,allow_reference_defects=True,authorized=True)
    first=operate(doc,p,operation="export",**options)
    assert first["archive_sha256"]==sha256(p.read_bytes()).hexdigest()
    checked=operate(doc,p,operation="verify",expected_archive_sha256=first["archive_sha256"],**options)
    assert checked["manifest_digest"]==first["manifest_digest"]
    with pytest.raises(FileExistsError):
        operate(doc,p,operation="export",**options)
    with pytest.raises(EvidenceError):
        operate(doc,p,operation="verify",expected_archive_sha256="0"*64,**options)


def test_unauthorized_and_degenerate_export_refused(tmp_path):
    with pytest.raises(PermissionError):
        operate({},tmp_path/"absent.zip",operation="export",sample_stride=1,
                page_frames=2,allow_reference_defects=False,authorized=False)
    collapsed=(Vec3(0,0,0),Vec3(1,0,0),Vec3(2,0,0))
    with pytest.raises(EvidenceError):
        encode_page(((0,1,2),),[(0,collapsed),(1,collapsed)],name="degenerate")
