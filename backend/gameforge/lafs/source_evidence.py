"""Bounded, opt-in Wikimedia summary ingestion; extracts are untrusted evidence."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
from urllib.parse import quote, urlsplit

import httpx
from core.loop_local_asyncio import LoopLocalAsyncPrimitive

MAX_BODY = 128 * 1024
MAX_EXTRACT = 12000
MAX_TOPIC = 160
HOST = "en.wikipedia.org"
ROOT = f"https://{HOST}/api/rest_v1/page/summary/"
_GATE = LoopLocalAsyncPrimitive(lambda: asyncio.Semaphore(2))
_DIGEST = re.compile(r"[0-9a-f]{64}", re.ASCII)


def online_enabled() -> bool:
    return os.getenv("LAFS_ONLINE_LEARNING", "").strip().lower() in {"1", "true", "yes"}


def _canonical(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def _topic(value: str) -> str:
    if type(value) is not str or not 2 <= len(value.strip()) <= MAX_TOPIC:
        raise ValueError("invalid topic length")
    value = value.strip()
    if any(ord(c) < 32 or ord(c) == 127 for c in value) or value in {".", ".."}:
        raise ValueError("invalid topic characters")
    return value


def validate_evidence(doc: dict) -> dict:
    if not isinstance(doc, dict):
        raise ValueError("invalid evidence")
    required = ("title", "extract", "source_url", "revision", "response_sha256", "evidence_sha256", "fetched_at")
    record = {k: doc.get(k) for k in required}
    for key, max_len in (("title", 512), ("extract", MAX_EXTRACT), ("source_url", 2048)):
        val = record[key]
        if type(val) is not str or not 1 <= len(val) <= max_len:
            raise ValueError("invalid bounded source field")
    url = urlsplit(record["source_url"])
    if (url.scheme != "https" or url.netloc != HOST or not url.path.startswith("/wiki/")
            or url.query or url.fragment):
        raise ValueError("source URL is outside the admitted origin")
    if type(record["revision"]) is not int or not 0 < record["revision"] < 2**63:
        raise ValueError("missing source revision")
    if any(type(record[k]) is not str or not _DIGEST.fullmatch(record[k])
           for k in ("response_sha256", "evidence_sha256")):
        raise ValueError("invalid evidence digest")
    if type(record["fetched_at"]) not in (float, int) or not 0 < record["fetched_at"] < 2**40:
        raise ValueError("invalid fetch time")
    fields = {k: record[k] for k in ("title", "extract", "source_url", "revision")}
    if hashlib.sha256(_canonical(fields)).hexdigest() != record["evidence_sha256"]:
        raise ValueError("evidence digest mismatch")
    return record


async def wiki_summary(topic: str) -> dict | None:
    if not online_enabled():
        raise PermissionError("online learning disabled")
    topic = _topic(topic)
    url = ROOT + quote(topic, safe="")
    # One admission window covers waiting, connecting, headers and all body bytes.
    async with asyncio.timeout(15):
        async with _GATE.get():
            async with httpx.AsyncClient(timeout=8, follow_redirects=False, trust_env=False,
                  headers={"User-Agent": "GameForge-LAFS/2.0 (https://github.com/Apeloff1/Skeleton)",
                           "Accept": "application/json", "Accept-Encoding": "identity"}) as client:
                async with client.stream("GET", url) as response:
                    if response.status_code != 200:
                        return None
                    if response.headers.get("content-encoding", "identity").lower() != "identity":
                        raise ValueError("unexpected content encoding")
                    if response.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
                        raise ValueError("unexpected source media type")
                    length = response.headers.get("content-length")
                    if length is not None and (not length.isascii() or not length.isdecimal()
                                               or len(length) > 7 or int(length) > MAX_BODY):
                        raise ValueError("source response exceeds byte budget")
                    raw = bytearray()
                    async for chunk in response.aiter_raw():
                        if len(raw) + len(chunk) > MAX_BODY:
                            raise ValueError("source response exceeds byte budget")
                        raw.extend(chunk)
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate source JSON key")
            result[key] = value
        return result
    doc = json.loads(raw, object_pairs_hook=unique_pairs)
    if not isinstance(doc, dict) or doc.get("type") == "disambiguation" or not doc.get("extract"):
        return None
    fields = {"title": doc.get("title"), "extract": doc.get("extract"),
              "source_url": ((doc.get("content_urls") or {}).get("desktop") or {}).get("page"),
              "revision": doc.get("revision")}
    if isinstance(fields["revision"], str) and re.fullmatch(r"[0-9]{1,19}", fields["revision"], re.ASCII):
        fields["revision"] = int(fields["revision"])
    return validate_evidence({**fields,
        "response_sha256": hashlib.sha256(raw).hexdigest(),
        "evidence_sha256": hashlib.sha256(_canonical(fields)).hexdigest(),
        "fetched_at": time.time()})
