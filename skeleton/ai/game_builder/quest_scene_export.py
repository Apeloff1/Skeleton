"""Content-addressed original game director playable browser preview."""
from __future__ import annotations
from dataclasses import dataclass
from hashlib import sha256
from html import escape
from .quest_scene_engine import DirectorWorld, DirectorError
from .quest_scene_browser_client import DIRECTOR_CLIENT
from .playable_export import _safe_script_json, _sha256_csp

STYLE = "body{font:16px system-ui;color:#eee;background:#172b39;padding:1rem}button{font:inherit;padding:.7rem;margin:.2rem}article{background:#234252;padding:1rem;margin:.5rem 0}#stage-screen{min-height:165px;background:#294a59;border:2px solid #94bece;border-radius:1rem;padding:1rem;transition:transform .5s,background .5s}#stage-cast{display:flex;gap:.7rem;flex-wrap:wrap}#stage-cast span{display:inline-flex;background:#557b84;padding:1rem;border:2px solid #c6e4dd;border-radius:2rem;transition:transform .4s,opacity .4s}#stage-subtitle{min-height:2rem;color:#ffe1a7}#cinema{background:#38314f;padding:1rem}#cinema[hidden]{display:none}pre{white-space:pre-wrap}"
TEMPLATE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="__CSP__">
<title>Original Quest Scene Director</title><style>__STYLE__</style></head><body>
<header><h1 id="name"></h1><p id="set"></p><p id="visual"></p>
<p id="actors"></p><strong id="stats"></strong></header><main>
<article id="stage-screen" aria-label="Authored original cutscene">
<div id="stage-cast"></div><p id="stage-subtitle"></p></article>
<article><h2>Play and travel</h2><div id="actions"></div>
<button id="undo">Undo</button><button id="restart">Restart</button>
<button id="download">Download actions</button></article>
<article id="cinema" hidden><h2 id="cinema-title"></h2><div id="cues"></div>
<button id="skip">Skip cinematic</button></article>
<article><h2>Quest paths</h2><div id="quests"></div></article>
<article><h2>Lore and decisions</h2><pre id="journal"></pre></article>
</main><script>__SCRIPT__</script></body></html>"""

@dataclass(frozen=True, slots=True)
class DirectorBrowser:
    html: bytes
    source_sha256: str
    world_digest: str

def render_director_browser(world: DirectorWorld, *, authorized: bool) -> DirectorBrowser:
    if not authorized:
        raise PermissionError("offline original game preview requires local approval")
    if not isinstance(world, DirectorWorld):
        raise DirectorError("typed director world required")
    script = DIRECTOR_CLIENT.replace("__WORLD__", _safe_script_json({
        **world.payload(), "world_digest": world.digest,
    }))
    csp = ("default-src 'none'; script-src '" + _sha256_csp(script)
           + "'; style-src '" + _sha256_csp(STYLE)
           + "'; connect-src 'none'; img-src 'none'; base-uri 'none'")
    html = (TEMPLATE.replace("__CSP__", escape(csp, quote=True))
                    .replace("__STYLE__", STYLE)
                    .replace("__SCRIPT__", script)).encode("utf-8")
    if len(html) > 900000:
        raise DirectorError("original game preview source exceeds size budget")
    return DirectorBrowser(html, sha256(html).hexdigest(), world.digest)

__all__ = ["DirectorBrowser", "render_director_browser"]
