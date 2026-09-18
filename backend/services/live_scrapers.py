"""
═══════════════════════════════════════════════════════════════════════════
 Live Scrapers Service (2026-05-15)
─────────────────────────────────────────────────────────────────────────
 Pulls fresh data from a curated set of public sources into the knowledge
 fabric. All scrape jobs are off-by-default in `scraper_jobs` and must be
 enabled (via API) before they will fire. The runner respects:
   • cadence (hourly / daily / weekly)
   • request timeouts (8s)
   • polite User-Agent + 1 req/3 s rate-limit per host
   • public-HTTPS-only redirect validation
   • streaming size cap (256 KiB per response) before buffering
 The job documents track last_run_at / last_run_status / last_run_count.

 ★ DESIGN NOTE: This is a *light* scraper. We do NOT replace the curated
 patch_notes / github_code_refs data — we only add a fresh row tagged
 `source:"live"` that the agent can grep alongside the canonical entries.
═══════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import asyncio
import hashlib
from ipaddress import ip_address
import logging
import re
import socket
import time
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

log = logging.getLogger("live.scrapers")

UA = "EmergentGalaxyStudio/2026.5 (+research; non-commercial)"
TIMEOUT = httpx.Timeout(8.0, connect=5.0)
SIZE_CAP = 256 * 1024  # 256 KiB
MAX_REDIRECTS = 4
HOST_GUARD: dict[str, float] = {}
HOST_DELAY = 3.0  # seconds between requests per host
CADENCE_SECONDS = {"hourly": 3600, "daily": 86_400, "weekly": 604_800}
_BLOCKED_SCRAPE_HOSTS = frozenset(
    {
        "localhost",
        "metadata.google.internal",
        "metadata.goog",
        "metadata.azure.internal",
    }
)


def _literal_ip(host: str):
    """Parse canonical and legacy IPv4 spellings without DNS resolution."""
    try:
        return ip_address(host)
    except ValueError:
        pass
    try:
        packed = socket.inet_aton(host)
    except OSError:
        return None
    return ip_address(packed)


def _is_public_unicast(address) -> bool:
    """Accept only globally routable unicast addresses for outbound scraping."""
    return bool(
        address.is_global
        and not address.is_multicast
        and not address.is_unspecified
        and not address.is_loopback
        and not address.is_link_local
        and not address.is_reserved
    )


async def _host_resolves_public(host: str) -> bool:
    """Fail closed unless every current DNS answer is a globally routable IP.

    This blocks hostnames that resolve directly to loopback/private/link-local
    space. It is a pre-connect guard, not DNS pinning: the HTTP transport still
    performs its own resolution, so callers must not treat this as complete
    DNS-rebinding protection.
    """
    literal = _literal_ip(host)
    if literal is not None:
        return _is_public_unicast(literal)

    try:
        answers = await asyncio.to_thread(
            socket.getaddrinfo,
            host,
            443,
            type=socket.SOCK_STREAM,
        )
    except (OSError, UnicodeError):
        return False

    if not answers:
        return False

    seen: set[str] = set()
    for answer in answers:
        try:
            raw = answer[4][0]
            resolved = ip_address(raw.split("%", 1)[0])
        except (IndexError, TypeError, ValueError):
            return False
        if not _is_public_unicast(resolved):
            return False
        seen.add(str(resolved))
    return bool(seen)


def _validated_scrape_url(url: str) -> tuple[str, str]:
    """Return normalized public HTTPS URL and hostname, or fail closed."""
    value = url.strip()
    if not value or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value):
        raise ValueError("invalid scrape URL")
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise ValueError("invalid scrape URL") from exc
    if parsed.scheme.lower() != "https":
        raise ValueError("scrape URL must use HTTPS")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("scrape URL must not contain credentials")
    hostname = parsed.hostname
    if not hostname:
        raise ValueError("scrape URL must include a hostname")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("scrape URL has invalid port") from exc
    try:
        normalized_host = hostname.rstrip(".").encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise ValueError("scrape URL has invalid hostname") from exc
    if normalized_host in _BLOCKED_SCRAPE_HOSTS or normalized_host.endswith(".localhost"):
        raise ValueError("scrape URL targets a blocked local endpoint")
    literal = _literal_ip(normalized_host)
    if literal is not None and not _is_public_unicast(literal):
        raise ValueError("scrape URL targets a non-public IP address")
    return value, normalized_host


async def _respect_host_delay(host: str) -> None:
    last = HOST_GUARD.get(host, 0.0)
    wait = HOST_DELAY - (time.time() - last)
    if wait > 0:
        await asyncio.sleep(wait)
    HOST_GUARD[host] = time.time()


async def _polite_get(client: httpx.AsyncClient, url: str) -> str | None:
    """GET public HTTPS content with validated redirects and a streaming size cap."""
    current = url
    for redirect_count in range(MAX_REDIRECTS + 1):
        try:
            current, host = _validated_scrape_url(current)
        except ValueError:
            log.warning("scrape URL rejected by outbound network policy")
            return None

        if not await _host_resolves_public(host):
            log.warning("scrape hostname rejected by outbound DNS policy")
            return None

        await _respect_host_delay(host)
        try:
            async with client.stream(
                "GET",
                current,
                headers={"User-Agent": UA},
                timeout=TIMEOUT,
                follow_redirects=False,
            ) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location or redirect_count >= MAX_REDIRECTS:
                        return None
                    current = urljoin(current, location)
                    # Validate before the next network request, including any
                    # redirect to metadata, loopback, private literal IP, or HTTP.
                    try:
                        _validated_scrape_url(current)
                    except ValueError:
                        log.warning("scrape redirect rejected by outbound network policy")
                        return None
                    continue

                if response.status_code != 200:
                    return None

                content_length = response.headers.get("content-length")
                if content_length:
                    try:
                        if int(content_length) > SIZE_CAP:
                            log.warning("scrape response rejected: declared body exceeds size cap")
                            return None
                    except ValueError:
                        pass

                body = bytearray()
                async for chunk in response.aiter_bytes():
                    if len(body) + len(chunk) > SIZE_CAP:
                        log.warning("scrape response rejected: streamed body exceeds size cap")
                        return None
                    body.extend(chunk)

                encoding = response.encoding or "utf-8"
                return bytes(body).decode(encoding, errors="replace")
        except Exception as exc:
            # Do not log the full URL, response body, signed query values, or raw
            # exception text from network libraries into operational telemetry.
            log.debug("scrape GET failed for host=%s error=%s", host, type(exc).__name__)
            return None
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
    except Exception as exc:
        log.warning("could not read scraper_jobs: %s", type(exc).__name__)
        return {"error": "scraper-jobs-unavailable"}
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
                    {"$set": {
                        "last_run_at":     datetime.now(timezone.utc).isoformat(),
                        "last_run_status": "ok",
                        "last_run_count":  inserted,
                    }},
                )
                summary["ran"].append({"name": name, "inserted": inserted})
                log.info("[scraper] %s: %s new", name, inserted)
            except Exception as exc:
                await db.scraper_jobs.update_one(
                    {"_id": job["_id"]},
                    {"$set": {
                        "last_run_at":     datetime.now(timezone.utc).isoformat(),
                        "last_run_status": f"error:{type(exc).__name__[:60]}",
                    }},
                )
                summary["errors"].append({"name": name, "error": type(exc).__name__})
                log.warning("[scraper] %s failed: %s", name, type(exc).__name__)
    return summary


async def scraper_loop(db, interval_seconds: int = 1800):
    """Long-running loop: wake every `interval_seconds`, run eligible jobs."""
    log.info("[scraper-loop] starting, interval=%ss", interval_seconds)
    while True:
        try:
            await run_scrapers_once(db)
        except Exception as exc:
            log.warning("[scraper-loop] tick failed: %s", type(exc).__name__)
        await asyncio.sleep(interval_seconds)
