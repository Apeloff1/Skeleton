# Jeeves Live Godot + Dragon Research Lab — Production Milestones

This development slice extends the earlier Director runtime with a foreground,
authenticated **loopback gameplay service** and a Godot 4 UI that delegates
decisions to the canonical Python Director engine. It also provides comparative
Dragon gameplay studies, selected-path coverage and authored story cue deltas.

These milestones produce working source paths and specialized regression suites.
A Godot binary execution, model training run, rendered cinematics, first-install
QA and real-player signoff are **not established by source publication**.

## 1. Play actual Director quest logic from the Godot preview

Create an approved original Director campaign using the earlier
`director-draft` → `director-examine` → `director-promote` workflow.

First create a persistent game session:

```bash
python -m skeleton dev game jeeves director-session-begin \
  --project ./original_game --source design/director_campaign_source.json \
  --session hero_a
```

Then explicitly supply a fresh random, local bearer secret and start the
foreground authoritative service. The environment must contain a printable,
non-whitespace ASCII secret at least 32 characters long:

```bash
export SKELETON_DIRECTOR_BRIDGE_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(36))')"
python -m skeleton dev game jeeves director-serve \
  --project ./original_game --session hero_a --port 8765
```

This is a foreground command; stop with Ctrl+C. It binds only 127.0.0.1,
accepts an exact local Host and bearer token, sends `Cache-Control: no-store`,
rejects browser Origins, and does not enable CORS or remote access. The secret
is not printed or stored in the project by the service. You must provide the
same token to the Godot UI manually.

In a **second terminal**, export the Godot project:

```bash
python -m skeleton dev game jeeves director-atlas-export \
  --project ./original_game \
  --source design/director_campaign_source.json
python -m skeleton dev game jeeves director-atlas-verify \
  --project ./original_game \
  --source design/director_campaign_source.json
```

Open the generated `build/director_atlases/<world-identity>-live-v3/project.godot`
in Godot 4. The versioned live project can coexist with an older scene-only export; the original preview now has a **Play live Director quests**
button opening `director_player.tscn`. Enter the local port and bearer token,
press Connect, inspect live quest availability and choose an allowed action.

Each action goes through the authoritative Python `Director.step` transition,
not a Godot-side guess. The response contains an up-to-date quest-progress
snapshot, narrative flags, stage consequences and new authored cinematic cues.
The Godot UI does **not** implement full 2D/3D sprite production or timed
cinematic playback. It is an authentic native UI driving the existing game-logic
runtime, contingent on a running local Python companion service.

### Local JSON API

All endpoints require `Authorization: Bearer <token>` and a loopback Host.

| Verb/path | Purpose |
|---|---|
| `GET /v1/health` | Local transport and runtime status |
| `GET /v1/status` | Replayed authoritative session snapshot |
| `POST /v1/actions` | Submit one legal `kind:key` choice with expected sequence/state |

A POST must contain exactly:

```json
{
  "choice": "wait:wait",
  "expected_sequence": 0,
  "expected_state_sha256": "<64 lowercase hexadecimal characters>"
}
```

The digest comes from the latest `GET /v1/status` response. The Director
journal checks the expected sequence/state again **under its exclusive write
lock** before publishing an append-only action receipt. Invalid, stale or
unavailable choices are rejected; the bridge never directly writes invented
quest victories.

## 2. Narrative presentation attached to actual results

The action response optionally includes `presentation` with newly completed
quest stages, narrative flags and authored cutscene cue timelines. Timelines
are selected only from the approved world after revalidating the actual session
head. This is the adapter seam for later camera motion, animation, subtitle,
voice, audio and scene-engine playback.

The UI currently **lists** typed cue timestamps and reasons. Actual cinematics,
asset rendering, voice performances and adaptive audio are not yet implemented.

## 3. Dragon comparison laboratory

Create two or more independent live Director sessions and record choices in
each. Then:

```bash
python -m skeleton dev game jeeves dragon-lab \
  --project ./original_game --sessions hero_a,hero_b

# After reviewing its research_sha256:
python -m skeleton dev game jeeves dragon-lab \
  --project ./original_game --sessions hero_a,hero_b \
  --approve <research_sha256>
```

The lab supports 2–10 sessions per comparison call, **not** a project-time or
session-count lifetime limit. It independently replays every selected session,
checks identical world identities, compares scene visits, interaction counts,
turns, stage coverage and different actual quest choices, and reports open
knowledge gaps. Approved reports are immutable, content-addressed documents in
`.jeeves/dragon_replay_candidates/`.

It does not infer player enjoyment, hallucinate tester identities, harvest
unlicensed games, train checkpoints or claim hardware FPS measurements.

## 4. Deep quest solution and narrative coverage

```bash
python -m skeleton dev game jeeves director-coverage \
  --project ./original_game \
  --source design/director_campaign_source.json --routes 8
```

This runs the selected strategies with and without optional objectives, up to
16 independently replay-verified route variations per pass. It records exercised
and missed quest solution keys, unfinished creative branches, cinematic links,
unique cast and audio cues. Workorders identify underexplored gameplay methods.

This is **bounded sample coverage**, not a proof every imaginable ending is
reachable or that a rendered installation has been tested.

## 5. Actual native Godot 4 import/startup smoke (opt-in)

After exporting the versioned live atlas, the CLI can invoke an **actual**
locally resolved Godot 4 executable for a headless source import plus a
headless atlas scene start and live quest UI start:

```bash
python -m skeleton dev game jeeves director-godot-smoke \
  --project ./original_game \
  --source design/director_campaign_source.json --timeout 90
```

The runner first verifies every exported source file, then checks the Godot
version. It runs `--headless --import` and separately starts
`res://main.tscn` and `res://director_player.tscn` for a small smoke frame
window. Every process has its own bounded timeout, and the server bearer token
is removed from its environment. A successful run is **genuine local Godot
source execution evidence**, but not an automated completed native game,
connected HTTP integration acceptance, quality certification or first install.
If no Godot binary exists, it reports an explicit incomplete diagnostic.

## 6. Regression suites and realistic acceptance

```bash
python -m unittest tests.test_jeeves_director_local_http
python -m unittest tests.test_jeeves_director_live_bridge
python -m unittest tests.test_jeeves_director_interactive
python -m unittest tests.test_jeeves_director_production
```

These specialized tests exercise HTTP request validation, real session actions,
stale-client rejection, event delta integrity, completed Director quest logic,
Godot source generation and Dragon comparison. No additional compulsory
GitHub Actions workflow, gate, or recurring notification is installed.

**Remaining blockers:** Run Python regressions on the installed repository;
open and debug the exported project with an actual Godot 4 binary; bind real
controller/scene assets to the UI; implement visual/cinematic/audio execution,
native save parity, independent quality review and measurable model checkpoint
training before declaring full game-production readiness.
