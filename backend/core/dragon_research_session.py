"""Explicit, request-scoped Dragon research projection over canonical stores.

Config is read only from trusted application environment at installation.
Each request gets its own SQLite connections so FastAPI threadpool workers do
not share a connection with another thread. There is NO empty-DB fallback,
no browser-supplied path, no crawler worker or model promotion.
"""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import sqlite3

from skeleton.ai.game_builder.dragon_almanacs import DragonAlmanacs
from skeleton.ai.game_builder.dragon_technical_source_atlas import DragonTechnicalSources
from skeleton.ai.game_builder.dragon_technical_source_captures import DragonSourceCaptures
from skeleton.ai.game_builder.dragon_article_hatchling import DragonArticleHatchling
from skeleton.ai.game_builder.dragon_source_delta_ledger import DragonSourceDeltaLedger
from skeleton.ai.game_builder.dragon_video_transcript_ledger import DragonVideoTranscriptLedger
from skeleton.ai.game_builder.dragon_three_hatchling_coordinator import (
    DragonThreeHatchlingCoordinator,
)
from skeleton.ai.game_builder.reviewed_knowledge import ReviewedKnowledgeStore
from skeleton.ai.webcrawler.dragon_nest_store import DragonNestStore
from skeleton.ai.webcrawler.dragon_nest_source_feed import DragonNestSourceFeed


class DragonResearchSessionFactory:
    """Trusted application configuration; no HTTP-issued authority."""

    def __init__(self, *, knowledge_path: str | Path, nest_path: str | Path,
                 nest_key: bytes, transcript_review_public_key: bytes,
                 transcript_issuer: str, transcript_key_id: str):
        knowledge=Path(knowledge_path).expanduser()
        nest=Path(nest_path).expanduser()
        if (not knowledge.is_absolute() or not nest.is_absolute()
            or not knowledge.is_file() or not nest.is_file()
            or knowledge.is_symlink() or nest.is_symlink()):
            raise ValueError("existing canonical research and nest SQLite files required")
        if type(nest_key) is not bytes or len(nest_key)<32:
            raise ValueError("independent signed nest secret required")
        if type(transcript_review_public_key) is not bytes or len(transcript_review_public_key)!=32:
            raise ValueError("separate 32-byte external transcript public key required")
        if not isinstance(transcript_issuer,str) or not transcript_issuer:
            raise ValueError("authenticated transcript reviewer issuer required")
        if not isinstance(transcript_key_id,str) or not transcript_key_id:
            raise ValueError("independent transcript review key ID required")
        self.knowledge_path=knowledge
        self.nest_path=nest
        self._nest_key=nest_key
        self._review_key=transcript_review_public_key
        self._issuer=transcript_issuer
        self._key_id=transcript_key_id

    @classmethod
    def from_env(cls):
        """Only called by the server's explicit trusted startup opt-in."""
        def secret(name: str)->bytes:
            value=os.environ.get(name,"")
            try:
                return bytes.fromhex(value)
            except ValueError:
                return b""
        return cls(
            knowledge_path=os.environ.get("SKL_DRAGON_KNOWLEDGE_DB_PATH",""),
            nest_path=os.environ.get("SKL_DRAGON_PRACTICE_DB_PATH",""),
            nest_key=secret("SKL_DRAGON_NEST_SIGNING_KEY_HEX"),
            transcript_review_public_key=secret(
                "SKL_DRAGON_TRANSCRIPT_REVIEW_PUBLIC_KEY_HEX"),
            transcript_issuer=os.environ.get("SKL_DRAGON_TRANSCRIPT_REVIEW_ISSUER",""),
            transcript_key_id=os.environ.get("SKL_DRAGON_TRANSCRIPT_REVIEW_KEY_ID",""),
        )

    @contextmanager
    def open(self):
        # Recheck existence: an operator must never move the file after boot
        # and accidentally cause SQLite to create a new empty research vault.
        if not self.knowledge_path.is_file() or not self.nest_path.is_file():
            raise ValueError("canonical research storage disappeared")
        with ReviewedKnowledgeStore(self.knowledge_path) as library:
            nest_db=sqlite3.connect(str(self.nest_path),timeout=5)
            try:
                nest_db.execute("PRAGMA busy_timeout=5000")
                nest=DragonNestStore(nest_db,signing_key=self._nest_key)
                almanacs=DragonAlmanacs(library)
                atlas=DragonTechnicalSources(almanacs)
                captures=DragonSourceCaptures(almanacs)
                feed=DragonNestSourceFeed(almanacs,atlas,nest)
                video=DragonVideoTranscriptLedger(
                    feed,review_public_key=self._review_key,
                    issuer=self._issuer,key_id=self._key_id)
                yield DragonThreeHatchlingCoordinator(
                    DragonArticleHatchling(captures),video,
                    DragonSourceDeltaLedger(captures),nest)
            finally:
                nest_db.close()
