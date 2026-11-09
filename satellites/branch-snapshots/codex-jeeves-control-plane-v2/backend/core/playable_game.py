"""
╔════════════════════════════════════════════════════════════════════════╗
║  PLAYABLE GAME — assemble forged gamefiles into a real playable build.   ║
║  ────────────────────────────────────────────────────────────────────  ║
║  Produces a self-contained, single-file HTML5 game (canvas + on-screen   ║
║  touch D-pad for Android) whose entities ARE the forged gamefiles — they ║
║  spawn at their placement regions, render in their forged palettes and   ║
║  are collectible. Era-styled (8-bit = low-res pixel canvas). The output  ║
║  opens straight in any mobile/desktop browser → genuinely playable.      ║
╚════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations

import json
import math

from core.universal_forge import REGION_ANCHOR as _REGION_ANCHOR
from typing import Any

from core import eras as eras_mod


def _entities(items: list[dict]) -> list[dict]:
    out = []
    for i, it in enumerate(items):
        skin = it.get("skin") or {}
        pal = skin.get("palette") or ["#9bbc0f"]
        out.append({
            "name": it.get("name", f"Item {i}"),
            "color": pal[i % len(pal)],
            "grade": it.get("grade", 1),
            "stage": it.get("stage", "world"),
            "region": (it.get("placement") or {}).get("region", "Field"),
            "x": 24 + (i * 53) % 232,
            "y": 40 + (i * 37) % 200,
        })
    return out


def _asset_entities(assets: list[dict], offset: int) -> list[dict]:
    """Fold forged constructs/materials/universal assets into world entities,
    placed into themed REGIONS by family so the playable map reads as a coherent
    biome (flora belt, settlement core, creature wild-zone, vehicle yard…)."""
    out = []
    perfam: dict[str, int] = {}
    for j, a in enumerate(assets):
        pal = a.get("palette") or ["#7dd3fc"]
        i = offset + j
        fam = a.get("family") or a.get("kind") or "asset"
        cx, cy, spread = _REGION_ANCHOR.get(fam, (128, 128, 40))
        k = perfam.get(fam, 0)
        perfam[fam] = k + 1
        # deterministic spiral scatter around the family anchor
        ang = (k * 2.39996) % 6.28318
        rad = spread * ((k % 7) / 7.0 + 0.25)
        px = int(max(8, min(248, cx + rad * math.cos(ang))))
        py = int(max(8, min(248, cy + rad * math.sin(ang))))
        out.append({
            "name": a.get("name", a.get("forge", "Asset")),
            "color": pal[0],
            "grade": int(a.get("grade", 2) or 2),
            "stage": fam,
            "region": str(fam).replace("_", " ").title(),
            "x": px, "y": py,
            "forged": True,
        })
    return out


def assemble(build_id: str, items: list[dict], era: str | None,
             title: str, genre: str = "rpg", extra_assets: list[dict] | None = None) -> dict:
    """Build the playable single-file HTML game + its file manifest.

    ``extra_assets`` are the COMBINED forged gamefiles (constructs + materials +
    universal families) mounted to the build — folded in as world entities so
    the world is built from EVERYTHING that was forged, not just item stages."""
    era_spec = eras_mod.get_era(era)
    is_8bit = era_spec["order"] <= 1
    ents = _entities(items)
    if extra_assets:
        ents = ents + _asset_entities(extra_assets, len(ents))
    ents = ents[:300]
    bg = "#0f380f" if is_8bit else "#10131a"
    fg = "#9bbc0f" if is_8bit else "#7dd3fc"
    res = 256 if is_8bit else 480

    data_js = json.dumps(ents)
    html = _GAME_HTML.format(
        title=title, genre=genre, era_label=era_spec["label"],
        bg=bg, fg=fg, res=res, entities=data_js,
        count=len(ents), build_id=build_id,
        pixelated="pixelated" if is_8bit else "auto",
    )
    files = [
        {"path": "index.html", "kind": "entry", "bytes": len(html)},
        {"path": "game.json", "kind": "data", "bytes": len(data_js)},
        {"path": "README.txt", "kind": "doc"},
    ]
    return {
        "build_id": build_id, "title": title, "era": era_spec["key"],
        "entry": "index.html", "entities": len(ents),
        "files": files, "html": html, "game_json": data_js,
        "playable": len(ents) > 0,
        "how_to_play": "Unzip and open index.html in any browser (incl. Android). "
                       "Move with the on-screen D-pad / arrow keys; collect every "
                       "forged item to win.",
    }


# Self-contained HTML5 game template. Placeholders filled by .format().
_GAME_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no"/>
<title>{title}</title>
<style>
 html,body{{margin:0;height:100%;background:#000;overflow:hidden;font-family:monospace;-webkit-user-select:none;user-select:none;touch-action:none}}
 #wrap{{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%}}
 #hud{{color:{fg};padding:8px;font-size:14px;text-align:center}}
 canvas{{background:{bg};image-rendering:{pixelated};width:min(94vw,520px);height:auto;border:3px solid {fg};border-radius:6px}}
 #pad{{position:fixed;bottom:18px;left:0;right:0;display:flex;justify-content:space-between;padding:0 24px;pointer-events:none}}
 .cluster{{display:grid;grid-template-columns:repeat(3,52px);grid-template-rows:repeat(3,52px);gap:4px;pointer-events:auto}}
 .btn{{background:rgba(255,255,255,.12);border:2px solid {fg};border-radius:8px;color:{fg};font-size:20px;display:flex;align-items:center;justify-content:center}}
 #msg{{color:{fg};font-size:18px;margin-top:6px;min-height:22px}}
</style></head>
<body><div id="wrap">
 <div id="hud">{title} · {era_label} · collect {count} forged gamefiles</div>
 <canvas id="c" width="{res}" height="{res}"></canvas>
 <div id="msg"></div>
</div>
<div id="pad">
 <div class="cluster">
  <div></div><div class="btn" data-k="up">▲</div><div></div>
  <div class="btn" data-k="left">◀</div><div></div><div class="btn" data-k="right">▶</div>
  <div></div><div class="btn" data-k="down">▼</div><div></div>
 </div>
 <div class="cluster" style="grid-template-columns:repeat(2,52px);grid-template-rows:52px">
  <div class="btn" data-k="up">A</div><div class="btn" data-k="up">B</div>
 </div>
</div>
<script>
const ENTS={entities};
const R={res};
const cv=document.getElementById('c'),ctx=cv.getContext('2d'),msg=document.getElementById('msg');
let px=R/2,py=R/2,score=0,keys={{}};
const items=ENTS.map(e=>({{...e,got:false}}));
function set(k,v){{keys[k]=v;}}
document.querySelectorAll('.btn').forEach(b=>{{
 const k=b.dataset.k;
 const on=ev=>{{ev.preventDefault();set(k,true);}},off=ev=>{{ev.preventDefault();set(k,false);}};
 b.addEventListener('touchstart',on);b.addEventListener('touchend',off);
 b.addEventListener('mousedown',on);b.addEventListener('mouseup',off);b.addEventListener('mouseleave',off);
}});
addEventListener('keydown',e=>{{const m={{ArrowUp:'up',ArrowDown:'down',ArrowLeft:'left',ArrowRight:'right'}};if(m[e.key])set(m[e.key],true);}});
addEventListener('keyup',e=>{{const m={{ArrowUp:'up',ArrowDown:'down',ArrowLeft:'left',ArrowRight:'right'}};if(m[e.key])set(m[e.key],false);}});
function loop(){{
 const sp=2.4;
 if(keys.up)py-=sp;if(keys.down)py+=sp;if(keys.left)px-=sp;if(keys.right)px+=sp;
 px=Math.max(6,Math.min(R-6,px));py=Math.max(6,Math.min(R-6,py));
 items.forEach(it=>{{if(!it.got&&Math.abs(it.x-px)<10&&Math.abs(it.y-py)<10){{it.got=true;score++;msg.textContent='Got '+it.name+'! ('+score+'/'+items.length+')';}}}});
 ctx.clearRect(0,0,R,R);
 items.forEach(it=>{{if(it.got)return;ctx.fillStyle=it.color;ctx.fillRect(it.x-5,it.y-5,10,10);ctx.fillStyle='#fff2';ctx.fillRect(it.x-5,it.y-5,10,2);}});
 ctx.fillStyle='{fg}';ctx.fillRect(px-6,py-6,12,12);
 if(score===items.length&&items.length>0){{msg.textContent='🏆 COMPLETE — you collected every forged gamefile!';}}
 requestAnimationFrame(loop);
}}
loop();
</script></body></html>
"""
