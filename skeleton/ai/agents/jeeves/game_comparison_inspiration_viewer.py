"""Static private comparison-inspired media gallery from original generated files.

References local SVG and WAV files under a bounded operator-owned output
directory, with no network access or copying protected source assets.
"""
from __future__ import annotations
from html import escape
from typing import Any, Mapping

def render_inspiration_gallery(receipt: Mapping[str,Any]) -> str:
    if (not isinstance(receipt,dict)
        or receipt.get("schema_version")!="skeleton.game.comparison_original_inspiration.v1"
        or len(receipt.get("stages",[]))!=3):
        raise ValueError("Original media gallery requires a complete generated receipt")
    out=[
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>Jeeves and Dragon · Original Design Lab</title>",
        "<style>:root{color-scheme:dark}body{margin:0;padding:24px;background:#0e1625;color:#e7f0f8;font:14px system-ui,sans-serif}",
        "main{max-width:1300px;margin:auto}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:15px}",
        "article{background:#1a2739;border:1px solid #34445c;border-radius:12px;padding:14px;min-width:0}",
        "img{width:100%;display:block;border-radius:7px;margin-top:14px}audio{width:100%;margin-top:9px}",
        "h1{font-size:24px}h2{font-size:18px}small{color:#b4c3d1}ul{padding-left:22px}",
        "li{margin:7px 0}.meta{overflow-wrap:anywhere}details{margin-top:12px}summary{cursor:pointer}",
        "@media(max-width:900px){.grid{grid-template-columns:1fr}}</style></head><body><main>",
        "<h1>Original Comparative Inspiration Lab</h1>",
        "<p>Generated abstract original art, new synthesized music, camera-shot plans and gameplay mechanics drafts. ",
        "No original game footage, art, music, ROMs or dialogue was copied. Model weights remain unchanged.</p>",
        "<p><strong>Creative brief:</strong> ",escape(receipt["creative_brief"],quote=True),
        " · <strong>Genre:</strong> ",escape(receipt["genre"],quote=True),
        " · <strong>Source study:</strong> ",escape(receipt["study_id"],quote=True),"</p><div class='grid'>",
    ]
    for stage in receipt["stages"]:
        name=stage["stage"]
        out.extend([
            "<article><h2>",escape(name.capitalize())," version</h2>",
            "<img alt='Original synthesized vector composition' loading='lazy' src='assets/",name,"_original.svg'>",
            "<h3>Original synthesized music</h3>",
            "<audio controls preload='none' src='music/",name,"_original.wav'></audio>",
            "<p><small>",str(stage["authored_music_metadata"]["duration_seconds"])," seconds · ",
            str(stage["authored_music_metadata"]["tempo_bpm"])," BPM · procedurally generated PCM</small></p>",
            "<h3>Editable cutscene and mechanics</h3>",
            "<p>",str(stage["cutscene_shot_count"])," original cinematic shots; ",
            str(stage["mechanic_count"])," mechanics drafts.</p>",
            "<p><a href='cutscenes/",name,"_original.json'>Open shot plan JSON</a></p>",
            "<p><a href='mechanics/",name,"_original.json'>Open gameplay mechanics JSON</a></p>",
            "<details><summary>Evidence and generated file receipts</summary><ul>",
        ])
        for artifact in stage["generated_file_receipts"]:
            out.extend(["<li class='meta'>",escape(artifact["path"],quote=True),
                        " — SHA-256 ",escape(artifact["sha256"],quote=True),"</li>"])
        out.append("</ul></details></article>")
    out.extend(["</div><h2>Independent reviewer matrix</h2>",
                "<p>Proposals, not measured performance or newly trained parameters.</p><ul>"])
    for entry in receipt["adversarial_review_queue"]:
        out.extend(["<li>",escape(entry["dimension"]),": ",
                    escape(entry["status"]),"</li>"])
    out.extend(["</ul><p><small>Receipt: ",escape(receipt["pack_receipt_sha256"],quote=True),
                " · all outputs remain source-independent original authored data, subject to manual originality review.</small></p></main></body></html>"])
    html="".join(out)
    if len(html.encode())>2*1024*1024:
        raise ValueError("Original inspiration gallery exceeds bounded output limit")
    return html
