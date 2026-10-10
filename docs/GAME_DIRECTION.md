# Game Direction — Player Fantasy, Pillars, Feel-Ready Gates, Cut-Line

**Owner:** Game Director (Zorander)
**Audience:** every studio role and bot that ships Skeleton × GameForge work
**Status:** living direction doc. Cards, not essays. Grounded in `main` at
`06eb3eb6` (2026-10-03). Every path, verb and route below exists on `main`
unless it is explicitly flagged **GAP**.
**Companion docs:** `docs/GROK_BOTS_DIRECTION.md` (organism map + backlog),
`docs/APP_ASSEMBLY.md` (runtime assembly), `docs/PRODUCT.md` (operator surface).

> Ship-ready is not feel-ready. A green CI run proves the code compiles.
> It does not prove an operator felt like they forged a game.

---

## 1. Core player fantasy

**One sentence:** *I answer a questionnaire, and a living, playable game
comes out the other side — one I can walk, play and keep shaping.*

The "player" of Skeleton × GameForge is the **operator**: a creator who
directs the factory, not a coder who patches it. The fantasy has three beats:

| Beat | What the operator feels | What must be true on main |
|---|---|---|
| **Intent** | "It understood what I wanted." | Questionnaire answers drive era, tensor and vision (`skeleton/context/questionnaire.py` `intake()`). |
| **Forge** | "It built a real thing, not a report." | A Godot 4 project tree is written to disk (`skeleton/context/pipeline.py` `_stage_emit` → `skeleton/forge/projector.write_project`). |
| **Proof** | "I can walk and play it right now." | The walk/sim proves spawn → extract (`skeleton/forge/walk.py`), and the build boots headless when Godot is present (`skeleton/forge/playtest.py`). |

`docs/GROK_BOTS_DIRECTION.md` §10 already states the stranger test. This doc
adopts it as the fantasy's **definition of done**:

1. `python -m skeleton run`
2. Answer or accept a Game Spec
3. Receive a Godot folder that opens and plays one verb
4. See `build_report.md` with seed, rotor cue, mass, field_pct
5. Export a zip without hand-editing cards

---

## 2. Pillars

Five pillars. Every feature, PR and issue must name the pillar it serves.
A change that serves none is a cut candidate (see §6).

### P1 — Intent is sovereign

The operator's answers decide the game. Defaults are a fallback, never a
silent override.

| Do | Don't |
|---|---|
| Thread questionnaire answers through every entry point (CLI, API, cockpit). | Hard-code empty answers and let the default era decide. |
| Show which answers bound which outputs (era, tensor, vision). | Drop answers on the floor without telling the operator. |
| Keep one intake contract (`intake()` → `Intake`). | Fork intake into two engines that disagree. |

### P2 — Every pulse is playable

From `GROK_BOTS_DIRECTION.md` §0: *make every pulse produce a playable delta
or a bound source — never a stamp.*

| Do | Don't |
|---|---|
| End each creator verb in an artefact you can open, walk or boot. | Ship verbs whose only output is a JSON "status: ok". |
| Prefer Godot files + `data/rooms.json` the walker can consume. | Count docs/CHANGELOG churn as progress. |
| Prove with `walk` / sim / playtest before claiming done. | Claim "playable" from static GDScript checks alone. |

### P3 — One verb loop, one truth

The CLI and API are two doors into the **same** factory.
`docs/API_CLI_PARITY.md` and `python -m skeleton contracts` already make this
law for shared commands; the creator loop must obey it too.

| Do | Don't |
|---|---|
| Route `run` from CLI and `/gameforge/run` to the same pipeline. | Let CLI and API produce different games from the same answers. |
| Document only verbs that `python -m skeleton help` dispatches. | Advertise verbs that return `Unknown command`. |
| Keep the walker as the shared proof (`walk_from_pack`). | Invent a second proof path per surface. |

### P4 — Readable at operator speed

Blizzard clarity on verbs. The operator reads one line and knows what happened.

| Do | Don't |
|---|---|
| One-line human summary + `--json` for machines (pattern already in `walk`, `run`). | Dump 200-line payloads as the only output. |
| Exit code = truth (`walk` returns 1 when the walk fails). | Return 0 on a failed forge. |
| Name failures by stage (`emit`, `seal`, `sim`). | Bury the failing stage in a stack trace. |

### P5 — Systemic depth, bounded

EVE depth with hardware-aware caps. Eras, blends, tensors and plans compose;
nothing runs unbounded.

| Do | Don't |
|---|---|
| Compose eras (`--blend A B --t`) and tensors instead of adding parallel systems. | Add a new kernel/stage with no catalog entry (forbidden in `GROK_BOTS_DIRECTION.md` §3). |
| Keep the ten pipeline stages as the backbone. | Bolt on side scripts outside the pipeline. |
| Respect caps (walk N-cap, repair `max_rounds: 3` in `GameForgeRun`). | Unbounded regenerate loops. |

---

## 3. Creator verb loop (as it exists on `main`)

The fantasy loop is:

```
questionnaire → eras → plan → walk → materialise → play/verify
```

### 3.1 Loop map

| # | Loop step | CLI on `main` (`skeleton/__main__.py`) | API on `main` | Engine | Status |
|---|---|---|---|---|---|
| 1 | Questionnaire | *none*: `run` passes `answers={}` (`_cmd_gameforge_run`) | `POST /gameforge/intake` (`skeleton/api/gameforge_routes.py`) | `skeleton/context/questionnaire.py` `Questionnaire` / `intake()` | **GAP**: no CLI path to answer |
| 2 | Eras | `python -m skeleton eras` | — | `skeleton/forge/eras.py` `list_eras`, `compile_era`, `blend_eras` | Live |
| 3 | Plan | `python -m skeleton plan <vision>` | — | `skeleton/cortex/live.py` `live_jeeves().plan_build` | Live |
| 3b | Steer | `python -m skeleton cockpit <COMMAND>` (e.g. `BIND ERA <era>`, `BIND ARCHETYPE <name>`, `SNAPSHOT`) | cockpit routes (`skeleton/api/cockpit.py`) | `skeleton/context/cockpit.py` `Cockpit.apply` | Live, but state doesn't carry across CLI calls (new `Cockpit()` per call) |
| 4 | Walk | `python -m skeleton walk [--era E] [--blend A B --t T] [--json]` | `POST /cortex/walk` (per `docs/PRODUCT.md`) | `skeleton/forge/walk.py` `walk_from_pack` | Live; exit 1 on fail |
| 5 | Materialise | `python -m skeleton run <vision> [--era E] --out DIR [--overwrite]` | `POST /gameforge/run` | CLI: `skeleton/context/pipeline.py` `GameForgeRun`; API: `state.gameforge.run(...)` via `skeleton/app/runtime/runtime_commands.py` `_run_handler` | **GAP**: CLI and API run different engines |
| 6 | Play / verify | *none*: no `--playtest` flag on `run` | — | `GameForgeRun.execute(playtest="auto"\|"require")` → `skeleton/forge/playtest.py` | **GAP**: headless boot not reachable from CLI |

`forge` (`python -m skeleton forge <name>`) only prints `Forge ready.` and a
blueprint component count. It is not a materialise verb today.

### 3.2 The ten-stage spine (CLI `run`)

`GameForgeRun.execute` runs: `ingest → detect → tensor → lattice → oracle →
forge → jeeves → emit → seal → sim`.

- `emit` runs `gdscript_check.check_ok`, writes the project when `--out` is
  given, plus `CONTEXT_LEDGER.json` and `CONTEXT_TENSOR.json`, and optionally
  playtests.
- `seal` verifies the cockpit ledger.
- `sim` runs `skeleton/forge/sim.simulate_session` over `data/rooms.json` and
  fails the run if the session sim fails.

This spine is the strongest part of the fantasy on `main`. The gaps are at
the edges: intake going in, and play-proof coming out.

### 3.3 Broken / missing links (verified on `main`)

| Link | Evidence | Pillar hit |
|---|---|---|
| CLI cannot take questionnaire answers | `skeleton/__main__.py` `_cmd_gameforge_run`: `answers={}` hard-coded; `_parse_run_args` has no `--answers` | P1 |
| CLI cannot request a playtest or repair mode | `_parse_run_args` has no `--playtest` / `--repair-mode`; `GameForgeRun.execute` supports both | P2 |
| CLI `run` ≠ API `run` | CLI → `skeleton.context.pipeline.GameForgeRun`; API/shared command → `state.gameforge.run(answers, title, target, repair)` with `target` default `"json"` | P3 |
| Documented operator verbs not dispatched | `docs/PRODUCT.md` lists `ready`, `product`, `health`, `doctor`, `next`, `pulse`, `day`, … ; `skeleton/__main__.py` `main()` dispatches none of them and prints `Unknown command` | P3, P4 |
| Cockpit steering is per-process | `_cmd_cockpit` builds a fresh `Cockpit()` each call, so `BIND ERA` from one CLI call does not reach the next `run` | P1 |

Each of these is filed as an issue (linked from the PR that adds this doc).

---

## 4. Feel-ready gates

A step is **feel-ready** only when every gate in its card passes. Numeric
targets are **TBD** until measured; no invented numbers. Owners measure,
then replace TBD with the measured baseline and the target.

### Gate card: G1 — Intake

- [ ] The operator can answer the questionnaire from the CLI **and** the API.
- [ ] Same answers → same `Intake` (era, vision, tensor) from both doors.
- [ ] Unanswered beats fall back to documented defaults, and the output says so.
- [ ] `Questionnaire.progress()` (answered/total/remaining) is visible to the operator.
- Time from first prompt to intake complete: **TBD** (measure).

### Gate card: G2 — Eras

- [ ] `eras` lists every era with a one-line read (dps, speed: present today).
- [ ] Every listed era compiles and walks (the walk matrix proposed in PR #2392 is the measurement tool when it lands).
- [ ] A blend (`--blend A B --t`) produces a pack that also walks.

### Gate card: G3 — Plan / steer

- [ ] `plan <vision>` returns a plan the operator can read in one screen.
- [ ] Cockpit steering (`BIND ERA`, `BIND ARCHETYPE`) visibly changes the next `run`.
- [ ] Plan bias / extract_late / era appear in the walk payload (present today in `walk --json`).

### Gate card: G4 — Walk

- [ ] `walk` exits 0 on pass and 1 on fail (present today).
- [ ] Human line reports `extracted`, `t`, `hops`, `cores/required_cores` (present today).
- [ ] Failure names the blocking room/edge, not just `extracted=False`.
- Walk wall-clock per era: **TBD** (measure).

### Gate card: G5 — Materialise

- [ ] `run --out DIR` writes a Godot 4 project, `CONTEXT_LEDGER.json` and `CONTEXT_TENSOR.json`.
- [ ] `build_report.md` is present with seed, mass, field_pct (DoD §1 item 4); verify on main, flag if missing.
- [ ] `gdscript_check` passes with zero problems.
- [ ] CLI and API `run` with the same answers produce the same file manifest.
- Files emitted / time to emit: **TBD** (measure).

### Gate card: G6 — Play / verify

- [ ] `run --playtest auto` boots headless when Godot is found (`SKELETON_GODOT_BIN` / `GODOT_BINARY` / `godot4` / `godot` on PATH).
- [ ] `run --playtest require` fails the run if the boot fails, naming the stage and error.
- [ ] The playtest status (`passed` / reason) is in the human summary line.
- [ ] A stranger can open the folder in Godot and perform one verb (manual QA check until automated).
- Time to first verb: **TBD**. `GROK_BOTS_DIRECTION.md` §2 sets "<5 min to first verb" for the core prototype; QA measures against it.

### Gate card: G7 — Loop as a whole

- [ ] The stranger test (§1) passes end to end on a clean checkout, run by QA, recorded.
- [ ] No step requires hand-editing cards or JSON.
- [ ] Every step's output is readable in one line + `--json`.

---

## 5. Feel review protocol

1. **Who:** Game Director + QA Director; the discipline owner of the step attends.
2. **When:** before any PR that claims to close a gate is merged, and once per
   milestone on the whole loop (G7).
3. **How:** run the loop as a stranger: clean env, documented commands only.
   Record command, exit code, wall-clock, artefacts.
4. **Verdict:** `feel-ready` / `ship-ready only` / `reject`. "Ship-ready only"
   means CI green but a gate unchecked; it does not close the gate.

---

## 6. Cut-line rubric

Every proposed feature, PR or backlog item gets one verdict.

| Verdict | Test | Examples |
|---|---|---|
| **KEEP** | Moves a feel-ready gate (§4) or closes a §3.3 link. | `--answers` on CLI `run`; unifying CLI/API run; playtest flag. |
| **DEFER** | Serves a pillar but no gate is blocked on it; needs the loop first. | New eras before every existing era walks; new export targets before G6 passes. |
| **CUT** | Serves no pillar, or is stamp-only. | CHANGELOG/STATUS edits with no code-path change; verbs documented but not dispatched; parallel engines that duplicate the spine; new kernels with no catalog + bank + poke. |

### Stamp-only = CUT

A change is **stamp-only** when it changes status text, counts, badges or
docs claiming completion **without** a code path or test that moves a gate.
`GROK_BOTS_DIRECTION.md` §3 already forbids "Stamp-only CHANGELOG with no code
path change". This rubric extends that to STATUS, BACKLOG and checklist ticks.

### Tie-breaks

1. Closer to the operator's hands wins (intake and play over internals).
2. Fewer engines wins (unify before extend).
3. Measured wins over asserted.

---

## 7. Ownership map

| Area | Owner role | Owns in this doc |
|---|---|---|
| Player fantasy, pillars, cut-line, feel verdict | **Game Director** | §1, §2, §6; final feel-ready call (§5) |
| Engine unity, CLI/API parity, perf budgets, TBD measurement harness | **Technical Director** | P3; G5 manifest parity; G4/G5/G6 timings |
| Visual read of emitted Godot slice, silhouette, material language | **Art Director** | G6 "opens and plays" visual bar |
| Questionnaire voice, era dialect/lore, readable outputs | **Narrative Director** | G1 prompt copy; era read lines in G2 |
| Loop structure, eras/blends, plan bias, progression hooks | **Systems Design Lead** | P5; G2, G3 |
| Stranger test, regression gates, gate evidence | **QA Director** | §5 runs; G7 record; manual G6 check |
| Implementation of gap fixes | **Engineering** (Coder Lead / Backend / Tools) | §3.3 issues |

---

## 8. How to use this doc

- **Opening a PR?** Name the pillar (P1–P5) and the gate (G1–G7) it moves.
- **Closing a gate?** Attach the evidence: command, exit code, artefact path.
- **Proposing work?** Run it through §6 first. If it is CUT, don't open it.
- **Found a new broken link?** Add a row to §3.3 and file an issue with
  evidence (path + function), acceptance criteria and an owner role.

---

## 9. Change log

| Date | Change | By |
|---|---|---|
| 2026-10-03 | Initial direction: fantasy, 5 pillars, loop map, 7 gate cards, cut-line, ownership. | Game Director |
