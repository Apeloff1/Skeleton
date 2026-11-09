"""
Skeleton Cockpit — Self-contained web UI over the live API surfaces.

A single HTML page (no build step, no CDN) served at /cockpit that
polls /api/v1/health, /api/v1/genesis, /cortex/status, and /api/v1/metrics
and renders the organism's live state: phases, handles, event rates,
retrieval planes, and Jeeves provider.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


COCKPIT_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Skeleton Cockpit</title>
<style>
  :root { --bg:#0b0f14; --panel:#131a22; --border:#1f2a36; --text:#d6e2ec; --dim:#7d93a8; --ok:#3ddc84; --warn:#f5b942; --bad:#ef5350; --accent:#5ac8fa; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font: 14px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; padding: 24px; }
  h1 { font-size: 18px; letter-spacing: 2px; color: var(--accent); margin-bottom: 4px; }
  .sub { color: var(--dim); font-size: 12px; margin-bottom: 20px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; }
  .card { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 14px 16px; }
  .card h2 { font-size: 11px; text-transform: uppercase; letter-spacing: 1.5px; color: var(--dim); margin-bottom: 10px; }
  .big { font-size: 28px; font-weight: 700; }
  .ok { color: var(--ok); } .warn { color: var(--warn); } .bad { color: var(--bad); }
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  td, th { text-align: left; padding: 3px 6px; border-bottom: 1px solid var(--border); }
  th { color: var(--dim); font-weight: 400; }
  .pill { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 11px; border: 1px solid var(--border); }
  .pill.ok { border-color: var(--ok); } .pill.bad { border-color: var(--bad); }
  .events { max-height: 220px; overflow-y: auto; }
  #tick { color: var(--dim); font-size: 11px; margin-top: 16px; }
</style>
</head>
<body>
<h1>SKELETON COCKPIT</h1>
<div class="sub" id="subtitle">v16.0 — connecting…</div>
<div class="grid">
  <div class="card"><h2>System Health</h2><div class="big" id="health">—</div><div id="health-detail" style="color:var(--dim);font-size:12px;margin-top:6px"></div></div>
  <div class="card"><h2>Genesis Boot</h2><div class="big" id="subsys">—</div><div id="phases" style="color:var(--dim);font-size:12px;margin-top:6px"></div></div>
  <div class="card"><h2>Cortex</h2><div class="big" id="events">—</div><div id="cortex-detail" style="color:var(--dim);font-size:12px;margin-top:6px"></div></div>
  <div class="card"><h2>Jeeves</h2><div class="big" id="provider">—</div><div style="color:var(--dim);font-size:12px;margin-top:6px">active LLM provider</div></div>
  <div class="card" style="grid-column:1/-1"><h2>Handles by Phase</h2><div id="handles"></div></div>
  <div class="card" style="grid-column:1/-1"><h2>Recent Event Topics</h2><div class="events" id="topics"></div></div>
</div>
<div id="tick"></div>
<script>
const $ = id => document.getElementById(id);
async function j(url){ try { const r = await fetch(url); return r.ok ? await r.json() : null; } catch(e){ return null; } }
async function tick(){
  const [root, health, genesis, handles, cortex] = await Promise.all([
    j('/'), j('/api/v1/health'), j('/api/v1/genesis'), j('/api/v1/genesis/handles'), j('/cortex/status')
  ]);
  if (root) { $('subtitle').textContent = `v${root.version} — ${root.status}`; $('provider').textContent = root.jeeves_provider || 'n/a'; }
  if (health) {
    const ok = health.status === 'healthy';
    $('health').textContent = health.status.toUpperCase();
    $('health').className = 'big ' + (ok ? 'ok' : 'bad');
  }
  if (genesis && genesis.health) {
    $('subsys').textContent = genesis.health.subsystems;
    $('phases').textContent = genesis.health.phases.join(' → ');
    $('health-detail').textContent = `invariant violations: ${genesis.health.invariant_violations}`;
  }
  if (handles && handles.wired) {
    let html = '<table><tr><th>Phase</th><th>Handles</th></tr>';
    for (const [phase, list] of Object.entries(handles.wired))
      html += `<tr><td>${phase}</td><td>${list.join(', ')}</td></tr>`;
    $('handles').innerHTML = html + '</table>';
  }
  if (cortex) {
    $('events').textContent = cortex.events_captured ?? '—';
    const tops = (cortex.top_topics || []).slice(0, 12);
    $('cortex-detail').textContent = `${cortex.topics_observed || 0} topics observed`;
    let html = '<table><tr><th>Topic</th><th>Count</th></tr>';
    for (const [topic, n] of tops) html += `<tr><td>${topic}</td><td>${n}</td></tr>`;
    $('topics').innerHTML = html + '</table>';
  }
  $('tick').textContent = 'refreshed ' + new Date().toLocaleTimeString();
}
tick(); setInterval(tick, 5000);
</script>
</body>
</html>"""


@router.get("/cockpit", response_class=HTMLResponse)
async def cockpit() -> Any:
    """Serve the self-contained cockpit UI."""
    return HTMLResponse(content=COCKPIT_HTML)
