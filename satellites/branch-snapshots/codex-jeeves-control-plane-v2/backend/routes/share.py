"""
#7 Shareable links / OG unfurl cards. Returns lightweight HTML with Open-Graph +
Twitter meta so a shared game/tournament link previews nicely; human visitors are
redirected into the app. Crawlable at /api/share/... (served by the backend).
"""
from __future__ import annotations

import os
import html

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from core.databases import client as _SHARED_MONGO_CLIENT

router = APIRouter(prefix="/api/share", tags=["share"])
_db = _SHARED_MONGO_CLIENT[os.environ.get("DB_NAME", "test_database")]


def _page(title: str, desc: str, image: str, deep_link: str) -> str:
    t, d = html.escape(title), html.escape(desc)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{t}</title>
<meta name="description" content="{d}">
<meta property="og:type" content="website">
<meta property="og:title" content="{t}">
<meta property="og:description" content="{d}">
<meta property="og:image" content="{image}">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{t}">
<meta name="twitter:description" content="{d}">
<meta name="twitter:image" content="{image}">
<style>body{{margin:0;background:#0A0A0A;color:#E5E5E5;font-family:system-ui,-apple-system,sans-serif;
display:flex;min-height:100vh;align-items:center;justify-content:center;text-align:center}}
.c{{padding:32px;max-width:520px}}img{{width:220px;height:220px;border-radius:20px;border:1px solid #262626;object-fit:cover}}
h1{{font-size:24px;letter-spacing:.4px}}a{{display:inline-block;margin-top:20px;background:#8B5CF6;color:#fff;
text-decoration:none;padding:14px 28px;border-radius:12px;font-weight:800}}p{{color:#A3A3A3}}</style>
<script>setTimeout(function(){{location.href={deep_link!r}}},1200)</script></head>
<body><div class="c"><img src="{image}" alt="cover"/><h1>{t}</h1><p>{d}</p>
<a href="{deep_link}">▶ Open in Galaxy Studio</a></div></body></html>"""


@router.get("/playable/{pid}", response_class=HTMLResponse)
async def share_playable(pid: str, request: Request):
    base = str(request.base_url).rstrip("/")
    g = await _db.playables.find_one(
        {"playable_id": pid}, {"_id": 0, "title": 1, "genre": 1, "has_cover": 1,
                               "evaluation.overall": 1, "plays": 1})
    base = _APP
    if not g:
        return HTMLResponse(_page("Game not found", "This game is unavailable.",
                                  f"{base}/icon.png", f"{base}/playable"), status_code=404)
    overall = (g.get("evaluation") or {}).get("overall")
    desc = f"A {g.get('genre','arcade')} game on Galaxy Studio" + (f" · scored {overall}/100" if overall else "") + \
           (f" · {g.get('plays')} plays" if g.get("plays") else "") + ". Play it now!"
    image = f"{base}/api/playable/{pid}/cover.png"
    return HTMLResponse(_page(g.get("title", "Untitled Game"), desc, image, f"{base}/playable?id={pid}"))


@router.get("/tournament/{tid}", response_class=HTMLResponse)
async def share_tournament(tid: str, request: Request):
    base = str(request.base_url).rstrip("/")
    t = await _db.tournaments.find_one({"tournament_id": tid}, {"_id": 0})
    base = _APP
    if not t:
        return HTMLResponse(_page("Tournament not found", "This bracket is unavailable.",
                                  f"{base}/icon.png", f"{base}/tournaments"), status_code=404)
    champ_img = f"{base}/icon.png"
    if t.get("champion_id"):
        champ_img = f"{base}/api/playable/{t['champion_id']}/cover.png"
    status = "🏆 Champion crowned!" if t.get("status") == "complete" else f"⚔️ Live · Round {t.get('current_round',0)+1}"
    desc = f"Bracket of {t.get('size')} · {status} — vote for your favourite game!"
    return HTMLResponse(_page(t.get("name", "Tournament"), desc, champ_img, f"{base}/tournaments"))
