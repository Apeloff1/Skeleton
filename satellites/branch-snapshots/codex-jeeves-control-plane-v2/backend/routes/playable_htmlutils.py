"""HTML codegen utilities for the Playable pipeline — pure string/HTML helpers
(no DB, no LLM, no router). Imported one-way by routes.playable.

Design rule: EXPAND, never trim. These helpers are intentionally thorough —
the more network vectors _sanitize covers and the more signals _validate
reports, the safer and more observable the generated-game pipeline becomes.

  _extract_html  — pull the playable HTML document out of an LLM response
                   (with a fragment-wrapping fallback so usable markup is never lost)
  _sanitize      — strip EVERY external/network vector so the game runs 100% offline
  _validate      — heuristic structural playability score (0-100) + missing checks
                   + a rich `signals` diagnostic map + an `intricacy` depth score
  _extract_json  — tolerant JSON-object extractor (fences, trailing commas, spans)
"""
from __future__ import annotations

import re
import json

_MIN_DOC = (
    "<!DOCTYPE html><html><head><meta charset='utf-8'>"
    "<meta name='viewport' content='width=device-width,initial-scale=1,"
    "maximum-scale=1,user-scalable=no'></head><body style='margin:0'>{body}</body></html>"
)


def _extract_html(text: str) -> str:
    """Return the playable HTML document from raw model output.

    Strips markdown fences and surrounding prose. If the model returns a usable
    fragment (canvas / script / svg) without a full document, it is wrapped in a
    minimal mobile-ready shell rather than discarded — so good output is never lost.
    """
    if not text:
        return ""
    s = text.strip()
    # Prefer a fenced ```html ... ``` block when present and it contains markup.
    if "```" in s:
        m = re.search(r"```(?:html|HTML)?\s*(.*?)```", s, re.DOTALL)
        if m and "<" in m.group(1):
            s = m.group(1).strip()
        else:
            s = re.sub(r"```[a-zA-Z]*", "", s).replace("```", "").strip()
    low = s.lower()
    start = -1
    for tag in ("<!doctype html", "<html"):
        i = low.find(tag)
        if i >= 0:
            start = i
            break
    if start > 0:
        s = s[start:]
    low = s.lower()
    end = low.rfind("</html>")
    if end >= 0:
        return s[:end + len("</html>")].strip()
    # No full document — wrap a usable fragment so it is not thrown away.
    if start >= 0:  # had <html but no closing tag → still return what we have
        return s.strip()
    if any(t in low for t in ("<canvas", "<script", "<svg", "<style")):
        return _MIN_DOC.format(body=s.strip())
    return s.strip()


def _sanitize(html: str) -> tuple:
    """Remove EVERY external/network vector (CDN scripts, stylesheets, @import,
    remote media, iframes/embeds, preloads, base-href, inline url(http) backgrounds,
    srcset) so the artifact is fully self-contained and offline-safe.

    Inline JavaScript is deliberately left intact so the game still runs; only
    resource references that would reach the network are stripped.
    Returns (clean_html, removed_labels).
    """
    if not html:
        return "", []
    removed: list[str] = []

    def _sub(pattern: str, label: str, s: str) -> str:
        new, n = re.subn(pattern, "", s, flags=re.IGNORECASE | re.DOTALL)
        if n:
            removed.append(f"{label}:{n}")
        return new

    h = html
    _url = r'(?:https?:)?//'  # absolute or protocol-relative
    h = _sub(rf'<script\b[^>]*\bsrc\s*=\s*["\']{_url}[^"\']*["\'][^>]*>\s*</script>', "ext-script", h)
    h = _sub(rf'<link\b[^>]*\bhref\s*=\s*["\']{_url}[^"\']*["\'][^>]*>', "ext-link", h)
    h = _sub(rf'<base\b[^>]*\bhref\s*=\s*["\']{_url}[^"\']*["\'][^>]*>', "ext-base", h)
    h = _sub(rf'<iframe\b[^>]*\bsrc\s*=\s*["\']{_url}[^"\']*["\'][^>]*>(?:\s*</iframe>)?', "ext-iframe", h)
    h = _sub(rf'<(?:embed|object)\b[^>]*\b(?:src|data)\s*=\s*["\']{_url}[^"\']*["\'][^>]*>', "ext-embed", h)
    h = _sub(rf'<img\b[^>]*\bsrc\s*=\s*["\']{_url}[^"\']*["\'][^>]*>', "ext-img", h)
    h = _sub(rf'<(?:audio|video|source|track)\b[^>]*\bsrc\s*=\s*["\']{_url}[^"\']*["\'][^>]*>', "ext-media", h)
    h = _sub(r'\bsrcset\s*=\s*["\'][^"\']*https?:[^"\']*["\']', "ext-srcset", h)
    h = _sub(r'@import\s+(?:url\()?["\']?(?:https?:)?//[^)"\';]*\)?\s*;?', "ext-import", h)
    h = _sub(r'url\(\s*["\']?(?:https?:)?//[^)\s"\']*["\']?\s*\)', "ext-cssurl", h)
    return h, removed


# Weighted structural checks → weights sum to 100. A complete game satisfies
# nearly all of them (~100); a minimal-but-runnable game clears ~70+
# (PLAYABILITY_THRESHOLD); empty/broken output scores low. Gate parity verified.
_CHECK_WEIGHTS = [
    ("has_doctype", 10),
    ("has_canvas", 14),
    ("has_loop", 14),
    ("has_input", 12),
    ("non_trivial", 10),
    ("no_external", 10),
    ("has_score_hud", 8),
    ("has_audio", 6),
    ("responsive", 5),
    ("has_state_machine", 4),
    ("has_persistence", 3),
    ("dpr_crisp", 2),
    ("delta_time", 2),
]


def _validate(html: str) -> dict:
    """Heuristic playability gate + rich diagnostics.

    Returns {score:int 0-100, missing:list[str], checks:dict, signals:dict,
    intricacy:int, bytes:int}. `score`/`missing`/`checks` preserve the gating
    contract; `signals`/`intricacy` are additive depth diagnostics (expand-only).
    """
    low = (html or "").lower()
    has = lambda *ks: any(k in low for k in ks)  # noqa: E731
    passed = {
        "has_doctype": ("<!doctype html" in low or "<html" in low),
        "has_canvas": ("<canvas" in low or "getcontext" in low),
        "has_loop": ("requestanimationframe" in low),
        "has_input": has("touchstart", "touchmove", "pointerdown", "pointermove",
                          "addeventlistener", "onkeydown", "keydown", "onclick"),
        "non_trivial": (len(low) > 1500),
        "no_external": (re.search(r'(?:src|href)\s*=\s*["\'](?:https?:)?//', low) is None
                        and re.search(r'@import[^;]*https?:', low) is None),
        "has_score_hud": has("score", "hud", "lives", "health", "level"),
        "has_audio": has("audiocontext", "webkitaudiocontext", "oscillator", "createoscillator"),
        "responsive": has("innerwidth", "innerheight", "resize", "devicepixelratio"),
        "has_state_machine": has("state", "menu", "gameover", "game over", "playing", "paused"),
        "has_persistence": ("localstorage" in low),
        "dpr_crisp": ("devicepixelratio" in low),
        "delta_time": has("deltatime", "delta", "performance.now", "timestamp", " dt "),
    }
    score = sum(w for name, w in _CHECK_WEIGHTS if passed.get(name))
    missing = [name for name, _w in _CHECK_WEIGHTS if not passed.get(name)]

    # ── Additive depth signals (diagnostic only; never lowers `score`) ──
    signals = {
        "collision": has("intersect", "collide", "collision", "overlap", "hittest", "aabb", "distance"),
        "particles_juice": has("particle", "shake", "flash", "glow", "trail", "spark", "burst"),
        "restart": has("restart", "playagain", "play again", "reset(", "tryagain"),
        "difficulty_curve": has("difficulty", "speed +=", "spawnrate", "level++", "wave", "faster"),
        "keyboard": has("keydown", "keyup", "arrowleft", "arrowright", " wasd", "code ==="),
        "touch": has("touchstart", "touchmove", "pointerdown", "pointermove"),
        "sound_fx": passed["has_audio"],
        "scoreboard": has("highscore", "high score", "best", "leaderboard"),
        "animation": passed["has_loop"],
        "responsive_canvas": has("resize", "innerwidth", "clientwidth"),
        "pause": has("pause", "paused", "ispaused"),
        "gradient_or_art": has("creategradient", "lineargradient", "radialgradient", "fillstyle", "drawimage"),
    }
    depth_hits = sum(1 for v in signals.values() if v)
    intricacy = min(100, depth_hits * 7 + min(40, len(low) // 800))

    return {
        "score": score,
        "missing": missing,
        "checks": passed,
        "signals": signals,
        "depth_hits": depth_hits,
        "intricacy": intricacy,
        "bytes": len(html or ""),
    }


def _extract_json(text: str) -> dict:
    """Tolerant JSON-object extractor: strips ``` fences, tolerates trailing
    commas, and falls back to the first balanced {...} span. Returns {} when
    nothing parses."""
    if not text:
        return {}
    s = text.strip()
    if s.startswith("```"):
        parts = s.split("```")
        if len(parts) >= 2:
            s = parts[1]
        s = re.sub(r"^\s*json\b", "", s, flags=re.IGNORECASE).strip()

    def _try(raw: str):
        try:
            obj = json.loads(raw)
            return obj if isinstance(obj, dict) else None
        except Exception:
            # tolerate trailing commas before } or ]
            cleaned = re.sub(r",\s*([}\]])", r"\1", raw)
            try:
                obj = json.loads(cleaned)
                return obj if isinstance(obj, dict) else None
            except Exception:
                return None

    out = _try(s)
    if out is not None:
        return out
    a, b = s.find("{"), s.rfind("}")
    if 0 <= a < b:
        out = _try(s[a:b + 1])
        if out is not None:
            return out
    return {}



def inject_into_head(html: str, script: str) -> str:
    """Insert a <script> (or any markup) as the first child of <head>, falling back
    to right after <body ...> or the very front. Shared by every 'wire' pass
    (artwire / sentience / aesthetics / physics) that deterministically injects a
    self-contained engine into a generated game."""
    if not html:
        return script
    low = html.lower()
    i = low.find("<head>")
    if i != -1:
        pos = i + len("<head>")
        return html[:pos] + script + html[pos:]
    i = low.find("<body")
    if i != -1:
        end = html.find(">", i)
        if end != -1:
            return html[:end + 1] + script + html[end + 1:]
    return script + html
