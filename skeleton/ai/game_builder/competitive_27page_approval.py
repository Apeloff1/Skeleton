"""Strict all-27-pages + 12,240-judgment user approval custody.

Approval binds the THREE final 9-page role PDFs, NINE 3-page round
fragments, exact all-probe catalog and exact each-role machine report,
and canonical manifest. A single model, a missing appendix, or altered
page can never silently become a user-approved campaign.
"""
from __future__ import annotations
from pathlib import Path
from io import BytesIO
from hashlib import sha256
import json
import hmac
import os
import zipfile

from .contracts import canonical_json,canonical_digest
from .competitive_battle_approval import UserPacketDecision
from .competitive_title_radar import ThreatRadarError,_sha,_date
from .competitive_4080_scrutiny import SIZES,ROLE_NAMES,TIMES
from .game_project_workspace import GameWorkspace


def _unique(pairs):
    out={}
    for k,v in pairs:
        if k in out:
            raise ThreatRadarError("duplicate manifest field in 27-page role packet")
        out[k]=v
    return out


def inspect_27page_packet(root,packet_digest: str,*,authorized: bool):
    if not authorized:
        raise PermissionError("operator approval required for full campaign inspection")
    _sha(packet_digest,"manifest digest")
    folder=GameWorkspace(root).root/"competitive_intelligence"/"battle_pdf_27"/packet_digest
    if folder.is_symlink() or not folder.is_dir():
        raise ThreatRadarError("missing or unsafe 27-page document folder")
    path=folder/"manifest.json"
    if path.is_symlink() or path.stat().st_size>1000000:
        raise ThreatRadarError("unsafe or oversized 27-page manifest")
    data=path.read_bytes()
    if sha256(data).hexdigest()!=packet_digest:
        raise ThreatRadarError("campaign PDF review root SHA corrupted")
    try:
        manifest=json.loads(data,object_pairs_hook=_unique)
    except (TypeError,ValueError,UnicodeDecodeError) as exc:
        raise ThreatRadarError("unparseable 27page manifest") from exc
    if (manifest.get("schema")!="skeleton.game_builder.27page_campaign_manifest.v1"
            or manifest.get("roles")!=list(ROLE_NAMES)
            or manifest.get("temporal_windows")!=list(TIMES)
            or manifest.get("per_round_unique_probes")!=list(SIZES)
            or manifest.get("review_obligations")!=12240
            or manifest.get("total_unique_pages")!=27
            or manifest.get("approved_by_user") is not False
            or manifest.get("role_final_pdf_pages")!={r:9 for r in ROLE_NAMES}
            or len(manifest.get("role_round_part_pdf_pages",{}))!=9
            or any(c!=3 for c in manifest["role_round_part_pdf_pages"].values())
            or len(manifest.get("pdf_file_sha256",{}))!=12
            or set(manifest.get("machine_annex_sha256",{}))!=
                {"full_probe_catalog.jsonl","all_role_probe_judgments.jsonl"}
            or (canonical_json(manifest)+"\n").encode()!=data):
        raise ThreatRadarError("27-page full coverage and nine unique role-round custody invalid")
    payloads={}
    expected=set()
    for name,digest in manifest["pdf_file_sha256"].items():
        if name not in (
                {r+"_full_9pages.pdf" for r in ROLE_NAMES}|
                {f"{r}_round_{i}.pdf" for r in ROLE_NAMES for i in (1,2,3)}):
            raise ThreatRadarError("unexpected or missing AI PDF name")
        expected.add(name)
        file=folder/name
        if file.is_symlink() or file.stat().st_size>3000000:
            raise ThreatRadarError("unsafe role PDF file")
        body=file.read_bytes()
        pages=9 if "_full_9pages" in name else 3
        if (not body.startswith(b"%PDF-1.4")
                or body.count(b"/Type /Page /Parent")!=pages
                or sha256(body).hexdigest()!=digest):
            raise ThreatRadarError("wrong role PDF pages or contents")
        payloads[name]=body
    if len(expected)!=12:
        raise ThreatRadarError("all 3 role PDFs and 9 subparts required")
    for name,digest in manifest["machine_annex_sha256"].items():
        path=folder/name
        if path.is_symlink() or path.stat().st_size>40000000:
            raise ThreatRadarError("unsafe exhaustive probe appendix")
        body=path.read_bytes()
        if sha256(body).hexdigest()!=digest:
            raise ThreatRadarError("changed or truncated 12,240-obligation annex")
        count=body.count(b"\n")
        if count!=(4080 if name=="full_probe_catalog.jsonl" else 12240):
            raise ThreatRadarError("machine appendix omits registered scrutiny obligations")
        payloads[name]=body
    payloads["manifest.json"]=data
    archive_path=folder/"complete_27page_campaign.zip"
    if archive_path.is_symlink() or archive_path.stat().st_size>40000000:
        raise ThreatRadarError("unsafe complete PDF bundle")
    try:
        with zipfile.ZipFile(BytesIO(archive_path.read_bytes())) as archive:
            if (len(archive.namelist())!=len(payloads)
                    or set(archive.namelist())!=set(payloads)):
                raise ThreatRadarError("multipart ZIP lost one or more AI role PDFs or annexes")
            for name,bytes_ in payloads.items():
                if archive.getinfo(name).file_size!=len(bytes_) or archive.read(name)!=bytes_:
                    raise ThreatRadarError("ZIP contents differ from reviewed exact role pages")
    except (zipfile.BadZipFile,RuntimeError,OSError) as exc:
        raise ThreatRadarError("invalid 27page ZIP") from exc
    return manifest


def sign_user_27page_decision(
    root,packet_digest: str,*,
    decision: str,
    feedback: str,
    signed_at: str,
    user_session_key: bytes,
    user_context_digest: str,
    reviewed_roles: tuple[str,...],
    authorized: bool,
)->UserPacketDecision:
    if not authorized:
        raise PermissionError("only authenticated user studio principal can confirm 27 pages")
    _date(signed_at);_sha(user_context_digest,"authenticated user session")
    if (type(user_session_key) is not bytes or len(user_session_key)<32
            or reviewed_roles!=tuple(sorted(ROLE_NAMES))
            or decision not in {"approve","revise","defer"}
            or type(feedback) is not str or len(feedback)>2000
            or (decision=="revise" and len(feedback)<40)):
        raise ThreatRadarError("full three-role review and consented feedback required")
    inspect_27page_packet(root,packet_digest,authorized=True)
    body=dict(
        schema="skeleton.game_builder.authenticated_user_packet_decision.v1",
        packet_digest=packet_digest,decision=decision,
        submitted_at=signed_at,
        reviewed_roles=list(reviewed_roles),feedback=feedback,
        signer_context_digest=user_context_digest)
    signature=hmac.new(user_session_key,canonical_digest(body).encode(),
                       "sha256").hexdigest()
    receipt=UserPacketDecision(packet_digest,decision,signed_at,
                               reviewed_roles,feedback,user_context_digest,
                               signature)
    folder=GameWorkspace(root).root/"competitive_intelligence"/"battle_pdf_27"/packet_digest
    path=folder/"user_decision.json"
    raw=(canonical_json(receipt.payload())+"\n").encode()
    if path.is_symlink():
        raise ThreatRadarError("symlinked user confirmation")
    try:
        with path.open("xb") as f:
            f.write(raw);f.flush();os.fsync(f.fileno())
    except FileExistsError:
        if path.is_symlink() or path.read_bytes()!=raw:
            raise ThreatRadarError("previous PDF packet decision cannot be overwritten")
    return receipt


__all__=["inspect_27page_packet","sign_user_27page_decision"]
