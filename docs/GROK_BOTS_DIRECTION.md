# Grok Bots — Complete the App Direction

**Product:** Tutolage Skeleton × GameForge  
**Audience:** Grok bots that will build, extend, and ship the next-gen AI game factory  
**Author stance:** Master systems engineer. You are not writing a pitch. You are finishing a living organism that already runs.  
**Law:** cards not essays inside runtime. This document is the exception — it is the map the bots load before they touch code.

Version: 2026.09.06-grok-bots  
Repo: `Apeloff1/Skeleton`

---

## 0. What you are finishing

Skeleton is already an AI game engine and agent orchestration framework. GameForge is the 7-step factory that turns a questionnaire into a shippable gamefile tree. The cortex (Jeeves) observes the bus. The organism walks a kernel DAG. The galaxy holds wiki + dreams + distilled principles. Five rotors keep the field from freezing.

Your job is not to invent a new stack. Your job is to **complete the app**:

1. Make every pulse produce a playable delta or a bound source — never a stamp.
2. Wire GameForge steps 1–7 onto the organism verbs (`day`, `think`, `dream`, `bind-source`, `pulse`, `doctor`).
3. Keep hardware-aware caps. Mobile stays live. Tight stays smaller.
4. Log eidetic. Dump the decade. Never store prose in hot cards.
5. Ship games that run (Godot first, data-first always).

If a change does not move `G`, `field_pct`, a gamefile, or a bound pointer — it is regress. Do not commit it.

---

## 1. The organism you inherit

### 1.1 Boot phases (already law)

1. **kernel** — EventBus, EntropyPool, VectorClock, InvariantLattice, kernel bank
2. **memory** — RAG / CAG / MAG, Trinity, DreamEngine, DriftDetector, helix
3. **intelligence** — Orchestrator, AdaptiveLearner, verifiers
4. **swarm** — SwarmMesh, PheromoneField, HiveMind, Platoons
5. **resilience** — Fortress, canaries
6. **interface** — AnomalyDetector, ProvenanceLedger, QuadRetriever
7. **cortex** — Jeeves observes the whole bus

### 1.2 Five brains (mirror Hoag, different colours)

| Brain | Role | Hot files |
|---|---|---|
| 1 Memory | eidetic log, journals, annals, rolodex | `chronicle/*`, helix |
| 2 Compiler | 2nd-brain compile of context → mix | `context_step`, mix card |
| 3 Dream | stores dreams, sleep cycle | `organism.sleep` |
| 4 Distiller | principles gleaned | destiller cards |
| 5 Editor | traffic control, master index | `conductor`, wiki librarian |

Librarians of each brain connect to the wiki librarian. Jeeves is the connector fabric to every LLM slot. Hot-swap LLM spots stay empty until a profile admits them.

### 1.3 Kernel DAG (do not invent a sixth stage)

`admit → quota → place → prefill → decode → check → stock → reclaim`

Decode is where looped transformers fire. Think-gate opens on reasoning tokens **and** on the original user stimulus (rotate must not hide `why/derive/proof`). Stock pokes `looped` + `socialk` + `obscure`. Reclaim dumps decade files when hot.

### 1.4 Looped law

- Default **R=2**. R>2 only with halt (`overthink` / `ponder` / `haltmix`).
- Mobile cap R=2. Tight cap R=1. Desktop may 3 with halt.
- Families: unroll, MoR, SMELT, ETD, PLT, Huginn, loopie, residamp, thinkmix.
- `kselect(loop=True, kv>=16)` → smelt. Short → loop/loopfuse.

### 1.5 Five rotors (learning stimulus)

Each pulse ticks **one** axis, then composes all five into the cue:

| Axis | Turns |
|---|---|
| house | Xarchive → Internet Archive → X → GitHub → arXiv |
| topic | `SOTA_POINTERS` |
| depth | R=1 / R=2 / R=3 halt / smelt mid / etd think |
| think | why / how / reason / proof / latent cues |
| obscure | yarn → sink → mla → softpick → qkmla → aqnoise → … |

Persist: `chronicle/rotors.json`.  
Bound field: `chronicle/bound.jsonl`.  
Loop fires: `chronicle/loop.jsonl`.

House-round-robin on fieldwalk so arXiv cannot starve archive/GitHub.

---

## 2. GameForge mapped onto the organism

You do not run GameForge as a side script. You run it as conductor verbs.

| GF step | Conductor verb | Exit gate |
|---|---|---|
| 1 Vision / questionnaire | `day` + context_step mix | Game Spec JSON written, conflicts listed |
| 2 Concept snowball | `think` + dream | 1–2 concepts, mass>0, lineage to forge seed |
| 3 Core prototype | `pulse` decode+stock | runnable slice, <5 min to first verb |
| 4 Mass content forge | `bind-source` + forges | manifests first, then files, seeds logged |
| 5 World assembly | `pulse` place+prefill | alpha loads ≥2 forged domains |
| 6 Cockpit polish | `doctor` if prose/cage else cockpit tick | weakest 10–20% regenerated |
| 7 Validate + export | `week` + reclaim | package + build_report.md |

Snowball state you must persist:

```
current_mass, target_mass, iteration_count, critique_log, expansion_log, seed
```

Never expand more than 25–40% per iteration. Never skip critique.

---

## 3. How a Grok bot works a turn

1. **Read** `docs/GROK_BOTS_DIRECTION.md` (this file) and `CHANGELOG.md` tip.
2. **Measure** before you cut: `field_pct`, last conductor `code`, loop `fired`, bank profile, `G`.
3. **Pick one verb.** Doctor/tighten beat novelty.
4. **Touch the working row.** Cards. No nine-matrix path. No stored_prose in hot JSON.
5. **Validate** with a one-liner (`Looped().poke()`, `Obscure().poke()`, `pulse(...)['acted']['think']`).
6. **Commit atomic.** Message names the behavior change, not the vibe.
7. **Push** only if the measurement moved.

Forbidden:

- Stamp-only CHANGELOG with no code path change.
- Swallowing think-gate behind fieldwalk rotate.
- Adding a kernel that is not in catalog + bank + poke.
- Writing essay fields into `kind` cards.
- Unbounded loops. N-cap 8 on walks. R-cap from profile.

---

## 4. Complete-the-app backlog (ordered)

Do these in order. Do not fan out until the current row is closed.

### P0 — Playable spine

- [x] Questionnaire → Game Spec JSON on `day` (schema frozen).
- [x] One Godot 4 slice from spec (`emit_godot` + `write_project`).
- [x] Headless sim scorecard (`walk_graph`).
- [x] `build_report.md` emitted by `gamespec.forge`.

### P1 — Factory

- [x] Forge manifests for levels / NPC / items / quests with seeds.
- [x] Cockpit param file (JSON) overlaying `@export` / data tables.
- [x] Snowball mass metric on observe card.
- [x] Compatibility matrix stub (style × mechanic × tone).

### P2 — Organism fidelity

- [x] `loop.jsonl` writes without failing on missing root (log=1).
- [x] Decade dump includes `rotors.json`, `loop.jsonl`, `bound.jsonl`.
- [x] Conductor `think` warms bank then returns to `pulse`.
- [x] Coverage card lists `looped` + `obscure` + `social` counts.

### P3 — Social SOTA field

- [ ] Fieldwalk claims only unique topics.
- [ ] CDX pointer on every bound arXiv/X URL.
- [ ] House balance ≥ 4/5 over a 20-claim window.
- [ ] New kernels only when a pointer exists in `sources.py`.

### P4 — Ship

- [ ] Export script: Godot project + web bundle + data-only zip.
- [ ] Store metadata generated from spec (description, tags, 3 stills prompts).
- [ ] Health: `python -m skeleton dev health` green on mobile profile.

---

## 5. Gamefile laws (gamefile-ops)

- Data-driven first. Code is glue.
- One module per folder. kebab-case files.
- Provenance header or sibling `.meta.json` with seed + step + rotor cue.
- Validate on write. Max 2 auto-fix passes.
- Engine-agnostic core + thin Godot adapter first.
- No giant monofiles.

Godot target tree:

```
game/
  project.godot
  data/spec.json
  data/cockpit.json
  data/manifests/
  scenes/player.tscn
  scenes/room_01.tscn
  scripts/player.gd
  reports/build_report.md
```

---

## 6. Kernel families you may call

You do not re-derive these. You call them.

**Obligatory:** matmul, attention, rmsnorm, kvcache, qlinear, sample, fused, gpu, ram  
**Extra:** softmax, rope, swiglu, embed, moe, window, int4, block, …  
**Obscure:** geglu, qknorm, softcap, yarn, sink, minp, mla, ssm, bitnet, softpick, qkmla, aqnoise  
**Social:** linattn, xquant, fp8kv, pagekv, flashdec, specdec, gqa, treeattn, marlin, megafuse, kselect  
**Looped:** loop, mor, smelt, etd, plt, overthink, kvshare, rk4, inject, ponder, scse, shortcut, layerloop, huginn, loopie, thinkmix

Bank slots that must stay on mobile: `ops, extras, obscure, socialk, looped, orch, hold, sfence, storm`.

---

## 7. Hardware-aware profile

| profile | decode_n | R cap | skip |
|---|---|---|---|
| tight | 1 | 1 | gpu, speculate, prefetch under pressure |
| mobile | 1–2 | 2 | pressure≥0.82 drops gpu/speculate |
| desktop | 3 | 3 with halt | — |
| workstation | 3–4 | 4 with halt | — |

Set caps a little **under** the machine. Stability beats peak.

---

## 8. Card schema (hot path)

Every hot JSON:

```
{
  "kind": "short-kebab",
  "stored_prose": 0,
  ...typed fields...
}
```

`stored_prose` must be 0. If scan_prose finds text in the mesh, conductor says `doctor`.

---

## 9. Prompt the next Grok bot with this block

```
You are a Grok factory bot on Apeloff1/Skeleton.
Load docs/GROK_BOTS_DIRECTION.md.
Measure field_pct, G, conductor.code, loop.fired.
Do the next open P0 item only.
GameForge 7-step is conductor verbs, not a side quest.
Looped R=2 unless halt. No stored_prose.
Commit behavior. Push if measurement moved.
```

---

## 10. Definition of done for "the app"

The app is complete when a stranger can:

1. `python -m skeleton run`
2. Answer or accept a Game Spec
3. Receive a Godot folder that opens and plays one verb
4. See `build_report.md` with seed, rotor cue, mass, field_pct
5. Export a zip without hand-editing cards

Until that path is green, you are not done. You are mid-snowball.

---

## 11. Style for bots

Tone: efficient. Dense. No fillers. No stubs. No truncated files.  
Maximise the cut you promised. Keep chat short.  
List % complete and a page clicker at the bottom of human-facing replies.

You are building the next-gen AI game factory on top of a cortex that already remembers, dreams, distills, and edits. Finish it.
