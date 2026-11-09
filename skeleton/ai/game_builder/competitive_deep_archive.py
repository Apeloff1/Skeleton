"""Persistent, versioned enemy deep dossier history for Dragon/Wiki/HOAG.

No stale snapshot can replace an earlier evolutionary chain. Each revision
anchors the exact reviewed-Wiki state, rights clearance, original studio
watch snapshot and all 51 measured/unmeasured facets. SQLite WAL provides
atomic local custody and a content hash-chain; it is NOT external notarization
or tamper proof against an attacker controlling the whole disk.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import json
import sqlite3

from .contracts import canonical_json,canonical_digest
from .competitive_title_radar import ThreatRadarError,_date,_id
from .competitive_deep_service import DeepCompetitorPortfolio
from .competitive_watch_service import CompetitionRun
from .reviewed_knowledge import KnowledgeBrief,ReviewedKnowledgeStore
from .knowledge_rights_bridge import (
    ClearedResearchPacket,require_cleared_research_current,
)
from .rights import RightsLedger
from .game_project_workspace import GameWorkspace

SCHEMA="skeleton.game_builder.enemy_deep_archive.v1"


@dataclass(frozen=True,slots=True)
class DeepArchiveReceipt:
    original_id: str
    revision: int
    as_of: str
    parent_digest: str|None
    entry_digest: str
    portfolio_digest: str
    source_knowledge_root: str
    enemy_ids: tuple[str,...]

    def payload(self):
        return dict(schema=SCHEMA,original_id=self.original_id,
                    revision=self.revision,as_of=self.as_of,
                    parent_digest=self.parent_digest,
                    entry_digest=self.entry_digest,
                    portfolio_digest=self.portfolio_digest,
                    source_knowledge_root=self.source_knowledge_root,
                    enemy_ids=list(self.enemy_ids),
                    immutable_game_title_history=True,
                    external_signature_or_notarization=False,
                    output_was_not_crawled_or_game_code_modified=True)


class DeepEnemyArchive:
    def __init__(self,root: str|Path):
        ws=GameWorkspace(root)
        folder=ws.root/"competitive_intelligence"
        if folder.is_symlink():
            raise ThreatRadarError("unsafe competitor root symlink")
        folder.mkdir(exist_ok=True)
        path=folder/"deep_archive.sqlite3"
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ThreatRadarError("unsafe competitor archive database")
        self.db=sqlite3.connect(str(path),timeout=12,isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=12000")
        self.db.execute("""CREATE TABLE IF NOT EXISTS competitor_deep_archive(
            original_id TEXT NOT NULL,
            revision INTEGER NOT NULL,
            as_of TEXT NOT NULL,
            parent_digest TEXT,
            content_json TEXT NOT NULL,
            digest TEXT NOT NULL,
            PRIMARY KEY(original_id,revision))""")

    def __enter__(self):
        return self

    def __exit__(self,*args):
        self.close()

    def close(self):
        self.db.close()

    @staticmethod
    def _unique(pairs):
        result={}
        for k,v in pairs:
            if k in result:
                raise ThreatRadarError("duplicate enemy archive field")
            result[k]=v
        return result

    def _history(self,original_id):
        _id(original_id,"original game identity")
        rows=self.db.execute(
            "SELECT revision,as_of,parent_digest,content_json,digest "
            "FROM competitor_deep_archive WHERE original_id=? ORDER BY revision",
            (original_id,)).fetchall()
        if len(rows)>5000:
            raise ThreatRadarError("enemy archive exceeds safe verification scan budget")
        prev=None
        prev_stamp=None
        items=[]
        for seq,(revision,stamp,parent,raw,digest) in enumerate(rows):
            if type(raw) is not str or len(raw)>1500000:
                raise ThreatRadarError("enemy archive size or encoding invalid")
            try:
                body=json.loads(raw,object_pairs_hook=self._unique,
                                parse_constant=lambda v: (_ for _ in ()).throw(
                                    ThreatRadarError("non-finite enemy analysis score")))
            except (TypeError,ValueError) as exc:
                raise ThreatRadarError("unparseable enemy archive revision") from exc
            if (revision!=seq or parent!=prev or
                    type(body) is not dict or body.get("schema")!=SCHEMA
                    or body.get("original_id")!=original_id
                    or body.get("revision")!=seq
                    or body.get("as_of")!=stamp
                    or body.get("parent_digest")!=prev
                    or canonical_json(body)!=raw
                    or canonical_digest(body)!=digest):
                raise ThreatRadarError("enemy archive parent/content integrity failure")
            when=_date(stamp)
            if prev_stamp is not None and when<=prev_stamp:
                raise ThreatRadarError("enemy archive chronology rollback")
            portfolio=body.get("portfolio")
            if (not isinstance(portfolio,dict)
                    or portfolio.get("original_id")!=original_id
                    or body.get("portfolio_digest")!=canonical_digest(portfolio)):
                raise ThreatRadarError("enemy archive portfolio custody mismatch")
            prev=digest
            prev_stamp=when
            items.append((body,digest))
        return tuple(items)

    def history(self,original_id: str,*,authorized: bool):
        if not authorized:
            raise PermissionError("historical rival analysis requires operator authorization")
        return self._history(original_id)

    def record(self, portfolio: DeepCompetitorPortfolio,
               overview: CompetitionRun,
               brief: KnowledgeBrief,
               packet: ClearedResearchPacket,
               wiki: ReviewedKnowledgeStore,
               rights: RightsLedger, *,
               as_of: str,
               expected_parent_digest: str|None,
               authorized: bool)->DeepArchiveReceipt:
        if not authorized:
            raise PermissionError("original enemy analysis custody needs authorization")
        if (not isinstance(portfolio,DeepCompetitorPortfolio)
                or not isinstance(overview,CompetitionRun)
                or not isinstance(brief,KnowledgeBrief)
                or not isinstance(packet,ClearedResearchPacket)
                or not isinstance(wiki,ReviewedKnowledgeStore)
                or not isinstance(rights,RightsLedger)):
            raise ThreatRadarError("existing canonical game competitor and Wiki authorities required")
        _date(as_of)
        if (portfolio.original_id!=overview.original_id
                or portfolio.overview_digest!=canonical_digest(overview.payload())
                or as_of!=overview.as_of
                or brief.scope!="design_reference"
                or brief.owner!=packet.owner
                or packet.knowledge_root!=brief.knowledge_root
                or packet.research_brief_digest!=brief.to_payload()["brief_digest"]):
            raise ThreatRadarError("deep evidence and current competitor watch mismatch")
        wiki.require_fresh_brief(brief,authorized=True)
        require_cleared_research_current(packet,wiki,rights,authorized=True)
        ids={x.rival_id for x in overview.assessments if x.status=="enemy"}
        if (ids!={d.enemy_id for d in portfolio.enemy_dossiers}
                or portfolio.pending_analyzes
                or len(portfolio.enemy_dossiers)!=len(ids)):
            raise ThreatRadarError("cannot archive incomplete enemy portfolio while claiming all coverage")
        for dossier in portfolio.enemy_dossiers:
            if (dossier.original_id!=portfolio.original_id
                    or dossier.evolution.source_root!=canonical_digest([
                        brief.knowledge_root,packet.rights_ledger_digest])
                    or dossier.ancestral_frontier.evolution_digest!=dossier.evolution.digest
                    or not dossier.analysis_scripts
                    or len(dossier.analysis_scripts)!=len(dossier.facet_verdicts)
                    or len(dossier.analysis_scripts)!=len(dossier.ancestral_frontier.studies)
                    or any(script.evidence_root!=brief.knowledge_root
                           for script in dossier.analysis_scripts)):
                raise ThreatRadarError("incomplete or non-current detailed game analysis")
        if expected_parent_digest is not None and (
                type(expected_parent_digest) is not str
                or len(expected_parent_digest)!=64 or
                any(c not in "0123456789abcdef" for c in expected_parent_digest)):
            raise ThreatRadarError("explicit optimistic archive parent SHA required")
        self.db.execute("BEGIN IMMEDIATE")
        try:
            history=self._history(portfolio.original_id)
            last=history[-1] if history else None
            parent=last[1] if last else None
            if parent!=expected_parent_digest:
                raise ThreatRadarError("stale independently reviewed evolution lineage revision")
            if last and _date(last[0]["as_of"])>=_date(as_of):
                raise ThreatRadarError("revision must contain a later independent review")
            payload=portfolio.payload()
            body=dict(schema=SCHEMA,original_id=portfolio.original_id,
                      revision=len(history),as_of=as_of,
                      parent_digest=parent,source_knowledge_root=brief.knowledge_root,
                      cleared_rights_digest=packet.rights_ledger_digest,
                      overview_digest=portfolio.overview_digest,
                      portfolio_digest=canonical_digest(payload),
                      portfolio=payload)
            raw=canonical_json(body)
            if len(raw)>1400000:
                raise ThreatRadarError("enemy analysis exceeded bounded archive limit")
            digest=canonical_digest(body)
            self.db.execute(
                "INSERT INTO competitor_deep_archive("
                "original_id,revision,as_of,parent_digest,content_json,digest)"
                " VALUES(?,?,?,?,?,?)",
                (portfolio.original_id,len(history),as_of,parent,raw,digest))
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return DeepArchiveReceipt(
            portfolio.original_id,len(history),as_of,parent,digest,
            canonical_digest(payload),brief.knowledge_root,tuple(sorted(ids)))


__all__=["DeepEnemyArchive","DeepArchiveReceipt"]
