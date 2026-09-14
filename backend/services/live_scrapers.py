"""
Live Scrapers Service.

Pulls fresh data from a fixed, curated set of public sources into the
knowledge fabric. Jobs are off by default. Network reads are intentionally
small and fail closed: redirects are not followed, only HTTPS URLs are
accepted, response bytes are capped while streaming, and identifiers use
SHA-256 rather than weak cryptographic hashes.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlsplit

import httpx

log = logging.getLogger("live.scrapers")

UA = "EmergentGalaxyStudio/2026.5 (+research; non-commercial)"
TIMEOUT = httpx.Timeout(8.0, connect=5.0)
SIZE_CAP = 256 * 1024
HOST_GUARD: dict[str, float] = {}
HOST_DELAY = 3.0
CADENCE_SECONDS = {"hourly": 3600, "daily": 86_400, "weekly": 604_800}
ALLOWED_SCRAPER_HOSTS = frozenset(
    {
        "blog.unity.com",
        "www.unrealengine.com",
        "unrealengine.com",
        "godotengine.org",
        "www.godotengine.org",
        "github.com",
    }
)


def _stable_id(namespace: str, value: str) -> str:
    """Return a compact deterministic identifier backed by SHA-256."""
    payload = f"{namespace}|{value}".encode("utf-8", errors="strict")
    return hashlib.sha256(payload).hexdigest()[:18]


def _validated_scraper_url(url: str) -> tuple[str, str] | None:
    """Return ``(url, host)`` only for an explicitly approved HTTPS host."""
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme != "https" or not host or host not in ALLOWED_SCRAPER_HOSTS:
        return None
    if parsed.username or parsed.password:
        return None
    if parsed.port not in (None, 443):
        return None
    return url, host


async def _polite_get(client: httpx.AsyncClient, url: str) -> str | None:
    """GET an approved URL with host throttling and an actual byte cap."""
    validated = _validated_scraper_url(url)
    if validated is None:
        log.warning("blocked non-curated scraper URL")
        return None
    safe_url, host = validated

    last = HOST_GUARD.get(host, 0.0)
    wait = HOST_DELAY - (time.monotonic() - last)
    if wait > 0:
        await asyncio.sleep(wait)
    HOST_GUARD[host] = time.monotonic()

    try:
        async with client.stream(
            "GET",
            safe_url,
            headers={"User-Agent": UA, "Accept": "text/html,application/rss+xml,application/xml;q=0.9,*/*;q=0.1"},
            timeout=TIMEOUT,
        ) as response:
            if response.status_code != 200:
                return None

            content_length = response.headers.get("content-length")
            if content_length:
                try:
                    if int(content_length) > SIZE_CAP:
                        return None
                except ValueError:
                    return None

            data = bytearray()
            async for chunk in response.aiter_bytes():
                if len(data) + len(chunk) > SIZE_CAP:
                    return None
                data.extend(chunk)

            encoding = response.encoding or "utf-8"
            try:
                return bytes(data).decode(encoding, errors="replace")
            except LookupError:
                return bytes(data).decode("utf-8", errors="replace")
    except httpx.HTTPError as exc:
        log.debug("scrape GET host=%s failed: %s", host, type(exc).__name__)
        return None


# ─── Parsers (lightweight, no external deps) ─────────────────────────
def _extract_rss_items(xml: str, limit: int = 12) -> list[dict[str, str]]:
    items = []
    for match in re.finditer(r"<item\b[^>]*>(.*?)</item>", xml, flags=re.S | re.I):
        block = match.group(1)
        title = _xml_tag(block, "title")
        link = _xml_tag(block, "link")
        pub = _xml_tag(block, "pubDate") or _xml_tag(block, "updated")
        if title:
            items.append({"title": title[:200], "link": link[:400], "pub": pub[:60]})
        if len(items) >= limit:
            break
    return items


def _xml_tag(block: str, tag: str) -> str:
    match = re.search(
        rf"<{tag}[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{tag}>",
        block,
        flags=re.S | re.I,
    )
    return (match.group(1) or "").strip() if match else ""


def _extract_github_trending(html: str, limit: int = 25) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for match in re.finditer(r'href="/([A-Za-z0-9_\-\.]+/[A-Za-z0-9_\-\.]+)"', html):
        repo = match.group(1)
        if repo.endswith(".git") or "/" not in repo or repo in seen:
            continue
        seen.add(repo)
        rows.append({"repo": repo, "url": f"https://github.com/{repo}"})
        if len(rows) >= limit:
            break
    return rows


# ─── Job implementations ─────────────────────────────────────────────
async def _job_unity_blog(db, client) -> int:
    text = await _polite_get(client, "https://blog.unity.com/feed")
    if not text:
        return 0
    inserted = 0
    for item in _extract_rss_items(text):
        doc = {
            "source": "live",
            "feed": "unity-blog",
            "title": item["title"],
            "link": item["link"],
            "pub_date": item["pub"],
            "tags": ["unity", "blog", "live"],
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "_id_hash": _stable_id("unity-blog", item["link"]),
        }
        try:
            result = await db.patch_notes.update_one(
                {"_id_hash": doc["_id_hash"]}, {"$set": doc}, upsert=True
            )
            if result.upserted_id is not None:
                inserted += 1
        except Exception:
            pass
    return inserted


async def _job_unreal_blog(db, client) -> int:
    text = await _polite_get(client, "https://www.unrealengine.com/rss")
    if not text:
        return 0
    inserted = 0
    for item in _extract_rss_items(text):
        doc = {
            "source": "live",
            "feed": "unreal-blog",
            "title": item["title"],
            "link": item["link"],
            "pub_date": item["pub"],
            "tags": ["unreal", "blog", "live"],
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "_id_hash": _stable_id("unreal-blog", item["link"]),
        }
        try:
            result = await db.patch_notes.update_one(
                {"_id_hash": doc["_id_hash"]}, {"$set": doc}, upsert=True
            )
            if result.upserted_id is not None:
                inserted += 1
        except Exception:
            pass
    return inserted


async def _job_godot_blog(db, client) -> int:
    text = await _polite_get(client, "https://godotengine.org/rss.xml")
    if not text:
        return 0
    inserted = 0
    for item in _extract_rss_items(text):
        doc = {
            "source": "live",
            "feed": "godot-blog",
            "title": item["title"],
            "link": item["link"],
            "pub_date": item["pub"],
            "tags": ["godot", "blog", "live"],
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "_id_hash": _stable_id("godot-blog", item["link"]),
        }
        try:
            result = await db.patch_notes.update_one(
                {"_id_hash": doc["_id_hash"]}, {"$set": doc}, upsert=True
            )
            if result.upserted_id is not None:
                inserted += 1
        except Exception:
            pass
    return inserted


async def _job_github_trending(db, client) -> int:
    text = await _polite_get(client, "https://github.com/trending?since=daily")
    if not text:
        return 0
    inserted = 0
    for row in _extract_github_trending(text):
        doc = {
            "source": "live",
            "feed": "github-trending",
            "repo": row["repo"],
            "url": row["url"],
            "tags": ["github", "trending", "live"],
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "_id_hash": _stable_id("github-trending", row["repo"]),
        }
        try:
            result = await db.github_code_refs.update_one(
                {"_id_hash": doc["_id_hash"]}, {"$set": doc}, upsert=True
            )
            if result.upserted_id is not None:
                inserted += 1
        except Exception:
            pass
    return inserted


JOB_HANDLERS = {
    "unity-blog": _job_unity_blog,
    "unreal-blog": _job_unreal_blog,
    "godot-blog": _job_godot_blog,
    "github-trending": _job_github_trending,
}


async def _should_run(job: dict) -> bool:
    if not job.get("enabled"):
        return False
    last = job.get("last_run_at")
    if not last:
        return True
    try:
        dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
        delta = (datetime.now(timezone.utc) - dt).total_seconds()
        return delta >= CADENCE_SECONDS.get(job.get("cadence", "daily"), 86_400)
    except (TypeError, ValueError):
        return True


async def run_scrapers_once(db) -> dict[str, Any]:
    """Run every eligible scraper once. Returns a summary dict."""
    summary: dict[str, Any] = {"ran": [], "skipped": [], "errors": []}
    try:
        jobs = await db.scraper_jobs.find({}).to_list(200)
    except Exception as exc:
        log.warning("could not read scraper_jobs: %s", type(exc).__name__)
        return {"error": type(exc).__name__}

    # Redirects are intentionally disabled. A compromised public feed must not
    # be able to bounce this backend toward an internal/private destination.
    async with httpx.AsyncClient(follow_redirects=False, timeout=TIMEOUT) as client:
        for job in jobs:
            name = job.get("name") or ""
            handler = JOB_HANDLERS.get(name)
            if not handler:
                summary["skipped"].append({"name": name, "reason": "no-handler"})
                continue
            if not await _should_run(job):
                summary["skipped"].append({"name": name, "reason": "not-due"})
                continue
            try:
                inserted = await handler(db, client)
                await db.scraper_jobs.update_one(
                    {"_id": job["_id"]},
                    {
                        "$set": {
                            "last_run_at": datetime.now(timezone.utc).isoformat(),
                            "last_run_status": "ok",
                            "last_run_count": inserted,
                        }
                    },
                )
                summary["ran"].append({"name": name, "inserted": inserted})
                log.info("[scraper] %s: %d new", name, inserted)
            except Exception as exc:
                error_name = type(exc).__name__
                await db.scraper_jobs.update_one(
                    {"_id": job["_id"]},
                    {
                        "$set": {
                            "last_run_at": datetime.now(timezone.utc).isoformat(),
                            "last_run_status": f"error:{error_name}",
                        }
                    },
                )
                summary["errors"].append({"name": name, "error": error_name})
                log.warning("[scraper] %s failed: %s", name, error_name)
    return summary


async def scraper_loop(db, interval_seconds: int = 1800):
    """Long-running loop: wake periodically and run eligible jobs."""
    interval_seconds = max(60, int(interval_seconds))
    log.info("[scraper-loop] starting, interval=%ss", interval_seconds)
    while True:
        try:
            await run_scrapers_once(db)
        except Exception as exc:
            log.warning("[scraper-loop] tick failed: %s", type(exc).__name__)
        await asyncio.sleep(interval_seconds)
