"""Human-readable local historical library across many bounded game studies."""
from __future__ import annotations

import html
import json
from collections.abc import Mapping


def render_series_ledger_html(raw: Mapping[str, object]) -> str:
    if not isinstance(raw, dict) or raw.get("schema_version") != "skeleton.game.comparative_series_ledger.v1":
        raise ValueError("A verified cross-study ledger is required")
    out = [
        "<!doctype html><html lang='en'><meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width,initial-scale=1'>",
        "<title>Jeeves &amp; Dragon — Game Series Library</title>",
        "<style>body{background:#111827;color:#edf2f7;font:15px system-ui,sans-serif;max-width:1300px;margin:24px auto;padding:16px}",
        "details{background:#1b2736;border:1px solid #39465a;border-radius:12px;padding:15px;margin:14px 0}",
        "summary{cursor:pointer;font-size:18px;font-weight:700}table{width:100%;border-collapse:collapse;overflow:auto}",
        "th,td{padding:8px;border-bottom:1px solid #384456;text-align:left;vertical-align:top}",
        "code,small{font-size:12px;color:#aebed0} .warn{color:#ffd29c}h2{margin-top:24px}</style>",
        "<h1>Jeeves × Dragon — Cross-study game series library</h1>",
        "<p>This library joins only native evidence already observed in separately bounded comparative studies. ",
        "It does not claim to have acquired every franchise installment or trained weights.</p>",
        "<p><strong>",str(raw["series_count"]),"</strong> observed series • <strong>",
        str(raw["native_game_variant_count"]),"</strong> observed title/core variants • <strong>",
        str(raw["source_study_count"]),"</strong> studies</p>",
    ]
    for series in raw["series"]:
        h=html.escape(series["series_id"], quote=True)
        out.extend(["<details><summary>",h," — ",str(series["distinct_release_orders_observed"]),
                    " distinct observed installments; ",str(series["game_or_emulator_variants_observed"])," versions</summary>"])
        out.append("<table><thead><tr><th>Order</th><th>Observed game/version</th><th>Emulator</th><th>Release phase</th><th>Evidence</th></tr></thead><tbody>")
        for installment in series["installments"]:
            for version in installment["versions"]:
                out.extend([
                    "<tr><td>",str(installment["release_order"]),"</td><td>",
                    html.escape(version["title"],quote=True),
                    " <small>(",html.escape(version["study_id"],quote=True),")</small></td><td>",
                    html.escape(version["core_id"],quote=True),"</td><td>",
                    html.escape(version["series_phase"],quote=True),"</td><td><code>",
                    html.escape(version["offline_trace_sha256"][:20]),"…</code></td></tr>",
                ])
        out.append("</tbody></table>")
        out.extend(["<h2>Notes &amp; cross-game insights pending independent verification</h2>"])
        notes = series["reviewed_observer_claim_candidates"]
        if not notes:
            out.append("<p>No locally reviewed observations currently attach to these native receipts.</p>")
        for n in notes:
            out.extend(["<p><strong>",html.escape(n["dimension"]),"</strong> · ",
                        html.escape(n["author"]), " · ",
                        html.escape(n["claim_type"]),": ",
                        html.escape(n["text"],quote=True),"</p>"])
        out.extend(["<p class='warn'>",str(len(series["proposed_build_parameter_hypotheses"])),
                    " candidate numerical build parameters require independent validation and are not applied.</p></details>"])
    out.extend(["<footer><small>Only measured frame/audio traces are native observations. Narrative insights, parameter proposals, commercial-ROM rights, and game mechanics are not established by hashes alone.</small></footer></html>"])
    data="".join(out)
    if len(data.encode("utf-8")) > 20*1024*1024:
        raise ValueError("Long-series viewer is too large; select fewer source studies")
    return data
