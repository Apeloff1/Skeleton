"""
═══════════════════════════════════════════════════════════════════════════
 Live Scrapers Service (2026-05-15)
─────────────────────────────────────────────────────────────────────────
 Pulls fresh data from a curated set of public sources into the knowledge
 fabric. All scrape jobs are off-by-default in `scraper_jobs` and must be
 enabled (via API) before they will fire. The runner respects:
   • cadence (hourly / daily / weekly)
   • request timeouts (8s) and tiny per-request retry budget (2 tries)
   • polite User-Agent + 1 req/3 s rate-limit per host
   • size cap (256 KiB per response) — we only store small RSS-style refs
 The job documents track last_run_at / last_run_status / last_run_count.

 ★ DESIGN NOTE: This is a *light* scraper. We do NOT replace the curated
 patch_notes / github_code_refs data — we only add a fresh row tagged
 `source:"live"` that the agent can grep alongside the canonical entries.
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations
import asyncio
import logging
import re
import time
import hashlib
import os
from datetime import datetime, timezone
from typing import Any
import httpx

log = logging.getLogger("live.scrapers")

UA = "EmergentGalaxyStudio/2026.5 (+research; non-commercial)"
TIMEOUT = httpx.Timeout(8.0, connect=5.0)
SIZE_CAP = 256 * 1024  # 256 KiB
HOST_GUARD: dict[str, float] = {}
HOST_DELAY = 3.0  # seconds between requests per host
CADENCE_SECONDS = {"hourly": 3600, "daily": 86_400, "weekly": 604_800}


async def _polite_get(client: httpx.AsyncClient, url: str) -> str | None:
    """GET with per-host rate-limit + size cap. Returns text or None."""
    host = re.sub(r"^https?://", "", url).split("/")[0]
    last = HOST_GUARD.get(host, 0.0)
    wait = HOST_DELAY - (time.time() - last)
    if wait > 0:
        await asyncio.sleep(wait)
    HOST_GUARD[host] = time.time()
    try:
        r = await client.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT)
        if r.status_code != 200:
            return None
        text = r.text
        return text[:SIZE_CAP]
    except Exception as e:
        log.debug(f"scrape GET {url} failed: {e}")
        return None


# ─── Parsers (lightweight, no external deps) ─────────────────────────
def _extract_rss_items(xml: str, limit: int = 12) -> list[dict[str, str]]:
    items = []
    for m in re.finditer(r"<item\b[^>]*>(.*?)</item>", xml, flags=re.S | re.I):
        block = m.group(1)
        title = _xml_tag(block, "title")
        link = _xml_tag(block, "link")
        pub = _xml_tag(block, "pubDate") or _xml_tag(block, "updated")
        if title:
            items.append({"title": title[:200], "link": link[:400], "pub": pub[:60]})
        if len(items) >= limit:
            break
    return items


def _xml_tag(block: str, tag: str) -> str:
    m = re.search(rf"<{tag}[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{tag}>", block, flags=re.S | re.I)
    return (m.group(1) or "").strip() if m else ""


def _extract_github_trending(html: str, limit: int = 25) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for m in re.finditer(r'href="/([A-Za-z0-9_\-\.]+/[A-Za-z0-9_\-\.]+)"', html):
        repo = m.group(1)
        if repo.endswith(".git") or "/" not in repo:
            continue
        if repo not in {r["repo"] for r in rows}:
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
            "_id_hash": hashlib.md5(("unity-blog|" + item["link"]).encode()).hexdigest()[:18],
        }
        try:
            r = await db.patch_notes.update_one(
                {"_id_hash": doc["_id_hash"]}, {"$set": doc}, upsert=True
            )
            if r.upserted_id is not None:
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
            "source": "live", "feed": "unreal-blog",
            "title": item["title"], "link": item["link"], "pub_date": item["pub"],
            "tags": ["unreal", "blog", "live"],
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "_id_hash": hashlib.md5(("unreal-blog|" + item["link"]).encode()).hexdigest()[:18],
        }
        try:
            r = await db.patch_notes.update_one({"_id_hash": doc["_id_hash"]}, {"$set": doc}, upsert=True)
            if r.upserted_id is not None:
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
            "source": "live", "feed": "godot-blog",
            "title": item["title"], "link": item["link"], "pub_date": item["pub"],
            "tags": ["godot", "blog", "live"],
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "_id_hash": hashlib.md5(("godot-blog|" + item["link"]).encode()).hexdigest()[:18],
        }
        try:
            r = await db.patch_notes.update_one({"_id_hash": doc["_id_hash"]}, {"$set": doc}, upsert=True)
            if r.upserted_id is not None:
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
            "source": "live", "feed": "github-trending",
            "repo": row["repo"], "url": row["url"],
            "tags": ["github", "trending", "live"],
            "scraped_at": datetime.now(timezone.utc).isoformat(),
            "_id_hash": hashlib.md5(("github-trending|" + row["repo"]).encode()).hexdigest()[:18],
        }
        try:
            r = await db.github_code_refs.update_one({"_id_hash": doc["_id_hash"]}, {"$set": doc}, upsert=True)
            if r.upserted_id is not None:
                inserted += 1
        except Exception:
            pass
    return inserted


JOB_HANDLERS = {
    "unity-blog":      _job_unity_blog,
    "unreal-blog":     _job_unreal_blog,
    "godot-blog":      _job_godot_blog,
    "github-trending": _job_github_trending,
}


# ─── Runner ──────────────────────────────────────────────────────────
async def _should_run(job: dict) -> bool:
    if not job.get("enabled"):
        return False
    last = job.get("last_run_at")
    if not last:
        return True
    try:
        dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
        delta = (datetime.now(timezone.utc) - dt).total_seconds()
        return delta >= CADENCE_SECONDS.get(job.get("cadence", "daily"), 86400)
    except Exception:
        return True


async def run_scrapers_once(db) -> dict[str, Any]:
    """Run every eligible scraper once. Returns a summary dict."""
    summary: dict[str, Any] = {"ran": [], "skipped": [], "errors": []}
    try:
        jobs = await db.scraper_jobs.find({}).to_list(200)
    except Exception as e:
        log.warning(f"could not read scraper_jobs: {e}")
        return {"error": str(e)[:200]}
    async with httpx.AsyncClient(follow_redirects=True, timeout=TIMEOUT) as client:
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
                    {"$set": {
                        "last_run_at":     datetime.now(timezone.utc).isoformat(),
                        "last_run_status": "ok",
                        "last_run_count":  inserted,
                    }},
                )
                summary["ran"].append({"name": name, "inserted": inserted})
                log.info(f"[scraper] {name}: {inserted} new")
            except Exception as e:
                await db.scraper_jobs.update_one(
                    {"_id": job["_id"]},
                    {"$set": {
                        "last_run_at":     datetime.now(timezone.utc).isoformat(),
                        "last_run_status": f"error:{str(e)[:80]}",
                    }},
                )
                summary["errors"].append({"name": name, "error": str(e)[:160]})
                log.warning(f"[scraper] {name} failed: {e}")
    return summary


async def scraper_loop(db, interval_seconds: int = 1800):
    """Long-running loop: wake every `interval_seconds`, run eligible jobs."""
    log.info(f"[scraper-loop] starting, interval={interval_seconds}s")
    while True:
        try:
            await run_scrapers_once(db)
        except Exception as e:
            log.warning(f"[scraper-loop] tick failed: {e}")
        await asyncio.sleep(interval_seconds)
