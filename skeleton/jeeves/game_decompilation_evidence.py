"""Offline structural attestation of game decompilation receipt chains.

Verifies exact hashes, budgets, scopes, input offsets and human/learning
separation. Never treats a self-committed report as independent proof that
code was executed, rights checked, game assets identified or quality improved.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from .game_decompilation import REPORT_SCHEMA, MAX_GAME_BYTES, SCOPES, _NAME, _SHA
from .game_decompilation_quality import QUALITY_SCHEMA
from .game_decompilation_learning import CANDIDATE_SCHEMA

MAX_REPORT_BYTES = 8 * 1024 * 1024


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value,sort_keys=True,
        separators=(",",":"),ensure_ascii=True,allow_nan=False).encode()).hexdigest()


def verify_game_decompilation_report(
    raw: Mapping[str, Any], *,
    expected_source_sha256: str | None = None,
    expected_rights_sha256: str | None = None,
) -> dict[str, Any]:
    if not isinstance(raw,dict) or raw.get("schema_version")!=REPORT_SCHEMA:
        raise ValueError("Canonical bounded decompilation evidence required")
    if len(json.dumps(raw,sort_keys=True,allow_nan=False).encode())>MAX_REPORT_BYTES:
        raise ValueError("Decompilation evidence exceeds maximum source proof size")
    unsigned={k:v for k,v in raw.items() if k!="report_sha256"}
    if raw.get("report_sha256")!=_digest(unsigned):
        raise ValueError("Source decompilation report receipt digest differs")
    source=raw.get("source_sha256")
    size=raw.get("source_size_bytes")
    rights=raw.get("provenance")
    if (type(source) is not str or not _SHA.fullmatch(source)
        or type(size) is not int or not 1<=size<=MAX_GAME_BYTES
        or not isinstance(rights,dict) or type(rights.get("rights_evidence_digest")) is not str
        or not _SHA.fullmatch(rights["rights_evidence_digest"])
        or not isinstance(rights.get("principal_ref"),str)
        or not _NAME.fullmatch(rights["principal_ref"])
        or type(rights.get("authorized_scopes")) is not list
        or any(x not in SCOPES for x in rights["authorized_scopes"])
        or len(set(rights["authorized_scopes"]))!=len(rights["authorized_scopes"])):
        raise ValueError("Game bytes, provenance or permitted scopes lack exact declared identity")
    if (expected_source_sha256 is not None and source!=expected_source_sha256
        or expected_rights_sha256 is not None
           and rights["rights_evidence_digest"]!=expected_rights_sha256):
        raise ValueError("Decompilation report mismatches expected rights or game source")
    if (raw.get("native_executable_or_game_rom_executed") is not False
        or raw.get("production_model_training_performed") is not False
        or raw.get("model_weights_updated") is not False
        or raw.get("full_original_source_recovered") is not False
        or raw.get("complete_source_or_asset_binary_embedded") is not False):
        raise ValueError("Evidence must not falsely claim code execution or production learning")
    previews=raw.get("preview_artifacts")
    if (not isinstance(previews,list) or len(previews)>256
        or previews and "export_asset_previews" not in rights["authorized_scopes"]):
        raise ValueError("PNG preview list exceeds authorized evidence limit")
    names=set()
    for item in previews:
        if (not isinstance(item,dict)
            or set(item)!={"name","sha256","size_bytes","content_kind"}
            or type(item["name"]) is not str
            or not _NAME.fullmatch(item["name"])
            or not item["name"].endswith(".png")
            or item["name"] in names
            or type(item["sha256"]) is not str or not _SHA.fullmatch(item["sha256"])
            or type(item["size_bytes"]) is not int
            or not 1<=item["size_bytes"]<=2*1024*1024):
            raise ValueError("Authorized export receipt has an unsafe or forged image shape")
        names.add(item["name"])
    code=raw.get("code_analysis")
    instruction_count=0
    if code and code.get("supported") is True:
        if "reverse_engineer_code" not in rights["authorized_scopes"]:
            raise ValueError("Unauthorized code disassembly included in report")
        listing=code.get("instructions")
        if (not isinstance(listing,list) or len(listing)>4096
            or len(listing)!=code.get("instructions_emitted")):
            raise ValueError("Static code map size/counters differ")
        seen={}
        for instr in listing:
            offset=instr.get("file_offset") if isinstance(instr,dict) else None
            if type(offset) is not int or not 0<=offset<size:
                raise ValueError("Instruction file offset is outside original binary")
            rawhex=instr.get("instruction_bytes",instr.get("instruction_word_hex"))
            if (type(rawhex) is not str or not 2<=len(rawhex)<=8
                or len(rawhex)%2 or any(ch not in "0123456789abcdef" for ch in rawhex)):
                raise ValueError("Decoded instruction byte representation was modified")
            # An NROM-128 16 KiB PRG is physically mirrored at $8000/$C000.
            # The same verified bytes can have two different CPU addresses.
            if offset in seen and (
                code.get("architecture") != "mos6502_nrom" or seen[offset] != rawhex
            ):
                raise ValueError("Conflicting duplicate binary instruction offset")
            seen[offset]=rawhex
        instruction_count=len(listing)
    assets=raw.get("asset_analysis")
    if assets is not None and "decode_assets" not in rights["authorized_scopes"]:
        raise ValueError("Unexpected graphics analysis without admitted rights")
    brief=raw.get("quality_brief")
    if brief is not None:
        if "derive_quality_features" not in rights["authorized_scopes"]:
            raise ValueError("Review features exist without an authorizing rights scope")
        if (not isinstance(brief,dict) or brief.get("schema_version")!=QUALITY_SCHEMA
            or brief.get("source_sha256")!=source
            or brief.get("rights_evidence_digest")!=rights["rights_evidence_digest"]
            or brief.get("raw_game_assets_included") is not False
            or brief.get("production_weight_promotion_allowed") is not False
            or brief.get("brief_digest")!=_digest({k:v for k,v in brief.items() if k!="brief_digest"})):
            raise ValueError("Derived quality brief differs from its source and scope proof")
    result={
        "schema_version":"skeleton.game.decompilation_evidence_verified.v1",
        "source_sha256":source,
        "report_sha256":raw["report_sha256"],
        "rights_evidence_digest":rights["rights_evidence_digest"],
        "static_instructions_verified_structurally":instruction_count,
        "authorized_preview_receipts":len(previews),
        "quality_brief_hash_verified":brief is not None,
        "locally_consistent":True,
        "gameplay_fidelity_or_rights_independently_verified":False,
        "production_training_occurred":False,
    }
    result["verification_sha256"]=_digest(result)
    return result


def verify_human_label_against_report(
    label: Mapping[str, Any], report: Mapping[str, Any],
) -> dict[str, Any]:
    status=verify_game_decompilation_report(report)
    if not isinstance(label,dict) or label.get("schema_version")!=CANDIDATE_SCHEMA:
        raise ValueError("Independent human-scored label evidence required")
    if (label.get("source_sha256")!=status["source_sha256"]
        or label.get("quality_brief_sha256")!=report.get("quality_brief",{}).get("brief_digest")
        or label.get("training_rights_digest")!=status["rights_evidence_digest"]
        or label.get("candidate_sha256")!=_digest({k:v for k,v in label.items() if k!="candidate_sha256"})
        or "human_labeled_shadow_training" not in report["provenance"]["authorized_scopes"]):
        raise ValueError("Human label points to a different source, brief, rights or scope")
    return {
        "source_sha256":status["source_sha256"],
        "report_sha256":status["report_sha256"],
        "human_label_receipt_sha256":label["candidate_sha256"],
        "sources_and_rights_bound":True,
        "license_legal_review_independent":False,
        "weights_promoted":False,
    }
