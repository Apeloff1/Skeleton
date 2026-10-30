"""Static, dependency-free companion UI for authenticated localhost offline chat.

Kept as individual same-origin assets so strict CSP can forbid inline scripts,
remote fonts, external images, frames and cross-origin network connections.
No token, conversation or model data is persisted in browser storage.
"""
from __future__ import annotations


HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Skeleton · Offline AI</title>
<link rel="stylesheet" href="/app.css">
</head><body>
<div class="shell library-open" id="shell">
  <button id="sidebar-scrim" class="sidebar-scrim" aria-label="Close library and connection panel" tabindex="-1"></button>
  <aside class="sidebar" id="sidebar" aria-label="Connection, conversations and references">
    <div class="brand"><span class="brand-mark">◈</span>
      <div><strong>Skeleton</strong><small>Offline AI Workspace</small></div>
      <button id="sidebar-close" class="small mobile-only" aria-label="Close library and connection panel">Close</button>
    </div>
    <section class="connect">
      <label for="secret">Local access token</label>
      <input id="secret" type="password" autocomplete="off" spellcheck="false"
             placeholder="Paste your private token">
      <div class="inline">
        <button id="connect" class="primary">Connect locally</button>
        <button id="disconnect" class="secondary">Lock</button>
      </div>
      <p class="hint">Read the token from the private file provided when the local server starts. It stays in this tab's memory only.</p>
    </section>
    <div class="heading"><span>Conversations</span><button id="new" class="small">+ New</button></div>
    <label class="hint" for="session-query">Search saved conversation text</label>
    <div class="inline"><input id="session-query" type="search" maxlength="256" placeholder="Search your conversations">
      <button id="session-search" class="small">Search</button></div>
    <div id="sessions" class="sessions" aria-label="Saved local conversations"></div>
    <button id="sessions-more" class="small" hidden>Load more conversations</button>
    <details class="instructions"><summary>New conversation instructions</summary>
      <label class="hint" for="system-prompt">Optional instructions for the next conversation</label>
      <textarea id="system-prompt" rows="4" maxlength="4096" placeholder="For example: help me build small, complete games."></textarea>
    </details>
    <section class="knowledge-section" aria-label="Private local knowledge">
      <div class="heading"><span>Local reference library</span></div>
      <p class="hint">Search operator-supplied text offline. Passages are evidence, not AI-generated claims.</p>
      <label class="import-label" for="knowledge-file">Add a text / Markdown file</label>
      <input type="file" id="knowledge-file" multiple accept=".txt,.md,.py,.js,.ts,.json,.toml,.yaml,.yml,.csv,text/plain,text/markdown">
      <div id="knowledge-documents" class="knowledge-documents" aria-label="Imported references"></div>
      <label for="knowledge-query">Search reference passages</label>
      <input id="knowledge-query" type="search" autocomplete="off"
             placeholder="A topic, symbol, API or exact phrase">
      <button id="knowledge-search" class="secondary">Search offline references</button>
      <label class="hint" for="reference-grant"><input id="reference-grant" type="checkbox"> Grant this reference read</label>
      <button id="reference-read" class="secondary">Read with a governed receipt</button>
      <button id="reference-job" class="secondary">Run bounded reference job</button>
      <label for="reference-draft-title">Approved reference title</label>
      <input id="reference-draft-title" type="text" maxlength="200" autocomplete="off">
      <label for="reference-draft">Approved reference text</label>
      <textarea id="reference-draft" rows="3" maxlength="65536"></textarea>
      <label class="hint" for="reference-approve"><input id="reference-approve" type="checkbox"> Approve this exact reference write</label>
      <button id="reference-prepare" class="secondary">Prepare approved write</button>
      <button id="reference-confirm" class="secondary">Confirm write</button>
      <button id="reference-rollback" class="secondary">Roll back last write</button>
      <div id="knowledge-hits" class="knowledge-hits" aria-live="polite"></div>
    </section>
    <section class="knowledge-section" aria-label="Local hardware resource monitor">
      <div class="heading"><span>Hardware &amp; memory fabric</span>
        <button id="resource-refresh" class="small" type="button" disabled>Refresh</button>
      </div>
      <p class="hint">Private device telemetry. GPU and shared memory remain
      backend-owned; unknown hardware capacity is never assumed available.</p>
      <pre id="resource-monitor" aria-live="polite">Connect to inspect your device.</pre>
      <label for="resource-bytes" class="hint">Estimated source bytes</label>
      <input id="resource-bytes" type="number" min="0" step="1" value="10000000">
      <label for="resource-streams" class="hint">Requested concurrent read streams</label>
      <input id="resource-streams" type="number" min="1" step="1" value="4">
      <button id="resource-plan" class="secondary" disabled>Calculate adaptive plan</button>
      <pre id="resource-plan-result">No workload planned.</pre>
      <details><summary>Long-form virtual memory (Mac M-series / local)</summary>
        <p class="hint">Spool selected, trusted local text files as compressed,
        verified disk pages without loading the whole file into RAM.
        This does not enlarge the model's trained context window.</p>
        <label for="longform-root">Selected local directory (absolute path)</label>
        <input id="longform-root" type="text" autocomplete="off" spellcheck="false">
        <label for="longform-relative">Filename relative to selected directory</label>
        <input id="longform-relative" type="text" autocomplete="off" spellcheck="false">
        <label for="longform-grant"><input id="longform-grant" type="checkbox">
          I approve this exact private disk-backed import</label>
        <button id="longform-ingest" class="secondary" disabled>Stage long-form source</button>
        <label for="longform-search">Search staged long-form pages</label>
        <input id="longform-search" type="search" autocomplete="off">
        <button id="longform-query" class="secondary" disabled>Retrieve verified passages</button>
        <pre id="longform-status" aria-live="polite">No staged source.</pre>
        <div class="heading"><span>Resumable long-form work</span></div>
        <label for="longform-work-id">Work ID (copy to resume after restart)</label>
        <input id="longform-work-id" type="text" autocomplete="off" spellcheck="false">
        <button id="longform-work-start" class="secondary" disabled>Begin durable work</button>
        <button id="longform-work-resume" class="secondary" disabled>Restore cursor</button>
        <button id="longform-work-next" class="secondary" disabled>Read and commit next page</button>
        <pre id="longform-work-status" aria-live="polite">No active work cursor.</pre>
      </details>
    </section>
    <div class="sidebar-footer">
      <button id="fork" class="secondary">Fork conversation</button>
      <button id="export" class="secondary">Export backup</button>
      <button id="export-text" class="secondary">Export Markdown</button>
      <label class="import-label" for="import">Import backup</label>
      <input id="import" type="file" accept=".json,application/json">
      <button id="delete" class="danger">Delete selected</button>
    </div>
  </aside>
  <main class="main">
    <header class="topbar">
      <button id="sidebar-toggle" class="small mobile-only" aria-controls="sidebar" aria-expanded="true">Library &amp; connection</button>
      <div><h1>Local model conversation</h1><p id="model">Not connected</p></div>
      <div id="indicator" class="indicator">LOCKED</div>
    </header>
    <div id="turn-progress" class="turn-progress" role="status" hidden>
      <span id="turn-label">Ready</span><span id="turn-elapsed"></span>
      <button id="check-turn" class="small">Check status</button>
      <button id="cancel-turn" class="danger small">Cancel generation</button>
    </div>
    <div class="intro" id="intro">
      <div class="glow">✧</div><h2>Your model. Your machine.</h2>
      <p>No hosted AI provider, account sign-in, remote retrieval or Docker required. Choose a locally installed model when starting the server.</p>
      <p class="minor">An untrained native checkpoint will not produce useful assistant responses. For useful chat, use a qualified GGUF model with the local llama.cpp backend.</p>
    </div>
    <div id="messages" class="messages" role="log" aria-live="polite" aria-label="Conversation"></div>
    <div class="transcript-tools"><button id="copy-transcript" class="small">Copy conversation</button>
      <button id="refresh-session" class="small">Refresh saved history</button></div>
    <div class="composer">
      <label for="prompt">Message to local model</label>
      <textarea id="prompt" rows="3" placeholder="Enter a message..." maxlength="4096"></textarea>
      <div class="inline bottom">
        <label for="grounded"><input id="grounded" type="checkbox"> Include local evidence</label>
        <label for="budget">Output tokens <input id="budget" type="number" min="1" max="8192" value="32"></label>
        <span id="revision">No conversation selected</span>
        <button id="send" class="primary">Generate locally ↗</button>
        <button id="retry-turn" class="secondary" hidden>Retry original turn</button>
      </div>
    </div>
    <div id="status" class="status" role="status">Paste the local access token to connect.</div>
    <dialog id="reference-dialog" aria-labelledby="reference-title">
      <h2 id="reference-title">Local reference</h2><p id="reference-digest" class="hint"></p>
      <pre id="reference-text"></pre><div class="inline">
        <button id="reference-save" class="secondary">Save original text</button>
        <button id="reference-close" class="primary">Close</button></div>
    </dialog>
  </main>
</div>
<script src="/app.js" defer></script>
</body></html>"""


CSS = r"""*{box-sizing:border-box}html,body{margin:0;min-height:100%;font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:#ebeef8;background:#0d0f17}button,input,textarea{font:inherit}button{cursor:pointer;border:1px solid #333b55;border-radius:9px;padding:9px 12px;color:#eff1ff;background:#202638;transition:background .15s}button:hover{background:#303a57}button:disabled{opacity:.38;cursor:default}.primary{border-color:#6379dc;background:#495dc1}.primary:hover{background:#6479dc}.secondary{background:#191e2d}.danger{color:#ffbfc1;background:#322127;border-color:#63343f}.shell{display:grid;grid-template-columns:300px 1fr;min-height:100vh}.sidebar{display:flex;flex-direction:column;background:#131823;border-right:1px solid #30374b;padding:21px 17px;min-height:100vh}.brand{display:flex;align-items:center;gap:11px;margin-bottom:28px}.brand-mark{display:grid;place-items:center;width:44px;height:44px;color:#b7c8ff;font-size:28px;border:1px solid #4d5e85;border-radius:14px;background:#202d48}.brand strong{display:block;font-size:20px;letter-spacing:.3px}.brand small{display:block;font-size:11px;color:#9faec9;letter-spacing:.6px}.connect{border-radius:12px;padding:13px;background:#1b2233;border:1px solid #303d5a}.connect label,.composer label{font-size:12px;font-weight:650;color:#c8d0e6}.connect input{width:100%;margin:9px 0;padding:11px 10px;color:#f6f7fb;background:#101521;border:1px solid #35425c;border-radius:8px}.inline{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.inline button{flex:1}.hint,.minor{font-size:12px;color:#a4b1ce;line-height:1.5}.heading{display:flex;justify-content:space-between;align-items:center;margin-top:27px;margin-bottom:11px;font-size:12px;color:#aebdd9;text-transform:uppercase;letter-spacing:1px}.small{padding:5px 8px;text-transform:none;letter-spacing:0}.sessions{display:flex;flex-direction:column;gap:5px;overflow-y:auto;flex:1;min-height:100px;max-height:50vh}.session{width:100%;text-align:left;white-space:normal;padding:11px 9px;background:transparent;border-color:transparent;font-size:13px;overflow-wrap:anywhere}.session.active{background:#2a3654;border-color:#596b93}.session small{display:block;margin-top:4px;color:#9daacc;font-size:11px}.sidebar-footer{display:grid;gap:7px;padding-top:13px;border-top:1px solid #343d50}.import-label{display:block;padding:9px 12px;border:1px solid #343d50;border-radius:9px;background:#1b2231;text-align:center;cursor:pointer}.sidebar-footer input[type=file]{width:100%;font-size:10px;color:#a3b4d2;max-width:100%}.main{min-width:0;display:flex;flex-direction:column;min-height:100vh}.topbar{display:flex;justify-content:space-between;align-items:center;padding:24px 35px;border-bottom:1px solid #222b3c}.topbar h1{font-size:17px;margin:0;font-weight:650}.topbar p{font-size:12px;color:#a5b1ca;margin:5px 0 0}.indicator{font-size:10px;letter-spacing:1px;border:1px solid #46506c;background:#1c2638;padding:7px 11px;border-radius:25px;color:#9aabd2}.intro{margin:auto;max-width:520px;text-align:center;padding:40px}.intro .glow{font-size:48px;color:#9fafff}.intro h2{font-size:29px;letter-spacing:-1px;margin:10px}.intro p{color:#b5c0d9;line-height:1.6}.messages{width:100%;max-width:900px;margin:0 auto;flex:1;min-height:0;overflow-y:auto;padding:30px 28px;display:flex;flex-direction:column;gap:16px}.message{padding:16px 18px;border:1px solid #2f3952;border-radius:14px;max-width:90%;overflow-wrap:anywhere;white-space:pre-wrap;line-height:1.55;font-size:14px}.message.user{background:#24314a;align-self:flex-end;border-color:#405882}.message.assistant{background:#171e2c;align-self:flex-start}.message header{font-weight:700;color:#bacafa;font-size:11px;margin-bottom:8px;letter-spacing:.6px}.composer{width:calc(100% - 50px);max-width:870px;margin:0 auto;padding:15px;border-radius:15px;border:1px solid #35435e;background:#191f2e}.composer textarea{width:100%;resize:vertical;background:#0e1522;color:#f0f2fa;border:1px solid #35405b;border-radius:9px;margin-top:7px;padding:12px;min-height:68px}.composer .bottom{justify-content:space-between;margin-top:9px}.bottom button{flex:0}.bottom label{display:flex;gap:8px;align-items:center}.bottom input{width:64px;padding:5px;color:#fff;background:#0e1522;border:1px solid #35405b;border-radius:6px}.bottom span{color:#abb8d2;font-size:11px}.status{padding:13px 30px;min-height:42px;text-align:center;color:#abb7cc;font-size:12px}@media(max-width:720px){.shell{grid-template-columns:1fr}.sidebar{min-height:0;padding:13px}.brand{margin-bottom:13px}.sidebar-footer{display:flex;flex-wrap:wrap}.sidebar-footer button,.sidebar-footer label{flex:1}.sessions{max-height:140px}.topbar{padding:14px}.intro{padding:16px}.messages{padding:14px}.composer{width:calc(100% - 20px);margin:10px}.bottom span{display:none}}
.knowledge-section{border-top:1px solid #333b50;margin-top:12px;padding-top:8px;display:grid;gap:7px;font-size:12px;max-height:48vh;overflow:auto}
.knowledge-section label{color:#c2cbe2}.knowledge-section input[type=search],.knowledge-section input[type=text],.knowledge-section textarea{width:100%;border:1px solid #35425c;border-radius:8px;padding:9px;background:#101521;color:#fff}.knowledge-section input[type=file]{width:100%;max-width:100%;font-size:10px;color:#a3b4d2}.knowledge-section textarea{min-height:64px;resize:vertical}
.knowledge-documents,.knowledge-hits{display:grid;gap:7px}.knowledge-record,.knowledge-hit{border:1px solid #34415d;border-radius:8px;padding:8px;background:#1c2638;overflow-wrap:anywhere}
.knowledge-record{display:flex;align-items:center;justify-content:space-between;gap:4px}.knowledge-record button{flex-shrink:0;font-size:10px;padding:5px}.knowledge-hit strong{display:block;color:#b4c8ff}.knowledge-hit p{white-space:pre-wrap;color:#e0e8f8;max-height:190px;overflow:auto}.knowledge-hit small{color:#a7bcdb;overflow-wrap:anywhere}

.source-custody-label{display:block;margin-top:12px;color:#adc2e8;font-size:10px;font-weight:700}
.faithfulness{display:block;margin-top:8px;font-size:11px;font-weight:700}
.faithfulness.supported{color:#b7e3c2}.faithfulness.qualified{color:#f0d48a}
.faithfulness.abstain,.faithfulness.contested{color:#ffc1c4}
.source-custody-item{white-space:pre-wrap;font-size:11px;margin-top:7px;color:#d0d9ed;background:#1e2d42;border:1px solid #344a68;border-radius:7px;padding:9px;max-height:180px;overflow:auto}
[hidden]{display:none!important}.turn-progress{display:flex;align-items:center;gap:10px;flex-wrap:wrap;background:#1c2943;border-bottom:1px solid #35466b;padding:12px 24px;font-size:12px}.turn-progress #turn-label{flex:1}.transcript-tools{display:flex;gap:8px;justify-content:center;margin:8px}.message-actions{display:flex;gap:7px;margin-top:12px;white-space:normal}.instructions{margin:12px 0;color:#b8c9e9;font-size:12px}.instructions textarea{width:100%;margin-top:9px;color:#eff2fa;background:#101521;border:1px solid #35425c;border-radius:8px;padding:8px}.sidebar input[type=search]{min-width:0;flex:1;width:100%;color:#eef2fa;background:#101521;border:1px solid #35425c;border-radius:8px;padding:9px}.reference-name{text-align:left;padding:4px;border:0;background:transparent;font-size:11px;overflow-wrap:anywhere}.session small:last-child{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}dialog{width:min(850px,94vw);max-height:86vh;overflow:auto;background:#131d2d;color:#ebf1ff;border:1px solid #526a95;border-radius:14px;padding:22px}dialog::backdrop{background:#000a}dialog pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:55vh;overflow:auto;background:#0b1321;padding:15px;border-radius:9px}dialog .hint{overflow-wrap:anywhere}:focus-visible{outline:2px solid #a1c1ff;outline-offset:3px}

.shell{height:100vh;height:100dvh;overflow:hidden}.sidebar{min-height:0;height:100%;overflow-y:auto}.main{height:100%;min-height:0}.messages{overscroll-behavior:contain}.intro{flex-shrink:1;overflow:auto}.mobile-only,.sidebar-scrim{display:none}.bottom input[type=checkbox]{width:auto}.turn-progress #turn-elapsed{font-variant-numeric:tabular-nums}.knowledge-record .reference-name{min-width:0;flex-shrink:1;flex:1}.brand #sidebar-close{margin-left:auto}
@media(max-width:720px){.shell{display:block;min-height:0}.sidebar{display:none}.main{height:100%}.topbar{flex-wrap:wrap;gap:8px}.topbar>div:first-of-type{flex:1;min-width:150px}.topbar h1{font-size:15px}.topbar p{overflow-wrap:anywhere}.mobile-only{display:inline-block}.library-open .sidebar{display:flex;position:fixed;top:0;bottom:0;left:0;width:min(350px,90vw);z-index:20;min-height:0;max-height:100dvh;overflow-y:auto;box-shadow:10px 0 40px #0007}.library-open .sidebar-scrim{display:block;position:fixed;inset:0;width:100%;height:100%;z-index:19;background:#0009;border:0;border-radius:0}.sidebar .sessions{flex:none;max-height:25vh}.sidebar .knowledge-section{flex:none;max-height:48vh}.sidebar .sidebar-footer{display:grid}.composer{flex-shrink:0;margin:0 auto;padding:10px}.composer textarea{min-height:50px;max-height:24vh}.composer .bottom{gap:6px}.turn-progress{padding:8px 12px}.status{padding:9px 12px}.messages{padding:12px;gap:10px}.message{max-width:97%}.intro h2{font-size:23px}.intro .glow{font-size:30px}.intro .minor{font-size:11px}.intro{padding:12px}.transcript-tools{margin:5px}}

"""


JAVASCRIPT = r"""'use strict';
(() => {
  const get = id => document.getElementById(id);
  const bytes = value => new TextEncoder().encode(value).byteLength;
  const state = {
    token: '', connected: false, busy: false, epoch: 0,
    session: '', revision: 0, messages: [], evidence: [], audits: [], faithfulness: [],
    sessions: [], cursor: null, query: '', drafts: new Map(),
    pending: null, turn: null, timer: null, polling: false,
    writePending: null, writeRequest: '',
    pollStarted: 0, pollErrors: 0, health: null, reference: null,
    network: new AbortController(), resourceTimer: null, longformSourceId: null,
    longformWork: null, longformPendingRequest: null,
  };
  async function refreshResources() {
    if (!state.connected || !state.token) return;
    try {
      const view = await api('GET', '/v1/resources');
      const h = view.hardware || {};
      const gib = value => typeof value === 'number' ? (value / 1073741824).toFixed(2) + ' GiB' : 'unknown';
      const vram = view.gpus && view.gpus.length ? view.gpus.map(d =>
        d.device + ': ' + (d.vendor === 'apple'
          ? 'Metal unified · recommended set ' + gib(d.recommended_working_set_bytes)
            + ' · currently allocated ' + gib(d.current_allocated_bytes)
          : gib(d.dedicated_free_bytes) + ' VRAM free' +
            (d.shared_free_bytes === null ? ' · shared unknown' :
              ' · ' + gib(d.shared_free_bytes) + ' host-shared (not additive)'))
      ).join('\n') : 'GPU telemetry unavailable — no VRAM allocation assumed';
      const c = view.controller || {};
      const throughput = typeof c.smoothed_read_bytes_per_second === 'number' ?
        (c.smoothed_read_bytes_per_second / 1048576).toFixed(2) + ' MiB/s' : 'not calibrated';
      get('resource-monitor').textContent =
        'RAM ' + gib(h.available_ram_bytes) + ' / ' + gib(h.total_ram_bytes) +
        '\nSwap/pagefile ' + gib(h.free_swap_bytes) + ' / ' + gib(h.total_swap_bytes) +
        '\nLocal disk ' + gib(h.free_disk_bytes) + ' / ' + gib(h.total_disk_bytes) +
        '\nCPU load ' + (h.cpu_load_ratio ?? 'unknown') +
        ' · worker budget ' + (c.adaptive_stream_budget ?? '?') +
        '\nMemory pressure ' + ((c.predictive_pressure ?? 0) * 100).toFixed(1) + '%' +
        '\n' + vram + '\nRead throughput: ' + throughput +
        '\nStaging: read-only host mmap / SQLite spill';
    } catch (error) {
      if (state.connected) get('resource-monitor').textContent = 'Resource telemetry unavailable.';
    }
  }
  const terminal = turn => !!turn && ['complete', 'failed', 'cancelled'].includes(turn.state);
  const unresolved = () => !!state.turn && !terminal(state.turn);
  const status = value => { get('status').textContent = value; };
  function sidebar(open, restoreFocus = false) {
    get('shell').classList.toggle('library-open', open);
    get('sidebar-toggle').setAttribute('aria-expanded', String(open));
    if (restoreFocus && window.matchMedia('(max-width:720px)').matches) get('sidebar-toggle').focus();
  }
  function clearSearch() {state.query = ''; get('session-query').value = '';}

  function updateControls() {
    const locked = !state.connected;
    const working = state.busy || state.polling || unresolved();
    ['new', 'fork', 'delete', 'import', 'system-prompt', 'session-search', 'sessions-more'].forEach(id => {
      get(id).disabled = locked || working;
    });
    ['knowledge-file', 'knowledge-search', 'knowledge-query', 'reference-read', 'reference-grant',
      'reference-job', 'reference-draft-title', 'reference-draft', 'reference-approve',
      'reference-prepare'].forEach(id => {
      get(id).disabled = locked || state.busy;
    });
    get('reference-confirm').disabled = locked || state.busy || !state.writePending;
    get('reference-rollback').disabled = locked || state.busy || !state.writeRequest;
    ['export', 'export-text', 'copy-transcript', 'refresh-session'].forEach(id => {
      get(id).disabled = locked || state.busy || !state.session;
    });
    ['prompt', 'budget', 'grounded'].forEach(id => {get(id).disabled = locked || working;});
    get('send').disabled = locked || working || !state.session;
    get('connect').disabled = state.busy || state.connected;
    get('disconnect').disabled = !state.connected && !state.token;
    get('resource-refresh').disabled = locked;
    get('resource-plan').disabled = locked;
    get('longform-ingest').disabled = locked || state.busy;
    get('longform-query').disabled = locked || state.busy || !state.longformSourceId;
    get('longform-work-start').disabled = locked || state.busy || !state.longformSourceId;
    get('longform-work-resume').disabled = locked || state.busy;
    get('longform-work-next').disabled = locked || state.busy || !state.longformWork;
    const progress = !!state.turn;
    get('turn-progress').hidden = !progress;
    get('cancel-turn').disabled = !unresolved() || state.turn?.cancel_requested || locked;
    get('check-turn').disabled = !state.turn || state.polling || locked;
    get('retry-turn').hidden = !state.pending || !terminal(state.turn) || state.turn.state === 'complete';
    get('retry-turn').disabled = locked || working;
    document.querySelectorAll('[data-session], [data-fork]').forEach(button => {
      button.disabled = locked || working;
    });
    if (state.turn) {
      const labels = {
        queued: 'Waiting for the local model', running: 'Generating on this device',
        cancelling: 'Cancellation requested — waiting for the model',
        unknown: 'Delivery uncertain — check or recover the original request',
        complete: 'Reply committed to local history', cancelled: 'Generation cancelled',
        failed: 'Generation failed',
      };
      get('turn-label').textContent = labels[state.turn.state] || state.turn.state;
    }
    get('indicator').textContent = locked ? 'LOCKED' : unresolved() ? 'LOCAL • RUNNING' : 'OFFLINE • CONNECTED';
  }
  function stopPolling() {
    if (state.timer !== null) clearTimeout(state.timer);
    state.timer = null;
  }
  function lock() {
    if (state.resourceTimer !== null) clearInterval(state.resourceTimer);
    state.resourceTimer = null;
    get('resource-monitor').textContent = 'Connect to inspect your device.';
    get('resource-plan-result').textContent = 'No workload planned.';
    get('longform-status').textContent = 'No staged source.';
    get('longform-work-status').textContent = 'No active work cursor.';
    get('longform-work-id').value = '';
    state.longformSourceId = null;
    state.longformWork = null;
    state.longformPendingRequest = null;
    const hadWork = unresolved();
    stopPolling();
    state.epoch++;
    state.network.abort();
    state.network = new AbortController();
    Object.assign(state, {token: '', connected: false, busy: false, session: '', revision: 0,
      messages: [], evidence: [], audits: [], faithfulness: [], sessions: [], cursor: null, query: '',
      pending: null, turn: null, polling: false, reference: null, health: null,
      writePending: null, writeRequest: ''});
    state.drafts.clear();
    ['secret', 'prompt', 'system-prompt', 'session-query', 'knowledge-query', 'import', 'knowledge-file',
      'reference-draft-title', 'reference-draft'].forEach(id => {get(id).value = '';});
    get('reference-grant').checked = false;
    get('reference-approve').checked = false;
    ['sessions', 'messages', 'knowledge-documents', 'knowledge-hits'].forEach(id => get(id).replaceChildren());
    get('reference-text').textContent = '';
    get('reference-dialog').close();
    get('model').textContent = 'Not connected';
    get('intro').hidden = false;
    get('revision').textContent = 'No conversation selected';
    get('sessions-more').hidden = true;
    updateControls();
    sidebar(true);
    status(hadWork ? 'Locked. The model may still be running. Reconnect to recover its status.' :
      'Locked. Token, drafts and visible conversation content were cleared from this tab.');
  }
  async function api(method, path, data, rawJSON = false) {
    if (!state.token) throw new Error('Provide the local bearer token first.');
    const epoch = state.epoch;
    const network = state.network;
    const headers = {Authorization: 'Bearer ' + state.token};
    if (data !== undefined) headers['Content-Type'] = 'application/json';
    const timeout = new AbortController();
    const cancel = () => timeout.abort();
    network.signal.addEventListener('abort', cancel, {once: true});
    const timer = setTimeout(cancel, 15000);
    let response;
    try {
      response = await fetch(path, {
        method, headers, cache: 'no-store', credentials: 'omit', signal: timeout.signal,
        body: data === undefined ? undefined : rawJSON ? data : JSON.stringify(data),
      });
      const result = await response.json();
      if (epoch !== state.epoch) throw new Error('Workspace locked.');
      if (!response.ok) {
        const error = new Error(result.error || 'Local operation failed.');
        error.status = response.status;
        throw error;
      }
      return result;
    } catch (error) {
      if (error.name === 'AbortError') throw new Error('The connection timed out. The server may still be working.');
      throw error;
    } finally {
      clearTimeout(timer);
      network.signal.removeEventListener('abort', cancel);
    }
  }
  async function run(work) {
    if (state.busy) return;
    const epoch = state.epoch;
    state.busy = true; updateControls();
    try {await work();}
    catch (error) {if (epoch === state.epoch) status(error.message || 'Local operation failed.');}
    finally {if (epoch === state.epoch) {state.busy = false; updateControls();}}
  }
  function download(content, filename, type) {
    const url = URL.createObjectURL(new Blob([content], {type}));
    const link = document.createElement('a');
    link.href = url; link.download = filename.replace(/[^a-zA-Z0-9._-]/g, '-').slice(0, 160);
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  async function copy(content) {
    try {
      await navigator.clipboard.writeText(content); status('Copied to clipboard.');
    } catch {
      status('Clipboard is unavailable. Select and copy the visible text, or export it.');
    }
  }
  function transcript() {
    const lines = ['# Local model conversation', '', 'Session: ' + state.session,
      'Model: ' + (state.health?.model_digest || ''), '', 'Exported: ' + new Date().toISOString(), ''];
    let turn = 0;
    state.messages.forEach(message => {
      lines.push('## ' + (message.role === 'user' ? 'You' : message.role === 'system' ? 'Instructions' : 'Local model'), '', message.content, '');
      if (message.role === 'assistant') {
        const evidence = state.evidence[turn];
        const faith = state.faithfulness[turn++];
        if (faith) {
          lines.push('### Grounded publication', '', faith.published_text, '',
            'Faithfulness: ' + faith.disposition, 'Deterministic atom check, not semantic verification.', '');
          if (faith.published_text !== message.content) lines.push('### Unverified model draft', '', message.content, '');
        }
        if (evidence?.citations?.length) {
          lines.push('### Supplied evidence', '');
          if (state.audits[turn - 1]) lines.push('Citation ID audit: ' + state.audits[turn - 1].status, '');
          evidence.citations.forEach(source => lines.push(source.title + ' — ' + source.citation, '', source.passage, ''));
        }
      }
    });
    return lines.join('\n');
  }
  function showMessages() {
    const list = get('messages'); list.replaceChildren();
    get('intro').hidden = state.messages.length > 0;
    let completed = 0;
    state.messages.forEach(message => {
      const card = document.createElement('article');
      card.className = 'message ' + (message.role === 'user' ? 'user' : 'assistant');
      const header = document.createElement('header');
      const faith = message.role === 'assistant' ? state.faithfulness[completed] : null;
      const visible = faith?.published_text || message.content;
      header.textContent = message.role === 'user' ? 'YOU' : message.role === 'system' ? 'CONVERSATION INSTRUCTIONS' : (faith && visible !== message.content ? 'GROUNDED ANSWER' : 'LOCAL MODEL');
      const content = document.createElement('div'); content.textContent = visible;
      card.append(header, content);
      const actions = document.createElement('div'); actions.className = 'message-actions';
      const copyButton = document.createElement('button'); copyButton.className = 'small'; copyButton.textContent = 'Copy';
      copyButton.addEventListener('click', () => void copy(visible)); actions.append(copyButton);
      if (message.role === 'assistant') {
        const index = completed++;
        const fork = document.createElement('button'); fork.className = 'small';
        fork.textContent = 'Branch from here'; fork.dataset.fork = String(completed);
        const afterTurn = completed;
        fork.addEventListener('click', () => run(async () => {
          const item = await api('POST', '/v1/sessions/' + state.session + '/fork', {after_turn: afterTurn});
          await selectSession(item.session_id);
          status('Created a separate branch through turn ' + afterTurn + '. The original is preserved.');
        }));
        actions.append(fork);
        const supplied = state.evidence[index];
        const audit = state.audits[index];
        const verdict = state.faithfulness[index];
        if (verdict) {
          const badge = document.createElement('small');
          badge.className = 'faithfulness ' + verdict.disposition;
          badge.textContent = 'Grounded publication: ' + verdict.disposition + ' · deterministic atom check, not semantic verification';
          card.append(badge);
          if (verdict.published_text !== message.content) {
            const draft = document.createElement('details'); draft.className = 'source-custody-item';
            const heading = document.createElement('summary'); heading.textContent = 'Unverified model draft';
            const body = document.createElement('p'); body.textContent = message.content;
            draft.append(heading, body); card.append(draft);
          }
        }
        if (supplied?.citations?.length) {
          const label = document.createElement('small'); label.className = 'source-custody-label';
          label.textContent = 'Sources supplied to the model' +
            (audit ? ' · citation IDs: ' + audit.status : '');
          card.append(label);
          supplied.citations.forEach(source => {
            const note = document.createElement('details'); note.className = 'source-custody-item';
            const heading = document.createElement('summary'); heading.textContent = source.title + ' · ' + source.citation;
            const passage = document.createElement('p'); passage.textContent = source.passage;
            note.append(heading, passage); card.append(note);
          });
        }
      }
      card.append(actions); list.append(card);
    });
    list.scrollTop = list.scrollHeight;
    updateControls();
  }
  function renderSessions() {
    const view = get('sessions'); view.replaceChildren();
    state.sessions.forEach(item => {
      const button = document.createElement('button'); button.dataset.session = item.session_id;
      button.className = 'session' + (item.session_id === state.session ? ' active' : '');
      const title = document.createElement('span'); title.textContent = item.title || 'New conversation';
      const detail = document.createElement('small');
      detail.textContent = item.revision + ' saved turns · ' + new Date(item.updated_at_ms).toLocaleString();
      const preview = document.createElement('small'); preview.textContent = item.preview || 'No messages yet';
      button.append(title, detail, preview);
      button.addEventListener('click', () => run(async () => {await selectSession(item.session_id); sidebar(false);}));
      view.append(button);
    });
    if (!state.sessions.length) {const empty = document.createElement('p'); empty.className = 'hint'; empty.textContent = state.query ? 'No matching conversations.' : 'Create your first local conversation.'; view.append(empty);}
    get('sessions-more').hidden = !state.cursor;
    updateControls();
  }
  async function loadSessions(more = false) {
    const result = await api('POST', '/v1/sessions/search', {
      query: state.query, limit: 30, cursor: more ? state.cursor : null,
    });
    const byId = new Map((more ? state.sessions : []).map(item => [item.session_id, item]));
    result.sessions.forEach(item => byId.set(item.session_id, item));
    state.sessions = Array.from(byId.values()); state.cursor = result.next_cursor;
    renderSessions();
  }
  async function selectSession(id) {
    const current = state.session;
    if (current) state.drafts.set(current, get('prompt').value);
    const result = await api('GET', '/v1/sessions/' + id);
    if (current !== id) {state.turn = null; state.pending = null; stopPolling();}
    state.session = result.session_id; state.revision = result.revision;
    state.messages = result.messages; state.evidence = result.evidence || []; state.audits = result.citation_audits || [];
    state.faithfulness = result.faithfulness_audits || [];
    if (current !== id) get('prompt').value = state.drafts.get(id) || '';
    get('revision').textContent = result.revision + ' saved turns';
    showMessages(); await loadSessions(); updateControls();
  }
  function schedulePoll(delay = 1200) {
    stopPolling();
    if (state.connected && unresolved()) state.timer = setTimeout(() => void pollTurn(), delay);
  }
  async function pollTurn() {
    if (!state.turn || state.polling || !state.connected) return;
    const observed = state.turn;
    const epoch = state.epoch;
    let superseded = false;
    state.polling = true; updateControls();
    try {
      const ticket = await api('GET', '/v1/sessions/' + observed.session_id + '/turns/' + observed.request_id);
      if (state.epoch !== epoch) return;
      if (state.turn !== observed) {superseded = true; return;}
      state.turn = ticket; state.pollErrors = 0;
      if (terminal(ticket)) {
        stopPolling();
        if (ticket.state === 'complete') {
          if (state.pending && get('prompt').value.trim() === state.pending.message) {
            get('prompt').value = ''; state.drafts.delete(ticket.session_id);
          }
          state.pending = null;
          await selectSession(ticket.session_id);
          const result = ticket.result;
          status('Reply saved' + (result?.replayed ? ' · recovered saved answer' : '') +
            (result ? ' · ' + result.output_tokens + ' output tokens' : '') + '.');
        } else {
          status(ticket.error || 'Cancelled without a completed reply. Retry original turn or edit your next request.');
        }
      } else {
        const seconds = Math.max(0, Math.floor((Date.now() - ticket.created_at * 1000) / 1000));
        get('turn-elapsed').textContent = seconds + 's elapsed';
        if (performance.now() - state.pollStarted > 10 * 60 * 1000) {
          status('Automatic status polling paused after 10 minutes. Check status or request cancellation.');
        } else schedulePoll();
      }
    } catch (error) {
      if (epoch !== state.epoch) return;
      state.pollErrors++;
      status(error.status === 404 ? (state.pending ? 'Execution ticket is unavailable. Retry the original request to recover its durable receipt.' : 'Execution ticket is unavailable. Refresh saved history to see committed replies.') :
        'Status unavailable. No new generation was requested. ' + error.message);
      if (error.status === 404) {
        state.turn = {...observed, state: 'failed', terminal: true, error: 'ticket unavailable'};
      } else if (state.pollErrors < 8) schedulePoll(Math.min(8000, 1000 * 2 ** state.pollErrors));
    } finally {
      if (epoch === state.epoch) {
        state.polling = false; updateControls();
        if (superseded && state.turn) {stopPolling(); state.timer = setTimeout(() => void pollTurn(), 100);}
      }
    }
  }
  async function submit(retry = false) {
    const epoch = state.epoch;
    if (!state.session) throw new Error('Create or select a conversation first.');
    if (unresolved()) throw new Error('Resolve the current request before starting another.');
    let request;
    if (retry) {
      if (!state.pending) throw new Error('The original request is not available in this tab. Refresh saved history.');
      request = state.pending;
    } else {
      const message = get('prompt').value.trim();
      const grounded = get('grounded').checked;
      const max_output_tokens = Number(get('budget').value);
      if (!message || bytes(message) > (grounded ? 1024 : 4096)) throw new Error(grounded ? 'Evidence questions must be 1–1024 UTF-8 bytes.' : 'Messages must be 1–4096 UTF-8 bytes.');
      if (!Number.isInteger(max_output_tokens) || max_output_tokens < 1 || max_output_tokens > state.health.max_output_tokens) throw new Error('Output budget exceeds the selected model limit.');
      request = {session_id: state.session, message, grounded, max_output_tokens,
        request_id: crypto.randomUUID().replace(/-/g, '')};
      const original = state.pending;
      if (original && original.session_id === request.session_id && original.message === message
          && original.grounded === grounded && original.max_output_tokens === max_output_tokens) {
        request = original; retry = true;
      }
      state.pending = request;
    }
    state.turn = {session_id: request.session_id, request_id: request.request_id, state: 'unknown'};
    state.pollStarted = performance.now(); state.pollErrors = 0; updateControls();
    const {session_id, ...body} = request;
    try {
      state.turn = await api('POST', '/v1/sessions/' + session_id + '/turns', {...body, retry});
      status('Local request admitted. You can cancel while the model runs.');
      // Poll even an immediately replayed result through the same finalization UI.
      void pollTurn();
    } catch (error) {
      if (epoch !== state.epoch) return;
      if (error.status && error.status < 500) {
        state.turn = {...state.turn, state: 'failed', terminal: true, error: error.message};
      } else schedulePoll();
      throw error;
    } finally {if (epoch === state.epoch) updateControls();}
  }
  async function loadDocuments() {
    const payload = await api('GET', '/v1/knowledge/documents');
    const view = get('knowledge-documents'); view.replaceChildren();
    payload.documents.forEach(doc => {
      const row = document.createElement('div'); row.className = 'knowledge-record';
      const open = document.createElement('button'); open.className = 'reference-name';
      open.textContent = doc.title + ' · ' + doc.character_count + ' characters';
      open.addEventListener('click', () => run(async () => {
        state.reference = await api('GET', '/v1/knowledge/documents/' + doc.document_id);
        get('reference-title').textContent = state.reference.title;
        get('reference-digest').textContent = 'SHA-256: ' + state.reference.sha256;
        get('reference-text').textContent = state.reference.text;
        get('reference-dialog').showModal();
      }));
      const remove = document.createElement('button'); remove.className = 'danger'; remove.textContent = 'Remove';
      remove.addEventListener('click', () => run(async () => {
        if (!window.confirm('Remove this reference from the local library? Existing conversation evidence is preserved.')) return;
        await api('DELETE', '/v1/knowledge/documents/' + doc.document_id);
        await loadDocuments(); get('knowledge-hits').replaceChildren(); status('Reference removed.');
      }));
      row.append(open, remove); view.append(row);
    });
  }
  get('sidebar-toggle').addEventListener('click', () => sidebar(!get('shell').classList.contains('library-open')));
  get('sidebar-close').addEventListener('click', () => sidebar(false, true));
  get('sidebar-scrim').addEventListener('click', () => sidebar(false, true));
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && !get('reference-dialog').open) sidebar(false, true);
  });
  get('connect').addEventListener('click', () => run(async () => {
    const token = get('secret').value.trim();
    if (token.length < 32) throw new Error('The local token is missing or invalid.');
    state.token = token;
    try {state.health = await api('GET', '/v1/status');}
    catch (error) {state.token = ''; throw error;}
    state.connected = true; get('secret').value = '';
    sidebar(false);
    get('model').textContent = state.health.runtime_kind + ' · ' + state.health.context_tokens + ' context tokens · ' + state.health.model_digest.slice(0, 16) + '…';
    get('budget').value = String(state.health.default_output_tokens);
    get('budget').max = String(state.health.max_output_tokens);
    await loadSessions(); await loadDocuments();
    await refreshResources();
    if (state.resourceTimer !== null) clearInterval(state.resourceTimer);
    state.resourceTimer = setInterval(refreshResources, 10000);
    if (state.health.active_turn) {
      const activeTurn = state.health.active_turn;
      await selectSession(activeTurn.session_id);
      state.turn = activeTurn; state.pollStarted = performance.now(); schedulePoll(100);
      status('Reconnected to a local generation already in progress.');
    } else status('Connected locally. Choose a conversation or create a new one.');
  }));
  get('disconnect').addEventListener('click', lock);
  get('resource-refresh').addEventListener('click', refreshResources);
  get('resource-plan').addEventListener('click', () => run(async () => {
    const source_bytes = Number(get('resource-bytes').value);
    const desired_streams = Number(get('resource-streams').value);
    if (!Number.isSafeInteger(source_bytes) || source_bytes < 0 ||
        !Number.isSafeInteger(desired_streams) || desired_streams < 1) {
      throw new Error('Select nonnegative source bytes and positive read streams.');
    }
    const plan = await api('POST', '/v1/resources/plan',
                           {source_bytes, desired_streams});
    get('resource-plan-result').textContent =
      'Placement ' + plan.residency + '\nStreams ' + plan.stream_count +
      '\nChunk bytes ' + plan.transfer_chunk_bytes +
      '\nRead-only staging ' + (plan.readonly_staging ? 'recommended' : 'optional') +
      '\nGPU transfer: backend qualification required';
  }));
  get('longform-ingest').addEventListener('click', () => run(async () => {
    if (!get('longform-grant').checked) throw new Error('Approve this source first.');
    const root = get('longform-root').value.trim();
    const relative_path = get('longform-relative').value.trim();
    if (!root || !relative_path) throw new Error('Choose the selected root and filename.');
    const receipt = await api('POST', '/v1/resources/longform/ingest',
      {root, relative_path, approved: true});
    state.longformSourceId = receipt.source_id;
    get('longform-grant').checked = false;
    get('longform-status').textContent =
      'Private archive verified: ' + receipt.source_sha256.slice(0, 20) +
      '…\nBytes: ' + receipt.source_bytes +
      '\nPages: ' + receipt.page_count +
      '\nDisk payload: ' + receipt.stored_payload_bytes;
    updateControls();
  }));
  get('longform-query').addEventListener('click', () => run(async () => {
    if (!state.longformSourceId) throw new Error('Stage a source before searching.');
    const query = get('longform-search').value.trim();
    if (!query) throw new Error('Enter a query.');
    const evidence = await api('POST', '/v1/resources/longform/search',
      {source_id: state.longformSourceId, query, limit: 3});
    get('longform-status').textContent =
      'Verified ' + evidence.source_sha256.slice(0, 20) +
      '…\n' + evidence.hits.map(h =>
        'Page ' + h.page + ': ' + h.text.slice(0, 400)
      ).join('\n\n');
  }));
  function displayLongformWork(work) {
    const progress = work.next_page + ' / ' + work.total_pages + ' pages';
    get('longform-work-id').value = work.work_id;
    get('longform-work-status').textContent =
      'Saved progress: ' + progress + '\nRevision: ' + work.revision +
      (work.complete ? '\nComplete.' : '\nReady for next page.');
    state.longformWork = work;
    updateControls();
  }
  get('longform-work-start').addEventListener('click', () => run(async () => {
    if (!state.longformSourceId) throw new Error('Stage a source first.');
    const work = await api('POST', '/v1/resources/longform/work-start',
      {source_id: state.longformSourceId, approved: true});
    state.longformPendingRequest = null;
    displayLongformWork(work);
  }));
  get('longform-work-resume').addEventListener('click', () => run(async () => {
    const work_id = get('longform-work-id').value.trim();
    if (!/^[0-9a-f]{48}$/.test(work_id)) throw new Error('Enter the exact work ID.');
    const work = await api('POST', '/v1/resources/longform/work-status', {work_id});
    state.longformPendingRequest = null;
    state.longformSourceId = work.source_id;
    displayLongformWork(work);
  }));
  get('longform-work-next').addEventListener('click', () => run(async () => {
    const work = state.longformWork;
    if (!work) throw new Error('Restore or begin a work cursor.');
    // Preserve request identity on uncertain delivery. Reusing the same
    // work/revision/pages replays the already committed delivery exactly.
    const request = state.longformPendingRequest || {
      work_id: work.work_id, expected_revision: work.revision,
      request_id: Array.from(crypto.getRandomValues(new Uint8Array(24)),
        n => n.toString(16).padStart(2, '0')).join(''), pages: 1,
    };
    state.longformPendingRequest = request;
    const result = await api('POST', '/v1/resources/longform/work-next', request);
    state.longformPendingRequest = null;
    displayLongformWork({
      ...work, next_page: result.next_page, revision: result.revision,
      complete: result.next_page >= work.total_pages,
      receipt_chain: result.receipt_chain,
    });
    get('longform-work-status').textContent +=
      '\nReceipt: ' + result.receipt_digest.slice(0, 20) + '…' +
      (result.replayed ? '\nOriginal delivery recovered.' : '\nPage committed.') +
      '\nPage: ' + result.text.slice(0, 2000);
  }));
  get('new').addEventListener('click', () => run(async () => {
    const system = get('system-prompt').value.trim();
    if (bytes(system) > 4096) throw new Error('Instructions exceed 4096 UTF-8 bytes.');
    const result = await api('POST', '/v1/sessions', system ? {system} : {});
    state.turn = null; state.pending = null; clearSearch();
    await selectSession(result.session_id); sidebar(false); get('prompt').focus(); status('New conversation ready.');
  }));
  get('send').addEventListener('click', () => run(() => submit(false)));
  get('retry-turn').addEventListener('click', () => run(() => submit(true)));
  get('check-turn').addEventListener('click', () => {state.pollStarted = performance.now(); state.pollErrors = 0; void pollTurn();});
  get('cancel-turn').addEventListener('click', async () => {
    const current = state.turn; if (!current || terminal(current)) return;
    const epoch = state.epoch;
    get('cancel-turn').disabled = true;
    try {
      const ticket = await api('POST', '/v1/sessions/' + current.session_id + '/turns/' + current.request_id + '/cancel', {});
      if (epoch !== state.epoch || state.turn?.request_id !== current.request_id) return;
      state.turn = ticket; state.pollStarted = performance.now();
      status('Cancellation requested. Waiting for a confirmed terminal state.');
      schedulePoll(100); if (terminal(ticket)) void pollTurn();
    } catch (error) {if (epoch === state.epoch) status('Cancellation is not confirmed. ' + error.message);}
    finally {if (epoch === state.epoch) updateControls();}
  });
  get('session-search').addEventListener('click', () => run(async () => {
    const query = get('session-query').value.trim();
    if (bytes(query) > 256) throw new Error('Search text exceeds 256 UTF-8 bytes.');
    state.query = query; await loadSessions();
  }));
  get('session-query').addEventListener('keydown', event => {if (event.key === 'Enter') {event.preventDefault(); get('session-search').click();}});
  get('sessions-more').addEventListener('click', () => run(() => loadSessions(true)));
  get('refresh-session').addEventListener('click', () => run(() => selectSession(state.session)));
  get('fork').addEventListener('click', () => run(async () => {
    const item = await api('POST', '/v1/sessions/' + state.session + '/fork', {});
    state.turn = null; state.pending = null; clearSearch(); await selectSession(item.session_id); sidebar(false);
    status('Created a separate conversation branch.');
  }));
  get('delete').addEventListener('click', () => run(async () => {
    if (!window.confirm('Permanently delete this conversation and its receipts? Export a backup first if needed.')) return;
    await api('DELETE', '/v1/sessions/' + state.session);
    state.drafts.delete(state.session); state.session = ''; state.revision = 0;
    state.messages = []; state.evidence = []; state.audits = []; state.faithfulness = []; state.pending = null; state.turn = null;
    get('prompt').value = ''; get('revision').textContent = 'No conversation selected';
    showMessages(); await loadSessions(); status('Conversation deleted.');
  }));
  get('export').addEventListener('click', () => run(async () => {
    const payload = await api('GET', '/v1/sessions/' + state.session + '/export');
    download(JSON.stringify(payload), 'skeleton-chat-' + state.session.slice(0, 16) + '.json', 'application/json');
    status('Private conversation backup exported.');
  }));
  get('export-text').addEventListener('click', () => download(transcript(), 'skeleton-conversation.md', 'text/markdown;charset=utf-8'));
  get('copy-transcript').addEventListener('click', () => void copy(transcript()));
  get('import').addEventListener('change', () => run(async () => {
    const epoch = state.epoch;
    const control = get('import'); const file = control.files[0]; if (!file) return;
    if (!file.size || file.size > 16 * 1024 * 1024) throw new Error('Backup must be 1 byte–16 MiB.');
    // Preserve raw JSON so duplicate-key rejection stays at the server boundary.
    const payload = new TextDecoder('utf-8', {fatal: true}).decode(await file.arrayBuffer());
    if (epoch !== state.epoch) return;
    const item = await api('POST', '/v1/sessions/import', payload, true);
    control.value = ''; state.turn = null; state.pending = null; clearSearch(); await selectSession(item.session_id); sidebar(false);
    status('Imported a model-compatible conversation into a new session.');
  }));
  get('knowledge-file').addEventListener('change', () => run(async () => {
    const epoch = state.epoch;
    const control = get('knowledge-file'); const files = Array.from(control.files || []);
    if (files.length > 16) throw new Error('Import at most 16 reference files at a time.');
    const failures = []; let imported = 0;
    for (let index = 0; index < files.length; index++) {
      if (epoch !== state.epoch) return;
      const file = files[index]; status('Importing reference ' + (index + 1) + ' of ' + files.length + '…');
      try {
        if (!file.size || file.size > 65536) throw new Error('file must be 1–65536 bytes');
        if (bytes(file.name) > 200) throw new Error('filename exceeds 200 UTF-8 bytes');
        const text = new TextDecoder('utf-8', {fatal: true}).decode(await file.arrayBuffer());
        if (epoch !== state.epoch) return;
        await api('POST', '/v1/knowledge/documents', {title: file.name, text}); imported++;
      } catch (error) {failures.push(file.name + ': ' + error.message);}
    }
    if (epoch !== state.epoch) return;
    control.value = ''; await loadDocuments();
    status(imported + ' reference(s) imported or reused.' + (failures.length ? ' Unchanged files: ' + failures.join('; ') : ''));
  }));
  get('knowledge-search').addEventListener('click', () => run(async () => {
    const query = get('knowledge-query').value.trim(); if (!query) throw new Error('Enter a reference search query.');
    const result = await api('POST', '/v1/knowledge/search', {query, limit: 6});
    const panel = get('knowledge-hits'); panel.replaceChildren();
    result.hits.forEach(hit => {
      const card = document.createElement('article'); card.className = 'knowledge-hit';
      const title = document.createElement('strong'); title.textContent = hit.title;
      const passage = document.createElement('p'); passage.textContent = hit.passage;
      const citation = document.createElement('small'); citation.textContent = hit.citation;
      card.append(title, passage, citation); panel.append(card);
    });
    status(result.hits.length + ' matching passage(s). Relevance and factual support require review.');
  }));
  function showHits(hits, prefix) {
    const panel = get('knowledge-hits'); panel.replaceChildren();
    hits.forEach(hit => {
      const card = document.createElement('article'); card.className = 'knowledge-hit';
      const title = document.createElement('strong'); title.textContent = hit.title;
      const passage = document.createElement('p'); passage.textContent = hit.passage;
      const citation = document.createElement('small');
      citation.textContent = hit.citation + (hit.instruction_bearing ? ' · source contains instructions; not authority' : '');
      card.append(title, passage, citation); panel.append(card);
    });
    status(prefix + hits.length + ' passage(s).');
  }
  get('reference-read').addEventListener('click', () => run(async () => {
    const query = get('knowledge-query').value.trim();
    if (!query) throw new Error('Enter a reference search query.');
    if (!get('reference-grant').checked) throw new Error('Grant the reference read before running it.');
    const result = await api('POST', '/v1/tools/reference-read', {
      query, granted: true, request_id: crypto.randomUUID(),
    });
    if (result.status !== 'succeeded') throw new Error('Reference read ' + result.status + '.');
    showHits(result.hits, 'Governed read · ');
    status('Governed read succeeded · ' + result.hits.length + ' passage(s). Receipt ' + result.receipt_id.slice(0, 8) + '…');
  }));
  function draftPair() {
    const title = get('reference-draft-title').value.trim();
    const text = get('reference-draft').value.trim();
    get('reference-draft-title').value = title;
    get('reference-draft').value = text;
    return {title, text};
  }
  function clearWriteBinding() {
    state.writePending = null;
    updateControls();
  }
  get('reference-draft-title').addEventListener('input', clearWriteBinding);
  get('reference-draft').addEventListener('input', clearWriteBinding);
  get('reference-approve').addEventListener('change', () => {
    if (!get('reference-approve').checked) clearWriteBinding();
  });
  get('reference-prepare').addEventListener('click', () => run(async () => {
    const draft = draftPair();
    if (!draft.title || !draft.text) throw new Error('Enter the reference title and text.');
    if (!get('reference-approve').checked) throw new Error('Approve the reference write before preparing it.');
    const request_id = crypto.randomUUID();
    const waiting = await api('POST', '/v1/tools/reference-write', {
      title: draft.title, text: draft.text, request_id, approved: true,
    });
    if (waiting.written || waiting.error_code !== 'approval_required' || !waiting.expected_approval_ref) {
      throw new Error('Reference write did not stop for approval.');
    }
    state.writePending = {request_id, title: draft.title, text: draft.text, approval_ref: waiting.expected_approval_ref};
    status('Approval is bound to this title and text. Confirm to write it.');
  }));
  get('reference-confirm').addEventListener('click', () => run(async () => {
    const pending = state.writePending;
    const draft = draftPair();
    if (!pending) throw new Error('Prepare the approved write first.');
    if (draft.title !== pending.title || draft.text !== pending.text) {
      state.writePending = null;
      throw new Error('The title or text changed. Prepare the write again.');
    }
    const result = await api('POST', '/v1/tools/reference-write', {
      title: pending.title, text: pending.text, request_id: pending.request_id,
      approved: true, approval_ref: pending.approval_ref,
    });
    if (!result.written) throw new Error('Reference write ' + (result.error_code || result.status) + '.');
    state.writeRequest = result.request_id;
    state.writePending = null;
    await loadDocuments();
    status('Approved write stored. Receipt ' + result.receipt_id.slice(0, 8) + '…');
  }));
  get('reference-rollback').addEventListener('click', () => run(async () => {
    if (!state.writeRequest) throw new Error('No approved write is available to roll back.');
    if (!get('reference-approve').checked) throw new Error('Approve the rollback before removing the document.');
    const result = await api('POST', '/v1/tools/reference-write/rollback', {
      request_id: state.writeRequest, approved: true,
    });
    if (!result.rolled_back) throw new Error('Rollback did not remove the document.');
    state.writeRequest = '';
    await loadDocuments();
    status('Rolled back document ' + result.document_id + '.');
  }));
  get('reference-job').addEventListener('click', () => run(async () => {
    const goal = get('knowledge-query').value.trim();
    if (!goal) throw new Error('Enter a reference search query.');
    if (!get('reference-grant').checked) throw new Error('Grant the reference read before running the job.');
    const result = await api('POST', '/v1/agents/reference-job', {
      goal, request_id: crypto.randomUUID(), granted: true, allow_writes: false,
    });
    if (result.status !== 'completed' || !result.read) throw new Error('Reference job ' + result.status + '.');
    showHits(result.read.hits, 'Bounded job · ');
    status('Bounded job completed in ' + result.steps + ' step(s). Writes stayed off.');
  }));
  get('knowledge-query').addEventListener('keydown', event => {if (event.key === 'Enter') {event.preventDefault(); get('knowledge-search').click();}});
  get('reference-close').addEventListener('click', () => {get('reference-dialog').close(); state.reference = null; get('reference-text').textContent = '';});
  get('reference-save').addEventListener('click', () => {
    if (state.reference) download(state.reference.text, state.reference.title, 'text/plain;charset=utf-8');
  });
  get('prompt').addEventListener('input', () => {if (state.session) state.drafts.set(state.session, get('prompt').value);});
  get('prompt').addEventListener('keydown', event => {
    if (!event.isComposing && event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {event.preventDefault(); get('send').click();}
  });
  window.addEventListener('pageshow', event => {if (event.persisted) lock();});
  window.addEventListener('pagehide', () => {stopPolling(); state.network.abort(); state.token = '';});
  updateControls();
})();
"""


__all__ = ["HTML", "CSS", "JAVASCRIPT"]
