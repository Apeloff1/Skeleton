// Skeleton Local Studio: dependency-free ES module. No inline script (strict CSP),
// no innerHTML with data (all text goes through textContent), and the launch token
// stays in this tab's sessionStorage only.
const TOKEN_KEY = 'skeleton.studio.token';
const BRIEF_KEY = 'skeleton.studio.lastBrief';
const main = document.getElementById('main');
const banner = document.getElementById('banner');
const conn = document.getElementById('conn');
let token = null;
let routeSeq = 0;
let unsaved = false;

const EXAMPLES = [
  ['Platformer', 'A small platformer. Fantasy: a fox on rain-slick rooftops. Core loop: run and jump from roof to roof until the far gate. Scope: small prototype.'],
  ['Top-down shooter', 'A small top-down shooter. Fantasy: neon sewer drones. Core loop: move, aim and clear enemy packs, then spend salvage. Scope: small prototype.'],
  ['Roguelike RPG', 'A small roguelike RPG. Fantasy: a cinder delve that forgets dead explorers. Core loop: enter rooms, fight, pay the vendor and follow the quest hook. Scope: small prototype.'],
];

// ------------------------------------------------------------------ dom helpers
function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (value === undefined || value === null || value === false) continue;
    if (key === 'class') el.className = value;
    else if (key === 'text') el.textContent = value;
    else if (key.startsWith('on') && typeof value === 'function') el.addEventListener(key.slice(2), value);
    else el.setAttribute(key, value === true ? '' : String(value));
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return el;
}

function render(title, ...nodes) {
  document.title = `${title} · Skeleton Studio`;
  main.replaceChildren(...nodes);
  main.setAttribute('aria-busy', 'false');
  const heading = main.querySelector('h1');
  if (heading) { heading.setAttribute('tabindex', '-1'); heading.focus({ preventScroll: false }); }
}

function loading(title) {
  main.setAttribute('aria-busy', 'true');
  main.replaceChildren(h('h1', { text: title }), h('p', { class: 'visually-hidden', role: 'status', text: 'Loading…' }),
    h('div', { class: 'skeleton-line', 'aria-hidden': 'true' }), h('div', { class: 'skeleton-line', 'aria-hidden': 'true' }));
}

function showBanner(message, retry) {
  banner.replaceChildren(h('span', { text: message }), retry ? h('button', { class: 'btn', type: 'button', onclick: () => { hideBanner(); retry(); } }, 'Try again') : null);
  banner.hidden = false;
}
function hideBanner() { banner.hidden = true; banner.replaceChildren(); }

function relTime(seconds) {
  const date = new Date(Number(seconds) * 1000);
  return Number.isFinite(date.getTime()) ? date.toLocaleString() : '';
}

// ------------------------------------------------------------------ api
class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}

async function api(method, path, body) {
  const init = { method, headers: { 'x-skeleton-studio-token': token || '', accept: 'application/json' }, credentials: 'same-origin' };
  if (body !== undefined) { init.headers['content-type'] = 'application/json'; init.body = JSON.stringify(body); }
  let response;
  try { response = await fetch(`/studio/api${path}`, init); }
  catch { throw new ApiError(0, 'Skeleton is not reachable. Is it still running? Start it with: skeleton.cmd start'); }
  if (response.status === 401) { lock(); throw new ApiError(401, 'Studio link expired.'); }
  const type = response.headers.get('content-type') || '';
  if (!response.ok) {
    let detail = `Request failed (HTTP ${response.status}).`;
    if (type.includes('json')) { const data = await response.json().catch(() => ({})); detail = data.detail || data.error || detail; }
    throw new ApiError(response.status, String(detail));
  }
  return type.includes('json') ? response.json() : response.blob();
}

// ------------------------------------------------------------------ token
function readToken() {
  const match = /^#token=([A-Za-z0-9_-]{20,})$/.exec(location.hash);
  if (match) {
    sessionStorage.setItem(TOKEN_KEY, match[1]);
    history.replaceState(null, '', `${location.pathname}#/`);
  }
  token = sessionStorage.getItem(TOKEN_KEY);
}

function lock() {
  sessionStorage.removeItem(TOKEN_KEY);
  token = null;
  conn.textContent = 'Locked';
  render('Open Studio from Skeleton',
    h('h1', { text: 'Open Studio from Skeleton' }),
    h('div', { class: 'panel' },
      h('p', { text: 'For your security, Studio only works from the private link Skeleton creates each time it starts.' }),
      h('ol', {},
        h('li', {}, 'Open a terminal in your Skeleton folder.'),
        h('li', {}, 'Run ', h('code', { text: 'scripts\\windows\\skeleton.cmd studio' }), '.'),
        h('li', {}, 'Your browser opens Studio with a fresh link.'))));
}

// ------------------------------------------------------------------ views
async function homeView(seq) {
  loading('My games');
  const data = await api('GET', '/projects');
  if (seq !== routeSeq) return;
  const projects = data.projects || [];
  if (projects.length === 0) {
    render('Welcome',
      h('h1', { text: 'Welcome to Skeleton Studio' }),
      h('p', { class: 'lead', text: 'Describe a game in a sentence. Skeleton builds a real Godot project, plays it to prove the core loop works, and saves it on this computer.' }),
      h('section', { class: 'panel empty', 'aria-labelledby': 'first-steps' },
        h('h2', { id: 'first-steps', text: 'Your first game in three steps' }),
        h('ol', {},
          h('li', {}, 'Choose ', h('strong', { text: 'New game' }), ' and describe your idea.'),
          h('li', {}, 'Watch Skeleton build and playtest it.'),
          h('li', {}, 'Play it in Godot, tweak the scripts here, or download the project.')),
        h('p', {}, h('a', { class: 'btn primary', href: '#/new' }, 'Build your first game'))));
    return;
  }
  render('My games',
    h('h1', { text: 'My games' }),
    h('p', { class: 'lead', text: `${projects.length} game${projects.length === 1 ? '' : 's'} on this computer.` }),
    h('p', {}, h('a', { class: 'btn primary', href: '#/new' }, 'New game')),
    h('ul', { class: 'grid', 'aria-label': 'Games' }, projects.map(project => h('li', {},
      h('article', { class: 'panel card' },
        h('h3', {}, h('a', { class: 'stretch', href: `#/game/${encodeURIComponent(project.name)}` }, project.title || project.name)),
        h('p', { class: 'meta', text: [project.genre ? project.genre.replaceAll('_', ' ') : null, relTime(project.created)].filter(Boolean).join(' · ') }),
        project.proof ? h('p', {}, h('span', { class: 'pill ok', text: 'Core loop proven' })) : null,
        project.last_playtest ? h('p', { class: 'meta', text: `Last playtest: ${project.last_playtest.ok ? 'passed' : 'failed'}` }) : null)))));
}

async function newView(seq) {
  let status = null;
  try { status = await api('GET', '/status'); } catch (error) { if (error.status === 401) return; }
  if (seq !== routeSeq) return;
  const godot = Boolean(status && status.godot_ready);
  const error = h('p', { id: 'brief-error', class: 'field-error', hidden: true });
  const counter = h('p', { id: 'brief-count', class: 'hint', 'aria-live': 'polite' });
  const textarea = h('textarea', { id: 'brief', name: 'brief', maxlength: '2000', required: true,
    'aria-describedby': 'brief-hint brief-count', autocomplete: 'off', spellcheck: 'true' });
  textarea.value = sessionStorage.getItem(BRIEF_KEY) || '';
  const updateCount = () => { counter.textContent = `${textarea.value.length} / 2000 characters`; };
  textarea.addEventListener('input', () => { updateCount(); textarea.removeAttribute('aria-invalid'); error.hidden = true; });
  updateCount();
  const submit = h('button', { class: 'btn primary', type: 'submit' }, 'Build game');
  const radio = (value, label, hint, checked) => h('label', {},
    h('input', { type: 'radio', name: 'playtest', value, checked }), `${label}`, h('span', { class: 'visually-hidden', text: ` (${hint})` }));
  const form = h('form', { class: 'panel', novalidate: true, 'aria-labelledby': 'new-title' },
    h('label', { for: 'brief', text: 'Describe your game' }),
    h('p', { id: 'brief-hint', class: 'hint', text: 'Name the genre, the setting, what the player does again and again, and keep it small.' }),
    textarea, counter, error,
    h('h2', { id: 'examples', text: 'Or start from an example' }),
    h('ul', { class: 'examples', 'aria-labelledby': 'examples' }, EXAMPLES.map(([label, brief]) => h('li', {},
      h('button', { class: 'btn', type: 'button', onclick: () => { textarea.value = brief; updateCount(); textarea.focus(); } }, label)))),
    h('fieldset', {},
      h('legend', { text: 'Playtest before saving' }),
      h('div', { class: 'radio-row' },
        radio('require', 'Required', 'build fails unless the game plays', godot),
        radio('auto', 'If Godot is available', 'skips the playtest without Godot', !godot),
        radio('off', 'Skip', 'fastest, not proven', false)),
      godot ? null : h('p', { class: 'hint', text: 'Godot was not found, so a required playtest would fail. Re-run bootstrap to install it.' })),
    h('div', { class: 'actions' }, submit));
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const brief = textarea.value.trim();
    if (!brief) {
      textarea.setAttribute('aria-invalid', 'true');
      textarea.setAttribute('aria-errormessage', 'brief-error');
      error.textContent = 'Describe the game you want to build.';
      error.hidden = false;
      textarea.focus();
      return;
    }
    const playtest = form.querySelector('input[name="playtest"]:checked')?.value || 'auto';
    submit.disabled = true;
    submit.textContent = 'Starting…';
    try {
      sessionStorage.setItem(BRIEF_KEY, brief);
      const started = await api('POST', '/builds', { brief, playtest });
      location.hash = `#/build/${encodeURIComponent(started.build_id)}`;
    } catch (err) {
      submit.disabled = false;
      submit.textContent = 'Build game';
      if (err.status === 422) {
        textarea.setAttribute('aria-invalid', 'true');
        error.textContent = err.message; error.hidden = false; textarea.focus();
      } else if (err.status !== 401) showBanner(err.message, () => form.requestSubmit());
    }
  });
  render('New game', h('h1', { id: 'new-title', text: 'New game' }),
    h('p', { class: 'lead', text: 'Skeleton turns your description into a playable Godot project. Building usually takes under a minute.' }), form);
}

async function buildView(seq, buildId) {
  const bar = h('span', {});
  const progress = h('div', { class: 'progress', role: 'progressbar', 'aria-label': 'Build progress', 'aria-valuemin': '0', 'aria-valuemax': '100', 'aria-valuenow': '0' }, bar);
  const statusLine = h('p', { role: 'status', 'aria-live': 'polite', text: 'Queued…' });
  const log = h('ol', { class: 'log', 'aria-label': 'Build stages' });
  const outcome = h('div', {});
  render('Building', h('h1', { text: 'Building your game' }),
    h('p', { class: 'lead', text: 'Compiling the design, generating content, writing the Godot project and playtesting it.' }),
    h('section', { class: 'panel', 'aria-labelledby': 'progress-title' }, h('h2', { id: 'progress-title', class: 'visually-hidden', text: 'Progress' }), progress, statusLine, log), outcome);
  const seen = new Set();
  let delay = 700;
  while (seq === routeSeq) {
    let view;
    try { view = await api('GET', `/builds/${encodeURIComponent(buildId)}`); }
    catch (err) {
      if (err.status === 401 || seq !== routeSeq) return;
      if (err.status === 404) { outcome.replaceChildren(h('div', { class: 'panel', role: 'alert' }, h('p', { text: 'This build is not known to the running Skeleton (it may have restarted).' }), h('a', { class: 'btn', href: '#/new' }, 'Start a new build'))); return; }
      statusLine.textContent = `${err.message} Retrying…`;
      await new Promise(resolve => setTimeout(resolve, 2500));
      continue;
    }
    if (seq !== routeSeq) return;
    const pct = Math.round(Math.max(0, Math.min(1, view.progress || 0)) * 100);
    bar.style.width = `${pct}%`;
    progress.setAttribute('aria-valuenow', String(pct));
    if (view.message && !seen.has(view.message)) { seen.add(view.message); log.append(h('li', { text: view.message })); }
    statusLine.textContent = `${pct}% · ${view.message || view.status} · ${view.elapsed_s ?? 0}s`;
    if (view.status === 'succeeded') {
      sessionStorage.removeItem(BRIEF_KEY);
      statusLine.textContent = `Done in ${view.elapsed_s}s.`;
      const open = h('a', { class: 'btn primary', href: `#/game/${encodeURIComponent(view.project)}` }, `Open ${view.title || 'your game'}`);
      outcome.replaceChildren(h('section', { class: 'panel', 'aria-labelledby': 'done-title' },
        h('h2', { id: 'done-title', text: `${view.title || 'Your game'} is ready` }),
        h('dl', { class: 'kv' },
          h('dt', { text: 'Genre' }), h('dd', { text: (view.genre || '').replaceAll('_', ' ') || '—' }),
          h('dt', { text: 'Proof' }), h('dd', { text: view.proof || 'not playtested' }),
          h('dt', { text: 'Playtest' }), h('dd', { text: view.playtest || 'skipped' })),
        view.stubbed && view.stubbed.length ? h('p', { class: 'hint', text: `Not generated yet: ${view.stubbed.join('; ')}.` }) : null,
        h('div', { class: 'actions' }, open)));
      open.focus();
      return;
    }
    if (view.status === 'failed' || view.status === 'cancelled') {
      statusLine.textContent = 'The build did not finish.';
      outcome.replaceChildren(h('div', { class: 'panel', role: 'alert' },
        h('h2', { text: 'Build failed' }), h('p', { text: view.error || 'Unknown error.' }),
        h('p', { class: 'hint', text: 'Try a more specific description (genre, core loop, small scope), or check Settings.' }),
        h('div', { class: 'actions' }, h('a', { class: 'btn primary', href: '#/new' }, 'Edit and try again'), h('a', { class: 'btn', href: '#/settings' }, 'Settings'))));
      outcome.querySelector('h2').setAttribute('tabindex', '-1');
      outcome.querySelector('h2').focus();
      return;
    }
    await new Promise(resolve => setTimeout(resolve, delay));
    delay = Math.min(2000, delay + 150);
  }
}

async function gameView(seq, name) {
  loading('Game');
  const detail = await api('GET', `/projects/${encodeURIComponent(name)}`);
  if (seq !== routeSeq) return;
  const meta = detail.meta || {};
  const title = meta.title || name;
  const live = h('p', { role: 'status', 'aria-live': 'polite', class: 'hint' });
  const results = h('div', {});
  const editorLabel = h('label', { for: 'editor', text: 'Select a file to view or edit' });
  const editor = h('textarea', { id: 'editor', class: 'code', spellcheck: 'false', readonly: true, 'aria-describedby': 'editor-hint' });
  const save = h('button', { class: 'btn primary', type: 'button', disabled: true }, 'Save');
  let current = null; let dirty = false;
  const setDirty = value => { dirty = value; unsaved = value; save.disabled = !value || !current?.editable; };
  editor.addEventListener('input', () => setDirty(true));
  editor.addEventListener('keydown', event => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 's') { event.preventDefault(); if (!save.disabled) save.click(); }
    if (event.key === 'Tab' && !event.shiftKey && !editor.readOnly && event.altKey === false && event.ctrlKey === false && editor.dataset.tabs === 'on') {
      event.preventDefault(); editor.setRangeText('\t', editor.selectionStart, editor.selectionEnd, 'end'); setDirty(true);
    }
    if (event.key === 'Escape') { editor.dataset.tabs = 'off'; live.textContent = 'Tab key now moves focus. Press Ctrl+M to indent with Tab again.'; }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'm') { event.preventDefault(); editor.dataset.tabs = editor.dataset.tabs === 'on' ? 'off' : 'on'; live.textContent = editor.dataset.tabs === 'on' ? 'Tab inserts a tab character. Press Escape to leave the editor with Tab.' : 'Tab key moves focus.'; }
  });
  editor.dataset.tabs = 'off';
  const fileButtons = [];
  const openFile = async (file, button) => {
    if (dirty && !window.confirm('Discard unsaved changes?')) return;
    try {
      const data = await api('GET', `/projects/${encodeURIComponent(name)}/file?path=${encodeURIComponent(file.path)}`);
      current = { path: file.path, editable: data.editable };
      editor.value = data.content;
      editor.readOnly = !data.editable;
      editorLabel.textContent = `${data.editable ? 'Editing' : 'Viewing'} ${file.path}`;
      fileButtons.forEach(b => b.removeAttribute('aria-current'));
      button.setAttribute('aria-current', 'true');
      setDirty(false);
      editor.focus();
    } catch (err) { if (err.status !== 401) live.textContent = err.status === 415 ? `${file.path} is a binary file.` : err.message; }
  };
  save.addEventListener('click', async () => {
    if (!current) return;
    save.disabled = true;
    try {
      await api('PUT', `/projects/${encodeURIComponent(name)}/file`, { path: current.path, content: editor.value });
      setDirty(false); live.textContent = `Saved ${current.path}.`;
    } catch (err) { setDirty(true); if (err.status !== 401) live.textContent = `Not saved: ${err.message}`; }
  });
  const busy = async (button, label, work) => {
    const original = button.textContent; button.disabled = true; button.textContent = label;
    try { await work(); } catch (err) { if (err.status !== 401) live.textContent = err.message; }
    finally { button.disabled = false; button.textContent = original; }
  };
  const playBtn = h('button', { class: 'btn primary', type: 'button' }, 'Play in Godot');
  playBtn.addEventListener('click', () => busy(playBtn, 'Opening…', async () => {
    await api('POST', `/projects/${encodeURIComponent(name)}/open`); live.textContent = 'Godot is opening in a new window.';
  }));
  const testBtn = h('button', { class: 'btn', type: 'button' }, 'Run playtest');
  testBtn.addEventListener('click', () => busy(testBtn, 'Playtesting…', async () => {
    live.textContent = 'Playtesting headlessly…';
    const result = await api('POST', `/projects/${encodeURIComponent(name)}/playtest`);
    live.textContent = result.ok ? 'Playtest passed.' : 'Playtest failed.';
    results.replaceChildren(h('section', { class: 'panel', 'aria-labelledby': 'pt-title' },
      h('h2', { id: 'pt-title', text: `Playtest ${result.ok ? 'passed' : 'failed'}` }),
      h('ul', { class: 'steps' }, result.steps.map(step => h('li', {},
        h('span', { class: `pill ${step.ok ? 'ok' : 'bad'}`, text: step.ok ? 'pass' : 'fail' }), ' ',
        step.step.replaceAll('_', ' '), step.marker ? h('span', { class: 'meta', text: ` — ${step.marker.slice(0, 120)}` }) : null,
        step.skipped ? h('span', { class: 'meta', text: ` — ${step.skipped}` }) : null)))));
  }));
  const exportBtn = h('button', { class: 'btn', type: 'button' }, 'Download project (.zip)');
  exportBtn.addEventListener('click', () => busy(exportBtn, 'Preparing…', async () => {
    const blob = await api('GET', `/projects/${encodeURIComponent(name)}/export.zip`);
    const url = URL.createObjectURL(blob);
    const link = h('a', { href: url, download: `${name}.zip` });
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 10000);
    live.textContent = `Downloaded ${name}.zip.`;
  }));
  const files = detail.files || [];
  render(title,
    h('p', {}, h('a', { href: '#/' }, '← My games')),
    h('h1', { text: title }),
    h('p', { class: 'meta', text: [meta.genre ? meta.genre.replaceAll('_', ' ') : null, meta.created ? relTime(meta.created) : null].filter(Boolean).join(' · ') }),
    meta.proof ? h('p', {}, h('span', { class: 'pill ok', text: 'Core loop proven' }), ' ', h('span', { class: 'meta', text: meta.proof })) : null,
    meta.brief ? h('p', { class: 'lead', text: meta.brief }) : null,
    h('div', { class: 'actions' }, playBtn, testBtn, exportBtn), live, results,
    h('h2', { id: 'files-title', text: 'Project files' }),
    files.length === 0 ? h('p', { class: 'panel', text: 'This project has no files.' }) :
      h('div', { class: 'split' },
        h('nav', { class: 'panel', 'aria-labelledby': 'files-title' },
          h('ul', { class: 'files' }, files.map(file => {
            const button = h('button', { type: 'button', title: `${file.bytes} bytes${file.editable ? '' : ' (read-only)'}` }, file.path);
            button.addEventListener('click', () => openFile(file, button));
            fileButtons.push(button);
            return h('li', {}, button);
          }))),
        h('div', { class: 'panel' }, editorLabel, editor,
          h('p', { id: 'editor-hint', class: 'hint', text: 'Ctrl+S saves. Tab moves focus; press Ctrl+M to type tab characters, Escape to switch back.' }),
          h('div', { class: 'actions' }, save))));
}

async function settingsView(seq) {
  loading('Settings');
  const status = await api('GET', '/status');
  if (seq !== routeSeq) return;
  const checks = status.checks || {};
  const row = (id, label) => {
    const check = checks[id];
    if (!check) return [];
    return [h('dt', { text: label }), h('dd', {}, h('span', { class: `pill ${check.ok ? 'ok' : 'bad'}`, text: check.ok ? 'ready' : 'needs attention' }), ' ', check.detail,
      !check.ok && check.remediation ? h('p', { class: 'hint', text: check.remediation }) : null)];
  };
  render('Settings',
    h('h1', { text: 'Settings' }),
    h('p', { class: 'lead', text: 'Studio runs only on this computer. Change these with the Skeleton launcher in a terminal.' }),
    h('section', { class: 'panel', 'aria-labelledby': 'health-title' },
      h('h2', { id: 'health-title', text: 'Health' }),
      h('dl', { class: 'kv' },
        h('dt', { text: 'Skeleton API' }), h('dd', {}, h('span', { class: `pill ${status.api_healthy ? 'ok' : 'bad'}`, text: status.api_healthy ? 'healthy' : 'unreachable' })),
        ...row('godot', 'Godot engine'), ...row('python', 'Python'), ...row('skeleton_import', 'Skeleton install'),
        ...row('ai_provider', 'AI provider'), ...row('games_dir', 'Games folder'))),
    h('section', { class: 'panel', 'aria-labelledby': 'provider-title' },
      h('h2', { id: 'provider-title', text: 'Change the AI provider' }),
      h('p', { text: 'Games build without any model. To add a hosted model for design help:' }),
      h('pre', {}, h('code', { text: 'scripts\\windows\\skeleton.cmd config -Provider openai -Model gpt-5.5\nscripts\\windows\\skeleton.cmd stop\nscripts\\windows\\skeleton.cmd studio' })),
      h('p', { class: 'hint', text: 'Your key is asked for with hidden input and stored encrypted for your Windows account only.' })),
    h('section', { class: 'panel', 'aria-labelledby': 'files-title' },
      h('h2', { id: 'files-title', text: 'Where your games are' }),
      h('p', {}, h('code', { text: status.games_dir })),
      h('p', { class: 'hint', text: 'Each game is a normal Godot project. Open the folder with: skeleton.cmd games' })));
}

function notFound() {
  render('Not found', h('h1', { text: 'Page not found' }), h('p', {}, h('a', { class: 'btn', href: '#/' }, 'Back to my games')));
}

// ------------------------------------------------------------------ router
async function route() {
  const seq = ++routeSeq;
  unsaved = false;
  hideBanner();
  if (!token) { lock(); return; }
  const path = (location.hash || '#/').slice(1) || '/';
  const parts = path.split('/').filter(Boolean).map(decodeURIComponent);
  const navKey = parts[0] === 'new' || parts[0] === 'build' ? 'new' : parts[0] === 'settings' ? 'settings' : parts.length === 0 || parts[0] === 'game' ? 'home' : '';
  document.querySelectorAll('[data-nav]').forEach(link => {
    if (link.dataset.nav === navKey) link.setAttribute('aria-current', 'page'); else link.removeAttribute('aria-current');
  });
  const retry = () => route();
  try {
    if (parts.length === 0) await homeView(seq);
    else if (parts[0] === 'new' && parts.length === 1) await newView(seq);
    else if (parts[0] === 'build' && parts.length === 2) await buildView(seq, parts[1]);
    else if (parts[0] === 'game' && parts.length === 2) await gameView(seq, parts[1]);
    else if (parts[0] === 'settings' && parts.length === 1) await settingsView(seq);
    else notFound();
  } catch (err) {
    if (seq !== routeSeq || err.status === 401) return;
    if (err.status === 404) { render('Not found', h('h1', { text: 'Not found' }), h('p', { text: err.message }), h('p', {}, h('a', { class: 'btn', href: '#/' }, 'Back to my games'))); return; }
    main.setAttribute('aria-busy', 'false');
    showBanner(err.message || 'Something went wrong.', retry);
  }
}

async function heartbeat() {
  if (!token) return;
  try { const status = await api('GET', '/status'); conn.textContent = status.api_healthy ? 'Connected · local' : 'API unhealthy'; }
  catch (err) { if (err.status !== 401) conn.textContent = 'Disconnected'; }
}

window.addEventListener('hashchange', route);
window.addEventListener('beforeunload', event => { if (unsaved) event.preventDefault(); });
readToken();
document.getElementById('foot-api').textContent = location.host;
route();
heartbeat();
setInterval(heartbeat, 15000);
