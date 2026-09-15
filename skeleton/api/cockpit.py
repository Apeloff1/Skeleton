"""
Skeleton Cockpit — Self-contained web UI over the live API surfaces.

A single HTML page (no build step, no CDN) served at /cockpit that
polls /api/v1/health, /api/v1/genesis, /cortex/status, and related
surfaces and renders the organism's live state: phases, handles, event
rates, retrieval planes, and Jeeves provider.

The cockpit deliberately renders API-provided values through DOM text
nodes rather than HTML interpolation. Polling is bounded by per-request
timeouts, serialized to avoid overlapping refreshes, and paused while
the page is hidden.
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
  .sub { color: var(--dim); font-size: 12px; margin-bottom: 20px; display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 12px; }
  .card { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 14px 16px; }
  .card h2 { font-size: 11px; text-transform: uppercase; letter-spacing: 1.5px; color: var(--dim); margin-bottom: 10px; }
  .big { font-size: 28px; font-weight: 700; }
  .ok { color: var(--ok); } .warn { color: var(--warn); } .bad { color: var(--bad); }
  table { width: 100%; border-collapse: collapse; font-size: 12px; }
  td, th { text-align: left; padding: 3px 6px; border-bottom: 1px solid var(--border); overflow-wrap:anywhere; }
  th { color: var(--dim); font-weight: 400; }
  .pill { display: inline-block; padding: 1px 8px; border-radius: 10px; font-size: 11px; border: 1px solid var(--border); }
  .pill.ok { border-color: var(--ok); } .pill.warn { border-color: var(--warn); } .pill.bad { border-color: var(--bad); }
  .events { max-height: 220px; overflow-y: auto; }
  #tick { color: var(--dim); font-size: 11px; margin-top: 16px; }
</style>
</head>
<body>
<h1>SKELETON COCKPIT</h1>
<div class="sub"><span id="subtitle">v16.0 — connecting…</span><span class="pill warn" id="connection">CONNECTING</span></div>
<div class="grid">
  <div class="card"><h2>System Health</h2><div class="big" id="health">—</div><div id="health-detail" style="color:var(--dim);font-size:12px;margin-top:6px"></div></div>
  <div class="card"><h2>Genesis Boot</h2><div class="big" id="subsys">—</div><div id="phases" style="color:var(--dim);font-size:12px;margin-top:6px"></div></div>
  <div class="card"><h2>Cortex</h2><div class="big" id="events">—</div><div id="cortex-detail" style="color:var(--dim);font-size:12px;margin-top:6px"></div></div>
  <div class="card"><h2>Jeeves</h2><div class="big" id="provider">—</div><div style="color:var(--dim);font-size:12px;margin-top:6px">active LLM provider</div></div>
  <div class="card" style="grid-column:1/-1"><h2>Handles by Phase</h2><div id="handles"></div></div>
  <div class="card" style="grid-column:1/-1"><h2>Recent Event Topics</h2><div class="events" id="topics"></div></div>
</div>
<div id="tick" aria-live="polite"></div>
<script>
const $ = id => document.getElementById(id);
const POLL_MS = 5000;
const REQUEST_TIMEOUT_MS = 3500;
let refreshTimer = null;
let refreshing = false;

function setText(id, value) {
  const node = $(id);
  if (node) node.textContent = value == null ? '—' : String(value);
}

function setConnection(okCount, total) {
  const node = $('connection');
  if (okCount === total) {
    node.textContent = 'LIVE';
    node.className = 'pill ok';
  } else if (okCount > 0) {
    node.textContent = `DEGRADED ${okCount}/${total}`;
    node.className = 'pill warn';
  } else {
    node.textContent = 'OFFLINE';
    node.className = 'pill bad';
  }
}

function renderTable(targetId, headers, rows) {
  const target = $(targetId);
  const table = document.createElement('table');
  const headRow = document.createElement('tr');
  for (const label of headers) {
    const th = document.createElement('th');
    th.textContent = String(label);
    headRow.appendChild(th);
  }
  table.appendChild(headRow);
  for (const row of rows) {
    const tr = document.createElement('tr');
    for (const value of row) {
      const td = document.createElement('td');
      td.textContent = value == null ? '' : String(value);
      tr.appendChild(td);
    }
    table.appendChild(tr);
  }
  target.replaceChildren(table);
}

async function j(url) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  try {
    const response = await fetch(url, {
      signal: controller.signal,
      headers: { 'Accept': 'application/json' },
      cache: 'no-store'
    });
    if (!response.ok) return { ok: false, status: response.status, data: null };
    return { ok: true, status: response.status, data: await response.json() };
  } catch (error) {
    return { ok: false, status: 0, data: null, error: error && error.name ? error.name : 'request-failed' };
  } finally {
    clearTimeout(timeout);
  }
}

function schedule(delay = POLL_MS) {
  if (refreshTimer !== null) clearTimeout(refreshTimer);
  if (!document.hidden) refreshTimer = setTimeout(tick, delay);
}

async function tick() {
  if (refreshing) return;
  refreshing = true;
  try {
    const results = await Promise.all([
      j('/'),
      j('/api/v1/health'),
      j('/api/v1/genesis'),
      j('/api/v1/genesis/handles'),
      j('/cortex/status')
    ]);
    const [rootResult, healthResult, genesisResult, handlesResult, cortexResult] = results;
    setConnection(results.filter(result => result.ok).length, results.length);

    const root = rootResult.data;
    if (root) {
      setText('subtitle', `v${root.version ?? '?'} — ${root.status ?? 'unknown'}`);
      setText('provider', root.jeeves_provider || 'n/a');
    }

    const health = healthResult.data;
    if (health) {
      const status = health.status || 'unknown';
      const healthy = status === 'healthy';
      setText('health', status.toUpperCase());
      $('health').className = 'big ' + (healthy ? 'ok' : 'bad');
    } else {
      setText('health', 'UNKNOWN');
      $('health').className = 'big warn';
    }

    const genesis = genesisResult.data;
    if (genesis && genesis.health) {
      setText('subsys', genesis.health.subsystems);
      const phases = Array.isArray(genesis.health.phases) ? genesis.health.phases : [];
      setText('phases', phases.join(' → '));
      setText('health-detail', `invariant violations: ${genesis.health.invariant_violations ?? '—'}`);
    }

    const handles = handlesResult.data;
    if (handles && handles.wired && typeof handles.wired === 'object') {
      const rows = Object.entries(handles.wired).map(([phase, list]) => [
        phase,
        Array.isArray(list) ? list.join(', ') : String(list ?? '')
      ]);
      renderTable('handles', ['Phase', 'Handles'], rows);
    }

    const cortex = cortexResult.data;
    if (cortex) {
      setText('events', cortex.events_captured ?? '—');
      setText('cortex-detail', `${cortex.topics_observed || 0} topics observed`);
      const tops = Array.isArray(cortex.top_topics) ? cortex.top_topics.slice(0, 12) : [];
      const rows = tops
        .filter(item => Array.isArray(item) && item.length >= 2)
        .map(item => [item[0], item[1]]);
      renderTable('topics', ['Topic', 'Count'], rows);
    }

    setText('tick', 'refreshed ' + new Date().toLocaleTimeString());
  } finally {
    refreshing = false;
    schedule();
  }
}

document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    if (refreshTimer !== null) clearTimeout(refreshTimer);
    refreshTimer = null;
  } else {
    tick();
  }
});

tick();
</script>
</body>
</html>"""


@router.get("/cockpit", response_class=HTMLResponse)
async def cockpit() -> Any:
    """Serve the self-contained cockpit UI."""
    return HTMLResponse(content=COCKPIT_HTML)
