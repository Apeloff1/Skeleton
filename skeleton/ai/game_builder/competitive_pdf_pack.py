"""Strict multipart Dragon/Jeeves/Adversarial PDF battle-plan publication.

Dependency-free, deterministic PDF 1.4 with exactly three A4 pages per role.
One three-part PDF each, plus a digest-verified JSON manifest and ZIP packet.
Each role's distinct 3-page argument:
  I. evidence-qualified diagnosis and criticism of current user's project
  II. research / counterclaims through three real reviewed crawler rounds
  III. implementable original-design battle plan and explicit user decision
The documents are review materials, NEVER proof that models really ran unless
separate signed AgentDeliberation requests arrived from authenticated runtimes.

No automatically generated text purports to copy competitor artwork/lyrics/
story/dialogue, and no user confirmation is prefilled in any PDF.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from collections import Counter
from io import BytesIO
import json
import os
import textwrap
import zipfile
import zlib

from .contracts import canonical_digest,canonical_json
from .competitive_title_radar import ThreatRadarError,_id
from .competitive_tri_council import (
    ROLES,ThreeRoundBattlePlan,attach_multipart_pdf_packet,
)
from .competitive_user_critique import CurrentProjectCritique
from .game_project_workspace import GameWorkspace

PAGE_W=595.276
PAGE_H=841.89
TEXT_W=498
LEFT=49
BASELINE_START=765
LEADING=12.5
LINES_PER_PAGE=54
MAX_SOURCE_CHARS=14000
ROLE_TITLES={
    "dragon":"DRAGON - Research, Rights and Knowledge Strategy",
    "jeeves":"JEEVES - Architecture, Logic and Delivery Strategy",
    "adversarial":"ADVERSARIAL - Faults, Weak Spots and Proof Strategy",
}
ROLE_FOCUS={
    "dragon":(
        "Independently verify each competitor and genre source; reject licensing or recency gaps.",
        "Distil peer-reviewed ideas without taking protected expression, audio, models or artwork.",
        "Order lawful wider searches through the canonical Dragon/Wiki/right-to-reference pipeline.",
        "Insist that human approval and source-rights revocation remain independent hard stops.",
    ),
    "jeeves":(
        "Derive new original mechanics, UI, narrative and NPC event/witness systems from project intent.",
        "Sequence work by causal blockers, estimated learning gain, platform budgets and reversibility.",
        "Require a deterministic original-game build, instrumented playtests and cross-platform staging.",
        "Do not turn a speculative comparator hypothesis into hard-coded product behavior.",
    ),
    "adversarial":(
        "Try to falsify every claimed win with independent same-protocol benchmark cohorts.",
        "Probe inaccessible interfaces, rights similarity, story deadlocks, sound masking and stress.",
        "Demand independently signed normal/fault control replays and confidence intervals.",
        "Veto release or self-improvement promotion when rival, ancestry or current project proof is absent.",
    ),
}


def _text_lines(value: str,width=91):
    if not isinstance(value,str):
        raise ThreatRadarError("only approved textual battle plans may be rendered")
    if len(value)>MAX_SOURCE_CHARS:
        raise ThreatRadarError("unbounded battle plan text would silently truncate")
    clean="".join(ch if ch.isprintable() or ch in "\n\t" else "?" for ch in value)
    out=[]
    for paragraph in clean.splitlines():
        if not paragraph.strip():
            out.append("")
        else:
            out.extend(textwrap.wrap(
                paragraph.replace("\t","    "),
                width=width,break_long_words=True,
                replace_whitespace=True,drop_whitespace=True) or [""])
    return out


def _literal_pdf_bytes(value):
    try:
        return value.encode("cp1252","strict")
    except UnicodeEncodeError as exc:
        raise ThreatRadarError("PDF content contains glyphs absent from built-in WinAnsi font") from exc


def _pdf_hex(value):
    return "<"+_literal_pdf_bytes(value).hex().upper()+">"


def _ensure_page(rows):
    content=[]
    for kind,value in rows:
        if kind=="heading":
            lines=_text_lines(value,79)
            content.extend(("heading",v) for v in lines)
        elif kind=="body":
            content.extend(("body",v) for v in _text_lines(value,93))
        elif kind=="blank":
            content.append(("blank",""))
        else:
            raise ThreatRadarError("unsupported PDF paragraph type")
    if len(content)>LINES_PER_PAGE:
        raise ThreatRadarError(
            f"excessive PDF longform content would overflow 3-page contract: {len(content)} lines")
    return content


def _pdf_pages(role,parts,battle,packet_id):
    if role not in ROLES or type(parts) is not tuple or len(parts) not in {3,9}:
        raise ThreatRadarError("only three-page role sections or nine-page role dossiers")
    streams=[]
    for page,rows in enumerate(parts,1):
        content=_ensure_page(rows)
        instructions=[
            "q","0.11 0.15 0.24 rg",
            "0 793 595.276 49 re f",
            "Q",
            "BT /F2 12 Tf 0.99 0.99 0.99 rg 49 809 Td "+
            _pdf_hex(ROLE_TITLES[role])+" Tj ET",
            "BT /F1 8.6 Tf 0.12 0.15 0.20 rg",
        ]
        # Position each row independently, avoiding text rendering/cursor drift.
        y=BASELINE_START
        for kind,value in content:
            if kind=="blank":
                y-=LEADING
                continue
            if kind=="heading":
                font="/F2 9.7 Tf"
                y-=2
            else:
                font="/F1 8.6 Tf"
            instructions.append(
                f"{font} 1 0 0 1 {LEFT} {y:.1f} Tm "+_pdf_hex(value)+" Tj")
            y-=LEADING
        instructions.extend([
            "ET","0.82 0.85 0.91 RG 49 60 m 546 60 l S",
            "BT /F1 7.5 Tf 0.38 0.43 0.50 rg "
            "1 0 0 1 49 47 Tm "+
            _pdf_hex(f"PART {page}/{len(parts)}  |  {role.upper()}  |  EPOCH {battle.epoch}  |  AWAITING YOUR DECISION")+
            " Tj ET",
        ])
        raw="\n".join(instructions).encode("ascii")
        streams.append(raw)
    # Deterministic object graph, no embedded JavaScript, URLs, attachments,
    # external resources, annotations, scripts or executable actions.
    object_blobs=[]
    def obj(data):
        object_blobs.append(data)
        return len(object_blobs)
    root=obj(b"<< /Type /Catalog /Pages 2 0 R >>")
    pages_id=obj(b"")
    font1=obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    font2=obj(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    pageids=[]
    for stream in streams:
        compressor=zlib.compress(stream,level=9)
        sid=obj(
            f"<< /Length {len(compressor)} /Filter /FlateDecode >>\nstream\n".encode()+
            compressor+b"\nendstream")
        page_id=obj(
            (f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {PAGE_W:.3f} {PAGE_H:.2f}] "
             f"/Resources << /Font << /F1 {font1} 0 R /F2 {font2} 0 R >> >> "
             f"/Contents {sid} 0 R >>").encode())
        pageids.append(page_id)
    object_blobs[pages_id-1]=(f"<< /Type /Pages /Count {len(parts)} /Kids ["+
                               " ".join(f"{p} 0 R" for p in pageids)+
                               "] >>").encode()
    info=obj((
        "<< /Title "+_pdf_hex(role.title()+" Game Outclassing Battle Plan")+
        " /Author "+_pdf_hex("Skeleton / Approved Multi-Agent Council")+
        " /Producer "+_pdf_hex("Skeleton deterministic PDF compiler")+
        " /Subject "+_pdf_hex(packet_id)+" >>").encode())
    stream=BytesIO()
    stream.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets=[0]
    for i,blob in enumerate(object_blobs,1):
        offsets.append(stream.tell())
        stream.write(f"{i} 0 obj\n".encode()+blob+b"\nendobj\n")
    xref=stream.tell()
    stream.write(f"xref\n0 {len(object_blobs)+1}\n".encode())
    stream.write(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        stream.write(f"{off:010d} 00000 n \n".encode())
    stream.write((
        f"trailer\n<< /Size {len(object_blobs)+1} /Root {root} 0 R "
        f"/Info {info} 0 R >>\nstartxref\n{xref}\n%%EOF\n").encode())
    return stream.getvalue()


def _pdf_3_pages(role,parts,battle,packet_id):
    if type(parts) is not tuple or len(parts)!=3:
        raise ThreatRadarError("legacy packet strictly needs three pages per role")
    return _pdf_pages(role,parts,battle,packet_id)


def _rows(role,page,battle,critique):
    rounds=battle.rounds
    most_recent=rounds[-1]
    review=next(r for r in most_recent.role_reviews if r.role==role)
    all_roles=[next(r for r in rnd.role_reviews if r.role==role)
               for rnd in rounds]
    if page==1:
        rows=[
            ("heading","PART 1 - PROJECT DIAGNOSIS: EVIDENCE BEFORE VICTORY"),
            ("body",f"Original project: {battle.original_id}. Snapshot SHA-256: {battle.snapshot_digest}. "
                    f"Current independent critique: {critique.digest}."),
            ("body",f"Scrutiny coverage: {critique.all_facet_count} facets. "
                    f"Unmeasured original-project facets: {critique.missing_live_measurements}. "
                    f"Verified current-build evidence: {critique.actual_build_measurement_qualified}."),
            ("heading","THE UNIQUE ROLE MANDATE"),
        ]
        rows.extend(("body","- "+x) for x in ROLE_FOCUS[role])
        rows.extend([
            ("heading","MOST CONSEQUENTIAL CURRENT-BUILD FINDINGS"),
        ])
        for v in critique.criticisms[:6]:
            rows.append(("body",f"{v.domain}/{v.facet}: {v.status}. "
                        f"{v.criticism} Remedy: {v.corrective_action[:190]}"))
        rows.extend([
            ("heading","INDUSTRY REFERENCE FRAME"),
            ("body","The ISO/IEC 25010:2023 quality model informs software reliability, "
                    "maintainability and measured effectiveness. Game Accessibility Guidelines "
                    "inform inclusive controls and perception; WCAG 2.2 informs Web-facing UI. "
                    "NIST AI RMF informs AI evaluation, traceability and review risk."),
            ("body","These are source-backed process references, not independent certificates "
                    "of game quality, commercial competitiveness or legal originality."),
            ("heading","HARD GUARD"),
            ("body","Do not assume the user's current game has implemented a feature or a "
                    "competitor has a flaw unless signed relevant game measurements actually exist."),
        ])
    elif page==2:
        rows=[
            ("heading","PART 2 - THREE ROUNDS OF ACTUAL RESEARCH AND CROSS-EXAMINATION"),
            ("body","Every research pass must be reviewed into the current Wiki/Dragon knowledge "
                    "store and cleared against live rights. This PDF contains no copied footage, "
                    "art, sound, lyrics, storylines or unauthorized competitor material."),
        ]
        for i,(round_item,memo) in enumerate(zip(rounds,all_roles),1):
            research=round_item.research
            rows.extend([
                ("heading",f"ROUND {i}: {research.strategy.upper()} / {len(research.source_ids)} SOURCES"),
                ("body",f"Reviewed publisher-dependence groups: {len(research.independent_groups)}. "
                        f"Rights root {research.rights_root[:16]}. Wiki root {research.wiki_root[:16]}. "
                        f"Review score: {memo.quantified_quality_bp}/10000."),
                ("body",f"Challenge to {memo.challenged_role.upper()}: {memo.challenge[:240]}"),
                ("body",f"Answer / strategic correction: {memo.answer_to_prior_objection[:260]}"),
                ("body",f"Priority areas: {', '.join(f.facet for f in memo.findings[:5])}. "
                        f"Hard vetoes: {len(memo.hard_vetoes)}. Verified round: {round_item.accepted}."),
            ])
        rows.extend([
            ("heading","CRAWLER BREADTH / ADVERSARIAL CUSTODY"),
            ("body","R1 scoped hypotheses; R2 refreshed and expanded prior published sources; "
                    "R3 a wider search with more independent groups and broader peer comparisons. "
                    "No round proceeds if crawler freshness, source-rights or any agent's score fails."),
            ("body","The Dragon and Jeeves role names describe separately supplied, credential-verified "
                    "deliberations. Their signatures attest configured keys, not independently verified model identity."),
        ])
    else:
        rows=[
            ("heading","PART 3 - ORIGINAL OUTCLASSING BATTLE PLAN / USER DECISION"),
            ("body","The legitimate objective is to exceed comparable games in verified player value, "
                    "mechanical coherence, visual clarity, sound access and causal storyline quality, "
                    "while retaining this project's authored personality and copyright boundary."),
            ("heading","SPECIFIC ORIGINAL DEVELOPMENT ACTIONS"),
        ]
        findings=sorted(review.findings,key=lambda f:(-f.severity_bp,f.facet))
        for i,f in enumerate(findings[:7],1):
            rows.append(("body",f"{i:02d} / {f.facet.upper()} / {f.evidence_status}. "
                        f"{f.recommendation[:230]} Success: {f.test_of_success[:140]}"))
        rows.extend([
            ("heading","DELIVERY AND GAIN EVIDENCE"),
            ("body","Gate 1: capture source ownership and freeze user design pillars. "
                    "Gate 2: implement a new playable original build in a reviewable branch. "
                    "Gate 3: run matched gameplay/audio/visual/story test cohorts and adversarial controls."),
            ("body","Gate 4: audit against historical rivals, current enemies, accessibility "
                    "and legal similarity. Gate 5: prove nonregression with conservative "
                    "confidence intervals and independent reviewer credentials."),
            ("body","Gate 6: distill only validated original knowledge into Dragon almanacs; "
                    "do not retrain Jeeves/Dragon foundation weights without separate licensed "
                    "training permission and controlled model qualification."),
            ("heading","ROUND-THREE TRI-COUNCIL CONCLUSION"),
            ("body",f"This role's final quality score: {review.quantified_quality_bp}/10000. "
                    f"All three council reviews passed: {all(x.accepted for x in rounds)}. "
                    "The plan is a proposal until the user explicitly approves ALL THREE "
                    "separate three-page PDFs and the identical manifest digest."),
            ("heading","USER CONFIRMATION (REQUIRED, NEVER PRECHECKED)"),
            ("body","[ ] APPROVE the complete Dragon/Jeeves/Adversarial PDF set and proceed "
                    "to separately governed implementation."),
            ("body","[ ] REVISE. State missing detail or strategic objections. A rejected "
                    "packet triggers higher-effort recrawl and all three deliberation rounds again."),
            ("body","[ ] DEFER. No game build, publication, source ingestion or AI model "
                    "promotion is authorized by this PDF alone."),
        ])
    return tuple(rows)


@dataclass(frozen=True,slots=True)
class BattlePdfPacket:
    digest: str
    folder: str
    role_file_sha: tuple[tuple[str,str],...]
    manifest_sha: str
    archive_sha: str
    three_pages_each: bool
    awaiting_user_approval: bool

    def payload(self):
        return dict(schema="skeleton.game_builder.three_ai_pdf_packet.v1",
                    digest=self.digest,folder=self.folder,
                    role_file_sha=[list(x) for x in self.role_file_sha],
                    manifest_sha=self.manifest_sha,archive_sha=self.archive_sha,
                    three_pages_each=self.three_pages_each,
                    awaiting_user_approval=self.awaiting_user_approval,
                    no_automatic_plan_acceptance=True)


def publish_three_ai_pdfs(
    root: str|Path,
    battle: ThreeRoundBattlePlan,
    critique: CurrentProjectCritique, *,
    authorized: bool,
)->tuple[BattlePdfPacket,ThreeRoundBattlePlan]:
    if not authorized:
        raise PermissionError("publish a battle-plan packet only on explicit studio authority")
    if (not isinstance(battle,ThreeRoundBattlePlan)
            or not isinstance(critique,CurrentProjectCritique)
            or not battle.ready_for_pdf_review
            or battle.critique_digest!=critique.digest
            or battle.snapshot_digest!=critique.snapshot_digest
            or battle.original_id!=critique.original_id
            or battle.packet_digest is not None):
        raise ThreatRadarError("three passed research/role rounds and exact current user game required")
    prefix=canonical_digest([battle.digest,critique.digest])
    documents={}
    for role in ROLES:
        pages=tuple(_rows(role,i,battle,critique) for i in (1,2,3))
        documents[role+".pdf"]=_pdf_3_pages(role,pages,battle,prefix)
    doc_sha={role:sha256(documents[role+".pdf"]).hexdigest() for role in ROLES}
    manifest={
        "schema":"skeleton.game_builder.multipart_battle_pdfs.v1",
        "original_id":battle.original_id,
        "battle_preapproval_digest":battle.digest,
        "critique_digest":critique.digest,
        "epoch":battle.epoch,
        "round_research_roots":[x.research.digest for x in battle.rounds],
        "role_pages":{role:3 for role in ROLES},
        "role_document_sha256":doc_sha,
        "all_three_required_for_approval":True,
        "user_approval_status":"AWAITING_EXPLICIT_USER_CONFIRMATION",
        "no_model_called_by_pdf_renderer":True,
        "no_external_network_calls_by_pdf_renderer":True,
    }
    manifest_bytes=(canonical_json(manifest)+"\n").encode("utf-8")
    packet_sha=sha256(manifest_bytes).hexdigest()
    folder=GameWorkspace(root).root/"competitive_intelligence"/"battle_pdf_packets"/packet_sha
    parent=folder.parent
    if parent.is_symlink() or folder.is_symlink():
        raise ThreatRadarError("refuse symlink destination for sensitive peer research PDFs")
    parent.mkdir(parents=True,exist_ok=True)
    folder.mkdir(exist_ok=True)
    archive=BytesIO()
    with zipfile.ZipFile(archive,"w",compression=zipfile.ZIP_DEFLATED) as z:
        for name in sorted(documents):
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,documents[name])
        info=zipfile.ZipInfo("manifest.json",date_time=(1980,1,1,0,0,0))
        info.compress_type=zipfile.ZIP_DEFLATED
        z.writestr(info,manifest_bytes)
    output={**documents,"manifest.json":manifest_bytes,
            "complete-review-packet.zip":archive.getvalue()}
    for name,data in output.items():
        dest=folder/name
        if dest.is_symlink():
            raise ThreatRadarError("untrusted PDF publication destination")
        try:
            with dest.open("xb") as fp:
                fp.write(data)
                fp.flush()
                os.fsync(fp.fileno())
        except FileExistsError:
            if dest.is_symlink() or dest.read_bytes()!=data:
                raise ThreatRadarError("review packet immutable publication collision")
    approved_state=attach_multipart_pdf_packet(battle,packet_sha,authorized=True)
    return BattlePdfPacket(
        packet_sha,str(folder),tuple((r,doc_sha[r]) for r in ROLES),
        sha256(manifest_bytes).hexdigest(),sha256(archive.getvalue()).hexdigest(),
        True,True),approved_state


__all__=["BattlePdfPacket","publish_three_ai_pdfs","_pdf_3_pages"]
