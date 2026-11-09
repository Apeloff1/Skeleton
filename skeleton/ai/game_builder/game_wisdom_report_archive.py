"""Immutable secondary-game-wisdom reporting with stage-by-stage provenance.

The report is an unambiguous *candidate experiment record*, not evidence
that trained core LLM weights were installed. All nine signed review SHA
receipts, newly researched Wiki roots, original-game source projects,
before/after measured model deltas and withheld-advice reasons survive
across subsequent Dragon recrawl cycles. The archive is content-addressed
and never permits silent overwrite of an earlier finding.
"""
from __future__ import annotations

from pathlib import Path
import json
import os

from .contracts import canonical_json,canonical_digest
from .game_secondary_wisdom_loop import SecondaryWisdomCycle
from .game_project_workspace import GameWorkspace
from .game_model_promotion import PromotionError


def publish_secondary_wisdom_report(
    workspace_root: str|Path,
    report: SecondaryWisdomCycle, *,
    authorized: bool,
)->str:
    if not authorized:
        raise PermissionError("auditable post-weight knowledge reporting needs operator permission")
    if (not isinstance(report,SecondaryWisdomCycle)
            or not report.source_breadth_increased
            or len(report.tasks)<3
            or len(report.verification_receipts)!=9
            or len(set(report.verification_receipts))!=9):
        raise PromotionError("full evidence-bound three-pass second-glance report required")
    if report.post_second_weights is not None and (
            report.second_training is None
            or report.second_training.optimization is None
            or report.post_second_weights.plan_digest!=
               report.second_training.original_game_plan_digest):
        raise PromotionError("second reviewer weight-delta report has mismatched original game projects")
    if report.second_training is not None and (
            report.second_training.optimization is not None
            and report.post_second_weights is None):
        raise PromotionError("cannot archive unexamined second candidate SGD weights")
    ws=GameWorkspace(workspace_root)
    base=ws.root/"training"
    folder=base/"post_weight_wisdom"
    if (base.is_symlink() or folder.is_symlink()
            or not base.is_dir()):
        raise PromotionError("unsafe verified-game learning directory")
    folder.mkdir(exist_ok=True,mode=0o700)
    payload=report.payload()
    raw=(canonical_json(payload)+"\n").encode("utf-8")
    if len(raw)>1_000_000:
        raise PromotionError("uncapped knowledge-promotion report size")
    digest=canonical_digest(payload)
    path=folder/(digest+".json")
    if path.is_symlink():
        raise PromotionError("post-weight wisdom symlink publication forbidden")
    try:
        with path.open("xb") as out:
            out.write(raw)
            out.flush()
            os.fsync(out.fileno())
    except FileExistsError:
        if path.is_symlink() or path.read_bytes()!=raw:
            raise PromotionError("content-addressed second wisdom report changed or was overwritten")
    return digest


def verify_secondary_wisdom_report(
    workspace_root: str|Path,report_digest: str,*,authorized: bool,
)->dict:
    if not authorized:
        raise PermissionError("historical weight/knowledge audit needs permission")
    if (type(report_digest) is not str or len(report_digest)!=64
            or any(c not in "0123456789abcdef" for c in report_digest)):
        raise PromotionError("exact canonical digest required")
    ws=GameWorkspace(workspace_root)
    base=ws.root/"training"/"post_weight_wisdom"
    if base.is_symlink():
        raise PromotionError("unsafe historic wisdom archive")
    path=base/(report_digest+".json")
    if path.is_symlink() or not path.is_file() or path.stat().st_size>1_000_000:
        raise PromotionError("missing, unsafe or oversized historical wisdom report")
    raw=path.read_bytes()
    try:
        def unique(pairs):
            out={}
            for key,value in pairs:
                if key in out:
                    raise PromotionError("repeated report key invalidates evidence")
                out[key]=value
            return out
        value=json.loads(raw,object_pairs_hook=unique,
                         parse_constant=lambda x: (_ for _ in ()).throw(
                             PromotionError("nonfinite wisdom confidence")))
    except (ValueError,TypeError,UnicodeError) as exc:
        raise PromotionError("invalid historical wisdom JSON") from exc
    if (type(value) is not dict
            or value.get("schema")!="skeleton.game_builder.second_glance_knowledge_and_weights.v1"
            or len(value.get("verification_receipts",[]))!=9
            or canonical_digest(value)!=report_digest
            or raw!=(canonical_json(value)+"\n").encode()):
        raise PromotionError("historical post-weight report parent or content integrity failure")
    return value


__all__=["publish_secondary_wisdom_report",
         "verify_secondary_wisdom_report"]
