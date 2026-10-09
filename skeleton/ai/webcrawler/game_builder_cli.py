"""Build a playable original game from previously captured research on disk.

Usage:
 python -m skeleton.ai.webcrawler.game_builder_cli \
   --title "Moon Leap" --genre platformer --engine web \
   --sources capture.json --output game.zip --approve

The JSON source file is LOCAL, UNTRUSTED input for design research; it is not
proof of a crawl, publication permissions, or permission to train on source text.
Remote acquisition belongs to the policy-bound CrawlEngine entry point.
"""
from __future__ import annotations

from argparse import ArgumentParser
from hashlib import sha256
from pathlib import Path
from time import time
from urllib.parse import urlsplit
import json
import sqlite3

from .core import CrawlDocument, FetchResponse, CrawlPolicy, extract_document
from .game_builder_knowledge_runtime import KnowledgeDrivenGameBuilder


def import_research_captures(
    filename: Path, *, max_bytes: int = 16_000_000,
    max_docs: int = 100,
) -> tuple[CrawlDocument, ...]:
    """Import acquired-text snapshots as *unverified* research, never training."""
    if not filename.is_file():
        raise ValueError("source capture file not found")
    if filename.stat().st_size > max_bytes:
        raise ValueError("capture manifest exceeds input budget")
    manifest=json.loads(filename.read_text(encoding="utf-8"))
    if not isinstance(manifest,list) or len(manifest)>max_docs:
        raise ValueError("source capture manifest must be a bounded list")
    documents=[]
    for item in manifest:
        if not isinstance(item,dict):
            raise ValueError("invalid capture record")
        url=item.get("url")
        text=item.get("text")
        if not isinstance(url,str) or not isinstance(text,str):
            raise ValueError("capture needs URL and text")
        if not CrawlPolicy().admits(url):
            raise ValueError("disallowed capture source")
        if urlsplit(url).username is not None or urlsplit(url).password is not None:
            raise ValueError("credentialed capture source")
        if len(text.encode("utf-8")) > 1000000:
            raise ValueError("capture document exceeds size budget")
        if not text.strip():
            raise ValueError("empty capture body")
        # Deliberately represent this as a LOCAL imported snapshot, not a
        # forged 200 HTTP response or signed transport provenance.
        digest=sha256(" ".join(text.split()).encode("utf-8")).hexdigest()
        from .core import canonicalize_url
        source=canonicalize_url(url)
        documents.append(CrawlDocument(
            source,source,str(item.get("title", ""))[:200],
            " ".join(text.split()),"text/plain",digest,0.,0.35,
            {"schema":"skeleton.ai.crawl.local_capture.v1",
             "canonical_url":source,"content_hash":digest,
             "trust":"unverified_local_import"},
            (),
        ))
    return tuple(documents)


def run(args=None) -> int:
    parser=ArgumentParser(description="Compile an original knowledge-guided game")
    parser.add_argument("--title", required=True)
    parser.add_argument("--genre", choices=("platformer","action","puzzle","exploration"),
                        required=True)
    parser.add_argument("--engine", choices=("web","godot"), default="web")
    parser.add_argument("--sources", type=Path, help="Optional locally captured research JSON")
    parser.add_argument("--database", type=Path, help="Persistent SQLite knowledge database")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--width", type=int, default=32)
    parser.add_argument("--height", type=int, default=14)
    parser.add_argument("--approve", action="store_true",
                        help="Explicitly approve original game generation")
    opts=parser.parse_args(args)
    if not opts.approve:
        parser.error("Game generation requires --approve")
    db=sqlite3.connect(str(opts.database) if opts.database else ":memory:")
    try:
        builder=KnowledgeDrivenGameBuilder(db)
        if opts.sources:
            builder.ingest_captured_documents(
                import_research_captures(opts.sources),
                engine=opts.engine,authorized=True,
            )
        generated=builder.build_game(
            title=opts.title,genre=opts.genre,engine=opts.engine,
            seed=opts.seed,width=opts.width,height=opts.height,
            authorized=True,human_approved=True,
        )
        opts.output.parent.mkdir(parents=True,exist_ok=True)
        opts.output.write_bytes(generated.archive)
        print(json.dumps({
            "output":str(opts.output),
            "game_title":generated.title,
            "target":opts.engine,
            "archive_sha256":sha256(generated.archive).hexdigest(),
            "knowledge_sources":generated.knowledge_sources,
            "missing_topics":[g.topic for g in generated.missing_topics if g.coverage<1],
            "playable_route":generated.metrics.playable,
            "mechanics":generated.blueprint.mechanics,
        },sort_keys=True,indent=2))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(run())
