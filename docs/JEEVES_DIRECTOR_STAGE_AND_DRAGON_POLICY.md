# Jeeves Director playable stage, branching and Dragon policy milestones

This slice extends the real canonical Director gameplay client and Dragon
companion without adding a global CI workflow or treating a UI scaffold as a
finished commercial game.

## 1. Native original procedural stage + controller interaction

The Godot 4 atlas exporter now adds `director_stage.gd`, an original,
self-contained 2D stage that procedurally draws landscape layers, buildings,
lighting/sky and the approved scene's cast as simple actor markers. No
copyrighted image/audio content is pulled into the project.

Open the existing live Godot quest interface from the atlas. The controls
appear immediately **below** the stage instead of obscuring the scenery.

| Control | Function |
|---|---|
| Godot UI Up/Down/Left/Right or controller D-pad | Move between legal Director actions |
| Gamepad A or **Act / A** button | Submit current action to Python Director |
| Gamepad B | Skip the local cinematic presentation, not gameplay |
| Gamepad Start | Pause/resume presentation |
| Gamepad X | Refresh canonical quest state |
| Cue x0.25 / x1 / x2 / x4 | Control the local cutscene clock |

A physically connected controller is still subject to Godot input mappings
and runtime verification. The bridge rejects unavailable or stale input, and
all quest consequences are computed in the original Python engine.

## 2. Authored cinematic cue clock

The procedural stage queues only the typed scene timelines returned by the
source-verified live Director action service. It consumes authored cue
timestamps and duration while playing live camera pan/zoom, cast entrance/exit,
environment/lighting changes and text/voice/music **cue descriptions**.

Unsupported cinematic/audio/media production is NOT silently presented as
rendered work. The local timeline player supports pause, resume, speed-up,
slow-down, and skipping presentation while preserving the authoritative
action journal. Actual voice synthesis, animation libraries, licensed original
assets, frame-complete camera direction, audio playback and native hardware
quality remain separate unverified implementations.

Godot UI tree reconstruction now runs outside the reserved `Control._draw`
callback. The stage script alone performs custom procedural drawing.

## 3. Fork and replay without overwriting the original game

```bash
python -m skeleton dev game jeeves director-session-trace \
  --project ./original_game --session hero_a --tail 64

# Inspect the returned head_sha256; preserve the original session.
python -m skeleton dev game jeeves director-session-fork \
  --project ./original_game \
  --session hero_a --other-session alternate_ending \
  --at 12 --approve <original_head_sha256>

python -m skeleton dev game jeeves director-session-status \
  --project ./original_game --session alternate_ending
```

Forking to a recorded sequence creates a new create-only session with a
different integrity chain but the **same exact Director state** at the fork
point. Its genesis manifest includes an immutable parent session identity,
parent head SHA-256 and fork sequence. Source drift, forged receipts and stale
approval are rejected. A fork preserves the original run and can diverge
independently thereafter.

The `--tail` cap limits only how many entries are printed, not game duration.
This is replay-backed logic-state recovery, not native Godot savegame parity.

## 4. Real local Dragon empirical micro-model training

The Dragon companion now has a *small actual fitted model* for local gameplay
actions. This is **not** production Jeeves LLM transformer training.

1. Record at least three distinct, consent/rights-appropriate original game
   sessions using the canonical Director actions.
2. Preview the empirical context-to-action counts and held-out-session results.
3. Explicitly approve the exact digest to persist the micro-model weights.
4. Ask for advisory legal actions in a separate game session.

```bash
python -m skeleton dev game jeeves dragon-policy-preview \
  --project ./original_game --sessions hero_a,alternate_ending,review_route

python -m skeleton dev game jeeves dragon-policy-train \
  --project ./original_game --sessions hero_a,alternate_ending,review_route \
  --approve <model_sha256>

python -m skeleton dev game jeeves dragon-policy-predict \
  --project ./original_game --session fresh_run --digest <model_sha256>
```

The model fits empirical action counts per world/scene/quest-progress context,
with the final named session held out from parameter estimation. Reported
held-out accuracy is **only over contexts observed in training**. The model
abstains when nothing was previously learned about the active quest state.
Any change to referenced training journals or game sources invalidates the
checkpoint's admissibility. Parameters are content-addressed and published
create-only under `.jeeves/dragon_policy_checkpoints/`.

The model does not invent user tastes, measure independent player
satisfaction, update transformer/production LLM weights or automatically
execute selected advice.

## 5. Optional Dragon advice in live Godot game

After training a model, start the local server with its checkpoint digest:

```bash
export SKELETON_DIRECTOR_BRIDGE_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(36))')"
python -m skeleton dev game jeeves director-serve \
  --project ./original_game --session fresh_run --port 8765 \
  --digest <model_sha256>
```

The Godot **Ask Dragon** button calls `GET /v1/advice` using the existing
loopback token. Advice is shown only if it matches the visible canonical
state SHA-256, and is never auto-executed. The service does not serve an
advisory endpoint unless the user explicitly enables a verified model.

## Specialized verification, no compulsory CI gate

```bash
python -m unittest tests.test_jeeves_director_branch_policy
python -m unittest tests.test_jeeves_director_live_bridge
python -m skeleton dev game jeeves director-godot-smoke \
  --project ./original_game \
  --source design/director_campaign_source.json
```

The regression suite covers immutable fork ancestry, replay drift, real
fitted parameter values, a held-out session, source/inference identity,
local authenticated advisory service, nonexecution of recommendations, and
the Godot procedural source package.

**Still needed:** execute Python tests and Godot startup; test a physical
controller and real renderer; build final art/audio, actual NPC animation,
physics, scene transition and timed performance quality; train and evaluate
the real production checkpoint; and complete a consumer first-install,
save/load and full visual gameplay run.
