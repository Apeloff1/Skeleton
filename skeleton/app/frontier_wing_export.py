"""Build deterministic bounded GLB page archives from actual reference solver output."""
from __future__ import annotations
from hashlib import sha256
from io import BytesIO
from zipfile import ZIP_STORED, ZipFile, ZipInfo
import math

from skeleton.app.recovered_evidence import EvidenceError,canonical,digest,integer,seal
from skeleton.app.frontier_wing_model import load_order,create_geometry
from skeleton.app.frontier_wing_replay import simulate
from skeleton.app.frontier_wing_glb import encode_page,MAX_PAGE_FRAMES

MAX_ARCHIVE_BYTES=64*1024*1024
MAX_SAMPLES=1024
MAX_EXPORT_VERTEX_SAMPLES=600_000


def _member(archive,name,raw):
    info=ZipInfo(name,date_time=(1980,1,1,0,0,0))
    info.compress_type=ZIP_STORED
    info.create_system=3
    info.external_attr=0o100644<<16
    archive.writestr(info,raw)


def build_archive(order,*,sample_stride,page_frames,allow_reference_defects,authorized):
    if authorized is not True:
        raise PermissionError("explicit reference export operator required")
    if type(allow_reference_defects) is not bool:
        raise EvidenceError("explicit defect admission required")
    spec=load_order(order)
    stride=integer(sample_stride,1,120)
    page_size=integer(page_frames,2,MAX_PAGE_FRAMES)
    geometry=create_geometry(spec)
    selected=list(range(0,spec.frames,stride))
    if selected[-1]!=spec.frames-1:
        selected.append(spec.frames-1)
    if len(selected)<2 or len(selected)>MAX_SAMPLES or len(selected)*len(geometry.mesh.vertices)>MAX_EXPORT_VERTEX_SAMPLES:
        raise EvidenceError("GLB sample work ceiling")
    selected=set(selected)
    sampled=[]
    def collect(index,time,positions,head):
        if index in selected:
            sampled.append((index,time,positions,head))
    report=simulate(order,frame_sink=collect)
    # Replay all source frames again without consuming exported geometry.
    if simulate(order)!=report:
        raise EvidenceError("reference solver replay differed")
    if not report["reference_invariants_passed"] and not allow_reference_defects:
        raise EvidenceError("reference invariants failed; export held")
    if len(sampled)!=len(selected):
        raise EvidenceError("sampled frames accounting mismatch")
    output=BytesIO()
    pages=[]
    total=0
    with ZipFile(output,"w",compression=ZIP_STORED,allowZip64=False) as z:
        start=0
        while start<len(sampled)-1:
            rows=sampled[start:start+page_size]
            name=f"wing_{len(pages):04d}"
            raw=encode_page(geometry.triangles,[(time,points) for _,time,points,_ in rows],name=name)
            total+=len(raw)
            if total>MAX_ARCHIVE_BYTES-1024*1024:
                raise EvidenceError("portable asset archive byte ceiling")
            path=f"animation/{name}.glb"
            _member(z,path,raw)
            pages.append({"path":path,"sha256":sha256(raw).hexdigest(),"bytes":len(raw),
                          "first_frame":rows[0][0],"last_frame":rows[-1][0],
                          "first_deadline_ns":rows[0][1],"last_deadline_ns":rows[-1][1],
                          "samples":len(rows),"source_frames":[{"index":i,"head":head} for i,_,_,head in rows]})
            # Overlap one boundary sample: segments have identical seam
            # geometry and time, even though each clip uses a local timeline.
            start+=len(rows)-1
        manifest=seal({"schema":"skeleton.frontier-wing-export.manifest.v1",
                       "order_digest":digest(order),"mesh_digest":geometry.mesh.digest,
                       "full_source_replay_head":report["head"],"source_frames":spec.frames,
                       "source_fps":spec.fps,"sample_stride":stride,"page_frames":page_size,
                       "unique_sample_count":len(selected),"vertices":len(geometry.mesh.vertices),
                       "triangles":len(geometry.triangles),"pages":pages,
                       "candidate_reference_invariants_passed":report["reference_invariants_passed"],
                       "invariant_failure_frames":report["invariant_failure_frames"],
                       "review_only_defects_accepted":allow_reference_defects,
                       "native_import_verified":False,"native_renderer_executed":False,
                       "release_certified":False})
        _member(z,"manifest.json",canonical(manifest))
    raw=output.getvalue()
    if len(raw)>MAX_ARCHIVE_BYTES:
        raise EvidenceError("portable asset archive byte ceiling")
    return raw,manifest
