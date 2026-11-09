"""Entire three-PDF packet approval, authenticated local session and revocation.

A decision is valid only for a byte-exact ZIP, manifest and all three
three-page Dragon/Jeeves/Adversarial PDFs. Approval cannot be simulated by
setting a boolean or choosing one favored role; require the currently
authenticated user's explicit set-wide action plus an HMAC-bound local
session key, stored once under strict no-overwrite authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from hashlib import sha256
from datetime import datetime
import hmac
import json
import os
import zipfile
from io import BytesIO

from .contracts import canonical_digest,canonical_json
from .competitive_tri_council import (
    ROLES,ThreeRoundBattlePlan,record_user_plan_decision,
)
from .competitive_title_radar import ThreatRadarError,_sha,_date
from .game_project_workspace import GameWorkspace

SCHEMA="skeleton.game_builder.multipart_battle_pdfs.v1"


def _read_exact_file(path,max_bytes=5_000_000):
    if path.is_symlink() or not path.is_file():
        raise ThreatRadarError("review file symlink, missing file or invalid upload")
    if path.stat().st_size>max_bytes:
        raise ThreatRadarError("oversize review packet component")
    return path.read_bytes()


def _unique_pairs(pairs):
    body={}
    for k,v in pairs:
        if k in body:
            raise ThreatRadarError("duplicate review manifest key")
        body[k]=v
    return body


def inspect_all_three_pdfs(root: str|Path,packet_digest: str,*,
                           authorized: bool)->dict:
    if not authorized:
        raise PermissionError("signed local packet inspection requires operator approval")
    _sha(packet_digest,"packet fingerprint")
    folder=GameWorkspace(root).root/"competitive_intelligence"/"battle_pdf_packets"/packet_digest
    if folder.is_symlink():
        raise ThreatRadarError("untrusted PDF review folder")
    raw=_read_exact_file(folder/"manifest.json")
    if sha256(raw).hexdigest()!=packet_digest:
        raise ThreatRadarError("PDF manifest digest changed after three-role deliberation")
    try:
        manifest=json.loads(raw,object_pairs_hook=_unique_pairs)
    except (TypeError,ValueError,UnicodeDecodeError) as exc:
        raise ThreatRadarError("malformed multipart PDF review manifest") from exc
    if (manifest.get("schema")!=SCHEMA
            or not manifest.get("all_three_required_for_approval")
            or manifest.get("user_approval_status")!="AWAITING_EXPLICIT_USER_CONFIRMATION"
            or set(manifest.get("role_document_sha256",{}))!=set(ROLES)
            or manifest.get("role_pages")!={r:3 for r in ROLES}
            or (canonical_json(manifest)+"\n").encode("utf-8")!=raw):
        raise ThreatRadarError("incomplete multipart role custody manifest")
    roledata={}
    for role in ROLES:
        raw_pdf=_read_exact_file(folder/(role+".pdf"))
        if (not raw_pdf.startswith(b"%PDF-1.4")
                or raw_pdf.count(b"/Type /Page /Parent")!=3
                or sha256(raw_pdf).hexdigest()!=manifest["role_document_sha256"][role]):
            raise ThreatRadarError("PDF missing page(s) or digest differs from approved manifest")
        roledata[role+".pdf"]=raw_pdf
    raw_zip=_read_exact_file(folder/"complete-review-packet.zip",max_bytes=20_000_000)
    try:
        with zipfile.ZipFile(BytesIO(raw_zip),"r") as z:
            if (set(z.namelist())!=set(roledata)|{"manifest.json"}
                    or len(z.namelist())!=4):
                raise ThreatRadarError("not the complete, correctly scoped 3-role bundle")
            for name,data in {**roledata,"manifest.json":raw}.items():
                if z.getinfo(name).file_size!=len(data) or z.read(name)!=data:
                    raise ThreatRadarError("PDF packet ZIP differs from exactly reviewed documents")
    except (zipfile.BadZipFile,RuntimeError,OSError) as exc:
        raise ThreatRadarError("broken or altered review ZIP") from exc
    return manifest


@dataclass(frozen=True,slots=True)
class UserPacketDecision:
    packet_digest: str
    decision: str
    submitted_at: str
    reviewed_roles: tuple[str,...]
    feedback: str
    signer_context_digest: str
    signature: str

    def body(self):
        return dict(
            schema="skeleton.game_builder.authenticated_user_packet_decision.v1",
            packet_digest=self.packet_digest,decision=self.decision,
            submitted_at=self.submitted_at,
            reviewed_roles=list(self.reviewed_roles),
            feedback=self.feedback,
            signer_context_digest=self.signer_context_digest)

    def payload(self):
        return dict(self.body(),signature=self.signature)


def submit_user_packet_decision(
    root: str|Path,packet_digest: str,*,decision: str,
    feedback: str,
    authenticated_session_key: bytes,
    authenticated_session_context_digest: str,
    reviewed_roles: tuple[str,...],
    as_of: str,
    authorized: bool,
)->UserPacketDecision:
    if not authorized:
        raise PermissionError("user PDF approval needs authenticated local studio session")
    _date(as_of);_sha(authenticated_session_context_digest,"user session identity")
    if (type(authenticated_session_key) is not bytes
            or len(authenticated_session_key)<32
            or reviewed_roles!=tuple(sorted(ROLES))
            or not isinstance(feedback,str)
            or len(feedback)>2000
            or (decision=="revise" and len(feedback)<40)
            or decision not in {"approve","revise","defer"}):
        raise ThreatRadarError("only explicit full-set typed and trusted user decision is admissible")
    inspect_all_three_pdfs(root,packet_digest,authorized=True)
    folder=GameWorkspace(root).root/"competitive_intelligence"/"battle_pdf_packets"/packet_digest
    body=dict(
        schema="skeleton.game_builder.authenticated_user_packet_decision.v1",
        packet_digest=packet_digest,decision=decision,
        submitted_at=as_of,
        reviewed_roles=list(reviewed_roles),feedback=feedback,
        signer_context_digest=authenticated_session_context_digest)
    signed=hmac.new(
        authenticated_session_key,canonical_digest(body).encode(),
        "sha256").hexdigest()
    decision_record=UserPacketDecision(
        packet_digest,decision,as_of,reviewed_roles,
        feedback,authenticated_session_context_digest,signed)
    path=folder/"user_decision.json"
    raw=(canonical_json(decision_record.payload())+"\n").encode()
    if path.is_symlink():
        raise ThreatRadarError("untrusted client decision source")
    try:
        with path.open("xb") as file:
            file.write(raw)
            file.flush()
            os.fsync(file.fileno())
    except FileExistsError:
        if path.is_symlink() or path.read_bytes()!=raw:
            raise ThreatRadarError("cannot rewrite an already recorded user approval/rejection")
    return decision_record


def require_authenticated_packet_decision(
    battle: ThreeRoundBattlePlan,
    signed: UserPacketDecision,*,authenticated_session_key: bytes,
    authenticated_session_context_digest: str,
    authorized: bool,
)->ThreeRoundBattlePlan:
    if not authorized:
        raise PermissionError("explicit studio principal must control approval transition")
    if (not isinstance(battle,ThreeRoundBattlePlan)
            or not isinstance(signed,UserPacketDecision)
            or type(authenticated_session_key) is not bytes
            or len(authenticated_session_key)<32
            or signed.packet_digest!=battle.packet_digest
            or signed.signer_context_digest!=authenticated_session_context_digest
            or signed.reviewed_roles!=tuple(sorted(ROLES))
            or not hmac.compare_digest(
                signed.signature,hmac.new(
                    authenticated_session_key,
                    canonical_digest(signed.body()).encode(),
                    "sha256").hexdigest())):
        raise ThreatRadarError("signed PDF approval not bound to this user/session/whole packet")
    if signed.decision=="defer":
        if battle.user_decision!="awaiting_user":
            raise ThreatRadarError("plan approval already finalized")
        return battle
    return record_user_plan_decision(
        battle,decision=signed.decision,feedback=signed.feedback,
        exact_packet_digest=signed.packet_digest,authorized=True)


__all__=["UserPacketDecision","inspect_all_three_pdfs",
         "submit_user_packet_decision",
         "require_authenticated_packet_decision"]
