"""
#7 Shareable links / OG unfurl cards. Returns lightweight HTML with Open-Graph +
Twitter meta so a shared game/tournament link previews nicely; human visitors are
redirected into the app. Crawlable at /api/share/... (served by the backend).
"""
from __future__ import annotations

import os
import html
import json
from urllib.parse import quote, urlencode, urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from core.databases import client as _SHARED_MONGO_CLIENT

router = APIRouter(prefix="/api/share", tags=["share"])
_db = _SHARED_MONGO_CLIENT[os.environ.get("DB_NAME", "test_database")]


def _app_origin() -> str:
    """Use an operator-supplied origin, never the request Host header."""
    raw = os.environ.get("PUBLIC_APP_URL", "").strip()
    if not raw:
        if os.environ.get("ENVIRONMENT", "").strip().lower() in {
            "production", "prod", "staging",
        }:
            raise ValueError("PUBLIC_APP_URL is required outside development")
        raw = "http://localhost:3000"
    parsed = urlsplit(raw)
    if (not parsed.hostname or parsed.username is not None
            or parsed.password is not None or parsed.fragment or parsed.query
            or parsed.path not in ("", "/") or "\\" in raw):
        raise ValueError("PUBLIC_APP_URL must be a plain absolute origin")
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    ):
        raise ValueError("PUBLIC_APP_URL must use HTTPS outside local development")
    # Reject malformed ports and URL authority suffixes before using the origin.
    port = parsed.port
    if not parsed.netloc or (port is not None and not 1 <= port <= 65535):
        raise ValueError("invalid PUBLIC_APP_URL authority")
    return raw.rstrip("/")


def _safe_link_id(value: str) -> str:
    """Keep untrusted identifiers as one URL component, never URL syntax."""
    if not isinstance(value, str) or not 1 <= len(value) <= 128:
        raise ValueError("invalid share identifier")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise ValueError("invalid share identifier")
    return quote(value, safe="")


def _page(title: str, desc: str, image: str, deep_link: str) -> str:
    t = html.escape(title, quote=True)
    d = html.escape(desc, quote=True)
    image_attr = html.escape(image, quote=True)
    deep_link_attr = html.escape(deep_link, quote=True)
    # JSON encoding makes the redirect a JavaScript string literal rather than
    # executable markup. Escape HTML-significant code points so a crafted URL
    # cannot terminate the surrounding script element.
    deep_link_js = (
        json.dumps(deep_link)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{t}</title>
<meta name="description" content="{d}">
<meta property="og:type" content="website">
<meta property="og:title" content="{t}">
<meta property="og:description" content="{d}">
<meta property="og:image" content="{image_attr}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{t}">
<meta name="twitter:description" content="{d}">
<meta name="twitter:image" content="{image_attr}">
<style>body{{margin:0;background:#0A0A0A;color:#E5E5E5;font-family:system-ui,-apple-system,sans-serif;
display:flex;min-height:100vh;align-items:center;justify-content:center;text-align:center}}
.c{{padding:32px;max-width:520px}}img{{width:220px;height:220px;border-radius:20px;border:1px solid #262626;object-fit:cover}}
h1{{font-size:24px;letter-spacing:.4px}}a{{display:inline-block;margin-top:20px;background:#8B5CF6;color:#fff;
text-decoration:none;padding:14px 28px;border-radius:12px;font-weight:800}}p{{color:#A3A3A3}}</style>
<script>setTimeout(function(){{location.href={deep_link_js}}},1200)</script></head>
<body><div class="c"><img src="{image_attr}" alt="cover"/><h1>{t}</h1><p>{d}</p>
<a href="{deep_link_attr}">▶ Open in Galaxy Studio</a></div></body></html>"""


@router.get("/playable/{pid}", response_class=HTMLResponse)
async def share_playable(pid: str, request: Request):
    base = _app_origin()
    g = await _db.playables.find_one(
        {"playable_id": pid}, {"_id": 0, "title": 1, "genre": 1, "has_cover": 1,
                               "evaluation.overall": 1, "plays": 1})
    if not g:
        return HTMLResponse(_page("Game not found", "This game is unavailable.",
                                  f"{base}/icon.png", f"{base}/playable"), status_code=404)
    overall = (g.get("evaluation") or {}).get("overall")
    desc = f"A {g.get('genre','arcade')} game on Galaxy Studio" + (f" · scored {overall}/100" if overall else "") + \
           (f" · {g.get('plays')} plays" if g.get("plays") else "") + ". Play it now!"
    encoded_pid = _safe_link_id(pid)
    image = f"{base}/api/playable/{encoded_pid}/cover.png"
    deep_link = f"{base}/playable?{urlencode({'id': pid})}"
    return HTMLResponse(_page(g.get("title", "Untitled Game"), desc, image, deep_link))


@router.get("/tournament/{tid}", response_class=HTMLResponse)
async def share_tournament(tid: str, request: Request):
    base = _app_origin()
    t = await _db.tournaments.find_one({"tournament_id": tid}, {"_id": 0})
    if not t:
        return HTMLResponse(_page("Tournament not found", "This bracket is unavailable.",
                                  f"{base}/icon.png", f"{base}/tournaments"), status_code=404)
    champ_img = f"{base}/icon.png"
    if t.get("champion_id"):
        champ_img = f"{base}/api/playable/{_safe_link_id(t['champion_id'])}/cover.png"
    status = "🏆 Champion crowned!" if t.get("status") == "complete" else f"⚔️ Live · Round {t.get('current_round',0)+1}"
    desc = f"Bracket of {t.get('size')} · {status} — vote for your favourite game!"
    return HTMLResponse(_page(t.get("name", "Tournament"), desc, champ_img, f"{base}/tournaments"))
