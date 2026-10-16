# Jeeves original game media and full-quest transport acceptance

This milestone slice targets three concrete production gaps: original playable
media, completed route execution over **actual** Python HTTP, and an optional
cross-process **Godot 4 HTTP input** qualification.

Every source file is create-only on export; no game user's session or existing
Godot atlas is deleted or overwritten. New exports are versioned
`build/director_atlases/<world-id>-live-v4/`, preserving v1/v2/v3.

## 1. Original procedural art and score files, not just scene descriptions

```bash
python -m skeleton dev game jeeves director-atlas-export \
  --project ./original_game --source design/director_campaign_source.json
python -m skeleton dev game jeeves director-atlas-verify \
  --project ./original_game --source design/director_campaign_source.json
```

The exporter now generates a deterministic RGB PNG panorama for **each
author-approved Director scene** using its lighting/weather/name and world
identity, plus a short original WAV sound loop for **each distinct scene music
cue**. These are self-contained assets: no online content, scraping,
third-party soundtrack or unlicensed game ROM is used. The atlas project
includes `media_catalog.json`, individual `media/scene_*.png` and
`media/score_*.wav` files with exact SHA-256 identities.

The Godot stage actually loads these backdrops and uses an
`AudioStreamPlayer` to play the original generated score upon scene arrival;
the UI includes a **Mute / play original score** control. The animated actor
and foreground silhouettes remain stylistic scaffolds—not professional
animation assets. Generated tones are **not** mastered orchestral music.

Verification recomputes original media bytes, hashes them and all Godot
scripts, allows Godot's expected import cache and asset `.import` sidecars,
and rejects tampering, foreign files, or source symlinks. This is source
integrity only until actual native Godot execution succeeds.

## 2. Actual complete campaign over HTTP, with crash/restart recovery

```bash
python -m skeleton dev game jeeves director-loopback-e2e \
  --project ./original_game \
  --source design/director_campaign_source.json --routes 3
```

This command creates an **isolated temporary project** from the exact
reviewed world source, starts an authenticated loopback HTTP server, and
submits every action required by the canonical full-campaign witness through
real `POST /v1/actions` requests. For each selected strategy, it:

- verifies legal action receipts and sequence progression;
- restarts the entire HTTP service at the midpoint and checks its game-state
  rehydration from append-only on-disk journal receipts;
- finishes **all approved story quests and stages** and checks final state
  hash parity against independently replayed canonical Director state;
- resubmits a stale first action, requiring HTTP 409;
- discards the isolated game and journals after the test.

The route count is a test-strategy parameter, **not a lifetime game recording
limit**. Every action in each selected game route is executed; the runner does
not artificially stop after 256 actions. It is nonetheless a Python HTTP
integration test and **not** a visual Godot playthrough or human evaluation.

## 3. Genuine optional Godot ↔ Python interoperability

```bash
python -m skeleton dev game jeeves director-native-http-e2e \
  --project ./original_game \
  --source design/director_campaign_source.json --timeout 90
```

If an actual configured Godot 4 binary is available, this independently:

1. clones the approved world into temporary storage;
2. exports and verifies its media-backed native project;
3. invokes an **actual Godot process** for headless source import;
4. starts a real Python loopback Director service for the clone;
5. invokes Godot again with `director_probe.gd`, a SceneTree script that
   reads authoritative state over HTTP, submits the legal `wait:wait`
   action and requests a refreshed state;
6. independently validates that Python's session journal advanced by
   exactly one action and that Godot printed its success marker.

This checks real Godot HTTP transport/JSON interoperability; it is **not**
the same as playing every quest from Godot's visual scene. If Godot is absent,
the command reports an explicit incomplete result rather than claiming a
pass. The one-time bearer credential exists only in a temporary environment
and is never printed or included in results.

For source parsing/startup smoke of both full UI scenes, also run:

```bash
python -m skeleton dev game jeeves director-godot-smoke \
  --project ./original_game \
  --source design/director_campaign_source.json --timeout 90
```

## 4. Specialized regression commands

```bash
python -m unittest tests.test_jeeves_director_media_e2e
python -m unittest tests.test_jeeves_director_local_http
python -m unittest tests.test_jeeves_director_live_bridge
python -m unittest tests.test_jeeves_director_branch_policy
```

These cover deterministic original PNG/WAV format, import sidecars and tamper
rejection, complete local HTTP campaign/recovery/stale-client behavior,
and the important **fail-closed** native boundary: a spoofed Godot process
success marker alone does not qualify an unexecuted canonical action.

The work does not install recurring workflow triggers or compulsory CI gates.
Native visual scene execution and complete graphic playthrough, high-fidelity
original art, sound mastering, professional story/canon review, checkpoint
training, and first-install packaging still require real evidence before
full game-production readiness can be signed off.
