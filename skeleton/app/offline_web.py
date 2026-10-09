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
<div class="shell">
  <aside class="sidebar">
    <div class="brand"><span class="brand-mark">◈</span>
      <div><strong>Skeleton</strong><small>Offline AI Workspace</small></div>
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
    <div id="sessions" class="sessions" aria-label="Saved local conversations"></div>
    <section class="knowledge-section" aria-label="Private local knowledge">
      <div class="heading"><span>Local reference library</span></div>
      <p class="hint">Search operator-supplied text offline. Passages are evidence, not AI-generated claims.</p>
      <label class="import-label" for="knowledge-file">Add a text / Markdown file</label>
      <input type="file" id="knowledge-file" accept=".txt,.md,text/plain,text/markdown">
      <div id="knowledge-documents" class="knowledge-documents" aria-label="Imported references"></div>
      <label for="knowledge-query">Search reference passages</label>
      <input id="knowledge-query" type="search" autocomplete="off"
             placeholder="A topic, symbol, API or exact phrase">
      <button id="knowledge-search" class="secondary">Search offline references</button>
      <div id="knowledge-hits" class="knowledge-hits" aria-live="polite"></div>
    </section>
    <div class="sidebar-footer">
      <button id="fork" class="secondary">Fork conversation</button>
      <button id="export" class="secondary">Export backup</button>
      <label class="import-label" for="import">Import backup</label>
      <input id="import" type="file" accept=".json,application/json">
      <button id="delete" class="danger">Delete selected</button>
    </div>
  </aside>
  <main class="main">
    <header class="topbar">
      <div><h1>Local model conversation</h1><p id="model">Not connected</p></div>
      <div id="indicator" class="indicator">LOCKED</div>
    </header>
    <div class="intro" id="intro">
      <div class="glow">✧</div><h2>Your model. Your machine.</h2>
      <p>No hosted AI provider, account sign-in, remote retrieval or Docker required. Choose a locally installed model when starting the server.</p>
      <p class="minor">An untrained native checkpoint will not produce useful assistant responses. For useful chat, use a qualified GGUF model with the local llama.cpp backend.</p>
    </div>
    <div id="messages" class="messages" role="log" aria-live="polite" aria-label="Conversation"></div>
    <div class="composer">
      <label for="prompt">Message to local model</label>
      <textarea id="prompt" rows="3" placeholder="Enter a message..." maxlength="4096"></textarea>
      <div class="inline bottom">
        <label for="grounded"><input id="grounded" type="checkbox"> Include local evidence</label>
        <label for="budget">Output tokens <input id="budget" type="number" min="1" max="8192" value="32"></label>
        <span id="revision">No conversation selected</span>
        <button id="send" class="primary">Generate locally ↗</button>
      </div>
    </div>
    <div id="status" class="status" role="status">Paste the local access token to connect.</div>
  </main>
</div>
<script src="/app.js" defer></script>
</body></html>"""


CSS = r"""*{box-sizing:border-box}html,body{margin:0;min-height:100%;font-family:system-ui,-apple-system,Segoe UI,sans-serif;color:#ebeef8;background:#0d0f17}button,input,textarea{font:inherit}button{cursor:pointer;border:1px solid #333b55;border-radius:9px;padding:9px 12px;color:#eff1ff;background:#202638;transition:background .15s}button:hover{background:#303a57}button:disabled{opacity:.38;cursor:default}.primary{border-color:#6379dc;background:#495dc1}.primary:hover{background:#6479dc}.secondary{background:#191e2d}.danger{color:#ffbfc1;background:#322127;border-color:#63343f}.shell{display:grid;grid-template-columns:300px 1fr;min-height:100vh}.sidebar{display:flex;flex-direction:column;background:#131823;border-right:1px solid #30374b;padding:21px 17px;min-height:100vh}.brand{display:flex;align-items:center;gap:11px;margin-bottom:28px}.brand-mark{display:grid;place-items:center;width:44px;height:44px;color:#b7c8ff;font-size:28px;border:1px solid #4d5e85;border-radius:14px;background:#202d48}.brand strong{display:block;font-size:20px;letter-spacing:.3px}.brand small{display:block;font-size:11px;color:#9faec9;letter-spacing:.6px}.connect{border-radius:12px;padding:13px;background:#1b2233;border:1px solid #303d5a}.connect label,.composer label{font-size:12px;font-weight:650;color:#c8d0e6}.connect input{width:100%;margin:9px 0;padding:11px 10px;color:#f6f7fb;background:#101521;border:1px solid #35425c;border-radius:8px}.inline{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.inline button{flex:1}.hint,.minor{font-size:12px;color:#a4b1ce;line-height:1.5}.heading{display:flex;justify-content:space-between;align-items:center;margin-top:27px;margin-bottom:11px;font-size:12px;color:#aebdd9;text-transform:uppercase;letter-spacing:1px}.small{padding:5px 8px;text-transform:none;letter-spacing:0}.sessions{display:flex;flex-direction:column;gap:5px;overflow-y:auto;flex:1;min-height:100px;max-height:50vh}.session{width:100%;text-align:left;white-space:normal;padding:11px 9px;background:transparent;border-color:transparent;font-size:13px;overflow-wrap:anywhere}.session.active{background:#2a3654;border-color:#596b93}.session small{display:block;margin-top:4px;color:#9daacc;font-size:11px}.sidebar-footer{display:grid;gap:7px;padding-top:13px;border-top:1px solid #343d50}.import-label{display:block;padding:9px 12px;border:1px solid #343d50;border-radius:9px;background:#1b2231;text-align:center;cursor:pointer}.sidebar-footer input[type=file]{width:100%;font-size:10px;color:#a3b4d2;max-width:100%}.main{min-width:0;display:flex;flex-direction:column;min-height:100vh}.topbar{display:flex;justify-content:space-between;align-items:center;padding:24px 35px;border-bottom:1px solid #222b3c}.topbar h1{font-size:17px;margin:0;font-weight:650}.topbar p{font-size:12px;color:#a5b1ca;margin:5px 0 0}.indicator{font-size:10px;letter-spacing:1px;border:1px solid #46506c;background:#1c2638;padding:7px 11px;border-radius:25px;color:#9aabd2}.intro{margin:auto;max-width:520px;text-align:center;padding:40px}.intro .glow{font-size:48px;color:#9fafff}.intro h2{font-size:29px;letter-spacing:-1px;margin:10px}.intro p{color:#b5c0d9;line-height:1.6}.messages{width:100%;max-width:900px;margin:0 auto;flex:1;min-height:0;overflow-y:auto;padding:30px 28px;display:flex;flex-direction:column;gap:16px}.message{padding:16px 18px;border:1px solid #2f3952;border-radius:14px;max-width:90%;overflow-wrap:anywhere;white-space:pre-wrap;line-height:1.55;font-size:14px}.message.user{background:#24314a;align-self:flex-end;border-color:#405882}.message.assistant{background:#171e2c;align-self:flex-start}.message header{font-weight:700;color:#bacafa;font-size:11px;margin-bottom:8px;letter-spacing:.6px}.composer{width:calc(100% - 50px);max-width:870px;margin:0 auto;padding:15px;border-radius:15px;border:1px solid #35435e;background:#191f2e}.composer textarea{width:100%;resize:vertical;background:#0e1522;color:#f0f2fa;border:1px solid #35405b;border-radius:9px;margin-top:7px;padding:12px;min-height:68px}.composer .bottom{justify-content:space-between;margin-top:9px}.bottom button{flex:0}.bottom label{display:flex;gap:8px;align-items:center}.bottom input{width:64px;padding:5px;color:#fff;background:#0e1522;border:1px solid #35405b;border-radius:6px}.bottom span{color:#abb8d2;font-size:11px}.status{padding:13px 30px;min-height:42px;text-align:center;color:#abb7cc;font-size:12px}@media(max-width:720px){.shell{grid-template-columns:1fr}.sidebar{min-height:0;padding:13px}.brand{margin-bottom:13px}.sidebar-footer{display:flex;flex-wrap:wrap}.sidebar-footer button,.sidebar-footer label{flex:1}.sessions{max-height:140px}.topbar{padding:14px}.intro{padding:16px}.messages{padding:14px}.composer{width:calc(100% - 20px);margin:10px}.bottom span{display:none}}
.knowledge-section{border-top:1px solid #333b50;margin-top:12px;padding-top:8px;display:grid;gap:7px;font-size:12px;max-height:35vh;overflow:auto}
.knowledge-section label{color:#c2cbe2}.knowledge-section input[type=search]{width:100%;border:1px solid #35425c;border-radius:8px;padding:9px;background:#101521;color:#fff}.knowledge-section input[type=file]{width:100%;max-width:100%;font-size:10px;color:#a3b4d2}
.knowledge-documents,.knowledge-hits{display:grid;gap:7px}.knowledge-record,.knowledge-hit{border:1px solid #34415d;border-radius:8px;padding:8px;background:#1c2638;overflow-wrap:anywhere}
.knowledge-record{display:flex;align-items:center;justify-content:space-between;gap:4px}.knowledge-record button{flex-shrink:0;font-size:10px;padding:5px}.knowledge-hit strong{display:block;color:#b4c8ff}.knowledge-hit p{white-space:pre-wrap;color:#e0e8f8;max-height:190px;overflow:auto}.knowledge-hit small{color:#a7bcdb;overflow-wrap:anywhere}

.source-custody-label{display:block;margin-top:12px;color:#adc2e8;font-size:10px;font-weight:700}
.source-custody-item{white-space:pre-wrap;font-size:11px;margin-top:7px;color:#d0d9ed;background:#1e2d42;border:1px solid #344a68;border-radius:7px;padding:9px;max-height:180px;overflow:auto}
"""


JAVASCRIPT = r"""'use strict';
(() => {
  const get = id => document.getElementById(id);
  const state = {token: '', session: '', revision: 0, busy: false, connected: false,
                 pending: null};
  const status = message => {get('status').textContent = message;};
  const setBusy = busy => {
    state.busy = busy;
    ['send','new','fork','export','delete','connect','disconnect'].forEach(id => {
      get(id).disabled = busy;
    });
  };
  const showMessages = (messages, evidence = []) => {
    const list = get('messages');
    list.replaceChildren();
    get('intro').hidden = messages.length > 0;
    let completedTurn = 0;
    messages.forEach(message => {
      const card = document.createElement('article');
      card.className = 'message ' + (message.role === 'user' ? 'user' : 'assistant');
      const header = document.createElement('header');
      header.textContent = message.role === 'user' ? 'YOU' :
        message.role === 'system' ? 'SYSTEM INSTRUCTION' : 'LOCAL MODEL';
      const content = document.createElement('div');
      content.textContent = message.content;
      card.append(header, content);
      if (message.role === 'assistant') {
        const supplied = evidence[completedTurn++];
        if (supplied && Array.isArray(supplied.citations)) {
          const label = document.createElement('small');
          label.textContent = 'Evidence supplied to model; answer accuracy not verified';
          label.className = 'source-custody-label';
          card.appendChild(label);
          supplied.citations.forEach(item => {
            const note = document.createElement('div');
            note.className = 'source-custody-item';
            note.textContent = item.title + ' · ' + item.citation +
              '\nSource excerpt: ' + item.passage;
            card.appendChild(note);
          });
        }
      }
      list.appendChild(card);
    });
    list.scrollTop = list.scrollHeight;
  };
  async function api(method, path, data, exportBytes) {
    if (!state.token) throw new Error('Provide the local bearer token first.');
    const headers = {'Authorization': 'Bearer ' + state.token};
    if (data !== undefined) headers['Content-Type'] = 'application/json';
    const response = await fetch(path, {
      method, headers, cache: 'no-store', credentials: 'omit',
      body: data === undefined ? undefined : JSON.stringify(data)
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Local model request failed.');
    return result;
  }
  async function loadSessions() {
    const result = await api('GET', '/v1/sessions');
    const view = get('sessions');
    view.replaceChildren();
    result.sessions.forEach(item => {
      const button = document.createElement('button');
      button.className = 'session' + (item.session_id === state.session ? ' active' : '');
      const headline = document.createElement('span');
      headline.textContent = item.session_id.slice(0, 24);
      const small = document.createElement('small');
      small.textContent = item.revision + ' committed turns';
      button.append(headline, small);
      button.addEventListener('click', () => run(() => selectSession(item.session_id)));
      view.appendChild(button);
    });
  }
  async function selectSession(id) {
    const result = await api('GET', '/v1/sessions/' + encodeURIComponent(id));
    if (state.session !== result.session_id) state.pending = null;
    state.session = result.session_id;
    state.revision = result.revision;
    get('revision').textContent = 'Saved turns: ' + result.revision;
    showMessages(result.messages, result.evidence || []);
    await loadSessions();
    status('Loaded session ' + id.slice(0, 18) + '…');
  }
  async function run(work) {
    if (state.busy) return;
    setBusy(true);
    try {await work();} catch(error) {status(error.message || 'Local operation failed.');}
    finally {setBusy(false);}
  }
  async function loadDocuments() {
    const payload = await api('GET', '/v1/knowledge/documents');
    const view = get('knowledge-documents');
    view.replaceChildren();
    payload.documents.forEach(doc => {
      const row = document.createElement('div');
      row.className = 'knowledge-record';
      const label = document.createElement('span');
      label.textContent = doc.title + ' · ' + doc.sha256.slice(0, 9);
      const del = document.createElement('button');
      del.className = 'danger';
      del.textContent = 'Remove';
      del.addEventListener('click', () => run(async () => {
        if (!window.confirm('Delete this model-local reference?')) return;
        await api('DELETE', '/v1/knowledge/documents/' + doc.document_id);
        await loadDocuments();
        get('knowledge-hits').replaceChildren();
        status('Local reference deleted.');
      }));
      row.append(label, del);
      view.appendChild(row);
    });
  }
  get('knowledge-file').addEventListener('change', () => run(async () => {
    const control = get('knowledge-file');
    const file = control.files[0];
    if (!file) return;
    if (file.size > 65536 || file.size === 0) throw new Error('Text reference must be 1–65536 bytes.');
    const source = await file.text();
    if (new TextEncoder().encode(source).byteLength > 65536) {
      throw new Error('Text reference exceeds the 64 KiB upload limit.');
    }
    const result = await api('POST', '/v1/knowledge/documents', {
      title: file.name, text: source
    });
    control.value = '';
    await loadDocuments();
    status(result.reused ? 'Existing exact-byte reference reused.' :
      'New private reference indexed offline: ' + result.sha256.slice(0, 12));
  }));
  get('knowledge-search').addEventListener('click', () => run(async () => {
    const query = get('knowledge-query').value.trim();
    if (!query) throw new Error('Enter a reference search query.');
    const result = await api('POST', '/v1/knowledge/search', {query, limit: 6});
    const panel = get('knowledge-hits');
    panel.replaceChildren();
    result.hits.forEach(hit => {
      const card = document.createElement('article');
      card.className = 'knowledge-hit';
      const source = document.createElement('strong');
      source.textContent = hit.title;
      const passage = document.createElement('p');
      passage.textContent = hit.passage;
      const citation = document.createElement('small');
      citation.textContent = hit.citation;
      card.append(source, passage, citation);
      panel.appendChild(card);
    });
    status('Found ' + result.hits.length +
      ' locally indexed passage(s). Search is lexical; verify relevance.');
  }));
  get('knowledge-query').addEventListener('keydown', event => {
    if (event.key === 'Enter') {
      event.preventDefault(); get('knowledge-search').click();
    }
  });
  get('connect').addEventListener('click', () => run(async () => {
    state.token = get('secret').value.trim();
    if (state.token.length < 32) throw new Error('The local token is missing or invalid.');
    const health = await api('GET', '/v1/status');
    state.connected = true;
    get('secret').value = '';
    get('indicator').textContent = 'OFFLINE • CONNECTED';
    get('model').textContent = health.runtime_kind + ' · ' + health.model_digest.slice(0, 20) + '…';
    get('budget').value = String(health.default_output_tokens);
    await loadSessions();
    await loadDocuments();
    status('Authenticated locally. No remote provider is involved.');
  }));
  get('disconnect').addEventListener('click', () => {
    if (state.busy) return;
    state.token = ''; state.connected = false; state.session = '';
    state.pending = null;
    get('indicator').textContent = 'LOCKED';
    get('model').textContent = 'Not connected';
    get('secret').value = ''; get('sessions').replaceChildren(); showMessages([]);
    get('knowledge-documents').replaceChildren(); get('knowledge-hits').replaceChildren();
    status('Locked. The token and conversation data have not been stored in this browser.');
  });
  get('new').addEventListener('click', () => run(async () => {
    const item = await api('POST', '/v1/sessions', {});
    await selectSession(item.session_id);
  }));
  get('send').addEventListener('click', () => run(async () => {
    if (!state.session) throw new Error('Create or select a conversation first.');
    const prompt = get('prompt').value.trim();
    if (!prompt) throw new Error('Enter a message.');
    const budget = Number(get('budget').value);
    if (!Number.isInteger(budget) || budget < 1 || budget > 8192) {
      throw new Error('Output tokens must be 1–8192.');
    }
    // Preserve the EXACT request identity across an ambiguous network loss.
    // A response may have committed even when fetch() reports failure.
    // Changing the prompt, budget or session intentionally creates a new turn.
    const grounded = get('grounded').checked;
    const same = state.pending &&
      state.pending.session === state.session &&
      state.pending.prompt === prompt &&
      state.pending.budget === budget &&
      state.pending.grounded === grounded;
    if (!same) state.pending = {
      session: state.session, prompt, budget, grounded,
      id: crypto.randomUUID().replace(/-/g, '')
    };
    const attempted = state.pending;
    status('Running locally; repeat an unchanged prompt to safely recover a lost response…');
    try {
      await api('POST', '/v1/sessions/' + attempted.session + '/turn', {
        message: attempted.prompt, max_output_tokens: attempted.budget,
        request_id: attempted.id, grounded: attempted.grounded
      });
      state.pending = null;
      get('prompt').value = '';
      await selectSession(attempted.session);
    } catch (error) {
      status('Not confirmed. Retrying this unchanged prompt uses the same request ID.');
      throw error;
    }
  }));
  get('fork').addEventListener('click', () => run(async () => {
    if (!state.session) throw new Error('Select a conversation.');
    const item = await api('POST', '/v1/sessions/' + state.session + '/fork', {});
    await selectSession(item.session_id);
  }));
  get('delete').addEventListener('click', () => run(async () => {
    if (!state.session) throw new Error('Select a conversation.');
    if (!window.confirm('Permanently delete the selected conversation and receipts?')) return;
    await api('DELETE', '/v1/sessions/' + state.session);
    state.session = ''; get('revision').textContent = 'No conversation selected';
    showMessages([]); await loadSessions();
    status('Conversation deleted from the local database.');
  }));
  get('export').addEventListener('click', () => run(async () => {
    if (!state.session) throw new Error('Select a conversation.');
    const data = await api('GET', '/v1/sessions/' + state.session + '/export');
    const object = new Blob([JSON.stringify(data)], {type: 'application/json'});
    const url = URL.createObjectURL(object);
    const a = document.createElement('a'); a.href = url;
    a.download = 'skeleton-chat-' + state.session.slice(0, 12) + '.json';
    document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    status('Backup exported. It contains private plaintext conversation content.');
  }));
  get('import').addEventListener('change', () => run(async () => {
    const file = get('import').files[0];
    if (!file) return;
    if (file.size > 16 * 1024 * 1024) throw new Error('Backup exceeds 16MB.');
    const payload = JSON.parse(await file.text());
    const item = await api('POST', '/v1/sessions/import', payload);
    get('import').value = ''; await selectSession(item.session_id);
    status('Imported model-compatible conversation into a new local session.');
  }));
  get('prompt').addEventListener('keydown', event => {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
      event.preventDefault(); get('send').click();
    }
  });
})();"""


__all__ = ["HTML", "CSS", "JAVASCRIPT"]
