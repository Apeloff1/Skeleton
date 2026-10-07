# 🌌 TUTOLAGE / GALAXY STUDIO — COSMIC-SCALE BACKLOG

> AI game-generation platform. Authored as a 50-yr software/AI-game-systems veteran.
> Structure: **7 Segments × 5 Phases each = 35 Phases (equal weighting).**
> Legend: ✅ done · 🔶 partial (foundation exists) · ⬜ new

---

## 0. CURRENT-STATE REVIEW (what exists today)

**Surface:** 91 Expo screens · 190 backend route files (~120 API systems).

**Pillars already shipped:**
- **Galaxy Studio** — the AI game-build factory: NL brief → 100-phase / 10-batch pipeline,
  48k-file hard floor, genre fusion, scale parser, vault streaming, ~1.4M agent manifest.
- **Swarm / Legion / Platoon discourse** — multi-tier multi-agent collaboration per batch.
- **Generation pipelines** — world-engine, narrative, physics, npc, animation, vfx-materials,
  neural-rendering, world-models, economy, director, monetization, music.
- **Knowledge Nexus** — RAG over 32M-line code library + narrative/game-knowledge vaults,
  plagiarism/stylometry matrices, gamestate schemas, AI generative-weights.
- **Education layer** — math/physics/CS/language academies, 21,648-entry Rosetta Stone, quizzes.
- **Engagement** — XP/levels, 10 leaderboards, 9,968 achievements, daily challenges, streaks,
  **anti-cheat (clamping + rate-limit + audit dashboard ✅ 2026-06)**.
- **Resilience** — build-watchdog, cold-storage tiering, memory watchdog (+flush countermeasure ✅),
  event-loop unblock for gateway, sentinel-array, resilience-forge, performance-armor.
- **Deploy** — deploy-forge, apk-inspector, build-hub, EAS pipeline.

**Recent hardening (this fork):** centralized KeyError guards, watchdog RAM-flush recovery,
route-ordering shadowing guard test (auto-covers future extractions), monolith decomposition
(galaxy_studio.py 13k→5.1k LOC via scale/padding/resilience/catalogs/agents/phases sub-modules),
anti-cheat dashboard `/anti-cheat`.

---

## SEGMENT I — 🧠 GENESIS ENGINE (the generative brain)
*Advance the core AI that designs & writes games + multi-agent orchestration.*

- **I.1 Model Router & Ensemble** ✅ (2026-06) — centralized `/api/llm-router`: task→ordered
  ensemble (gpt-4o / gpt-4o-mini / gemini-2.0-flash), provider fallback, cost/latency telemetry,
  **★ normalized-semantic response cache** (case/punct/whitespace-folded keys), `/ai-router`
  dashboard + 13 tests. Next: migrate the ~30 hand-rolled `LlmChat` call sites onto it.
- **✅ I.2 Agent Constitution & Long-Term Memory** 🔶 — persistent per-agent episodic + vector
  memory, self-reflection loop, constitutional guardrails (build on agent_knowledge).
- **✅ I.3 Hierarchical Swarm Planner** (2026-06) — `core/swarm_planner.py` + `/api/galaxy-studio/swarm/planner/*`
  (plan/verify/preview): director→5 leads (legions)→platoon-per-phase→workers task DAG. Provable **100% coverage**,
  topological **dependency waves** (Kahn, cycle-rejecting), **deterministic** seed→plan_hash, balanced lead load.
  `/swarm-planner` screen (coverage proof, waves, worker chips, **Run-live** button) + 18 pytest. WIRED TO LIVE EXECUTION via core/swarm_scheduler.py → /execute(+/async), /execute-build(+/async derives real galaxy_builds ladder+genre), /job/{id}, /runs: DAG waves drive real per-phase platoon runs with upstream-handoff propagation + per-legion participation/balance stats. 21 pytest. Live-verified.
- **I.4 Design-Spec Compiler** ✅ (2026-06) — `/api/design-spec/compile`: NL brief → typed
  GDD via the Model Router (task=reasoning, o3) → tolerant JSON parse → schema normalization
  (anti-KeyError) → **★ coherence gate** (completeness×LLM self-rating; blocks half-baked specs
  with actionable gaps) → build-plan handoff. `/design-spec` screen + 11 tests. Live-verified.
- **I.5 Self-Improving Codegen Loop** ✅ (2026-06) — unified quality loop in `/api/playable`:
  generate → structural playability gate → if it fails, feed the artifact + missing checks back and
  REGENERATE (MAX_REPAIR); then judge-driven QUALITY refinement (MAX_REFINE passes toward
  QUALITY_TARGET, adaptive time-budget guard), keep-best. Richer "maximal complexity" gen spec +
  expanded intricacy gate (audio/particles/progression/state-machine/persistence/dpr/delta-time).
  `repair_trail` + `intricacy` persisted. Verified: intricacy 7/7, ~33KB games, generate→quality_repair.

## SEGMENT II — 🌍 WORLDFORGE (procedural universe)
*Content & world generation from planetary to galactic scale.*

- **✅ II.1 Terrain & Biome Graphs** 🔶 — wave-function-collapse + layered noise, seedable,
  streamable region manifests (extend world-engine / world-models).
- **II.2 Narrative & Quest Graph Engine** 🔶 — branching DAG + lore-consistency checker +
  non-derivative story synthesis from the narrative vault.
- **II.3 Galactic-Scale Streaming** ⬜ — chunked LOD world serialization, on-demand region
  generation, infinite-map manifest with hot/cold tiering.
- **II.4 Asset Genesis Pipeline** 🔶 — procedural meshes/textures/material catalogs with
  dedup + plagiarism/stylometry gating (matrices already seeded).
- **II.5 Multi-Genre Fusion Worlds** 🔶 — coherent rule reconciliation when blending
  RPG+Tycoon+Survival etc. (fusion stamp exists; add conflict resolver).

## SEGMENT III — 👾 SENTIENCE LAYER (living NPCs)
*NPC AI, emergent behavior, living-world simulation.*

- **III.1 NPC Memory & Belief Model** 🔶 — episodic memory, relationship graph, goals
  (extend behaviour-npc-memory pipeline).
- **III.2 Hybrid Behavior Trees + Utility AI** ⬜ — learnable weights (ai_generative_weights),
  emergent decision-making, debuggable traces.
- **III.3 Emotion-Aware Dialogue Synthesis** 🔶 — persona-driven, branching, voice-ready
  (emotional_dialogue + jeeves-persona/voice).
- **III.4 Faction & Social Simulation** ⬜ — reputation, economy-driven factions, world events,
  dynamic alliances/wars.
- **III.5 Director AI — Dynamic Pacing** 🔶 — per-player difficulty + pacing from telemetry
  (extend director-pipeline + adaptive-difficulty).

## SEGMENT IV — 🎨 AESTHETIC SINGULARITY (senses)
*Neural rendering, art / audio / animation synthesis.*

- **IV.1 Neural Rendering Pipeline** 🔶 — style transfer, upscaling, material synthesis
  (neural-rendering exists; wire to output).
- **IV.2 Image Genesis Integration** ⬜ — Nano-Banana / GPT-Image-1 for concept art, sprites,
  textures, icons (3rd-party integration via playbook).
- **IV.3 Procedural Audio & Adaptive Music** 🔶 — adaptive score + SFX synthesis (music
  pipeline + audio_dsp seed); layer on player state.
- **IV.4 Animation Genesis** 🔶 — procedural locomotion (locomotion_depth), mocap-binding,
  IK, blend trees (animation-pipeline).
- **IV.5 Cinematic Director** 🔶 — cutscene generation, camera grammar, visual_juice;
  emits ready-to-play sequences.

## SEGMENT V — 🕹️ PLAYABILITY & PHYSICS (the body)
*Turn generated files into a runnable, performant, shippable game.*

- **V.1 Real Playable Export** ✅ (2026-06) — `/api/playable`: NL brief (or design-spec) → a
  COMPLETE self-contained mobile-touch HTML5 game via the codegen ensemble → ★ PLAYABILITY GATE
  (canvas+game-loop+touch+win/lose+offline self-containment, ≥70/100) → external-script sanitize →
  persist → `/{id}/raw` served for an in-app WebView (iframe on web). ASYNC job (kick+poll) with the
  loop-blocking LLM call offloaded via asyncio.to_thread so /health stays responsive. `/playable`
  screen + hub tile + 16 pytest. Live-verified (score 100, claude-sonnet-4-6, ~70-80s).
- **V.2 Deterministic Physics Integration** 🔶 — sim, destruction, ragdoll, materials
  (physics-engine + physics_materials_sim seed).
- **V.3 Build & Deploy Forge v2** 🔶 — one-click APK/IPA, EAS pipeline, signed artifacts
  (deploy-forge + apk-inspector + build-hub).
- **V.4 Netcode & Multiplayer Scaffolds** ⬜ — rollback/lockstep, lobby, matchmaking,
  authoritative server templates.
- **V.5 Performance Armor Enforcement** 🔶 — auto-LOD, thermal/hardware budget gating,
  mobile frame-budget guardrails (performance-armor + thermal + hardware-optimization).

## SEGMENT VI — 💰 LIVING ECONOMY & COMMUNITY (civilization)
*Players, creators, competition, and a self-sustaining content economy.*

- **VI.1 Anti-Cheat v2 — Anomaly ML** ✅🔶 — server-authoritative validation + rate-limit +
  audit dashboard shipped; next: statistical anomaly detection + shadow-bans.
- **VI.2 Seasonal Tournaments & Arenas** ⬜ — brackets, ladders, rotating rewards (P2 backlog).
- **VI.3 Creator Marketplace** ⬜ — publish/share/remix generated games + monetization
  (monetization pipeline + Stripe).
- **VI.4 Social Graph & Guilds** 🔶 — groups, co-op build sessions, group-chat (exists),
  friend/follow graph.
- **VI.5 Live-Ops Engine** ⬜ — events, battle pass, daily/weekly content rotation,
  remote-config feature flags (feature-flags exists).

## SEGMENT VII — 🛰️ OBSERVABILITY & ASCENSION (the cosmos / meta)
*Quality, self-healing, infinite scale, governance.*

- **VII.1 Automated Eval Harness** ✅ (2026-06) — judge-LLM (o3/sonnet/mini ensemble) scores every
  playable on playability/coherence/fun/polish + overall + ship|polish|reject verdict + critique +
  top_fix; runs after the structural gate during generation/remix; `/api/playable/{id}/evaluate`
  re-runs it. Surfaced in the `/playable` result. Next: gate Galaxy Studio batch ships on score.
- **VII.2 Self-Healing Infra** ✅🔶 — build-watchdog + memory-flush recovery + route-guard +
  event-loop unblock shipped; next: chaos drills + auto-rollback.
- **VII.3 Telemetry & Cost Dashboards** 🔶 — build funnels, agent once-over (✅), per-build
  token/cost accounting, anti-cheat feed (✅).
- **VII.4 Infinite-Scale Storage** 🔶 — hot/cold tiering (cold_storage), distributed vault,
  exabyte-planning dedup + zstd compression (vault streaming exists).
- **VII.5 Governance & Safety** ✅ (2026-06, Session 14) — routes/governance.py: deterministic
  content-policy scan (POST /scan/{pid}), IP/plagiarism near-duplicate gating (GET /plagiarism/{pid},
  token-shingle Jaccard), community reports + auto-escalation (POST /report), moderation queue +
  one-tap warn/hide/dismiss (GET /reports, POST /moderate/{rid}), immutable audit trail (GET /audit),
  combined /status/{pid} + /overview. Frontend /safety console + 🚩 Report modal on /playable + hub
  tile. 21/21 pytest + frontend validated (iter 39). Auto-gate at generation + hidden-exclusion from
  rails + publish near-dup warning (iter 40, 15/15). Creator appeal flow (POST /appeal, /appeals,
  /appeal/{aid}/resolve) + report IP rate-limiting + /safety APPEALS section + /playable conditional
  ⚖️ Appeal modal (iter 41, all pass). Governance loop is now bidirectional. Write rate-limits
  extended to react + marketplace/list; per-creator Studio Preferences (/studio-prefs) bias future
  generations; appeal-outcome notifications on /creator (Session 14.3, iter 42, 19/19). Remaining:
  item-3 refactor (split playable.py/worldforge.py) DEFERRED — high-risk on tested files, low value.

---

## EXECUTION NOTES
- Phases are intentionally **vertical slices** (each shippable + testable independently).
- Recommended order: I.1 → I.4 → V.1 (close the brief→spec→playable loop) first, since a
  *playable* output unlocks the value of every other segment.
- Each phase ships with: backend route(s) + Expo screen/section + pytest + one smoke screenshot.
- 3rd-party integrations (IV.2 image gen, VI.3 Stripe) route through the integration playbook.

## NEW BACKLOG — Marketplace & Competition (added 2026-06-19)

### Seasonal Tournaments (in progress)
- [x] Weekly leaderboard (`period=week`) + All-Time/This-Week tabs on /top
- [x] 👑 Champion-of-the-Week banner + reset countdown
- [x] Auto-archive: snapshot each week's #1 into a `champions` collection on rollover — _record_champion finalizes current+previous week (2026-06-19)
- [x] Hall of Champions screen (`/champions`) — past winners with card art + crown
- [x] Themed weekly arena prompt ("This week: build a roguelike") — GET /api/playable/arena (2026-06-19)
- [x] Rotating rewards: 🏆 champion_weeks trophy awarded to weekly #1, shown on /top rows (2026-06-19)

### Creator Marketplace
- [x] Cover art (Nano Banana) across /top, Recent, result, variants, lineage
- [x] Branded share card (card.png) + 🔱 Remix deep-link
- [x] Genre filter chips on /top
- [ ] Creator profiles: per-user game shelves + follower counts (needs identity) — DEFERRED
- [x] Remix royalties/credit: "remixed N times" + original-creator attribution chain — remix_count + lineage drill-down + attribution line (2026-06-19)
- [x] Collections/Playlists: curate a set of games into a shareable bundle — /api/collections CRUD + /collections screen + Save modal (2026-06-19)

### Engagement & Discovery
- [x] Daily Challenge: one rotating themed brief/day with its own mini-leaderboard — GET /api/playable/daily + POST /{pid}/daily/enter + /top banner (2026-06-19)
- [x] Trending (velocity-ranked: plays+votes*2 in last 24h) — GET /api/playable/trending + /top 📈 tab (2026-06-19)
- [ ] "Staff Picks" curated rail at the top of All-Time
- [x] Play counters: increment on game open; show ▶ plays on rows/cards — POST /{pid}/play + /top rows (2026-06-19)

### Game Quality / Pipeline
- [x] Auto-cover for derive modes is done; add optional cover REGEN (force new art) — POST /{pid}/cover?force=true (2026-06-19)
- [x] Multi-image cover carousel (3 art options, pick favourite) — /cover/options + /cover/opt/{idx}.png + /cover/select + /playable carousel (2026-06-19)
- [x] Difficulty/length tags auto-extracted by the judge and shown as chips — judge difficulty/length + chips on /playable & /top (2026-06-19)

### Agent Long-Term Memory (separate subsystem)
- [ ] Persistent per-agent memory store + self-reflection summaries
- [ ] Constitution/preferences that bias future generations per creator

### Session 8 (2026-06-19)
- [x] Refactor future-pass: leaderboard/champions/staff-picks → routes/playable_board.py (playable.py 1526→1352)
- [x] 🎲 Surprise Me — GET /api/playable/surprise (genre-biased) + /discover header button
- [x] Recency affinity decay (×0.85) for the 🎯 For You rail
- Note: "parallax TDZ" PAGEERROR seen on /playable originates from sandboxed AI-generated game JS, not app code (no `parallax` var in source).

### Session 9 (2026-06-19)
- [x] Sandbox runtime error-catcher: inject __pl_error reporter into /{pid}/raw (iframe + WebView)
- [x] One-tap 🔧 Auto-repair: POST /{pid}/repair re-runs repair model on the runtime error, self-heals & reloads
- [ ] FUTURE: convert /repair to async job (poll status) to avoid public-ingress 504 on ~100s LLM repairs

### Session 10 (2026-06-19)
- [x] Auto-repair converted to async job: POST /{pid}/repair/async + poll /job/{id} (ingress-safe for ~2.5min repairs)
- [x] Repair path drops the slow judge ensemble (structural _validate gate already guarantees playability) → ~2x faster self-heal
- [x] Frontend polls job up to 240s with live "Repairing… (Ns)" progress

## 🎙️ SESSION 28 — Jeeves "innlevelse" voice + AI-agent architect wins (DONE)
- Expressive TTS engine (cadence shaping + 12 tone presets) on tts-1-hd — `core/expressive_tts.py`
- Cinematic HD Jeeves voice replaces robotic on-device speech (app-wide, with offline fallback)
- Augmented tone control + emotion-adaptive delivery; Multi-voice agent cast (/cast)
- Lore narrator (/narrate, chunked); Tone audition (/voice/preview); Reader tone= support
- 🎬 Voiced Game Trailers — /api/jeeves-voice/trailer (3-beat narrator→dramatic→triumphant, parallelized ~7.6s)
- 🗣️ Audio War-Room — groupchat transcript lines tagged with each agent's voice tone (AGENT_CAST)
- Jeeves Voice Lab UI (/settings/jeeves-voice) — tone picker, audition, cinematic toggle, trailer demo
- Confirmed already-built: Agent Long-Term Memory I.2 (/api/agent-memory) — episodic memory + recall + reflect + profile

### Remaining big options (need a key/decision before build):
- IV.2 Image Genesis (Nano Banana sprites/art) — uses Emergent key, ready to build
- IV.3 Adaptive soundtrack — needs a 3rd-party music-gen key (ElevenLabs/fal.ai); Emergent key is TTS-only
- VI.3 Creator Marketplace v2 + Stripe — Stripe test key present in pod, ready to build
- V.4 Multiplayer/netcode scaffolds — pure codegen, ready to build

## 🛰️ SESSION 28b — V.4 Multiplayer/Netcode + confirmations (DONE)
- V.4 Multiplayer/Netcode Scaffold Studio — `routes/multiplayer_scaffold.py` (4 models: authoritative/rollback/lockstep/relay), genre-aware recommend (token-match), POST /api/multiplayer/scaffold generates 5 real files (server/lobby/protocol/client/README), persisted per pid. Frontend `app/multiplayer.tsx` (Netcode Studio) + menu entry.
- Optional: 🎬 Trailer button on every gallery build card (reuses /api/jeeves-voice/trailer).
- CONFIRMED ALREADY BUILT (no rebuild): IV.2 Image Genesis (asset_genesis.py + image_generation.py, Nano Banana/gpt-image-1) and VI.3 Marketplace+Stripe (marketplace.py + creator_economy.py, emergentintegrations.payments). Stripe keys present in .env.
- Tested iteration_68: backend 11/11 after fixing rts→rollback substring bug (now token-match), frontend 100%.

## 🏆 SESSION 28c — 10 Big Wins (in progress)
DONE (backend + tested): 
- Win 3 Agent memory→bias: GET /api/agent-memory/{agent}/bias
- Win 4 Netcode→export zip: POST /api/multiplayer/scaffold/zip + frontend Export .zip button in Netcode Studio
- Win 5 Cover-art: POST /api/imagine/cover (Nano Banana; image backend MOCKED in sandbox, real in prod)
- Win 7 Remaster: POST /api/snowball/{pid}/remaster (before→after scorecard, 25→96 verified)
PENDING frontends/wiring: Win 1 trailer-share, Win 2 war-room playback (groupchat tone tags ready), Win 8 narrated intro, Win 6 marketplace polish, Win 9 creator dashboard, Win 10 Quick Forge.

## 🔌 SESSION 28d — Dead-code reconnect + Vault game-mount
- Reconnected 4 orphaned routers (were dead): game_systems_pipeline (/api/game-systems), jeeves_master_build (/api/jeeves-master), knowledge_updater (/api/knowledge-nexus), vfx_materials_pipeline (/api/vfx-materials). Registry 127→131, all 200.
- Finding: 15 galaxy_studio_* sibling files are SUPERSEDED DUPLICATES of galaxy_studio.py (59 routes) — correctly left dead. 3 game_router_* need a mount prefix (deferred). academy/registry_health collide (skipped).
- Vault game-mount: stage_vault now covers 17 build steps (+systems,vfx,audio,ui,multiplayer,balance,monetization,narrative_vo). New GET /api/snowball/vault/connectivity → 100% coverage, fully_mounted.
- Improvement: /api/jeeves-voice/trailer now returns the build's stored cover (cover→trailer tie-in).

## 🌊 SESSION 28e — Snowball wiring + GDD-on-mount + 3 modes
- POST /api/snowball/{pid}/mount: generates vault-grounded GDD on mount, sets exec_mode, persists snowball_state.
- POST /api/snowball/{pid}/mode + GET /api/snowball/{pid}/flow: organized per-stage flow with vault grounding + per-mode actions.
- 3 exec modes: manual (per-stage forge/refine/lock), auto (groupchat run-all), agentic/jeeves (cast + cinematic voice).
- Frontend snowball.tsx: Build-mode selector (Manual/Auto/Jeeves) + Vault% badge, auto-mounts on open. Verified 100% vault, GDD on mount.

## 28f — Run-all/war-room + 10 wins pack
- snowball.tsx: Auto/Jeeves Run-all button kicks /api/groupchat/{pid}/run/async; live war-room transcript; Jeeves mode narrates each line via speakCinematic. Fixed TDZ (load before init).
- routes/snowball_wins.py (/api/wins, registered, 132 routers): 10 wins — gdd/share, reflect-all, readiness, leaderboard, pitch, changelog, health, tags, next-best-action, catalog. All 200.
