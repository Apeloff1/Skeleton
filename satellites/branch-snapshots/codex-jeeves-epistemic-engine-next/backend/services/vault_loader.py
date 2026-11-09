"""
vault_loader.py — Stream samples from any of the 300+ compressed vault
collections (`/app/backend/data/vault/compressed/*.jsonl.zst`).

Used by:
  • Compiler            — fetch relevant code patterns for the target language
  • Galaxy Studio       — already wired via _fetch_vault_samples
  • Agents              — query for design patterns / build recipes during a step
  • Jeeves              — pull domain knowledge to flavour responses

All access is read-only and streaming — collections are 100k+ rows each.
"""
from __future__ import annotations
import os, json, asyncio, re, glob
from pathlib import Path
from typing import Iterator, AsyncIterator, Optional
try:
    import zstandard as zstd
    _HAS_ZSTD = True
except Exception:
    _HAS_ZSTD = False

VAULT_DIR = Path("/app/backend/data/vault/compressed")


def list_collections() -> list[str]:
    """Return all available collection names (without extension)."""
    if not VAULT_DIR.exists():
        return []
    out = []
    for p in VAULT_DIR.glob("*.jsonl.zst"):
        out.append(p.stem.replace(".jsonl", ""))
    return sorted(out)


def _iter_jsonl(path: Path, limit: int = 50) -> Iterator[dict]:
    """Stream-decompress a .jsonl.zst file, yielding parsed rows up to limit."""
    if not _HAS_ZSTD:
        return
    if not path.exists():
        return
    n = 0
    dctx = zstd.ZstdDecompressor()
    with path.open("rb") as fh, dctx.stream_reader(fh) as reader:
        buffer = b""
        while n < limit:
            chunk = reader.read(65536)
            if not chunk:
                if buffer:
                    try:
                        yield json.loads(buffer.decode("utf-8", errors="ignore"))
                    except Exception:
                        pass
                break
            buffer += chunk
            while b"\n" in buffer and n < limit:
                line, buffer = buffer.split(b"\n", 1)
                if not line.strip():
                    continue
                try:
                    yield json.loads(line.decode("utf-8", errors="ignore"))
                    n += 1
                except Exception:
                    continue


def query_collection(
    collection: str,
    limit: int = 10,
    contains: Optional[str] = None,
) -> list[dict]:
    """Fetch up to `limit` rows from a vault collection. Optional substring filter."""
    candidates = [
        VAULT_DIR / f"{collection}.jsonl.zst",
        VAULT_DIR / f"coll__{collection}.jsonl.zst",
    ]
    path = next((p for p in candidates if p.exists()), None)
    if not path:
        return []
    out: list[dict] = []
    needle = contains.lower() if contains else None
    for row in _iter_jsonl(path, limit=limit * 5 if needle else limit):
        if needle:
            blob = json.dumps(row).lower()
            if needle not in blob:
                continue
        out.append(row)
        if len(out) >= limit:
            break
    return out


def query_topic(topic: str, limit: int = 10) -> dict:
    """
    Fuzzy: look up the best-matching collection(s) for a topic word and return
    samples from each. Useful for compiler/agent integration when caller doesn't
    know exact collection names.
    """
    norm = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")
    cols = list_collections()
    matches = [c for c in cols if norm and norm in c.lower()]
    if not matches:
        # Try first-word fallback
        first = norm.split("-")[0]
        if first:
            matches = [c for c in cols if first in c.lower()]
    out = {}
    for m in matches[:3]:
        out[m] = query_collection(m, limit=limit)
    return out


def stats() -> dict:
    cols = list_collections()
    total_bytes = 0
    for p in VAULT_DIR.glob("*.jsonl.zst"):
        try:
            total_bytes += p.stat().st_size
        except Exception:
            pass
    return {
        "collections":  len(cols),
        "total_bytes":  total_bytes,
        "has_zstd":     _HAS_ZSTD,
        "vault_dir":    str(VAULT_DIR),
        "sample_names": cols[:10],
    }
