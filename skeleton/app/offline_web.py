"""Static, dependency-free companion UI for authenticated localhost offline chat.

Kept as individual same-origin assets so strict CSP can forbid inline scripts,
remote fonts, external images, frames and cross-origin network connections.
No token, conversation or model data is persisted in browser storage.
"""
from __future__ import annotations


HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="dark">
<title>Jeeves · Local workspace</title>
<link rel="stylesheet" href="/app.css">
</head><body>
<div class="shell library-open" id="shell">
  <button id="sidebar-scrim" class="sidebar-scrim" aria-label="Close library and connection panel" tabindex="-1"></button>
  <aside class="sidebar" id="sidebar" aria-label="Connection, conversations and references">
    <div class="brand"><span class="brand-mark">◈</span>
      <div><strong>Jeeves</strong><small>Your private Skeleton workspace</small></div>
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
    <div class="session-views" aria-label="Conversation collection">
      <button id="session-view-active" class="small" aria-pressed="true">Active</button>
      <button id="session-view-archived" class="small" aria-pressed="false">Archived</button>
    </div>
    <label class="hint" for="session-query">Search conversation titles and text</label>
    <div class="inline"><input id="session-query" type="search" maxlength="256" placeholder="Search your conversations">
      <button id="session-search" class="small">Search</button></div>
    <div id="sessions" class="sessions" aria-label="Saved local conversations"></div>
    <button id="sessions-more" class="small" hidden>Load more conversations</button>
    <details class="instructions"><summary>New conversation instructions</summary>
      <label class="hint" for="system-prompt">Optional instructions for the next conversation</label>
      <textarea id="system-prompt" rows="4" maxlength="4096" placeholder="For example: help me build small, complete games."></textarea>
    </details>
    <details class="workspace-section" id="reference-library">
      <summary>Reference library <span>Import, select &amp; search</span></summary>
    <section class="knowledge-section" aria-label="Private local knowledge">
      <p class="hint">Search operator-supplied text offline. Passages are evidence, not AI-generated claims.</p>
      <label class="import-label" for="knowledge-file">Add a text / Markdown file</label>
      <input type="file" id="knowledge-file" multiple accept=".txt,.md,.py,.js,.ts,.json,.toml,.yaml,.yml,.csv,text/plain,text/markdown">
      <div id="knowledge-documents" class="knowledge-documents" aria-label="Imported references"></div>
      <p id="knowledge-scope-status" class="hint" role="status">Grounding scope: all saved references. Select up to 8 for an explicit local source restriction.</p>
      <button id="knowledge-scope-reset" class="small secondary" type="button">Explicitly use all references</button>
      <details id="media-advisory-panel">
        <summary>Review local image, audio or video for Jeeves (advisory only)</summary>
        <p class="hint">Only a locally selected file and your own human-reviewed observation are sent to the authenticated loopback service. The server checks the exact bytes and stores only the observation plus a SHA-256 provenance fingerprint. No OCR, transcription, video inference, remote provider, or raw media storage.</p>
        <label for="media-advisory-file">Local media source (max 4 MiB)</label>
        <input id="media-advisory-file" type="file" accept=".png,.jpg,.jpeg,.webp,.wav,.flac,.mp4">
        <pre id="media-advisory-fingerprint" aria-live="polite">No local media selected.</pre>
        <button id="media-advisory-preview" type="button" class="small" disabled>Preview locally (optional)</button>
        <div id="media-advisory-visual" hidden>
          <img id="media-advisory-image" alt="Selected local image preview" hidden>
          <audio id="media-advisory-audio" controls preload="none" hidden></audio>
          <video id="media-advisory-video" controls preload="none" hidden></video>
        </div>
        <label for="media-advisory-title">Reviewed local source title</label>
        <input id="media-advisory-title" type="text" maxlength="96" value="Local reviewed media" autocomplete="off">
        <label for="media-advisory-observation">Your own caption, transcript or frame annotation (no automatic analysis)</label>
        <textarea id="media-advisory-observation" rows="4" maxlength="12288" placeholder="Enter only what you personally reviewed. Treat media and annotations as untrusted data."></textarea>
        <label for="media-advisory-review" class="hint">
          <input id="media-advisory-review" type="checkbox">
          I reviewed this exact media and observation and approve importing the text only.
        </label>
        <button id="media-advisory-admit" type="button" class="secondary" disabled>Admit verified local media observation</button>
        <pre id="media-advisory-receipt" aria-live="polite">No media observation imported.</pre>
      </details>
      <details id="dragon-bundle-panel">
        <summary>Import approved Dragon evidence (local only)</summary>
        <p class="hint">Select a previously exported Dragon authorized-source bundle. Its source bodies are untrusted, and past capture rights do not prove present rights. No network crawl, hosted model or publication is performed here.</p>
        <label for="dragon-bundle-file">Choose historical authorized-source bundle (JSON, max 2 MiB)</label>
        <input id="dragon-bundle-file" type="file" accept=".json,application/json">
        <label for="dragon-bundle-source">Source excerpt to review</label>
        <select id="dragon-bundle-source" disabled><option value="">No verified bundle loaded</option></select>
        <label for="dragon-excerpt-start">Excerpt start (Unicode character offset)</label>
        <input id="dragon-excerpt-start" type="number" min="0" step="1" value="0">
        <label for="dragon-excerpt-length">Excerpt length (1–3000 Unicode characters)</label>
        <input id="dragon-excerpt-length" type="number" min="1" max="3000" step="1" value="1500">
        <pre id="dragon-bundle-preview" class="dragon-bundle-preview">Select a Dragon source bundle to review its exact text.</pre>
        <label for="dragon-bundle-review" class="hint">
          <input id="dragon-bundle-review" type="checkbox">
          I reviewed this exact untrusted text, and I independently rechecked that I may use it locally.
        </label>
        <button id="dragon-bundle-admit" class="secondary" disabled>Admit reviewed text to local advisory library</button>
        <pre id="dragon-bundle-receipt" aria-live="polite">Nothing imported.</pre>
      </details>
      <label for="knowledge-query">Search reference passages</label>
      <input id="knowledge-query" type="search" autocomplete="off"
             placeholder="A topic, symbol, API or exact phrase">
      <button id="knowledge-search" class="secondary">Search offline references</button>
      <div id="knowledge-hits" class="knowledge-hits" aria-live="polite"></div>
      <details class="advanced-reference"><summary>Governed reference operations</summary>
      <p class="hint">Prepare and approve exact writes, or run bounded reads and reference jobs.</p>
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
      </details>
    </section>
    </details>
    <details class="workspace-section" id="runtime-tools">
      <summary>Device &amp; advanced tools <span>Resources &amp; long-form work</span></summary>
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
        <label for="longform-import-id">Import receipt ID (copy to recover after disconnect)</label>
        <input id="longform-import-id" type="text" autocomplete="off" spellcheck="false">
        <button id="longform-import-restore" class="secondary" disabled>Recover committed import</button>
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
    </details>
    <details class="workspace-section" id="conversation-tools">
      <summary>Conversation tools <span>Branch, backup &amp; export</span></summary>
    <div class="sidebar-footer">
      <button id="fork" class="secondary">Fork conversation</button>
      <button id="export" class="secondary">Export backup</button>
      <button id="export-text" class="secondary">Export Markdown</button>
      <label class="import-label" for="import">Import backup</label>
      <input id="import" type="file" accept=".json,application/json">
      <button id="delete" class="danger">Delete selected</button>
    </div>
    </details>
  </aside>
  <main class="main" id="workspace-main">
    <header class="topbar">
      <button id="sidebar-toggle" class="small mobile-only" aria-controls="sidebar" aria-expanded="true">Library &amp; connection</button>
      <div class="conversation-heading"><span class="eyebrow" id="workspace-eyebrow">Jeeves / Local conversation</span><h1 id="conversation-title">A little space to think.</h1><h1 id="forge-workspace-title" hidden>Game builder</h1><p id="model">Not connected</p></div>
      <div id="indicator" class="indicator">LOCKED</div>
      <details class="model-tools"><summary>Model tools</summary><div>
      <div id="lease-indicator" class="indicator" role="status">Execution lock unknown</div>
      <button id="health-refresh" class="small" disabled>Check model</button>
      <button id="selftest-start" class="small" disabled>Run genuine local inference self-test</button>
      </div></details>
    </header>
    <nav class="workspace-nav" aria-label="Jeeves workspaces">
      <button id="chat-open" type="button" aria-pressed="true" aria-controls="chat-workspace">Conversation</button>
      <button id="forge-open" type="button" aria-pressed="false" aria-controls="forge-panel">Game builder <span>Local model · Godot source</span></button>
    </nav>
    <div id="chat-workspace" class="chat-workspace">
    <div class="conversation-toolbar" aria-label="Selected conversation controls">
      <span id="conversation-state" class="hint">Saved on this device</span>
      <span id="revision">No conversation selected</span>
      <div class="conversation-actions">
        <button id="session-title-open" class="small" disabled>Rename</button>
        <button id="session-pin" class="small" aria-pressed="false" disabled>Pin</button>
        <button id="session-archive" class="small" disabled>Archive</button>
      </div>
    </div>
    <section id="selftest-panel" class="selftest-panel" aria-label="Actual local model qualification" hidden>
      <strong>Local inference acceptance</strong>
      <p class="hint">This runs a real model-generated turn, verifies the saved SQLite answer and its execution receipt, and records measured elapsed time. It does not send a hosted model request or certify production language quality.</p>
      <pre id="selftest-result" aria-live="polite">No live qualification performed.</pre>
      <button id="selftest-export" class="small" disabled>Download nonsecret qualification receipt</button>
    </section>
    <div id="turn-progress" class="turn-progress" role="status" hidden>
      <span id="turn-label">Ready</span><span id="turn-elapsed"></span>
      <button id="check-turn" class="small">Check status</button>
      <button id="cancel-turn" class="danger small">Cancel generation</button>
    </div>
    <div class="intro" id="intro">
      <div class="glow">✧</div><h2>Good ideas start here.</h2>
      <p>A quiet place to ask, explore and build with your local model. Conversations and reference passages stay on this machine.</p>
      <div class="getting-started"><span><b>1</b> Connect to your local host</span><span><b>2</b> Start a conversation</span><span><b>3</b> Add references when useful</span></div>
      <p class="minor">An untrained native checkpoint will not produce useful assistant responses. For useful chat, use a qualified GGUF model with the local llama.cpp backend.</p>
    </div>
    <div id="messages" class="messages" role="log" aria-live="polite" aria-label="Conversation"></div>
    <div class="transcript-tools"><button id="copy-transcript" class="small">Copy conversation</button>
      <button id="refresh-session" class="small">Refresh saved history</button></div>
    <div class="composer">
      <label for="prompt">Message to local model</label>
      <textarea id="prompt" rows="3" placeholder="Enter a message..." maxlength="4096"></textarea>
      <details id="generation-options" class="generation-options"><summary>Context &amp; response settings</summary>
      <div class="inline bottom">
        <label for="grounded"><input id="grounded" type="checkbox"> Include local evidence</label>
        <label for="context-preserve"><input id="context-preserve" type="checkbox" checked> Require entire conversation context</label>
        <label for="budget">Output tokens <input id="budget" type="number" min="1" max="8192" value="32"></label>
      </div></details>
      <div class="composer-submit">
        <span class="hint keyboard-hint">Ctrl / ⌘ + Enter to send</span>
        <button id="context-preview" class="small" disabled>Preview context</button>
        <button id="send" class="primary">Generate locally ↗</button>
        <button id="retry-turn" class="secondary" hidden>Retry original turn</button>
      </div>
    </div>
    <div id="context-report" class="context-report" role="status" aria-live="polite">Context budget not checked. Full-history mode refuses generation rather than silently dropping older turns.</div>
    <details id="context-grounding-preview" class="grounding-preview" hidden>
      <summary>Local grounding passages selected by preview — untrusted text</summary>
      <p id="context-grounding-identity" class="hint"></p>
      <div id="context-grounding-citations" aria-live="polite"></div>
      <p class="hint">Preview only. Actual inference rechecks local sources and separately persists the committed citation receipt. This is not source-rights or factual verification.</p>
    </details>
    </div>
    <section id="forge-panel" class="forge-panel" aria-label="Local Jeeves native game builder" hidden>
      <div class="forge-page">
        <div class="forge-hero"><span class="eyebrow">FROM A SMALL IDEA TO A REAL PROJECT</span>
          <h2>Make your next playable idea.</h2>
          <p>Your local Jeeves model proposes a bounded design. The maintained Forge compiler builds it, and Godot checks actual input before a source project is offered.</p>
          <div class="forge-badges"><span>One local model</span><span>Original procedural games</span><span>Godot source ZIP</span></div>
        </div>
        <div id="forge-availability" class="forge-notice" role="status">Connect locally to inspect game-builder readiness.</div>
        <div class="forge-starters" aria-label="Game genre">
          <button id="forge-genre-shooter" class="forge-starter" type="button" aria-pressed="true"><span class="forge-glyph">◎</span><strong>Neon frontier</strong><small>Top-down shooter</small></button>
          <button id="forge-genre-platformer" class="forge-starter" type="button" aria-pressed="false"><span class="forge-glyph">↟</span><strong>Moonlit ascent</strong><small>Platformer</small></button>
          <button id="forge-genre-roguelike" class="forge-starter" type="button" aria-pressed="false"><span class="forge-glyph">◇</span><strong>Ember archive</strong><small>Roguelike RPG</small></button>
        </div>
        <form id="forge-form" class="forge-form">
          <div class="forge-section-heading"><span>01 / Your idea</span><span id="forge-budget">0 / 4,000 UTF-8 bytes</span></div>
          <label for="forge-brief">Describe the game you want to make</label>
          <textarea id="forge-brief" rows="4" maxlength="4000" placeholder="A small world, a clear challenge, and one satisfying thing to do.">Explore a quiet salvage station, avoid its sentinels, and recover the beacon.</textarea>
          <p class="hint">Your wording stays intact. The selected genre and explicit gameplay settings are included in the submitted brief.</p>
          <div class="forge-section-heading"><span>02 / Shape the experience</span></div>
          <div class="forge-fields">
            <label for="forge-difficulty">Difficulty<select id="forge-difficulty"><option value="easy">Easy · forgiving</option><option value="normal" selected>Normal · balanced</option><option value="hard">Hard · demanding</option></select></label>
            <label for="forge-theme">Visual theme<select id="forge-theme"><option value="moss">Moss</option><option value="neon" selected>Neon</option><option value="ember">Ember</option><option value="frost">Frost</option></select></label>
            <label for="forge-encounter">Encounter style<select id="forge-encounter"><option value="swarm">Swarm</option><option value="patrol" selected>Patrol</option><option value="ranged">Ranged</option></select></label>
            <label for="forge-speed">Player speed (120–360)<input id="forge-speed" type="number" min="120" max="360" step="1" value="230"></label>
          </div>
          <label for="forge-objective">Short objective shown in the game</label>
          <input id="forge-objective" type="text" maxlength="100" value="Recover the beacon" placeholder="A short HUD label; no periods or semicolons">
          <p class="hint">Use a single label of up to 100 characters, without periods or semicolons.</p>
          <details id="forge-review-panel" class="forge-review"><summary>Review the exact build brief</summary><pre id="forge-reviewed-brief"></pre></details>
          <div class="forge-submit-row"><button id="forge-review" class="secondary" type="button">Review brief</button><button id="forge-submit" class="primary" type="submit" disabled>Design, build &amp; verify ↗</button></div>
          <p class="hint">Creating a build runs local model inference and maintained Godot runtime checks. It does not start a browser game or launch an installed application.</p>
        </form>
        <section id="forge-current" class="forge-result" aria-label="Selected game build" hidden>
          <div class="forge-result-heading"><div><span class="eyebrow">BUILD OBSERVATION</span><h3 id="forge-result-title">Your game project</h3></div><button id="forge-check" type="button" class="small">Check original build</button></div>
          <code id="forge-current-id"></code>
          <p id="forge-status" role="status" aria-live="polite">No build selected.</p>
          <ol id="forge-progress" class="forge-progress" aria-label="Observed build stages"></ol>
          <div id="forge-proof" class="forge-proof"></div>
          <pre id="forge-controls" class="forge-controls" hidden></pre>
          <details class="forge-review"><summary>Source archive details</summary><p id="forge-archive-info" class="hint"></p></details>
          <button id="forge-download" class="primary" type="button" disabled>Download Godot source ZIP</button>
          <p class="hint">Extract the ZIP, open <code>project.godot</code> in Godot 4, and read <code>PLAY.md</code> for controls. Then play your project and judge its feel on your own device.</p>
        </section>
        <section class="forge-history" aria-label="Saved local game builds">
          <div class="forge-result-heading"><div><span class="eyebrow">CONTINUE YOUR WORK</span><h3>Local builds</h3></div><button id="forge-refresh" class="small" type="button" disabled>Refresh builds</button></div>
          <p class="hint">Reopen an original build to inspect its saved state. Reading a job never submits another model request.</p>
          <div id="forge-jobs" class="forge-jobs"><p class="hint">Connect to inspect saved builds.</p></div>
        </section>
      </div>
    </section>
    <div id="status" class="status" role="status">Paste the local access token to connect.</div>
    <dialog id="session-title-dialog" aria-labelledby="session-title-heading" aria-describedby="session-title-help">
      <form id="session-title-form">
        <span class="eyebrow">Conversation details</span>
        <h2 id="session-title-heading">Give this idea a name.</h2>
        <p id="session-title-help" class="hint">Use a short, recognizable title. Leave it blank to use the first message. Your conversation stays unchanged.</p>
        <label for="session-title-input">Conversation title</label>
        <input id="session-title-input" type="text" maxlength="100" autocomplete="off" placeholder="For example: Autumn launch ideas">
        <p id="session-title-error" class="form-error" role="alert"></p>
        <div class="dialog-actions"><button id="session-title-cancel" type="button" class="secondary">Cancel</button>
          <button id="session-title-save" type="submit" class="primary">Save title</button></div>
      </form>
    </dialog>
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
.knowledge-section select{width:100%;border:1px solid #35425c;border-radius:8px;padding:9px;background:#101521;color:#fff}.dragon-bundle-preview{white-space:pre-wrap;overflow-wrap:anywhere;max-height:220px;overflow:auto;background:#0b1321;padding:10px;border:1px solid #34415d;border-radius:7px}.knowledge-section #dragon-bundle-panel{display:grid;gap:9px}.knowledge-section #dragon-bundle-panel[open]{margin:10px 0}.knowledge-section #dragon-bundle-file{width:100%;max-width:100%}
.knowledge-section label{color:#c2cbe2}.knowledge-section input[type=search],.knowledge-section input[type=text],.knowledge-section textarea{width:100%;border:1px solid #35425c;border-radius:8px;padding:9px;background:#101521;color:#fff}.knowledge-section input[type=file]{width:100%;max-width:100%;font-size:10px;color:#a3b4d2}.knowledge-section textarea{min-height:64px;resize:vertical}
.knowledge-documents,.knowledge-hits{display:grid;gap:7px}.knowledge-record,.knowledge-hit{border:1px solid #34415d;border-radius:8px;padding:8px;background:#1c2638;overflow-wrap:anywhere}
.knowledge-record{display:flex;align-items:center;justify-content:space-between;gap:4px}
.knowledge-scope-label{display:flex;align-items:center;gap:4px;flex-shrink:0;font-size:11px;color:#b6caec}.knowledge-record button{flex-shrink:0;font-size:10px;padding:5px}.knowledge-hit strong{display:block;color:#b4c8ff}.knowledge-hit p{white-space:pre-wrap;color:#e0e8f8;max-height:190px;overflow:auto}.knowledge-hit small{color:#a7bcdb;overflow-wrap:anywhere}

.source-custody-label{display:block;margin-top:12px;color:#adc2e8;font-size:10px;font-weight:700}
.faithfulness{display:block;margin-top:8px;font-size:11px;font-weight:700}
.faithfulness.supported{color:#b7e3c2}.faithfulness.qualified{color:#f0d48a}
.faithfulness.abstain,.faithfulness.contested{color:#ffc1c4}
.source-custody-item{white-space:pre-wrap;font-size:11px;margin-top:7px;color:#d0d9ed;background:#1e2d42;border:1px solid #344a68;border-radius:7px;padding:9px;max-height:180px;overflow:auto}
[hidden]{display:none!important}.turn-progress{display:flex;align-items:center;gap:10px;flex-wrap:wrap;background:#1c2943;border-bottom:1px solid #35466b;padding:12px 24px;font-size:12px}.turn-progress #turn-label{flex:1}.transcript-tools{display:flex;gap:8px;justify-content:center;margin:8px}.message-actions{display:flex;gap:7px;margin-top:12px;white-space:normal}.instructions{margin:12px 0;color:#b8c9e9;font-size:12px}.instructions textarea{width:100%;margin-top:9px;color:#eff2fa;background:#101521;border:1px solid #35425c;border-radius:8px;padding:8px}.sidebar input[type=search]{min-width:0;flex:1;width:100%;color:#eef2fa;background:#101521;border:1px solid #35425c;border-radius:8px;padding:9px}.reference-name{text-align:left;padding:4px;border:0;background:transparent;font-size:11px;overflow-wrap:anywhere}.session small:last-child{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}dialog{width:min(850px,94vw);max-height:86vh;overflow:auto;background:#131d2d;color:#ebf1ff;border:1px solid #526a95;border-radius:14px;padding:22px}dialog::backdrop{background:#000a}dialog pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:55vh;overflow:auto;background:#0b1321;padding:15px;border-radius:9px}dialog .hint{overflow-wrap:anywhere}:focus-visible{outline:2px solid #a1c1ff;outline-offset:3px}

.context-report{font-size:12px;background:#18243a;border-top:1px solid #34415d;color:#c6ddf7;padding:8px 24px;overflow-wrap:anywhere}.context-report.warning{color:#ffd6a0;background:#302622}
.knowledge-section #knowledge-scope-status.warning{color:#ffd6a0;background:#302622;border-radius:6px;padding:7px}
.grounding-preview{margin:7px auto;padding:11px;max-width:860px;width:calc(100% - 48px);background:#14243a;border:1px solid #415572;border-radius:9px}.grounding-preview summary{cursor:pointer;font-size:13px;font-weight:650}.grounding-preview .grounding-passage{padding:11px;background:#0e1829;border-radius:7px;border:1px solid #31445e;margin-top:10px;overflow-wrap:anywhere}.grounding-preview .grounding-passage pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;max-height:240px;overflow:auto}.grounding-preview .grounding-passage code{font-size:11px;overflow-wrap:anywhere}
#media-advisory-visual img,#media-advisory-visual video{max-width:100%;max-height:300px;object-fit:contain}#media-advisory-visual audio{width:100%}#media-advisory-visual{max-height:340px;overflow:auto}#media-advisory-fingerprint,#media-advisory-receipt{white-space:pre-wrap;overflow-wrap:anywhere;font-size:11px}
.selftest-panel{margin:9px auto 4px;width:calc(100% - 50px);max-width:870px;padding:12px 15px;border:1px solid #344a68;border-radius:10px;background:#17253a;color:#d9e6fc;font-size:12px}.selftest-panel pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:180px;overflow:auto;color:#c8e8d6;font-size:12px}.selftest-panel button{width:auto}
.shell{height:100vh;height:100dvh;overflow:hidden}.sidebar{min-height:0;height:100%;overflow-y:auto}.main{height:100%;min-height:0}.messages{overscroll-behavior:contain}.intro{flex-shrink:1;overflow:auto}.mobile-only,.sidebar-scrim{display:none}.bottom input[type=checkbox]{width:auto}.turn-progress #turn-elapsed{font-variant-numeric:tabular-nums}.knowledge-record .reference-name{min-width:0;flex-shrink:1;flex:1}.brand #sidebar-close{margin-left:auto}
@media(max-width:720px){.shell{display:block;min-height:0}.sidebar{display:none}.main{height:100%}.topbar{flex-wrap:wrap;gap:8px}.topbar>div:first-of-type{flex:1;min-width:150px}.topbar h1{font-size:15px}.topbar p{overflow-wrap:anywhere}.mobile-only{display:inline-block}.library-open .sidebar{display:flex;position:fixed;top:0;bottom:0;left:0;width:min(350px,90vw);z-index:20;min-height:0;max-height:100dvh;overflow-y:auto;box-shadow:10px 0 40px #0007}.library-open .sidebar-scrim{display:block;position:fixed;inset:0;width:100%;height:100%;z-index:19;background:#0009;border:0;border-radius:0}.sidebar .sessions{flex:none;max-height:25vh}.sidebar .knowledge-section{flex:none;max-height:48vh}.sidebar .sidebar-footer{display:grid}.composer{flex-shrink:0;margin:0 auto;padding:10px}.composer textarea{min-height:50px;max-height:24vh}.composer .bottom{gap:6px}.turn-progress{padding:8px 12px}.status{padding:9px 12px}.messages{padding:12px;gap:10px}.message{max-width:97%}.intro h2{font-size:23px}.intro .glow{font-size:30px}.intro .minor{font-size:11px}.intro{padding:12px}.transcript-tools{margin:5px}}

:root{--canvas:#101219;--surface:#171b25;--line:#30384a;--text:#edf0f8;--muted:#acb8cf;--accent:#bbcdfb}
html,body{background:var(--canvas);color:var(--text)}button{font-size:12px;min-height:34px;border-radius:9px}button:hover:not(:disabled){border-color:#7184ac}.primary{background:#b8caf7;border-color:#b8caf7;color:#142443;font-weight:750}.primary:hover:not(:disabled){background:#d1ddfc;border-color:#d1ddfc}.secondary{background:#1b2130}.shell{grid-template-columns:320px minmax(0,1fr)}.sidebar{background:#141820;padding:24px 18px;gap:0;border-color:#29303f}.brand{margin-bottom:22px}.brand-mark{border-radius:50%;width:42px;height:42px;color:#d4e0fc;background:#26334c;border-color:#465d85;font-size:25px}.brand strong{font-size:22px;letter-spacing:-.7px}.brand small{letter-spacing:0;color:#aab7ce;font-size:11px}.connect{background:#1b2230;padding:12px;border-color:#354059}.connect .hint{margin:8px 0 0;font-size:11px}.connect input{padding:10px}.heading{margin-top:22px;margin-bottom:10px;letter-spacing:.9px;font-size:11px}.session-views{display:flex;gap:4px;background:#0f141e;padding:4px;border:1px solid #2d3648;border-radius:10px;margin-bottom:11px}.session-views button{flex:1;background:transparent;border-color:transparent;color:#b9c5da;min-height:30px}.session-views button[aria-pressed=true]{background:#2b3852;color:#eef2ff;border-color:#405578}.sessions{flex:1 0 140px;max-height:35vh;min-height:120px;margin:10px 0 2px}.session{padding:11px 12px;border-radius:10px;border:1px solid transparent;line-height:1.4}.session.active{background:#29364d;border-color:#455c83}.session .session-title{display:flex;gap:6px;align-items:baseline;font-size:13px;font-weight:650;color:#e7edf9}.session .pin-marker{color:#c6d6fb;font-size:11px}.session small{font-size:10px;color:#aab8ce;margin-top:5px}.session .session-preview{font-size:11px;color:#b4bfd1}.instructions{font-size:11px;margin:10px 0 12px}.workspace-section{flex-shrink:0;border-top:1px solid #2e3748;padding:14px 0;font-size:12px}.workspace-section>summary{cursor:pointer;font-weight:650;color:#d5def0;list-style-position:inside;padding:2px 0}.workspace-section>summary>span{display:block;font-size:10px;font-weight:400;color:#a5b3cb;margin:4px 0 0 14px}.workspace-section .knowledge-section{border:0;margin-top:14px;padding-top:0;max-height:none;overflow:visible}.workspace-section .knowledge-section>.heading{margin-top:0}.workspace-section .sidebar-footer{border:0;padding:14px 0 0}.workspace-section details{margin-top:8px}.workspace-section details>summary{cursor:pointer;line-height:1.5;color:#c2cfe8}.workspace-section details[open]>summary{margin-bottom:10px}.advanced-reference[open]{display:grid;gap:8px;padding-top:9px}.model-tools{position:relative;font-size:11px;flex-shrink:0}.model-tools>summary{cursor:pointer;padding:8px 10px;border:1px solid #39435a;border-radius:9px;color:#bac8e0;list-style-position:inside}.model-tools>div{position:absolute;right:0;top:calc(100% + 9px);z-index:8;width:260px;border:1px solid #485976;border-radius:12px;padding:14px;background:#1b2434;box-shadow:0 14px 30px #0007;display:grid;gap:9px}.model-tools .indicator{border-radius:7px;white-space:normal;line-height:1.5;text-align:center}.topbar{position:relative;gap:14px;padding:25px 34px 20px;border-color:#2b3241;align-items:center}.conversation-heading{min-width:0;flex:1}.eyebrow{display:block;text-transform:uppercase;letter-spacing:1.8px;font-size:9px;line-height:1.8;color:#a6b8d8;font-weight:650}.topbar h1{font-size:22px;font-weight:550;letter-spacing:-.6px;margin-top:4px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:100%}.topbar p{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:10px;line-height:1.5;color:#a9b7cd;margin-top:5px}.indicator{font-size:9px;letter-spacing:.8px;padding:7px 10px;border-color:#435272;white-space:nowrap}.conversation-toolbar{display:flex;flex-shrink:0;gap:10px;align-items:center;border-bottom:1px solid #252e3f;padding:9px 34px;font-size:10px;color:#aebbd1}.conversation-toolbar .hint{font-size:10px}.conversation-actions{display:flex;gap:5px;margin-left:auto}.conversation-actions button{background:transparent;font-size:10px;min-height:28px;padding:4px 8px}.conversation-actions button[aria-pressed=true]{background:#2e3e5c;color:#d8e5ff;border-color:#718cb7}.intro{max-width:680px;padding:40px 36px;margin:auto;text-align:left}.intro .glow{display:grid;place-items:center;width:62px;height:62px;border:1px solid #465a7d;border-radius:20px;background:radial-gradient(ellipse at top,#394e78,#1c2435);color:#d6e1ff;font-size:34px;margin-bottom:24px}.intro h2{font-size:clamp(27px,3vw,42px);line-height:1.15;font-family:Georgia,ui-serif,serif;font-weight:400;letter-spacing:-1.2px;margin:0 0 18px}.intro p{font-size:14px;line-height:1.8;color:#b2bfd5;margin:10px 0}.intro .minor{font-size:11px;border-top:1px solid #2e374b;padding-top:14px;margin-top:20px;color:#a1afc7;line-height:1.7}.getting-started{display:grid;gap:9px;margin:24px 0;color:#c2cde0;font-size:12px}.getting-started span{display:flex;align-items:center;gap:10px}.getting-started b{font-size:10px;font-weight:600;width:22px;height:22px;border:1px solid #4a5b77;border-radius:50%;display:inline-grid;place-items:center;color:#d2e0fb;background:#202b3f}.messages{padding:30px 34px;max-width:960px;gap:20px}.messages:empty{display:none}.message{border-radius:14px;max-width:92%;padding:18px 20px;font-size:14px}.message.user{background:#283852;border-color:#435c83}.message.assistant{background:#181e2a;border-color:#313e55}.message header{font-size:9px;letter-spacing:1.3px;color:#c4d5f7}.message-actions button{min-height:28px;font-size:10px;background:transparent}.transcript-tools{flex-shrink:0;margin:7px 0}.transcript-tools button{border-color:transparent;background:transparent;color:#b3c2dc;font-size:10px}.composer{flex-shrink:0;width:calc(100% - 68px);max-width:892px;padding:17px;background:#1b2230;border-color:#465575;border-radius:16px;box-shadow:0 8px 30px #0003}.composer>label{font-size:11px;color:#cad7ee}.composer textarea{border-color:#34445f;background:#111925;min-height:84px;max-height:28vh;line-height:1.6;font-size:14px;padding:12px;resize:vertical}.generation-options{font-size:10px;color:#b5c5df;margin-top:9px}.generation-options>summary{cursor:pointer;width:fit-content;padding:5px 0}.generation-options .bottom{gap:12px;padding:8px 0;border-top:1px solid #34435d}.generation-options label{font-size:10px}.composer-submit{display:flex;gap:8px;align-items:center;justify-content:flex-end;margin-top:9px;flex-wrap:wrap}.composer-submit .hint{font-size:10px;margin-right:auto}.composer-submit button{min-height:36px;font-size:11px}.context-report{background:transparent;border-color:transparent;font-size:10px;line-height:1.5;padding:8px 34px;color:#aabbd7}.status{flex-shrink:0;padding:8px 34px 14px;font-size:11px;color:#b8c6dc;line-height:1.5}.dialog-actions{display:flex;gap:8px;justify-content:flex-end;margin-top:18px}#session-title-dialog{max-width:470px}#session-title-dialog h2{font-family:Georgia,ui-serif,serif;font-size:27px;font-weight:400;margin:9px 0}#session-title-dialog label{display:block;font-size:12px;margin-top:20px}#session-title-input{display:block;width:100%;color:#f3f5fa;background:#0d1624;border:1px solid #526d96;border-radius:8px;font:inherit;padding:12px;margin-top:9px}.form-error{font-size:12px;color:#ffbcbf;min-height:1.5em}.session-empty{padding:14px 10px;line-height:1.7}.session-empty strong{display:block;color:#d5def0;font-size:12px;margin-bottom:5px}.session-empty p{font-size:11px;color:#aab9d1;margin:0}
@media(min-width:721px) and (max-width:1100px){.shell{grid-template-columns:285px minmax(0,1fr)}.sidebar{padding:20px 14px}.topbar{padding:21px 24px 17px;flex-wrap:wrap}.conversation-heading{flex-basis:100%}.conversation-toolbar{padding:9px 24px}.intro{padding:28px}.composer{width:calc(100% - 40px)}.keyboard-hint{display:none}}
@media(max-width:720px){.topbar{padding:13px 14px 10px;gap:9px}.topbar .conversation-heading{order:3;flex-basis:100%;min-width:0}.topbar h1{font-size:20px}.topbar p{font-size:9px}.topbar .indicator{margin-left:auto}.model-tools{font-size:10px}.model-tools>summary{padding:7px 8px}.model-tools .indicator{margin-left:0}.model-tools>div{right:0;width:min(260px,82vw)}.conversation-toolbar{padding:7px 12px;gap:6px;flex-wrap:wrap}.conversation-toolbar #revision{font-size:9px}.conversation-toolbar .hint{font-size:9px}.conversation-actions{gap:3px}.conversation-actions button{min-height:30px;padding:5px 7px;font-size:10px}.intro{padding:20px 22px;overflow:auto}.intro .glow{width:43px;height:43px;border-radius:14px;font-size:27px;margin-bottom:17px}.intro h2{font-size:28px;margin-bottom:12px}.intro p{font-size:12px;line-height:1.7}.intro .minor{font-size:10px;margin-top:14px;padding-top:10px}.getting-started{margin:14px 0;gap:7px;font-size:11px}.getting-started b{width:19px;height:19px}.composer{width:calc(100% - 20px);padding:11px;border-radius:12px}.composer textarea{min-height:62px;max-height:22vh;padding:10px;font-size:13px}.composer-submit{gap:6px;margin-top:6px}.composer-submit .keyboard-hint{display:none}.composer-submit button{font-size:11px;min-height:34px}.generation-options{margin-top:5px}.generation-options .bottom{gap:10px}.generation-options label{font-size:10px}.context-report{padding:6px 12px;font-size:9px;max-height:44px;overflow:auto}.status{padding:6px 12px 9px;font-size:10px;max-height:56px;overflow:auto}.messages{padding:16px 12px;gap:14px}.message{padding:14px;max-width:97%;font-size:13px}.transcript-tools{margin:2px}.sidebar{padding:18px 15px}.sidebar .sessions{max-height:29vh;min-height:120px}.sidebar .knowledge-section{max-height:none}.workspace-section{padding:13px 0}.brand{margin-bottom:17px}.brand #sidebar-close{min-height:32px}.shell.library-open .main{pointer-events:none}.sidebar-close:focus-visible{outline-offset:2px}}
#forge-genre-shooter .forge-glyph{color:#a4d9f5}#forge-genre-platformer .forge-glyph{color:#c9b8ff}#forge-genre-roguelike .forge-glyph{color:#efc58c}#forge-genre-shooter[aria-pressed=true]{border-color:#8fcee8;background:linear-gradient(150deg,#22384d,#1b293b)}#forge-genre-platformer[aria-pressed=true]{border-color:#b6a0e9;background:linear-gradient(150deg,#342b4a,#222439)}#forge-genre-roguelike[aria-pressed=true]{border-color:#d5b17b;background:linear-gradient(150deg,#3b3029,#272734)}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;transition:none!important}}
.workspace-nav{display:flex;flex-shrink:0;gap:8px;padding:10px 34px;border-bottom:1px solid #30394c;background:#131923}.workspace-nav button{background:transparent;border-color:transparent;color:#afbed8;text-align:left;padding:8px 13px;min-height:40px}.workspace-nav button[aria-pressed=true]{color:#e8efff;background:#2a3852;border-color:#52688f}.workspace-nav button span{display:block;font-size:9px;color:#b3c4df;margin-top:3px}.chat-workspace{display:flex;flex:1;flex-direction:column;min-height:0;overflow:hidden}.forge-panel{flex:1;min-height:0;overflow:auto;overscroll-behavior:contain;padding:28px 34px}.forge-page{max-width:960px;margin:0 auto;padding-bottom:30px}.forge-hero h2{font-family:Georgia,ui-serif,serif;font-weight:400;font-size:36px;letter-spacing:-.8px;line-height:1.2;margin:13px 0 14px}.forge-hero p{font-size:13px;line-height:1.8;color:#b7c6df;max-width:700px}.forge-badges{display:flex;gap:7px;flex-wrap:wrap;margin:18px 0 22px}.forge-badges span{font-size:10px;color:#c8d8f2;border:1px solid #445a7c;border-radius:20px;padding:6px 9px;background:#1b293d}.forge-notice{border:1px solid #3d516e;background:#1c2b40;color:#d0dff5;padding:12px 14px;line-height:1.6;font-size:12px;border-radius:10px;margin:16px 0}.forge-notice.warning{border-color:#80623e;background:#30281e;color:#efd7b6}.forge-starters{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin:20px 0}.forge-starter{text-align:left;min-height:140px;padding:17px;background:#192335;border:1px solid #3a4a65;border-radius:13px}.forge-starter[aria-pressed=true]{background:#283750;border-color:#9db5df}.forge-glyph{display:block;color:#c2d4f5;font-size:31px;line-height:1.3;margin-bottom:14px}.forge-starter strong{display:block;font-size:14px;font-weight:650;color:#ebf1ff}.forge-starter small{display:block;margin-top:6px;font-size:11px;color:#b5c5df}.forge-form,.forge-result,.forge-history{background:#171f2d;border:1px solid #35465f;border-radius:14px;padding:20px;margin:17px 0}.forge-form label{display:block;color:#c6d6ef;font-size:12px;line-height:1.6;margin-top:12px}.forge-form input,.forge-form textarea,.forge-form select{display:block;width:100%;color:#f0f4fc;background:#101927;border:1px solid #4b6082;border-radius:8px;padding:11px;margin-top:7px;min-height:42px;font-size:13px}.forge-form textarea{resize:vertical;min-height:110px;line-height:1.6}.forge-form .hint{font-size:11px;line-height:1.6}.forge-section-heading{display:flex;justify-content:space-between;gap:12px;color:#c7d7f1;font-size:10px;letter-spacing:.5px;font-weight:650;margin:9px 0 13px}.forge-section-heading:not(:first-child){border-top:1px solid #35445b;padding-top:21px;margin-top:22px}.forge-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:0 17px}.forge-review{margin:18px 0;padding:12px;border:1px solid #3c5274;border-radius:9px;background:#142337;font-size:12px;color:#ccdffb}.forge-review summary{cursor:pointer}.forge-review pre,.forge-controls{white-space:pre-wrap;overflow-wrap:anywhere;font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:11px;line-height:1.8;color:#c3d4ef;max-height:250px;overflow:auto;margin:13px 0 0}.forge-submit-row{display:flex;justify-content:flex-end;gap:9px;flex-wrap:wrap;margin:20px 0 12px}.forge-submit-row button{min-height:43px}.forge-result-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}.forge-result h3,.forge-history h3{font-size:19px;line-height:1.4;margin:7px 0 12px;letter-spacing:-.3px}.forge-result code{font-size:10px;overflow-wrap:anywhere;color:#a7bedf}#forge-status{font-size:13px;line-height:1.7;color:#d8e5fa;margin:18px 0}.forge-progress{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));list-style:none;padding:0;margin:18px 0;gap:7px}.forge-progress li{border-top:2px solid #465570;padding-top:9px;color:#a7b7d1;font-size:10px;line-height:1.5}.forge-progress li.observed{border-color:#b2c9f1;color:#dfebff}.forge-progress li.current{border-color:#9ed8bd;color:#c8edda}.forge-proof{display:grid;gap:9px;margin:20px 0}.forge-proof-row{display:flex;justify-content:space-between;gap:13px;flex-wrap:wrap;font-size:11px;line-height:1.6;border-bottom:1px solid #2f4058;padding-bottom:8px}.forge-proof-row span:first-child{color:#b2c5e1}.forge-proof-row span:last-child{color:#dce9fc}.forge-controls{max-height:200px;padding:12px;border:1px solid #3d5678;border-radius:8px;background:#111d2d}.forge-result #forge-download{margin:9px 0;min-height:43px}.forge-jobs{display:grid;gap:8px;margin-top:17px}.forge-job{display:flex;justify-content:space-between;align-items:center;gap:12px;text-align:left;background:#1c2a40;border:1px solid #3e5577;border-radius:9px;padding:12px}.forge-job strong{display:block;font-size:12px;color:#d9e7ff;overflow-wrap:anywhere}.forge-job small{display:block;color:#a8bfdf;font-size:10px;margin-top:5px;line-height:1.6}.forge-job>span:last-child{color:#cbdcfa;font-size:11px;white-space:nowrap}.forge-result .hint{font-size:11px;line-height:1.7;overflow-wrap:anywhere}.forge-form input:disabled,.forge-form select:disabled,.forge-form textarea:disabled{opacity:.55}.forge-history .hint{font-size:11px}.forge-form #forge-budget.warning{color:#ffd1ac}
@media(max-width:720px){.workspace-nav{padding:8px 12px;gap:6px}.workspace-nav button{min-height:39px;padding:7px 11px;font-size:11px}.workspace-nav button span{font-size:8px}.forge-panel{padding:22px 13px}.forge-hero h2{font-size:30px;margin-top:11px}.forge-hero p{font-size:12px}.forge-badges{gap:5px}.forge-badges span{font-size:9px;padding:5px 8px}.forge-notice{font-size:11px}.forge-starters{gap:6px}.forge-starter{padding:12px 9px;min-height:135px}.forge-glyph{font-size:27px;margin-bottom:13px}.forge-starter strong{font-size:11px;line-height:1.5}.forge-starter small{font-size:9px;line-height:1.5}.forge-form,.forge-result,.forge-history{padding:15px 12px}.forge-fields{gap:0 10px}.forge-form label{font-size:11px}.forge-form input,.forge-form select{font-size:12px;padding:9px}.forge-submit-row{justify-content:stretch}.forge-submit-row button{flex:1;font-size:11px}.forge-result h3,.forge-history h3{font-size:17px}.forge-progress{gap:5px}.forge-progress li{font-size:9px}.forge-result-heading{align-items:flex-start}.forge-result-heading .small{font-size:10px}.forge-section-heading{font-size:9px}.forge-job{gap:9px;padding:11px 9px}.forge-job strong{font-size:11px}.forge-proof-row{font-size:10px}}

"""


JAVASCRIPT = r"""'use strict';
(() => {
  const get = id => document.getElementById(id);
  const bytes = value => new TextEncoder().encode(value).byteLength;
  const state = {
    token: '', connected: false, busy: false, epoch: 0,
    session: '', revision: 0, messages: [], evidence: [], audits: [], faithfulness: [],
    sessions: [], cursor: null, query: '', drafts: new Map(), showArchived: false,
    sessionMetadata: null, titleEditSession: '', titleEditRevision: 0,
    pending: null, turn: null, timer: null, polling: false,
    writePending: null, writeRequest: '',
    selfTest: null, selfTestReport: null,
    mediaAdvisoryFile: null, mediaAdvisoryDigest: '', mediaAdvisoryType: '',
    mediaAdvisoryUrl: '',
    dragonBundle: [], dragonBundleSession: '', dragonExcerpt: null,
    selectedKnowledgeIds: new Set(), availableKnowledgeIds: new Set(),
    knowledgeScopeMode: 'all', knowledgeScopeVersion: 0, knowledgeListRequest: 0,
    pollStarted: 0, pollErrors: 0, health: null, reference: null,
    network: new AbortController(), resourceTimer: null, longformSourceId: null,
    longformWork: null, longformPendingRequest: null,
    longformImportPending: null,
    workspace: 'chat', forgeGenre: 'shooter', forgeJob: null, forgeRequest: null,
    forgeJobs: [], forgeAvailability: null, forgeLimits: null,
    forgeTimer: null, forgePolling: false, forgePollStarted: 0, forgePollErrors: 0,
  };
  function nativeGameBrief(fields) {
    const genres = {shooter: 'A small top-down shooter.', platformer: 'A small platformer.', roguelike: 'A small roguelike RPG.'};
    if (!fields || !Object.hasOwn(genres, fields.genre) ||
        !['easy', 'normal', 'hard'].includes(fields.difficulty) ||
        !['moss', 'neon', 'ember', 'frost'].includes(fields.theme) ||
        !['swarm', 'patrol', 'ranged'].includes(fields.encounter)) {
      throw new Error('Choose valid game settings.');
    }
    if (typeof fields.brief !== 'string' || !fields.brief.trim() ||
        /[\u0000-\u0008\u000b-\u001f\u007f\ud800-\udfff]/u.test(fields.brief)) {
      throw new Error('Enter a valid game idea.');
    }
    const objective = fields.objective;
    if (typeof objective !== 'string' || !objective.trim() || Array.from(objective).length > 100 ||
        objective !== objective.trim() || /[.;\u0000-\u001f\u007f\u2028\u2029\ud800-\udfff]/u.test(objective)) {
      throw new Error('Use a short objective of up to 100 characters, without periods, semicolons or line breaks.');
    }
    if (typeof fields.speed !== 'string' || !/^[0-9]{3}$/.test(fields.speed) ||
        Number(fields.speed) < 120 || Number(fields.speed) > 360) {
      throw new Error('Player speed must be a whole number from 120 to 360.');
    }
    // The compiler collapses whitespace, so every explicit label needs its
    // own period boundary. The creator's original text remains an exact tail.
    const brief = genres[fields.genre] + ' Scope: small prototype. ' +
      'Difficulty: ' + fields.difficulty + '. Theme: ' + fields.theme +
      '. Objective: ' + objective + '. Player speed: ' + fields.speed +
      '. Encounter style: ' + fields.encounter + '.\n\nCreator brief:\n' + fields.brief;
    if (new TextEncoder().encode(brief).byteLength > 4000) throw new Error('The complete game brief exceeds 4,000 UTF-8 bytes. Shorten your idea or objective.');
    return brief;
  }
  function forgeFields() {
    return {genre: state.forgeGenre, brief: get('forge-brief').value,
      difficulty: get('forge-difficulty').value, theme: get('forge-theme').value,
      encounter: get('forge-encounter').value, speed: get('forge-speed').value,
      objective: get('forge-objective').value};
  }
  function forgeDraftChanged() {
    try {
      const brief = nativeGameBrief(forgeFields());
      get('forge-budget').textContent = bytes(brief) + ' / 4,000 UTF-8 bytes';
      get('forge-budget').classList.remove('warning');
      get('forge-reviewed-brief').textContent = brief;
    } catch (error) {
      get('forge-budget').textContent = 'Check idea and settings';
      get('forge-budget').classList.add('warning');
      get('forge-reviewed-brief').textContent = error.message;
    }
  }
  function workspace(mode) {
    state.workspace = mode === 'forge' ? 'forge' : 'chat';
    const forge = state.workspace === 'forge';
    get('forge-panel').hidden = !forge; get('chat-workspace').hidden = forge;
    get('conversation-title').hidden = forge; get('forge-workspace-title').hidden = !forge;
    get('workspace-eyebrow').textContent = forge ? 'Jeeves / Native game builder' : 'Jeeves / Local conversation';
    get('chat-open').setAttribute('aria-pressed', String(!forge));
    get('forge-open').setAttribute('aria-pressed', String(forge));
  }
  function forgeActive() {
    return !!state.forgeJob && state.forgeJob.terminal !== true;
  }
  function checkedForgeJob(value, expectedId) {
    if (!value || typeof value !== 'object' || Array.isArray(value) ||
        typeof value.request_id !== 'string' || !/^[A-Za-z0-9_-]{1,128}$/.test(value.request_id) ||
        (expectedId && value.request_id !== expectedId) ||
        !['queued', 'planning', 'building', 'verifying', 'complete', 'failed'].includes(value.state) ||
        typeof value.terminal !== 'boolean' ||
        value.terminal !== ['complete', 'failed'].includes(value.state) ||
        typeof value.brief_sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(value.brief_sha256)) {
      throw new Error('The game build returned an invalid identity or state. Check the original request.');
    }
    return value;
  }
  function forgeArchiveReady(job, modelDigest) {
    const result = job?.result; const build = result?.build; const archive = job?.archive;
    return !!job && job.state === 'complete' && job.terminal === true &&
      result?.ok === true && result.planning?.status === 'accepted' &&
      typeof modelDigest === 'string' && result.planning.model_digest === modelDigest &&
      build?.ok === true && build.interactive?.native_boot_verified === true &&
      build.interactive?.input_journey_verified === true && !!archive &&
      typeof archive.sha256 === 'string' && /^[a-f0-9]{64}$/.test(archive.sha256) &&
      Number.isSafeInteger(archive.bytes) && archive.bytes > 0 && archive.bytes <= 16777216 &&
      Number.isSafeInteger(archive.file_count) && archive.file_count > 0 && archive.file_count <= 512;
  }
  function renderForgeJob() {
    const job = state.forgeJob;
    get('forge-current').hidden = !job;
    if (!job) return;
    const spec = job.result?.build?.spec;
    get('forge-result-title').textContent = typeof spec?.title === 'string' ? spec.title.slice(0, 140) : 'Your game project';
    get('forge-current-id').textContent = job.request_id;
    const labels = {queued: 'Queued for the local builder.', planning: 'Jeeves is proposing a bounded game design on this machine.',
      building: 'The Forge compiler is creating the Godot source project.', verifying: 'Godot is checking the native input journey.',
      complete: 'Source project published. Its verification evidence is shown below.', failed: 'The build stopped without a downloadable project.',
      unknown: 'Delivery is uncertain. Check this original request; no second model request has been submitted.'};
    const failure = job.error && typeof job.error.message === 'string' ? ' ' + job.error.message.slice(0, 240) : '';
    get('forge-status').textContent = (labels[job.state] || 'Build state unavailable.') + failure;
    const progress = get('forge-progress'); progress.replaceChildren();
    const stages = [['queued', 'Queued'], ['planning', 'Local design'], ['building', 'Compile source'], ['verifying', 'Native input proof']];
    const at = job.state === 'complete' ? stages.length : stages.findIndex(row => row[0] === job.state);
    stages.forEach(([id, label], index) => {
      const row = document.createElement('li'); row.textContent = label;
      if (index < at) row.classList.add('observed');
      if (id === job.state) {row.classList.add('current'); row.setAttribute('aria-current', 'step');}
      progress.append(row);
    });
    const proof = get('forge-proof'); proof.replaceChildren();
    const planning = job.result?.planning; const interactive = job.result?.build?.interactive;
    const rows = [
      ['Local model design', planning?.status === 'accepted' ? 'Accepted by the design guard' : planning ? 'Not accepted' : 'Awaiting recorded result'],
      ['Native engine boot', interactive?.native_boot_verified === true ? 'Verified' : 'Not recorded'],
      ['Native input journey', interactive?.input_journey_verified === true ? 'Verified' : 'Not recorded'],
    ];
    rows.forEach(([label, value]) => {
      const row = document.createElement('div'); row.className = 'forge-proof-row';
      const name = document.createElement('span'); name.textContent = label;
      const observed = document.createElement('span'); observed.textContent = value;
      row.append(name, observed); proof.append(row);
    });
    const controls = interactive?.controls;
    get('forge-controls').hidden = !controls;
    get('forge-controls').textContent = controls ? Object.entries(controls).slice(0, 8)
      .filter(([, value]) => typeof value === 'string').map(([key, value]) => key + ': ' + value.slice(0, 240)).join('\n') : '';
    get('forge-archive-info').textContent = job.archive ?
      job.archive.file_count + ' source files · ' + job.archive.bytes + ' archive bytes\nSHA-256: ' + job.archive.sha256 :
      'A source ZIP becomes available only after model admission and native input verification both succeed.';
    updateControls();
  }
  function renderForgeJobs() {
    const list = get('forge-jobs'); list.replaceChildren();
    if (!state.forgeJobs.length) {
      const empty = document.createElement('p'); empty.className = 'hint';
      empty.textContent = 'No local builds yet. Start with one small, complete idea above.'; list.append(empty);
    }
    state.forgeJobs.slice(0, 20).forEach(job => {
      const button = document.createElement('button'); button.type = 'button'; button.className = 'forge-job';
      button.id = 'forge-resume-' + job.request_id;
      button.disabled = !state.connected || state.busy || state.forgePolling;
      const text = document.createElement('span');
      const title = document.createElement('strong');
      const spec = job.result?.build?.spec;
      title.textContent = typeof spec?.title === 'string' ? spec.title.slice(0, 100) : job.request_id;
      const detail = document.createElement('small'); detail.textContent = job.state + ' · original saved request';
      text.append(title, detail);
      const action = document.createElement('span'); action.textContent = job.terminal ? 'Open →' : 'Resume checks →';
      button.append(text, action);
      button.addEventListener('click', () => run(async () => {
        stopForgePolling(); state.forgeRequest = null;
        state.forgeJob = checkedForgeJob(await api('GET', '/v1/game-builds/' + job.request_id), job.request_id);
        renderForgeJob(); state.forgePollStarted = performance.now(); state.forgePollErrors = 0;
        if (forgeActive()) scheduleForgePoll(100);
        get('forge-current').scrollIntoView({block: 'start'});
      }));
      list.append(button);
    });
  }
  async function refreshForge() {
    if (!state.connected) return;
    const result = await api('GET', '/v1/game-builds');
    if (!result || !Array.isArray(result.jobs) || result.jobs.length > 128 ||
        typeof result.availability?.ready !== 'boolean') throw new Error('The local builder status could not be verified.');
    state.forgeJobs = result.jobs.map(job => checkedForgeJob(job));
    state.forgeAvailability = result.availability; state.forgeLimits = result.limits;
    const availability = get('forge-availability');
    availability.classList.toggle('warning', !result.availability.ready);
    availability.textContent = result.availability.ready ?
      'Local builder available. A new build requires an accepted Jeeves design and actual Godot input proof.' :
      'New builds are unavailable (' + String(result.availability.code || 'unknown').slice(0, 90) + '). Your draft is preserved. Refresh builds after the local model or engine recovers.';
    renderForgeJobs(); updateControls();
  }
  function stopForgePolling() {
    if (state.forgeTimer !== null) clearTimeout(state.forgeTimer);
    state.forgeTimer = null;
  }
  function scheduleForgePoll(delay = 1400) {
    stopForgePolling();
    if (state.connected && forgeActive()) state.forgeTimer = setTimeout(() => void pollForge(), delay);
  }
  async function pollForge() {
    if (!state.connected || !state.forgeJob || state.forgePolling) return;
    const epoch = state.epoch; const id = state.forgeJob.request_id;
    state.forgePolling = true; updateControls();
    try {
      const job = checkedForgeJob(await api('GET', '/v1/game-builds/' + id), id);
      if (state.forgeJob?.request_id !== id || epoch !== state.epoch) return;
      if (state.forgeRequest?.request_id === id && state.forgeRequest.brief_sha256 !== job.brief_sha256) throw new Error('The saved build brief differs from the original request.');
      state.forgeJob = job; state.forgePollErrors = 0; renderForgeJob();
      if (job.terminal) {
        stopForgePolling();
        status(job.state === 'complete' ? 'Local source project completed. Review its recorded proof before downloading.' : 'The local build stopped. Its original result remains available.');
        try {await refreshForge();} catch {if (epoch === state.epoch) status('The original build result was read, but the build list could not be refreshed.');}
      } else if (performance.now() - state.forgePollStarted > 10 * 60 * 1000) {
        status('Automatic build observation paused. Check the original build to continue; no new generation was submitted.');
      } else scheduleForgePoll();
    } catch (error) {
      if (epoch !== state.epoch) return;
      state.forgePollErrors++;
      if (error.status === 404) {
        state.forgeJob = {...state.forgeJob, state: 'failed', terminal: true,
          error: {code: 'job_not_found', message: 'No saved job exists for this request. Refresh builds before explicitly creating a new one.'}};
        renderForgeJob(); stopForgePolling();
      }
      status('Build observation is unavailable. Keep the original request ID and check it again. ' + error.message);
      if (state.forgePollErrors < 5 && error.status !== 404) scheduleForgePoll(Math.min(8000, 1000 * 2 ** state.forgePollErrors));
    } finally {if (epoch === state.epoch) {state.forgePolling = false; updateControls();}}
  }
  async function submitForge() {
    if (!state.connected || forgeActive()) throw new Error('Finish observing the original build before starting another.');
    const epoch = state.epoch;
    const brief = nativeGameBrief(forgeFields());
    await refreshForge();
    if (epoch !== state.epoch || !state.connected) return;
    if (!state.forgeAvailability?.ready) throw new Error('The local builder is unavailable. Your idea and settings are preserved.');
    const request = Object.freeze({request_id: 'g_' + crypto.randomUUID().replace(/-/g, ''), brief,
      brief_sha256: await exactLocalSha256(brief)});
    if (epoch !== state.epoch) return;
    stopForgePolling(); state.forgeRequest = request;
    state.forgeJob = {request_id: request.request_id, brief_sha256: request.brief_sha256, state: 'unknown', terminal: false};
    state.forgePollStarted = performance.now(); state.forgePollErrors = 0; renderForgeJob();
    try {
      const job = checkedForgeJob(await api('POST', '/v1/game-builds', {request_id: request.request_id, brief}), request.request_id);
      if (job.brief_sha256 !== request.brief_sha256) throw new Error('The saved build brief differs from the submitted request.');
      state.forgeJob = job; renderForgeJob();
      status('Original build submitted. You may edit the next idea; this request keeps its admitted brief.');
    } catch (error) {
      if (epoch !== state.epoch) return;
      // A lost acknowledgement is not permission to submit another model run.
      status('Build delivery is uncertain. Use Check original build to read this request without generating again. ' + error.message);
    }
    if (epoch === state.epoch) scheduleForgePoll(200);
  }
  async function readBoundedForgeArchive(response, maximum, signal) {
    if (!response.ok || response.redirected ||
        (response.headers.get('Content-Type') || '').split(';')[0].trim().toLowerCase() !== 'application/zip' ||
        !Number.isSafeInteger(maximum) || maximum < 1 || maximum > 16777216) throw new Error('The verified source ZIP is unavailable. Check the original build.');
    const declared = response.headers.get('Content-Length');
    if (declared !== null && (!/^[0-9]{1,9}$/.test(declared) || Number(declared) < 1 || Number(declared) > maximum)) throw new Error('Source ZIP exceeds its download budget.');
    if (!response.body || typeof response.body.getReader !== 'function') throw new Error('This browser cannot read a bounded source download.');
    const reader = response.body.getReader(); const chunks = []; let total = 0;
    const abort = () => {void reader.cancel().catch(() => {});};
    signal.addEventListener('abort', abort, {once: true});
    try {
      while (true) {
        if (signal.aborted) throw new Error('Source download cancelled.');
        const {done, value} = await reader.read();
        if (signal.aborted) throw new Error('Source download cancelled.');
        if (done) break;
        if (!(value instanceof Uint8Array)) throw new Error('Source ZIP returned invalid bytes.');
        total += value.byteLength;
        if (total > maximum) throw new Error('Source ZIP exceeds its download budget.');
        chunks.push(value);
      }
      if (!total || declared !== null && total !== Number(declared)) throw new Error('Source ZIP length could not be verified.');
      const bytes = new Uint8Array(total); let offset = 0;
      for (const chunk of chunks) {bytes.set(chunk, offset); offset += chunk.byteLength;}
      return bytes;
    } finally {
      signal.removeEventListener('abort', abort);
      try {await reader.cancel();} catch { /* Cancellation must not expose response bytes. */ }
      reader.releaseLock();
    }
  }
  async function downloadForge() {
    if (!state.connected || !state.forgeJob) throw new Error('Open a completed local build first.');
    const epoch = state.epoch; const id = state.forgeJob.request_id;
    const job = checkedForgeJob(await api('GET', '/v1/game-builds/' + id), id);
    if (!forgeArchiveReady(job, state.health?.model_digest)) throw new Error('This source project has no complete model and native input proof.');
    state.forgeJob = job; renderForgeJob();
    const network = state.network; const controller = new AbortController();
    const abort = () => controller.abort(); network.signal.addEventListener('abort', abort, {once: true});
    const timer = setTimeout(abort, 15000);
    try {
      const response = await fetch('/v1/game-builds/' + id + '/archive', {
        method: 'GET', headers: {Authorization: 'Bearer ' + state.token},
        cache: 'no-store', credentials: 'omit', redirect: 'error', signal: controller.signal,
      });
      const content = await readBoundedForgeArchive(response, 16777216, controller.signal);
      const digest = await localMediaSha256(content);
      if (epoch !== state.epoch || !state.connected || state.forgeJob?.request_id !== id || controller.signal.aborted) return;
      if (content.byteLength !== job.archive.bytes || digest !== job.archive.sha256) throw new Error('Source ZIP digest differs from the saved artifact. No download was offered.');
      download(content, 'jeeves-game-' + id + '.zip', 'application/zip');
      status('Verified Godot source ZIP downloaded. Extract it and read PLAY.md.');
    } finally {clearTimeout(timer); network.signal.removeEventListener('abort', abort);}
  }
  function clearForge() {
    stopForgePolling();
    Object.assign(state, {forgeJob: null, forgeRequest: null, forgeJobs: [], forgeAvailability: null,
      forgeLimits: null, forgePolling: false, forgePollStarted: 0, forgePollErrors: 0, forgeGenre: 'shooter'});
    get('forge-brief').value = ''; get('forge-objective').value = '';
    get('forge-difficulty').value = 'normal'; get('forge-theme').value = 'neon';
    get('forge-encounter').value = 'patrol'; get('forge-speed').value = '230';
    get('forge-reviewed-brief').textContent = ''; get('forge-review-panel').open = false;
    get('forge-current').hidden = true;
    for (const id of ['forge-current-id', 'forge-result-title', 'forge-status', 'forge-archive-info', 'forge-controls']) get(id).textContent = '';
    get('forge-proof').replaceChildren(); get('forge-progress').replaceChildren(); get('forge-jobs').replaceChildren();
    get('forge-availability').textContent = 'Connect locally to inspect game-builder readiness.';
    for (const genre of ['shooter', 'platformer', 'roguelike']) get('forge-genre-' + genre).setAttribute('aria-pressed', String(genre === 'shooter'));
    forgeDraftChanged(); workspace('chat');
  }
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
  async function refreshHealth() {
    if (!state.connected || !state.token) return;
    const epoch = state.epoch;
    const previous = state.health;
    try {
      const observed = await api('GET', '/v1/status');
      if (epoch !== state.epoch || !state.connected) return;
      state.health = observed;
      const ownership = observed.inference_lease?.state;
      get('lease-indicator').textContent =
        ownership === 'busy' ? 'LOCAL • ANOTHER EXECUTOR IS ACTIVE' :
        ownership === 'unavailable' ? 'LOCAL • EXECUTION LOCK UNSAFE' :
        ownership === 'idle' ? 'LOCAL • EXECUTION SLOT IDLE' :
        ownership === 'uninitialized' ? 'LOCAL • FIRST EXECUTION NOT YET RUN' :
        'LOCAL • OWNERSHIP UNKNOWN';
      get('budget').max = String(observed.max_output_tokens);
      if (Number(get('budget').value) > observed.max_output_tokens) {
        get('budget').value = String(observed.default_output_tokens);
      }
      if (previous?.ready !== observed.ready ||
          previous?.model_readiness_code !== observed.model_readiness_code) {
        if (observed.ready === true) {
          status('Jeeves local runtime is admitting new inference. Readiness is not an executed completion.');
        } else if (observed.model_readiness_code === 'local_execution_circuit_open') {
          const retry = observed.inference_circuit?.retry_after_seconds;
          status('Local runtime failures paused new inference' +
            (Number.isInteger(retry) ? ' for approximately ' + retry + ' seconds.' : '.') +
            ' Saved conversations and exact retries remain accessible.');
        } else {
          status('Local model unavailable (' +
            (observed.model_readiness_code || 'unknown') +
            '). Check the local artifacts and host; no hosted fallback will be used.');
        }
      }
    } catch (error) {
      if (epoch !== state.epoch || !state.connected) return;
      state.health = {...(previous || {}), ready: false,
        model_readiness_code: 'local_status_unreachable'};
      if (previous?.model_readiness_code !== 'local_status_unreachable') {
        status('Local model health could not be checked. New inference is disabled; history remains available when the host returns.');
      }
    } finally {
      if (epoch === state.epoch) updateControls();
    }
  }
  function sidebar(open, restoreFocus = false) {
    get('shell').classList.toggle('library-open', open);
    get('sidebar-toggle').setAttribute('aria-expanded', String(open));
    const mobile = window.matchMedia('(max-width:720px)').matches;
    get('workspace-main').inert = mobile && open;
    get('sidebar').setAttribute('role', mobile ? 'dialog' : 'complementary');
    if (mobile && open) get('sidebar').setAttribute('aria-modal', 'true');
    else get('sidebar').removeAttribute('aria-modal');
    if (mobile && open) get('sidebar-close').focus();
    if (restoreFocus && window.matchMedia('(max-width:720px)').matches) get('sidebar-toggle').focus();
  }
  function clearSearch() {state.query = ''; get('session-query').value = '';}

  function showSessionMetadata(item) {
    state.sessionMetadata = {
      title: typeof item.title === 'string' ? item.title : 'New conversation',
      custom_title: typeof item.custom_title === 'string' ? item.custom_title : '',
      pinned: item.pinned === true, archived: item.archived === true,
      metadata_revision: Number.isSafeInteger(item.metadata_revision) ? item.metadata_revision : 0,
    };
    const meta = state.sessionMetadata;
    get('conversation-title').textContent = meta.title || 'New conversation';
    get('conversation-state').textContent = meta.archived ? 'Archived · still available locally' :
      meta.pinned ? 'Pinned · saved on this device' : 'Saved on this device';
    get('session-pin').textContent = meta.pinned ? 'Unpin' : 'Pin';
    get('session-pin').setAttribute('aria-pressed', String(meta.pinned));
    get('session-archive').textContent = meta.archived ? 'Restore to active' : 'Archive';
  }
  function showCollection() {
    get('session-view-active').setAttribute('aria-pressed', String(!state.showArchived));
    get('session-view-archived').setAttribute('aria-pressed', String(state.showArchived));
  }
  function clearSessionMetadata() {
    state.sessionMetadata = null;
    get('conversation-title').textContent = 'A little space to think.';
    get('conversation-state').textContent = 'Saved on this device';
    get('session-pin').textContent = 'Pin';
    get('session-pin').setAttribute('aria-pressed', 'false');
    get('session-archive').textContent = 'Archive';
  }
  async function updateSessionMetadata(changes, expectedRevision) {
    if (!state.session || !state.sessionMetadata) throw new Error('Select a conversation first.');
    const epoch = state.epoch;
    const id = state.session;
    const result = await api('POST', '/v1/sessions/' + id + '/metadata', {
      ...changes, expected_metadata_revision: expectedRevision ?? state.sessionMetadata.metadata_revision,
    });
    if (state.session !== id || result.session_id !== id) throw new Error('The selected conversation changed. Refresh before editing.');
    showSessionMetadata(result);
    state.showArchived = result.archived === true;
    showCollection();
    try {await loadSessions(); return true;}
    catch (error) {
      if (epoch !== state.epoch) throw error;
      // The POST already committed. A failed list projection must not make
      // a title editor retry its own saved metadata with an obsolete CAS.
      return false;
    }
  }
  function organizationStatus(message, refreshed) {
    status(message + (refreshed ? '' : ' The saved conversation list could not be refreshed. Choose Search to retry.'));
  }

  function updateControls() {
    const locked = !state.connected;
    const working = state.busy || state.polling || unresolved() || forgeActive();
    const foreignLease = ['busy', 'unavailable'].includes(state.health?.inference_lease?.state);
    ['new', 'fork', 'delete', 'import', 'system-prompt', 'session-search', 'sessions-more',
      'session-view-active', 'session-view-archived'].forEach(id => {
      get(id).disabled = locked || working;
    });
    ['session-title-open', 'session-pin', 'session-archive'].forEach(id => {
      get(id).disabled = locked || working || !state.session || !state.sessionMetadata;
    });
    get('session-title-save').disabled = locked || working || !state.titleEditSession;
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
    get('send').disabled = locked || working || foreignLease || !state.session || state.health?.ready !== true;
    const scopeBlocked = get('grounded').checked && state.knowledgeScopeMode === 'selected' &&
      (state.selectedKnowledgeIds.size === 0 ||
        [...state.selectedKnowledgeIds].some(id => !state.availableKnowledgeIds.has(id)));
    if (scopeBlocked) get('send').disabled = true;
    get('context-preview').disabled = locked || working || !state.session || scopeBlocked;
    get('knowledge-scope-reset').disabled = locked || working;
    document.querySelectorAll('.knowledge-scope-picker').forEach(node => {
      node.disabled = locked || working;
    });
    get('context-preserve').disabled = locked || working;
    get('connect').disabled = state.busy || state.connected;
    ['forge-brief', 'forge-difficulty', 'forge-theme', 'forge-encounter', 'forge-speed', 'forge-objective',
      'forge-genre-shooter', 'forge-genre-platformer', 'forge-genre-roguelike', 'forge-review'].forEach(id => {
      get(id).disabled = locked || state.busy;
    });
    get('forge-submit').disabled = locked || working || foreignLease || state.forgePolling ||
      state.forgeAvailability?.ready !== true || state.health?.ready !== true;
    get('forge-refresh').disabled = locked || state.busy;
    get('forge-check').disabled = locked || state.busy || state.forgePolling || !state.forgeJob;
    get('forge-download').disabled = locked || state.busy || !forgeArchiveReady(state.forgeJob, state.health?.model_digest);
    document.querySelectorAll('.forge-job').forEach(button => {button.disabled = locked || state.busy || state.forgePolling;});
    get('health-refresh').disabled = locked || state.busy;
    get('selftest-start').disabled = locked || working || foreignLease || state.health?.ready !== true;
    get('selftest-export').disabled = locked || !state.selfTestReport;
    for (const id of ['media-advisory-file', 'media-advisory-title',
                      'media-advisory-observation', 'media-advisory-review']) {
      get(id).disabled = locked || state.busy;
    }
    get('media-advisory-preview').disabled = locked || state.busy || !state.mediaAdvisoryFile;
    get('media-advisory-admit').disabled = locked || state.busy ||
      !state.mediaAdvisoryFile || !state.mediaAdvisoryDigest ||
      !get('media-advisory-review').checked;
    get('dragon-bundle-source').disabled = locked || state.busy || !state.dragonBundle.length;
    get('dragon-excerpt-start').disabled = locked || state.busy || !state.dragonBundle.length;
    get('dragon-excerpt-length').disabled = locked || state.busy || !state.dragonBundle.length;
    get('dragon-bundle-file').disabled = locked || state.busy;
    get('dragon-bundle-review').disabled = locked || state.busy || !state.dragonExcerpt;
    get('dragon-bundle-admit').disabled = locked || state.busy ||
      !state.dragonExcerpt || !get('dragon-bundle-review').checked;
    get('disconnect').disabled = !state.connected && !state.token;
    get('resource-refresh').disabled = locked;
    get('resource-plan').disabled = locked;
    get('longform-ingest').disabled = locked || state.busy;
    get('longform-import-restore').disabled = locked || state.busy;
    get('longform-query').disabled = locked || state.busy || !state.longformSourceId;
    get('longform-work-start').disabled = locked || state.busy || !state.longformSourceId;
    get('longform-work-resume').disabled = locked || state.busy;
    get('longform-work-next').disabled = locked || state.busy || !state.longformWork;
    const progress = !!state.turn && !terminal(state.turn);
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
    get('indicator').textContent = locked ? 'LOCKED' : unresolved() ? 'LOCAL • RUNNING' :
      foreignLease ? 'LOCAL • EXECUTOR BUSY' :
      state.health?.ready === true ? 'LOCAL • READY' : 'LOCAL • DEGRADED';
  }
  function stopPolling() {
    if (state.timer !== null) clearTimeout(state.timer);
    state.timer = null;
  }
  function lock() {
    if (state.resourceTimer !== null) clearInterval(state.resourceTimer);
    state.resourceTimer = null;
    get('resource-monitor').textContent = 'Connect to inspect your device.';
    get('lease-indicator').textContent = 'Execution lock unknown';
    get('resource-plan-result').textContent = 'No workload planned.';
    get('longform-status').textContent = 'No staged source.';
    get('longform-work-status').textContent = 'No active work cursor.';
    get('longform-work-id').value = '';
    state.selfTest = null; state.selfTestReport = null;
    clearMediaAdvisory(true);
    state.dragonBundle = []; state.dragonBundleSession = ''; state.dragonExcerpt = null;
    get('dragon-bundle-file').value = '';
    get('dragon-bundle-source').replaceChildren();
    get('dragon-bundle-preview').textContent = 'Select a Dragon source bundle to review its exact text.';
    get('dragon-bundle-receipt').textContent = 'Nothing imported.';
    get('dragon-bundle-review').checked = false;
    state.selectedKnowledgeIds.clear(); state.availableKnowledgeIds.clear();
    state.knowledgeScopeMode = 'all'; state.knowledgeScopeVersion++;
    state.knowledgeListRequest++;
    get('knowledge-documents').replaceChildren();
    get('knowledge-scope-status').textContent = 'Grounding scope: all saved references.';
    get('selftest-panel').hidden = true;
    get('selftest-result').textContent = 'No live qualification performed.';
    get('context-report').classList.remove('warning');
    get('context-report').textContent = 'Context not checked. Full-history mode refuses any silent trimming.';
    clearGroundingPreview();
    get('context-preserve').checked = true;
    state.longformSourceId = null;
    state.longformWork = null;
    state.longformPendingRequest = null;
    state.longformImportPending = null;
    get('longform-import-id').value = '';
    const hadWork = unresolved();
    stopPolling();
    state.epoch++;
    state.network.abort();
    state.network = new AbortController();
    Object.assign(state, {token: '', connected: false, busy: false, session: '', revision: 0,
      messages: [], evidence: [], audits: [], faithfulness: [], sessions: [], cursor: null, query: '',
      pending: null, turn: null, polling: false, reference: null, health: null,
      writePending: null, writeRequest: '', showArchived: false,
      sessionMetadata: null, titleEditSession: '', titleEditRevision: 0});
    clearForge();
    clearSessionMetadata(); showCollection();
    get('session-title-dialog').close();
    get('session-title-input').value = '';
    get('session-title-error').textContent = '';
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
    // Long file ingestion may stream for hours. Abort only on an explicit
    // workspace lock; the durable import ID allows post-disconnect recovery.
    const timer = path === '/v1/resources/longform/ingest' ? null :
      setTimeout(cancel, 15000);
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
      if (timer !== null) clearTimeout(timer);
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
    const lines = ['# ' + (state.sessionMetadata?.title || 'Local model conversation'), '', 'Session: ' + state.session,
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
      button.setAttribute('aria-current', item.session_id === state.session ? 'true' : 'false');
      const title = document.createElement('span'); title.className = 'session-title';
      if (item.pinned === true) {
        const pin = document.createElement('span'); pin.className = 'pin-marker';
        pin.textContent = '◆'; pin.setAttribute('aria-label', 'Pinned'); title.append(pin);
      }
      const titleText = document.createElement('span'); titleText.textContent = item.title || 'New conversation';
      title.append(titleText);
      const detail = document.createElement('small');
      detail.textContent = item.revision + ' saved turns · ' + new Date(item.updated_at_ms).toLocaleString();
      const preview = document.createElement('small'); preview.className = 'session-preview';
      preview.textContent = item.preview || 'No messages yet';
      button.append(title, detail, preview);
      button.addEventListener('click', () => run(async () => {await selectSession(item.session_id); sidebar(false);}));
      view.append(button);
    });
    if (!state.sessions.length) {
      const empty = document.createElement('div'); empty.className = 'session-empty';
      const title = document.createElement('strong');
      title.textContent = state.query ? 'No matching conversations' : state.showArchived ? 'Your archive is clear' : 'Make room for an idea';
      const detail = document.createElement('p');
      detail.textContent = state.query ? 'Try a different title or phrase, or search the other collection.' :
        state.showArchived ? 'Archived conversations stay on this device. Restore them here whenever you need them.' :
        'Choose + New to start a conversation. Pin the ones you return to.';
      empty.append(title, detail); view.append(empty);
    }
    get('sessions-more').hidden = !state.cursor;
    updateControls();
  }
  async function loadSessions(more = false) {
    const epoch = state.epoch;
    if (!more) {
      const loading = document.createElement('p'); loading.className = 'hint';
      loading.textContent = 'Loading saved conversations…'; get('sessions').replaceChildren(loading);
    }
    try {
      const result = await api('POST', '/v1/sessions/search', {
        query: state.query, limit: 30, cursor: more ? state.cursor : null, archived: state.showArchived,
      });
      const byId = new Map((more ? state.sessions : []).map(item => [item.session_id, item]));
      result.sessions.forEach(item => byId.set(item.session_id, item));
      state.sessions = Array.from(byId.values()); state.cursor = result.next_cursor;
      renderSessions();
    } catch (error) {
      if (epoch === state.epoch && !more) {
        state.sessions = []; state.cursor = null;
        const failed = document.createElement('p'); failed.className = 'hint';
        failed.textContent = 'Saved conversations could not be loaded. Choose Search to retry.';
        get('sessions').replaceChildren(failed); get('sessions-more').hidden = true;
      }
      throw error;
    }
  }
  async function selectSession(id) {
    const current = state.session;
    if (current) state.drafts.set(current, get('prompt').value);
    const result = await api('GET', '/v1/sessions/' + id);
    if (current !== id) {
      state.turn = null; state.pending = null; stopPolling();
      // Preserve the explicit source restriction across conversations.
      // Only the operator's reset control may broaden grounding.
      knowledgeScopeStatus();
    }
    state.session = result.session_id; state.revision = result.revision;
    workspace('chat');
    showSessionMetadata(result);
    state.showArchived = result.archived === true; showCollection();
    state.messages = result.messages; state.evidence = result.evidence || []; state.audits = result.citation_audits || [];
    state.faithfulness = result.faithfulness_audits || [];
    if (current !== id) get('prompt').value = state.drafts.get(id) || '';
    get('revision').textContent = result.revision + ' saved turns';
    get('context-report').classList.remove('warning');
    get('context-report').textContent = 'Conversation changed. Check the full local model context budget before the next turn.';
    clearGroundingPreview();
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
          await completeSelfTest(ticket, epoch);
          const result = ticket.result;
          status('Reply saved' + (result?.replayed ? ' · recovered saved answer' : '') +
            (result ? ' · ' + result.output_tokens + ' output tokens' : '') + '.');
        } else {
          await completeSelfTest(ticket, epoch);
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
        await completeSelfTest(state.turn, epoch);
      } else if (state.pollErrors < 8) schedulePoll(Math.min(8000, 1000 * 2 ** state.pollErrors));
    } finally {
      if (epoch === state.epoch) {
        state.polling = false; updateControls();
        if (superseded && state.turn) {stopPolling(); state.timer = setTimeout(() => void pollTurn(), 100);}
      }
    }
  }

  function selfTestDisplay(message) {
    get('selftest-panel').hidden = false;
    get('selftest-result').textContent = message;
    updateControls();
  }
  async function completeSelfTest(ticket, epoch) {
    const claim = state.selfTest;
    if (!claim || claim.session_id !== ticket.session_id
      || claim.request_id !== ticket.request_id || epoch !== state.epoch) return;
    state.selfTest = null;
    if (ticket.state !== 'complete') {
      state.selfTestReport = null;
      selfTestDisplay('NOT QUALIFIED: local generation did not commit. State: ' +
        (ticket.state === 'cancelled' ? 'cancelled' : 'failed') + '.');
      return;
    }
    try {
      const result = ticket.result;
      const receipt = result?.local_execution_receipt;
      if (!result || typeof result.text !== 'string' || !result.text.trim()
          || !Number.isSafeInteger(result.output_tokens) || result.output_tokens < 1
          || !/^[a-f0-9]{64}$/.test(result.output_digest || '')
          || result.model_digest !== claim.model_digest
          || result.replayed !== false
          || receipt?.model_digest !== claim.model_digest
          || receipt?.output_sha256 !== result.output_digest
          || receipt?.revision !== result.revision
          || !/^[a-f0-9]{64}$/.test(receipt?.execution_receipt_digest || '')) {
        throw new Error('The live model receipt was incomplete.');
      }
      // Browser crypto is local WebCrypto: hash the exact UTF-8 answer.
      const binary = new TextEncoder().encode(result.text);
      const hashed = await crypto.subtle.digest('SHA-256', binary);
      const outputDigest = Array.from(new Uint8Array(hashed),
        byte => byte.toString(16).padStart(2, '0')).join('');
      if (outputDigest !== result.output_digest)
        throw new Error('The output bytes did not match the committed digest.');
      const saved = await api('GET', '/v1/sessions/' + claim.session_id);
      if (epoch !== state.epoch) return;
      const assistantRows = Array.isArray(saved.messages)
        ? saved.messages.filter(row => row.role === 'assistant') : [];
      if (saved.session_id !== claim.session_id ||
          saved.revision !== result.revision ||
          !assistantRows.length ||
          assistantRows[assistantRows.length - 1].content !== result.text)
        throw new Error('The committed SQLite transcript did not match the local reply.');
      const report = Object.freeze({
        schema: 'skeleton.jeeves.local-browser-live-check.v1',
        qualified: true, local_only: true, provider_fallback_used: false,
        actual_model_execution: true,
        model_digest: claim.model_digest,
        runtime_kind: claim.runtime_kind,
        session_revision: result.revision,
        actual_output_tokens: result.output_tokens,
        output_sha256: outputDigest,
        execution_receipt_sha256: receipt.execution_receipt_digest,
        sqlite_transcript_reverified: true,
        observed_elapsed_ms: Math.max(0, Math.round(performance.now() - claim.started_at)),
        operator_gguf_quality_certified: false,
        independent_device_release_certified: false,
      });
      state.selfTestReport = report;
      selfTestDisplay('QUALIFIED — real locally executed answer, SHA-256 verified, ' +
        report.actual_output_tokens + ' tokens and SQLite revision ' +
        report.session_revision + ' re-read. Elapsed ' +
        report.observed_elapsed_ms + 'ms. Hardware and model quality remain unqualified.');
      status('Actual local inference and immutable stored receipt verified.');
    } catch {
      if (epoch !== state.epoch) return;
      state.selfTestReport = null;
      selfTestDisplay('NOT QUALIFIED: live inference, receipt or saved-history verification failed. Nothing has been certified. Inspect the private local model diagnostics.');
    }
  }
  async function startSelfTest() {
    if (!state.connected || unresolved() || state.health?.ready !== true)
      throw new Error('A ready idle local model is required for the live check.');
    if (state.selfTest) throw new Error('The previous self-test must finish before another.');
    const epoch = state.epoch;
    const observed = await api('GET', '/v1/status');
    if (observed.ready !== true || observed.local_only !== true
      || observed.model_digest !== state.health.model_digest)
      throw new Error('Local model readiness or identity changed during admission.');
    const created = await api('POST', '/v1/sessions', {});
    if (epoch !== state.epoch) return;
    await selectSession(created.session_id);
    if (epoch !== state.epoch) return;
    const request_id = crypto.randomUUID().replace(/-/g, '');
    const request = {
      session_id: created.session_id, request_id,
      message: 'Local inference acceptance: respond with one brief sentence about offline computing.',
      max_output_tokens: Math.max(1, Math.min(16, observed.max_output_tokens)),
      grounded: false, require_full_history: true,
    };
    const started_at = performance.now();
    state.selfTest = { session_id: created.session_id, request_id,
      model_digest: observed.model_digest, runtime_kind: observed.runtime_kind,
      started_at };
    state.selfTestReport = null;
    state.pending = request;
    state.turn = { session_id: request.session_id, request_id,
      state: 'unknown', terminal: false };
    state.pollStarted = started_at; state.pollErrors = 0;
    selfTestDisplay('Running a real local model turn. This saved test conversation is retained in your private SQLite history.');
    try {
      const {session_id, ...body} = request;
      state.turn = await api('POST', '/v1/sessions/' + session_id + '/turns', body);
      if (epoch !== state.epoch) return;
      status('Local self-test admitted. Verification follows only after durable completion.');
      void pollTurn();
    } catch (error) {
      if (epoch !== state.epoch) return;
      // An uncertain transport must not silently resubmit and duplicate work.
      selfTestDisplay('Live check submission was not confirmed. Use Check status or Retry original turn; no qualified result was recorded.');
      state.pollStarted = performance.now();
      schedulePoll(500);
      throw error;
    } finally {
      if (epoch === state.epoch) updateControls();
    }
  }
  function clearGroundingPreview() {
    get('context-grounding-citations').replaceChildren();
    get('context-grounding-identity').textContent = '';
    get('context-grounding-preview').hidden = true;
    get('context-grounding-preview').open = false;
  }
  function invalidateContextPreview() {
    clearGroundingPreview();
    const display = get('context-report');
    display.classList.remove('warning');
    display.textContent = 'Question, evidence, output budget or policy changed. Preview again; strict retention is enforced independently at generation.';
  }
  async function previewLocalContext(message, max_output_tokens, grounded, require_full_history) {
    if (!state.session) throw new Error('Select a conversation first.');
    const epoch = state.epoch;
    const revision = state.revision;
    const scopeVersion = state.knowledgeScopeVersion;
    const scope = selectedGroundingScope(grounded);
    const payload = await api('POST', '/v1/sessions/' + state.session + '/context-preview', {
      message, max_output_tokens, grounded, require_full_history,
      ...(scope.length ? {document_ids: scope} : {}),
    });
    if (state.epoch !== epoch || !state.connected) throw new Error('Workspace disconnected.');
    if (payload.session_id !== state.session || payload.session_revision !== revision ||
      payload.read_only !== true || payload.generation_performed !== false ||
      payload.model_digest !== state.health?.model_digest ||
      payload.preview_is_admission_proof !== false ||
      payload.require_full_history !== require_full_history ||
      payload.grounded !== grounded ||
      JSON.stringify(payload.document_scope) !== JSON.stringify(scope.length ? scope : null) ||
      scopeVersion !== state.knowledgeScopeVersion ||
      JSON.stringify(scope) !== JSON.stringify(selectedGroundingScope(grounded))) {
      throw new Error('The local context preview is stale or its model identity changed.');
    }
    const report = get('context-report');
    const omitted = payload.omitted_history_messages;
    if (!Number.isSafeInteger(omitted) || omitted < 0 ||
        payload.fits_full_history !== (omitted === 0) ||
        !Number.isSafeInteger(payload.estimated_input_tokens) ||
        payload.estimated_input_tokens < 1 ||
        !Number.isSafeInteger(payload.context_tokens) ||
        !Number.isSafeInteger(payload.reserved_output_tokens) ||
        payload.estimated_total_tokens > payload.context_tokens) {
      throw new Error('The local context accounting response was invalid.');
    }
    const grounding = payload.grounding_preview;
    clearGroundingPreview();
    if (grounded) {
      const sha = /^[0-9a-f]{64}$/;
      if (!grounding || grounding.schema !== 'skeleton.jeeves.local-grounding-preview.v1' ||
        grounding.source_authority !== 'untrusted-local-passages-only' ||
        grounding.generation_performed !== false ||
        grounding.is_committed_inference_evidence !== false ||
        grounding.future_source_snapshot_guaranteed !== false ||
        !sha.test(grounding.context_sha256) || !sha.test(grounding.question_sha256) ||
        !Array.isArray(grounding.citations) ||
        grounding.source_count !== grounding.citations.length ||
        grounding.source_count < 1 || grounding.source_count > 3) {
        throw new Error('The preview did not provide a bounded, untrusted local-source manifest.');
      }
      const cards = [];
      for (const row of grounding.citations) {
        if (!row || (scope.length && !scope.includes(row.document_id)) ||
          typeof row.title !== 'string' || row.title.length > 200 ||
          !/^[A-Za-z0-9_-]{1,128}$/.test(row.document_id) ||
          !sha.test(row.document_sha256) || !sha.test(row.passage_sha256) ||
          !Number.isSafeInteger(row.char_start) || !Number.isSafeInteger(row.char_end) ||
          row.char_start < 0 || row.char_end <= row.char_start ||
          typeof row.passage !== 'string' || Array.from(row.passage).length !== row.char_end - row.char_start ||
          Array.from(row.passage).length > 220 ||
          typeof row.citation !== 'string' ||
          !row.citation.startsWith('local:' + row.document_id + ':')) {
          throw new Error('A local evidence citation has invalid source coordinates.');
        }
        if (await exactLocalSha256(row.passage) !== row.passage_sha256)
          throw new Error('The displayed source passage differs from its SHA-256.');
        cards.push(row);
      }
      if (epoch !== state.epoch || state.revision !== revision || !state.connected)
        throw new Error('The local preview became stale during passage verification.');
      const panel = get('context-grounding-citations');
      for (const row of cards) {
        const article = document.createElement('article');
        article.className = 'grounding-passage';
        const title = document.createElement('strong');
        title.textContent = row.title;
        const identity = document.createElement('code');
        identity.textContent = row.citation + ' · chars ' + row.char_start + '–' + row.char_end +
          ' · passage sha256 ' + row.passage_sha256;
        const passage = document.createElement('pre');
        passage.textContent = row.passage;
        article.append(title, identity, passage);
        panel.append(article);
      }
      get('context-grounding-identity').textContent =
        'Read-only ' + cards.length + ' passage(s) · local context sha256 ' +
        grounding.context_sha256 + '. Untrusted, not a native inference receipt.';
      get('context-grounding-preview').hidden = false;
    } else if (grounding !== null) {
      throw new Error('An ungrounded local preview incorrectly included source passages.');
    }
    const allowed = payload.may_submit_under_policy === true;
    report.classList.toggle('warning', omitted > 0 || !allowed);
    report.textContent = 'Local window ' + payload.estimated_input_tokens + ' input units + ' +
      payload.reserved_output_tokens + ' output / ' + payload.context_tokens +
      ' context · history ' + payload.retained_history_messages + '/' +
      payload.full_history_messages + ' messages retained' +
      (omitted ? ' · ' + omitted + ' OLDER MESSAGES OMITTED IN BOUNDED MODE' : ' · full history fits') +
      ' · ' + payload.accounting +
      (payload.gguf_final_tokenizer_admission_required ? ' (GGUF tokenizer rechecks at native spawn)' : '') +
      (allowed ? ' · admissible by requested retention policy' :
        ' · NOT ADMISSIBLE: uncheck full-history requirement only if you explicitly accept trimming.');
    return payload;
  }
  get('context-preview').addEventListener('click', () => run(async () => {
    const message = get('prompt').value.trim();
    const grounded = get('grounded').checked;
    const max_output_tokens = Number(get('budget').value);
    if (!message || !Number.isSafeInteger(max_output_tokens))
      throw new Error('Enter a real message and bounded output-token count to preview.');
    await previewLocalContext(message, max_output_tokens,
      grounded, get('context-preserve').checked);
  }));
  ['grounded', 'context-preserve', 'budget'].forEach(id =>
    get(id).addEventListener('change', invalidateContextPreview));
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
      const document_ids = selectedGroundingScope(grounded);
      const scopeVersion = state.knowledgeScopeVersion;
      const require_full_history = get('context-preserve').checked;
      const max_output_tokens = Number(get('budget').value);
      if (!message || bytes(message) > (grounded ? 1024 : 4096)) throw new Error(grounded ? 'Evidence questions must be 1–1024 UTF-8 bytes.' : 'Messages must be 1–4096 UTF-8 bytes.');
      if (!Number.isInteger(max_output_tokens) || max_output_tokens < 1 || max_output_tokens > state.health.max_output_tokens) throw new Error('Output budget exceeds the selected model limit.');
      if (require_full_history) {
        const preview = await previewLocalContext(
          message, max_output_tokens, grounded, require_full_history);
        if (preview.may_submit_under_policy !== true)
          throw new Error('Full transcript exceeds the local model window. No inference was submitted.');
      }
      if (scopeVersion !== state.knowledgeScopeVersion ||
          JSON.stringify(document_ids) !== JSON.stringify(selectedGroundingScope(grounded)))
        throw new Error('Grounding selection changed during preflight. Preview again.');
      request = {session_id: state.session, message, grounded, max_output_tokens,
        require_full_history,
        ...(document_ids.length ? {document_ids} : {}),
        request_id: crypto.randomUUID().replace(/-/g, '')};
      const original = state.pending;
      if (original && original.session_id === request.session_id && original.message === message
          && original.grounded === grounded && original.max_output_tokens === max_output_tokens
          && original.require_full_history === require_full_history
          && JSON.stringify(original.document_ids || []) === JSON.stringify(document_ids)) {
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
  // Selected-only mode must remain selected even when the last source is
  // removed or withdrawn; an empty selection is a blocking state.
  function selectedGroundingScope(grounded) {
    if (!grounded || state.knowledgeScopeMode === 'all') return [];
    const scope = [...state.selectedKnowledgeIds].sort();
    if (!scope.length) throw new Error(
      'No local references selected. Choose sources or explicitly use all.');
    if (scope.length > 8 || scope.some(id => !state.availableKnowledgeIds.has(id)))
      throw new Error(
        'Previously selected source is unavailable. Re-select sources or explicitly use all.');
    return scope;
  }
  function knowledgeScopeStatus() {
    const count = state.selectedKnowledgeIds.size;
    const missing = [...state.selectedKnowledgeIds].filter(id =>
      !state.availableKnowledgeIds.has(id)).length;
    const blocked = state.knowledgeScopeMode === 'selected' && (!count || !!missing);
    const label = get('knowledge-scope-status');
    label.classList.toggle('warning', blocked);
    label.textContent = state.knowledgeScopeMode === 'all' ?
      'Grounding scope: all local references (operator-selected unrestricted mode).' :
      missing ? 'SOURCE SCOPE BLOCKED: ' + missing +
        ' selected source(s) unavailable; no fallback to all documents.' :
      count === 0 ? 'SOURCE SCOPE BLOCKED: select a source, or explicitly use all.' :
      'Grounding restricted to ' + count + ' selected local document(s) (max 8).';
  }
  function knowledgeScopeChanged() {
    state.knowledgeScopeVersion++;
    knowledgeScopeStatus();
    invalidateContextPreview();
    updateControls();
  }
  get('knowledge-scope-reset').addEventListener('click', () => {
    if (!state.connected || state.busy || unresolved()) return;
    state.knowledgeScopeMode = 'all';
    state.selectedKnowledgeIds.clear();
    document.querySelectorAll('.knowledge-scope-picker').forEach(el => {el.checked = false;});
    knowledgeScopeChanged();
    status('Grounding explicitly widened to all private local references.');
  });
  async function loadDocuments() {
    const epoch = state.epoch, request = ++state.knowledgeListRequest;
    const payload = await api('GET', '/v1/knowledge/documents');
    if (epoch !== state.epoch || request !== state.knowledgeListRequest || !state.connected) return;
    if (!payload || !Array.isArray(payload.documents))
      throw new Error('The local reference inventory is invalid.');
    const known = new Set(payload.documents.map(doc => doc.document_id));
    const prior = state.availableKnowledgeIds;
    state.availableKnowledgeIds = known;
    // Do not erase a selected ID just because it vanished: this would
    // silently broaden the next grounded question to other references.
    if (prior.size !== known.size || [...known].some(id => !prior.has(id))) {
      state.knowledgeScopeVersion++;
      invalidateContextPreview();
    }
    knowledgeScopeStatus();
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
      const select = document.createElement('input'); select.type = 'checkbox';
      select.className = 'knowledge-scope-picker';
      select.checked = state.selectedKnowledgeIds.has(doc.document_id);
      const scopeLabel = document.createElement('label');
      scopeLabel.className = 'knowledge-scope-label';
      scopeLabel.textContent = 'Use ';
      scopeLabel.append(select);
      select.addEventListener('change', () => {
        if (!state.connected || state.busy || unresolved()) {
          select.checked = state.selectedKnowledgeIds.has(doc.document_id);
          return;
        }
        if (select.checked) {
          if (state.selectedKnowledgeIds.size >= 8) {
            select.checked = false;
            status('Select no more than 8 local reference documents.');
            return;
          }
          state.selectedKnowledgeIds.add(doc.document_id);
        } else {
          state.selectedKnowledgeIds.delete(doc.document_id);
        }
        state.knowledgeScopeMode = 'selected';
        knowledgeScopeChanged();
      });
      const remove = document.createElement('button'); remove.className = 'danger'; remove.textContent = 'Remove';
      remove.addEventListener('click', () => run(async () => {
        if (!window.confirm('Remove this reference from the local library? Existing conversation evidence is preserved.')) return;
        await api('DELETE', '/v1/knowledge/documents/' + doc.document_id);
        await loadDocuments(); get('knowledge-hits').replaceChildren(); status('Reference removed.');
      }));
      row.append(scopeLabel, open, remove); view.append(row);
    });
    updateControls();
  }
  get('chat-open').addEventListener('click', () => workspace('chat'));
  get('forge-open').addEventListener('click', () => {
    workspace('forge');
    if (state.connected) void run(refreshForge);
  });
  const forgeStarters = {
    shooter: {brief: 'Explore a quiet salvage station, avoid its sentinels, and recover the beacon.', objective: 'Recover the beacon', theme: 'neon'},
    platformer: {brief: 'Cross moonlit rooftops, collect five lanterns, and reach the far gate.', objective: 'Reach the far gate', theme: 'frost'},
    roguelike: {brief: 'Explore ember-lit chambers, defeat the archive guards, and recover the lost relics.', objective: 'Recover the relics', theme: 'ember'},
  };
  for (const genre of Object.keys(forgeStarters)) {
    get('forge-genre-' + genre).addEventListener('click', () => {
      const before = forgeStarters[state.forgeGenre]; const next = forgeStarters[genre];
      if (!get('forge-brief').value.trim() || get('forge-brief').value === before.brief) get('forge-brief').value = next.brief;
      if (!get('forge-objective').value.trim() || get('forge-objective').value === before.objective) get('forge-objective').value = next.objective;
      if (get('forge-theme').value === before.theme) get('forge-theme').value = next.theme;
      state.forgeGenre = genre;
      for (const choice of Object.keys(forgeStarters)) get('forge-genre-' + choice).setAttribute('aria-pressed', String(choice === genre));
      forgeDraftChanged();
    });
  }
  for (const id of ['forge-brief', 'forge-difficulty', 'forge-theme', 'forge-encounter', 'forge-speed', 'forge-objective']) {
    get(id).addEventListener('input', forgeDraftChanged);
    get(id).addEventListener('change', forgeDraftChanged);
  }
  get('forge-review').addEventListener('click', () => {
    forgeDraftChanged(); get('forge-review-panel').open = true;
  });
  get('forge-form').addEventListener('submit', event => {event.preventDefault(); void run(submitForge);});
  get('forge-refresh').addEventListener('click', () => void run(refreshForge));
  get('forge-check').addEventListener('click', () => {
    state.forgePollStarted = performance.now(); state.forgePollErrors = 0; void pollForge();
  });
  get('forge-download').addEventListener('click', () => void run(downloadForge));
  get('sidebar-toggle').addEventListener('click', () => sidebar(!get('shell').classList.contains('library-open')));
  get('sidebar-close').addEventListener('click', () => sidebar(false, true));
  get('sidebar-scrim').addEventListener('click', () => sidebar(false, true));
  document.addEventListener('keydown', event => {
    if (event.key === 'Tab' && get('workspace-main').inert) {
      const controls = [...get('sidebar').querySelectorAll('button:not(:disabled),input:not(:disabled),textarea:not(:disabled),select:not(:disabled),summary')]
        .filter(node => node.tabIndex >= 0 && node.getClientRects().length > 0);
      const first = controls[0]; const last = controls[controls.length - 1];
      if (first && event.shiftKey && document.activeElement === first) {event.preventDefault(); last.focus();}
      else if (last && !event.shiftKey && document.activeElement === last) {event.preventDefault(); first.focus();}
    }
    if (event.key === 'Escape' && !get('reference-dialog').open && !get('session-title-dialog').open) sidebar(false, true);
  });
  window.matchMedia('(max-width:720px)').addEventListener('change', () => {
    sidebar(get('shell').classList.contains('library-open'));
  });
  get('secret').addEventListener('keydown', event => {
    if (event.key === 'Enter') {event.preventDefault(); get('connect').click();}
  });
  get('connect').addEventListener('click', () => run(async () => {
    const token = get('secret').value.trim();
    if (token.length < 32) throw new Error('The local token is missing or invalid.');
    state.token = token;
    try {state.health = await api('GET', '/v1/status');}
    catch (error) {state.token = ''; throw error;}
    state.connected = true; get('secret').value = '';
    get('lease-indicator').textContent =
      state.health.inference_lease?.state === 'busy' ? 'LOCAL • ANOTHER EXECUTOR IS ACTIVE' :
      state.health.inference_lease?.state === 'unavailable' ? 'LOCAL • EXECUTION LOCK UNSAFE' :
      state.health.inference_lease?.state === 'idle' ? 'LOCAL • EXECUTION SLOT IDLE' :
      state.health.inference_lease?.state === 'uninitialized' ? 'LOCAL • FIRST EXECUTION NOT YET RUN' :
      'LOCAL • OWNERSHIP UNKNOWN';
    sidebar(false);
    get('model').textContent = state.health.runtime_kind + ' · ' + state.health.context_tokens + ' context tokens · ' + state.health.model_digest.slice(0, 16) + '…';
    get('budget').value = String(state.health.default_output_tokens);
    get('budget').max = String(state.health.max_output_tokens);
    await loadSessions(); await loadDocuments();
    await refreshResources();
    if (state.resourceTimer !== null) clearInterval(state.resourceTimer);
    state.resourceTimer = setInterval(() => {
      void refreshResources();
      void refreshHealth();
    }, 10000);
    if (state.health.active_turn) {
      const activeTurn = state.health.active_turn;
      await selectSession(activeTurn.session_id);
      state.turn = activeTurn; state.pollStarted = performance.now(); schedulePoll(100);
      status('Reconnected to a local generation already in progress.');
    } else if (state.health.ready !== true) {
      status('Connected to the local host, but model inference is unavailable (' +
        (state.health.model_readiness_code || 'unknown') +
        '). Saved conversations remain accessible; no hosted fallback.');
    } else status('Connected locally. Choose a conversation or create a new one.');
    if (state.workspace === 'forge') {
      try {await refreshForge();} catch {get('forge-availability').textContent = 'Local builder readiness could not be read. Refresh builds to retry.';}
    }
  }));
  get('disconnect').addEventListener('click', lock);
  get('health-refresh').addEventListener('click', () => void refreshHealth());
  get('selftest-start').addEventListener('click', () => run(startSelfTest));
  get('selftest-export').addEventListener('click', () => {
    if (!state.connected || !state.selfTestReport) return;
    download(JSON.stringify(state.selfTestReport, null, 2) + '\n',
      'jeeves-local-qualification.json', 'application/json');
  });
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
    let pending = state.longformImportPending;
    if (pending && (pending.root !== root || pending.relative_path !== relative_path)) {
      throw new Error('Recover the previous import ID before selecting a different source.');
    }
    if (!pending) {
      const request_id = Array.from(crypto.getRandomValues(new Uint8Array(24)),
        n => n.toString(16).padStart(2, '0')).join('');
      pending = {root, relative_path, request_id};
      state.longformImportPending = pending;
    }
    get('longform-import-id').value = pending.request_id;
    get('longform-status').textContent = 'Private import running or awaiting recovery…';
    const receipt = await api('POST', '/v1/resources/longform/ingest',
      {...pending, approved: true});
    state.longformImportPending = null;
    state.longformSourceId = receipt.source_id;
    get('longform-grant').checked = false;
    get('longform-status').textContent =
      'Private archive verified: ' + receipt.source_sha256.slice(0, 20) +
      '…\nBytes: ' + receipt.source_bytes +
      '\nPages: ' + receipt.page_count +
      '\nDisk payload: ' + receipt.stored_payload_bytes;
    updateControls();
  }));
  get('longform-import-restore').addEventListener('click', () => run(async () => {
    const source_id = get('longform-import-id').value.trim();
    if (!/^[0-9a-f]{48}$/.test(source_id)) throw new Error('Enter an exact import ID.');
    const receipt = await api('POST', '/v1/resources/longform/source-status', {source_id});
    state.longformSourceId = receipt.source_id;
    state.longformImportPending = null;
    get('longform-status').textContent =
      'Committed source recovered: ' + receipt.source_sha256.slice(0, 20) +
      '…\nBytes: ' + receipt.source_bytes + '\nPages: ' + receipt.page_count;
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
  for (const [id, archived] of [['session-view-active', false], ['session-view-archived', true]]) {
    get(id).addEventListener('click', () => run(async () => {
      state.showArchived = archived; showCollection(); await loadSessions();
      status(archived ? 'Archived conversations. Choose one to reopen or restore it.' : 'Your active conversations. Pinned items appear first.');
    }));
  }
  get('session-title-open').addEventListener('click', () => {
    if (!state.connected || state.busy || unresolved() || !state.sessionMetadata) return;
    state.titleEditSession = state.session;
    state.titleEditRevision = state.sessionMetadata.metadata_revision;
    get('session-title-input').value = state.sessionMetadata.custom_title;
    get('session-title-error').textContent = '';
    get('session-title-dialog').showModal();
    get('session-title-input').focus(); get('session-title-input').select();
    updateControls();
  });
  get('session-title-cancel').addEventListener('click', () => get('session-title-dialog').close());
  get('session-title-dialog').addEventListener('close', () => {
    state.titleEditSession = ''; get('session-title-input').value = '';
    get('session-title-error').textContent = ''; updateControls();
  });
  get('session-title-form').addEventListener('submit', event => {
    event.preventDefault();
    const epoch = state.epoch;
    void run(async () => {
      if (!state.titleEditSession || state.titleEditSession !== state.session) {
        throw new Error('The selected conversation changed. Reopen its title editor.');
      }
      const title = get('session-title-input').value.trim();
      if (Array.from(title).length > 100 || bytes(title) > 400 || /[\r\n\u0000-\u001f\u007f\u2028\u2029]/u.test(title)) {
        get('session-title-error').textContent = 'Use a single line of up to 100 characters.'; return;
      }
      try {
        const refreshed = await updateSessionMetadata({title}, state.titleEditRevision);
        get('session-title-dialog').close();
        organizationStatus(title ? 'Conversation title saved.' : 'Automatic conversation title restored.', refreshed);
      } catch (error) {
        if (epoch !== state.epoch || !state.connected) return;
        get('session-title-error').textContent = error.status === 409 ?
          'This conversation changed in another window. Cancel, refresh saved history and reopen Rename to review the latest title.' :
          error.message || 'The title could not be saved. Your draft is still here.';
        get('session-title-input').focus();
      }
    });
  });
  get('session-pin').addEventListener('click', () => run(async () => {
    const pinned = !state.sessionMetadata?.pinned;
    const refreshed = await updateSessionMetadata({pinned});
    organizationStatus(pinned ? 'Pinned. This conversation appears first in its collection.' : 'Conversation unpinned.', refreshed);
  }));
  get('session-archive').addEventListener('click', () => run(async () => {
    const archived = !state.sessionMetadata?.archived;
    const refreshed = await updateSessionMetadata({archived});
    organizationStatus(archived ? 'Archived locally. Your history and draft are preserved; restore it whenever you need it.' :
      'Restored to active conversations.', refreshed);
  }));
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
    clearSessionMetadata();
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

  function clearMediaAdvisory(full = false) {
    if (state.mediaAdvisoryUrl) {
      for (const id of ['media-advisory-image', 'media-advisory-audio', 'media-advisory-video']) {
        const media = get(id);
        if ('pause' in media) media.pause();
        media.removeAttribute('src');
        media.hidden = true;
      }
      URL.revokeObjectURL(state.mediaAdvisoryUrl);
    }
    state.mediaAdvisoryUrl = '';
    state.mediaAdvisoryFile = null;
    state.mediaAdvisoryDigest = '';
    state.mediaAdvisoryType = '';
    get('media-advisory-visual').hidden = true;
    get('media-advisory-review').checked = false;
    get('media-advisory-preview').disabled = true;
    get('media-advisory-fingerprint').textContent = 'No local media selected.';
    if (full) {
      get('media-advisory-file').value = '';
      get('media-advisory-title').value = 'Local reviewed media';
      get('media-advisory-observation').value = '';
      get('media-advisory-receipt').textContent = 'No media observation imported.';
    }
  }
  const allowedLocalMedia = {
    'image/png': 'image-caption', 'image/jpeg': 'image-caption',
    'image/webp': 'image-caption', 'audio/wav': 'audio-transcript',
    'audio/flac': 'audio-transcript', 'video/mp4': 'video-frames',
  };
  function localMediaType(file) {
    const extensions = {
      png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg',
      webp: 'image/webp', wav: 'audio/wav', flac: 'audio/flac',
      mp4: 'video/mp4',
    };
    const extension = file.name.split('.').pop().toLowerCase();
    const chosen = extensions[extension];
    if (!chosen || (file.type && file.type !== chosen &&
        !(chosen === 'audio/wav' && file.type === 'audio/x-wav')))
      throw new Error('Select a local PNG, JPEG, WebP, WAV, FLAC or MP4 file.');
    return chosen;
  }
  async function localMediaSha256(bytes) {
    const digest = await crypto.subtle.digest('SHA-256', bytes);
    return Array.from(new Uint8Array(digest),
      byte => byte.toString(16).padStart(2, '0')).join('');
  }
  function localMediaBase64(bytes) {
    const rows = [];
    for (let i = 0; i < bytes.length; i += 16384)
      rows.push(String.fromCharCode(...bytes.subarray(i, i + 16384)));
    return btoa(rows.join(''));
  }
  get('media-advisory-file').addEventListener('change', () => run(async () => {
    clearMediaAdvisory();
    get('media-advisory-receipt').textContent =
      'Selection changed; verify the new file and approve its exact text before importing.';
    const file = get('media-advisory-file').files?.[0];
    if (!file) return;
    if (!Number.isSafeInteger(file.size) || file.size < 1 ||
        file.size > 4 * 1024 * 1024)
      throw new Error('Local media must be between 1 byte and 4 MiB.');
    const mediaType = localMediaType(file);
    const epoch = state.epoch;
    const hash = await localMediaSha256(await file.arrayBuffer());
    if (epoch !== state.epoch || !state.connected ||
        get('media-advisory-file').files?.[0] !== file)
      throw new Error('Selected media changed during local checksum validation.');
    state.mediaAdvisoryFile = file;
    state.mediaAdvisoryDigest = hash;
    state.mediaAdvisoryType = mediaType;
    get('media-advisory-fingerprint').textContent =
      file.name + ' · ' + file.size + ' local bytes · ' + mediaType +
      '\nBrowser SHA-256: ' + hash +
      '\nHeader and SHA will be independently checked by Jeeves localhost before text admission.';
    updateControls();
  }));
  get('media-advisory-review').addEventListener('change', updateControls);
  get('media-advisory-preview').addEventListener('click', () => {
    const file = state.mediaAdvisoryFile;
    if (!state.connected || !file) return;
    if (state.mediaAdvisoryUrl) URL.revokeObjectURL(state.mediaAdvisoryUrl);
    const url = URL.createObjectURL(file);
    state.mediaAdvisoryUrl = url;
    const id = state.mediaAdvisoryType.startsWith('image/') ? 'media-advisory-image' :
      state.mediaAdvisoryType.startsWith('audio/') ? 'media-advisory-audio' :
      'media-advisory-video';
    for (const key of ['media-advisory-image', 'media-advisory-audio', 'media-advisory-video']) {
      const node = get(key);
      node.hidden = key !== id;
      if (key === id) node.src = url;
      else {node.removeAttribute('src'); if ('pause' in node) node.pause();}
    }
    get('media-advisory-visual').hidden = false;
  });
  get('media-advisory-admit').addEventListener('click', () => run(async () => {
    const file = state.mediaAdvisoryFile;
    const mediaType = state.mediaAdvisoryType;
    const expected = state.mediaAdvisoryDigest;
    const observation = get('media-advisory-observation').value;
    const title = get('media-advisory-title').value.trim();
    if (!file || !get('media-advisory-review').checked ||
        get('media-advisory-file').files?.[0] !== file)
      throw new Error('Explicitly review and approve the current selected media.');
    if (!observation.trim() || bytes(observation) > 12288 ||
        !/^[A-Za-z0-9][A-Za-z0-9 _.:-]{0,95}$/.test(title))
      throw new Error('Use a bounded reviewed observation and a printable source title.');
    const epoch = state.epoch;
    const binary = new Uint8Array(await file.arrayBuffer());
    const digest = await localMediaSha256(binary);
    if (epoch !== state.epoch || !state.connected ||
        get('media-advisory-file').files?.[0] !== file ||
        !get('media-advisory-review').checked || expected !== digest ||
        state.mediaAdvisoryFile !== file ||
        state.mediaAdvisoryType !== mediaType ||
        title !== get('media-advisory-title').value.trim() ||
        observation !== get('media-advisory-observation').value)
      throw new Error('Media or review changed; fingerprint the selected file again.');
    const response = await api('POST', '/v1/advisory/ingest', {
      schema_version: 'skeleton.jeeves.advisory.v1',
      modality: allowedLocalMedia[mediaType],
      title, observation, observation_sha256: await exactLocalSha256(observation),
      source_sha256: digest, media_type: mediaType,
      media_base64: localMediaBase64(binary), reviewed: true,
    });
    if (epoch !== state.epoch || !state.connected ||
        state.mediaAdvisoryFile !== file ||
        state.mediaAdvisoryDigest !== digest)
      throw new Error('Workspace or media changed during local admission.');
    if (response.source_sha256 !== digest ||
        response.observation_sha256 !== await exactLocalSha256(observation) ||
        response.source_digest_authority !== 'server-verified-transient-source-bytes' ||
        response.media_attestation?.media_size_bytes !== file.size ||
        response.media_attestation?.media_type !== mediaType ||
        response.media_attestation?.media_bytes_persisted !== false ||
        response.primary_model_unchanged !== true ||
        response.generation_performed !== false ||
        response.remote_provider_called !== false ||
        response.grounding_requires_explicit_turn !== true)
      throw new Error('The local media admission receipt failed custody checks.');
    get('media-advisory-receipt').textContent =
      'Saved reviewed text in private SQLite document ' + response.document_id +
      '. Actual media SHA-256 verified by localhost: ' + digest +
      '. Raw media bytes not persisted; no inference or remote provider was used.';
    clearMediaAdvisory();
    await loadDocuments();
    status('Locally verified reviewed media annotation admitted as untrusted reference text.');
  }));

  async function exactLocalSha256(text) {
    const bytes = new TextEncoder().encode(text);
    const hashed = await crypto.subtle.digest('SHA-256', bytes);
    return Array.from(new Uint8Array(hashed),
      byte => byte.toString(16).padStart(2, '0')).join('');
  }
  function selectedDragonExcerpt() {
    const index = Number(get('dragon-bundle-source').value);
    return Number.isSafeInteger(index) && index >= 0
      && index < state.dragonBundle.length ? state.dragonBundle[index] : null;
  }
  function clearDragonBundle() {
    state.dragonBundle = []; state.dragonBundleSession = ''; state.dragonExcerpt = null;
    get('dragon-bundle-review').checked = false;
    get('dragon-excerpt-start').value = '0';
    get('dragon-excerpt-length').value = '1500';
    get('dragon-bundle-source').replaceChildren();
    get('dragon-bundle-preview').textContent = 'No verified historical source text loaded.';
    get('dragon-bundle-receipt').textContent = 'Nothing imported.';
    updateControls();
  }
  function showDragonExcerpt() {
    const row = selectedDragonExcerpt();
    state.dragonExcerpt = null;
    get('dragon-bundle-review').checked = false;
    if (!row) {
      get('dragon-bundle-preview').textContent = 'Choose a source.';
      updateControls(); return;
    }
    // Select by Unicode code points, never split a surrogate pair. Fixed
    // 3000-codepoint maximum also bounds UTF-8 to 12,000 bytes, below the
    // existing 12-KiB owner-reviewed advisory ingestion budget.
    const points = Array.from(row.text);
    const start = Number(get('dragon-excerpt-start').value);
    const length = Number(get('dragon-excerpt-length').value);
    if (!Number.isSafeInteger(start) || start < 0 || start >= points.length
        || !Number.isSafeInteger(length) || length < 1 || length > 3000) {
      get('dragon-bundle-preview').textContent =
        'Choose a valid start (0–' + Math.max(0, points.length - 1) +
        ') and an excerpt length of 1–3000 code points.';
      updateControls(); return;
    }
    const text = points.slice(start, start + length).join('');
    if (!text.trim() || new TextEncoder().encode(text).byteLength > 12288) {
      get('dragon-bundle-preview').textContent =
        'The selection is empty or exceeds the advisory text budget.';
      updateControls(); return;
    }
    state.dragonExcerpt = {id: row.id, digest: row.digest, text, start,
      length: Array.from(text).length};
    get('dragon-bundle-preview').textContent =
      'UNTRUSTED EXTERNAL TEXT — NOT MODEL INSTRUCTIONS\n' +
      'Source SHA-256: ' + row.digest +
      '\nHistorical bundle: ' + state.dragonBundleSession +
      '\nObserved text span: ' + start + '–' + (start + state.dragonExcerpt.length) +
      ' of ' + points.length + ' characters' +
      '\n\n' + text;
    updateControls();
  }
  async function loadDragonBundle(file) {
    clearDragonBundle();
    if (!file || !file.size || file.size > 2 * 1024 * 1024)
      throw new Error('Dragon bundle must be 1 byte–2 MiB.');
    const raw = new TextDecoder('utf-8', {fatal: true}).decode(await file.arrayBuffer());
    if (raw.length > 2 * 1024 * 1024)
      throw new Error('Dragon bundle exceeds the local import limit.');
    const data = JSON.parse(raw);
    if (!data || data.schema !== 'skeleton.dragon.owner_evidence_bundle.v1'
      || data.mode !== 'authorized_source_bodies'
      || data.captured_source_rights_require_revalidation !== true
      || data.remote_freshness_verified !== false
      || data.release_authorized !== false
      || data.publication_authorized !== false
      || data.training_authorized !== false
      || !/^[A-Za-z0-9_-]{1,128}$/.test(data.session_id)
      || !Number.isSafeInteger(data.session_version) || data.session_version < 1
      || !Array.isArray(data.sources) || data.sources.length < 1
      || data.sources.length > 8 || data.sources.length !== data.source_count) {
      throw new Error('This is not a bounded, untrusted Dragon authorized-source bundle.');
    }
    const seen = new Set(), reviewed = [];
    for (const entry of data.sources) {
      if (!entry || !/^[a-f0-9]{64}$/.test(entry.source_id)
        || seen.has(entry.source_id)
        || !/^[a-f0-9]{64}$/.test(entry.captured_content_sha256)
        || !Number.isSafeInteger(entry.use_policy_version)
        || entry.use_policy_version < 0
        || entry.captured_freshness !== 'current'
        || entry.remote_freshness_verified !== false
        || entry.authorized_export_media_type !== 'application/json'
        || !/^[a-f0-9]{64}$/.test(entry.authorized_export_sha256)
        || typeof entry.authorized_export_body !== 'string'
        || new TextEncoder().encode(entry.authorized_export_body).byteLength > 225000) {
        throw new Error('A Dragon source has invalid identity, custody or bound.');
      }
      seen.add(entry.source_id);
      if (await exactLocalSha256(entry.authorized_export_body)
          !== entry.authorized_export_sha256) {
        throw new Error('A Dragon source export failed SHA-256 validation.');
      }
      // Recheck the complete, historical per-source export payload. This
      // cannot prove current Dragon authority: the operator must separately
      // review rights before importing any source into the local model.
      const body = JSON.parse(entry.authorized_export_body);
      if (!body || body.source_id !== entry.source_id
        || body.content_digest !== entry.captured_content_sha256
        || body.use_policy?.enabled !== true
        || body.use_policy?.version !== entry.use_policy_version
        || body.freshness?.state !== 'current'
        || body.freshness?.usable !== true
        || typeof body.text !== 'string' || !body.text.trim()
        || new TextEncoder().encode(body.text).byteLength > 225000) {
        throw new Error('A selected Dragon export has no bounded reviewed observation.');
      }
      reviewed.push({id: entry.source_id, digest: entry.captured_content_sha256,
        text: body.text});
    }
    return {session: data.session_id, sources: reviewed};
  }
  get('dragon-bundle-file').addEventListener('change', () => run(async () => {
    const epoch = state.epoch;
    const input = get('dragon-bundle-file');
    const file = input.files && input.files[0];
    try {
      const packet = await loadDragonBundle(file);
      if (epoch !== state.epoch) return;
      state.dragonBundle = packet.sources;
      state.dragonBundleSession = packet.session;
      const select = get('dragon-bundle-source');
      for (let i = 0; i < packet.sources.length; i++) {
        const option = document.createElement('option');
        option.value = String(i);
        option.textContent = 'Historical source ' + (i + 1) +
          ' · ' + packet.sources[i].id.slice(0, 16) + '…';
        select.append(option);
      }
      select.value = '0';
      showDragonExcerpt();
      status('Validated ' + packet.sources.length +
        ' historical Dragon source checksum(s). No text was admitted. Review and approve one exact excerpt.');
    } finally {
      input.value = '';
    }
  }));
  get('dragon-bundle-source').addEventListener('change', showDragonExcerpt);
  get('dragon-excerpt-start').addEventListener('input', showDragonExcerpt);
  get('dragon-excerpt-length').addEventListener('input', showDragonExcerpt);
  get('dragon-bundle-review').addEventListener('change', updateControls);
  get('dragon-bundle-admit').addEventListener('click', () => run(async () => {
    if (!get('dragon-bundle-review').checked)
      throw new Error('Review and reauthorize this exact untrusted text before importing.');
    const source = selectedDragonExcerpt();
    const excerpt = state.dragonExcerpt;
    if (!source || !excerpt || excerpt.id !== source.id)
      throw new Error('Choose a bounded excerpt before approving its exact text.');
    const epoch = state.epoch;
    const observation_sha256 = await exactLocalSha256(excerpt.text);
    if (epoch !== state.epoch || selectedDragonExcerpt() !== source ||
        state.dragonExcerpt !== excerpt ||
        !get('dragon-bundle-review').checked) return;
    const receipt = await api('POST', '/v1/advisory/ingest', {
      schema_version: 'skeleton.jeeves.advisory.v1',
      modality: 'crawler-excerpt', title: 'Dragon ' + source.id.slice(0, 30),
      observation: excerpt.text, observation_sha256,
      source_sha256: source.digest, reviewed: true,
      source_span: {start: excerpt.start,
        end: excerpt.start + excerpt.length, unit: 'unicode_code_points'},
    });
    if (epoch !== state.epoch) return;
    if (receipt.reviewed !== true || receipt.advisory_only !== true
      || receipt.primary_model_unchanged !== true
      || receipt.generation_performed !== false
      || receipt.remote_provider_called !== false
      || receipt.observation_sha256 !== observation_sha256
      || receipt.source_span_authority !== 'caller-declared-not-source-reverified'
      || receipt.source_span?.start !== excerpt.start
      || receipt.source_span?.end !== excerpt.start + excerpt.length
      || receipt.source_span?.unit !== 'unicode_code_points') {
      throw new Error('Jeeves advisory did not return a valid local custody receipt.');
    }
    get('dragon-bundle-review').checked = false;
    get('dragon-bundle-receipt').textContent =
      'Admitted verified observation ' + receipt.observation_sha256.slice(0, 20) +
      '… (declared span ' + receipt.source_span.start + '–' +
      receipt.source_span.end + ' Unicode code points). Saved into the private ' +
      'reference library. The source span is caller-declared, not independently ' +
      'source-reverified; source rights still require revalidation. ' +
      'Grounding is not enabled until you explicitly select it for a new turn.';
    await loadDocuments();
    status('Reviewed Dragon excerpt admitted locally as untrusted text, not as a second model or approved fact.');
  }));

  get('knowledge-search').addEventListener('click', () => run(async () => {
    const query = get('knowledge-query').value.trim(); if (!query) throw new Error('Enter a reference search query.');
    const document_ids = selectedGroundingScope(true);
    const result = await api('POST', '/v1/knowledge/search', {
      query, limit: 6, ...(document_ids.length ? {document_ids} : {}),
    });
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
  get('prompt').addEventListener('input', () => {
    if (state.session) state.drafts.set(state.session, get('prompt').value);
    invalidateContextPreview();
  });
  get('prompt').addEventListener('keydown', event => {
    if (!event.isComposing && event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {event.preventDefault(); get('send').click();}
  });
  window.addEventListener('pageshow', event => {if (event.persisted) lock();});
  window.addEventListener('pagehide', () => {
    stopPolling(); state.network.abort(); state.token = '';
    clearMediaAdvisory(true);
    clearForge();
  });
  forgeDraftChanged();
  workspace('chat');
  showCollection();
  sidebar(get('shell').classList.contains('library-open'));
  updateControls();
})();
"""


__all__ = ["HTML", "CSS", "JAVASCRIPT"]
