"""Actual acquisition-to-playable-game orchestration for Dragon Game Forge.

Unlike a document-only masterplan, this API accepts acquired pages, persists
mechanics, constructs original build levels, and returns executable HTML/ZIP
artifacts. Explicit authorization and human approval remain separate gates.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Callable, Iterable
from io import BytesIO
from zipfile import ZipFile
import sqlite3

from .core import CrawlDocument, CrawlEngine
from .game_knowledge_acquisition import (
    GameSource, acquire_game_documents, discover_game_research,
    prioritize_game_sources, queue_game_sources,
)
from .game_knowledge_index import GameKnowledgeIndex, KnowledgeGap
from .game_knowledge_design import (
    GameBlueprint, LevelMetrics, propose_game_blueprint,
    populate_game_level, analyze_level_playability,
)
from .game_playable_builder import (
    CompiledGame, build_playable_web_game, export_playable_game_archive,
)
from .dragon_game_builder_bridge import GameBuilderHandoff


@dataclass(frozen=True)
class GameKnowledgeBuild:
    title: str
    blueprint: GameBlueprint
    playable: CompiledGame
    archive: bytes
    metrics: LevelMetrics
    knowledge_sources: int
    missing_topics: tuple[KnowledgeGap, ...]
    human_review_required: bool


class KnowledgeDrivenGameBuilder:
    """Working game acquisition + knowledge + construction entry point."""

    def __init__(self, db: sqlite3.Connection):
        self.knowledge = GameKnowledgeIndex(db)

    def ingest_captured_documents(
        self, docs: Iterable[CrawlDocument], *, engine: str,
        authorized: bool, max_docs: int = 100,
    ) -> int:
        if not authorized:
            raise PermissionError("game knowledge ingestion requires authorization")
        if not 1<=max_docs<=1000:
            raise ValueError("invalid game document budget")
        count=0
        for doc in docs:
            if count>=max_docs:
                raise ValueError("game document ingestion budget exceeded")
            source_id=sha256(doc.canonical_url.encode("utf-8")).hexdigest()
            self.knowledge.ingest_document(
                source_id,doc,engine=engine,authorized=True,
            )
            count+=1
        return count

    def discover_and_acquire(
        self, crawler: CrawlEngine, transport: Callable, *,
        genre: str, engine: str, now: float,
        authorized: bool, max_sources: int = 50, max_steps: int = 100,
    ) -> tuple[CrawlDocument, ...]:
        """Use installed crawler's real robots/frontier/redirect/egress controls.

        Live network I/O occurs only through caller-provided policy-bound
        transport/fetcher. A candidate source is not evidence until its page
        is actually fetched and indexed.
        """
        if not authorized:
            raise PermissionError("game research execution requires authorization")
        suggestions=discover_game_research(
            genre,engine,transport,authorized=True,
            max_results=max_sources,
        )
        selected=prioritize_game_sources(suggestions,genre=genre,engine=engine,
                                         max_sources=max_sources)
        queue_game_sources(crawler,selected,max_enqueues=max_sources)
        docs=acquire_game_documents(crawler,now=now,max_steps=max_steps)
        self.ingest_captured_documents(docs,engine=engine,authorized=True,
                                       max_docs=max_sources)
        return docs

    def build_game(
        self, *, title: str, genre: str, seed: int = 0,
        engine: str = "web", authorized: bool, human_approved: bool,
        width: int = 32, height: int = 14,
        handoff: GameBuilderHandoff | None = None,
    ) -> GameKnowledgeBuild:
        if not authorized or not human_approved:
            raise PermissionError("playable game generation requires human approval")
        if handoff is not None:
            if not isinstance(handoff,GameBuilderHandoff):
                raise ValueError("invalid Game Forge handoff")
            if not handoff.requires_original_assets:
                raise ValueError("game builder must retain original-asset rule")
            if not handoff.prototype.candidate_id or not handoff.review_fingerprint:
                raise ValueError("missing reviewed design provenance")
            # Use the human-reviewed Forge genre, not a caller-controlled
            # competing genre that could defeat the approved design scope.
            reviewed_genre=handoff.prototype.constraints.genre.casefold().strip()
            mapping={"platforming":"platformer","platformer":"platformer",
                     "action":"action","combat":"action","puzzle":"puzzle",
                     "exploration":"exploration","adventure":"exploration"}
            genre=mapping.get(reviewed_genre,genre)
        source_count=self.knowledge.db.execute(
            "SELECT COUNT(*) FROM game_knowledge_sources WHERE active=1"
        ).fetchone()[0]
        blueprint=propose_game_blueprint(
            self.knowledge,title=title,genre=genre,engine=engine,
            seed=seed,width=width,height=height,
        )
        blueprint=populate_game_level(blueprint)
        metrics=analyze_level_playability(blueprint)
        if not metrics.playable:
            raise RuntimeError("generated game failed route validation")
        playable=build_playable_web_game(blueprint)
        archive=export_playable_game_archive(blueprint)
        gaps=self.knowledge.missing_knowledge(
            tuple(m for m in blueprint.mechanics
                  if m in ("movement","collision","jump","combat",
                           "camera","puzzle","enemy_ai","collectible")),
            min_sources=2,
        )
        return GameKnowledgeBuild(
            title,blueprint,playable,archive,metrics,
            source_count,gaps,True,
        )
