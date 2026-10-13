# Animation State Machine & Frame-Timing Spec

Owner: Animation Lead (Yosh) · Contract version: `anim.timing.v1` · Status: active

This spec describes what `backend/routes/animation_pipeline.py` (prefix
`/api/animation-pipeline`) actually does. Items marked **(proposed)** are
not implemented yet. They are design intent for later PRs and are not
something consumers can rely on today.

Tests that enforce this spec: `backend/tests/test_animation_pipeline.py`
(`TestHitFrameContract`, `TestStateMachineGuards`, `TestReducedMotion`,
`TestTimingEndpoints`, `TestBlendTreeCoverage`, `TestAIFallback`).

---

## 1. Units and conventions

| Term | Definition |
|---|---|
| `fps` | Authored clip frame rate. Generated clips use `DEFAULT_FPS = 30`. |
| frame | 0-based integer index from clip start at the clip's `fps`. |
| `end_frame` | Exclusive. A phase `[start_frame, end_frame)` has `frames = end_frame - start_frame`. |
| `time` | Seconds, always derived as `frame / fps` (rounded to 4 dp). Frames are authoritative and times are for display only. |
| duration | Seconds. Requests accept `0.1 ≤ duration ≤ 120` (`MIN/MAX_ANIMATION_DURATION_SECONDS`). Values outside that range return 422. 0.1 s is 3 frames, one per combat phase. |

---

## 2. Canonical states

### 2.1 Locomotion (looping)

`LOOPING_STATES = {idle, walk, jog, run, sprint, strafe, crouch, fall, swim, block}`.
A state in this set gets `loop: true`. Every other state is a one-shot clip.

| State | Clip family | Notes |
|---|---|---|
| `idle` | idle | Breathing at 4 s and weight shift at 6 s (templates). Usually the default state. |
| `walk` | locomotion | Template 1.0 s cycle at 1.4 m/s. |
| `run` | locomotion | Template 0.6 s cycle at 5.0 m/s. |
| `sprint` | locomotion | Template 0.4 s cycle at 8.0 m/s. |
| `fall` | air | Loops until `grounded`. |

### 2.2 Combat / reactive (one-shot unless noted)

| State | Entered via | Exits via (auto mode) |
|---|---|---|
| `attack` | any-state `attack_trigger` (priority 20) | `anim_complete` (exit time 1.0) → default |
| `jump` | any-state `jump_trigger` (priority 40) | `jump → fall` on `anim_complete` if `fall` exists, else `grounded` → default |
| `land` | `fall → land` on `grounded` | `anim_complete` → default |
| `dodge` | any-state `dodge_trigger` (priority 60) | `anim_complete` → default |
| `hit_react` | any-state `hit_trigger` (priority 80) | `anim_complete` → default |
| `block` | (authored) | Looping hold pose (template `hold_pose: true`) |
| `death` / `dead` | any-state `health <= 0` (priority 100) | **Terminal.** No outgoing transitions. |

---

## 3. Transition table and guards

### 3.1 Auto-generated transitions (when the request has `transitions: []`)

A transition is only created if both endpoint states are declared.

| From | To | Condition | Blend (s) | Notes |
|---|---|---|---|---|
| idle | walk | `speed > 0.1` | 0.25 | hysteresis enter |
| walk | idle | `speed < 0.05` | 0.25 | hysteresis exit |
| walk | run | `speed > 0.5` | 0.25 | |
| run | walk | `speed < 0.45` | 0.25 | |
| run | sprint | `speed > 0.85` | 0.25 | |
| sprint | run | `speed < 0.8` | 0.25 | |
| jump | fall | `anim_complete` | 0.25 | `has_exit_time`, `exit_time: 1.0` |
| fall | land | `grounded` | 0.25 | |
| land | *default* | `anim_complete` | 0.25 | |
| any | death | `health <= 0` | 0.1 | priority 100 |
| any | hit_react | `hit_trigger` | 0.1 | priority 80 |
| any | dodge | `dodge_trigger` | 0.1 | priority 60 |
| any | jump | `jump_trigger` | 0.1 | priority 40 |
| any | attack | `attack_trigger` | 0.1 | priority 20 |
| *one-shot w/o exit* | *default* | `anim_complete` (or `grounded` for jump/fall) | 0.2 | dead-end fill |

The locomotion thresholds use hysteresis on purpose: the enter threshold is
above the exit threshold. That stops a speed sitting on a boundary from
flickering between clips every frame.

### 3.2 Guards (enforced)

Request validation rejects these with **422**:

- Duplicate state names, or a name that is empty or longer than 100 characters.
- A `default_state` that isn't in `states`.
- A transition `to` that isn't a declared state.
- A transition `from` that isn't a declared state or `"any"`. These used to be silently dropped.
- Any transition *from* a terminal state (`death`, `dead`).
- `duration` that isn't a number or falls outside `[0, 2.0]` s (`MAX_TRANSITION_BLEND_SECONDS`).
- `priority` that isn't an integer in `[-1000, 1000]`.
- `condition` that isn't a string or is longer than 500 characters.

Rules applied when the machine is generated:

- Every any-state transition carries `can_transition_to_self: false`. A
  re-trigger (combo) has to be an explicit authored transition.
- Every any-state transition carries `excluded_source_states`, which lists
  the terminal states. A dead character can't be pulled into `hit_react`.
- `any_state_transitions` are sorted by `priority`, highest first. When
  several conditions fire on the same frame, the highest one wins.
- Transitions on `anim_complete` get `has_exit_time: true, exit_time: 1.0`.
- Interruption source is `current_then_next` for all transitions.

### 3.3 Parameters

The generator infers parameters from both state and any-state conditions:

| Pattern | Type |
|---|---|
| `*_trigger` | `trigger` |
| identifier used with `< <= > >= == !=` | `float` (default 0) |
| bare identifier (e.g. `grounded`) | `bool` (default false) |
| `anim_complete`, `and`, `or`, `not`, `true`, `false` | not a parameter |

### 3.4 Graph validation (reported, not rejected)

Every generated machine includes `validation`:

```json
{ "valid": true, "unreachable_states": [], "dead_end_states": [],
  "terminal_states": ["death"], "terminal_states_with_exits": [] }
```

- **Unreachable**: no path from `default_state` through state transitions
  plus any-state targets. Any-state transitions don't fire from terminal
  states.
- **Dead end**: the state isn't looping, isn't terminal, and has no outgoing
  transition, so the character would freeze on the last frame. Auto mode
  fills these with exits. Authored machines are reported but left as written.

---

## 4. Frame-timing and readability budgets

### 4.1 Combat phases

Every combat clip is split into three phases that tile the clip exactly:

```
| anticipation | active (contact) | recovery |
0           hit_frame        active_end    total_frames
```

Phases come from the move template's `damage_window`, normalised to the
template duration and scaled to the requested duration
(`compute_combat_phases`). Each phase is clamped to at least 1 frame.

| Move (template) | Duration | Frames @30 | Anticipation | Active | Recovery | `hit_frame` |
|---|---|---|---|---|---|---|
| `light_attack` | 0.5 s | 15 | 6 | 4 | 5 | 6 |
| `heavy_attack` | 1.0 s | 30 | 12 | 6 | 12 | 12 |

If no duration is given, a combat clip uses its move's authored length:
"powerful/aggressive/strong" maps to heavy, otherwise light. That keeps
default output inside budget.

Pose placement in generated combat keyframes:

- The wind-up peaks at `hit_frame − max(1, anticipation // 3)` and holds
  into contact.
- The strike pose lands **exactly** on `hit_frame`.
- Follow-through lands on the end of the active window.
- The return to neutral lands at the end of the clip.

### 4.2 Readability budgets (frames @30 fps, scaled linearly by `fps / 30`)

| Weight class | Anticipation | Active | Recovery |
|---|---|---|---|
| light | 4 – 12 | 2 – 8 | 4 – 15 |
| heavy | 10 – 24 | 3 – 10 | 8 – 30 |

Rationale:

- Under about 4 frames (133 ms) of anticipation, a telegraph can't be read
  at gameplay speed.
- Heavy moves have to sell weight, so they need at least 10 frames of
  wind-up.
- Recovery above the maximum makes a move feel sluggish and uncancellable.

A breach shows up as a **warning** (`readable: false`). A broken contract
shows up as an **error** (`valid: false`). Contract errors are:

- A phase shorter than 1 frame.
- Phases that don't sum to `total_frames`.
- No hit frame.
- A hit frame outside `[active_start, active_end)`.
- Unsorted or duplicate hit frames.

Generated combat clips report the result in `animation.timing.readability`.

### 4.3 Blend times (`BLEND_TIME_DEFAULTS`)

| Family | Default |
|---|---|
| locomotion ↔ locomotion | 0.25 s |
| any-state entry (combat, reactive) | 0.10 s |
| one-shot exit to default | 0.20 s |
| hard ceiling for any transition | 2.0 s |

**(proposed)** Entering `hit_react` or `death` should snap at 0–2 frames
(≤ 0.066 s) rather than 0.1 s, so the reaction lands on the impact frame.
Entering `attack` from a recovery cancel window should blend no more than
0.05 s.

### 4.4 Endpoints

- `GET /api/animation-pipeline/timing/budgets` returns the contract version,
  budgets, blend defaults, and the computed presets for `light_attack` and
  `heavy_attack`.
- `POST /api/animation-pipeline/timing/validate` checks authored timing:

```json
{ "fps": 30, "weight_class": "light", "anticipation_frames": 6,
  "active_frames": 4, "recovery_frames": 5, "hit_frames": [6], "total_frames": 15 }
```

It returns `valid`, `readable`, `errors[]`, `warnings[]`, the scaled
`budget`, and `active_window`.

---

## 5. Hit-frame sync contract (VFX + audio)

**There is one timing source.** Animation owns contact timing. VFX (combat
VFX cue catalog, `feat/forge-combat-vfx`) and audio both key off the same
field, so there are no separate timing tables.

- Every **contact** event carries an integer **`hit_frame`**: the 0-based
  frame index from clip start at the clip's authored `fps`. The name is fixed
  as `hit_frame`. Don't alias or rename it.
- `hit_frame` always falls inside the active window:
  `phases.active.start_frame ≤ hit_frame < phases.active.end_frame`. In
  generated clips it equals `phases.active.start_frame`.
- Each event's `time` field is `hit_frame / fps`, provided for convenience.
  Consumers that need to sync must use `hit_frame`, not `time`.

Combat clips emit these events in frame order:

| `type` | `frame` | Extra fields |
|---|---|---|
| `anticipation_start` | 0 | |
| `contact` | `hit_frame` | `hit_frame` (int), `weight_class`, `cue_hooks: ["vfx", "audio"]` |
| `damage_start` | `hit_frame` | kept for existing consumers |
| `damage_end` | active `end_frame` | |
| `recovery_start` | active `end_frame` | |

Consumer rules:

1. VFX spawns impact cues on `hit_frame`. Audio fires impact SFX on
   `hit_frame`. Neither adds its own offset table. Any intentional lead or
   lag (e.g. a whoosh before contact) has to be expressed relative to
   `hit_frame`.
2. If a clip is resampled to another fps, consumers rescale with
   `round(hit_frame * new_fps / fps)`. Animation stays the authority.
3. Multi-hit clips **(proposed)** emit one `contact` event per hit, each
   with its own `hit_frame`. `/timing/validate` already accepts a sorted list
   of `hit_frames` within the active window.
4. **(proposed)** Locomotion clips emit `footstep` events with an integer
   `contact_frame` for foot plant, so footfall audio and dust VFX use the same
   frame-index convention.

---

## 6. Reduced motion

Client source of truth: `frontend/src/hooks/useReduceMotion.ts`, which reads
the OS reduce-motion setting through `AccessibilityInfo`. The server side is
`AnimationGenerationRequest.reduced_motion: bool` (default false).

When `reduced_motion` is true (enforced):

- **Gameplay timing never changes.** Phases, `hit_frame`, all events,
  keyframe times, and root travel stay identical
  (`accessibility.timing_preserved: true`).
- Locomotion: vertical root bob is removed (`root_bob_enabled: false`) and
  spine twist is halved.
- Idle: breathing and shoulder sway amplitude is halved
  (`cosmetic_motion_scale: 0.5`).
- Responses include an `accessibility` block that records what was applied.

**(proposed)** The client should also suppress camera shake, hit-stop zoom,
and full-screen flashes driven by `contact` events, but still play the event.
A reduced-motion player must still get the hit confirm through audio and a
static VFX variant.

---

## 7. Level-design scaling (proposed)

**(proposed)** Level design's numeric per-room `intensity` and
`encounter_density` tags may scale anticipation and recovery budgets, but
never the active window or `hit_frame` semantics:

- High `encounter_density` (many attackers on screen) moves enemy
  anticipation toward the top of its budget range, so each telegraph stays
  readable in a crowd.
- High `intensity` may tighten player recovery toward the budget minimum, so
  the player feels faster in climactic rooms.
- Scaling stays clamped to the budget ranges in §4.2, and each scaled clip
  still has to pass `/timing/validate`.

This isn't implemented. It needs an agreed tag range from level design and a
scaling curve before code lands.

---

## 8. Known gaps (tracked, not yet fixed)

- Interaction, emote, and cinematic clips use generic keyframes with empty
  transforms (placeholder output).
- Humanoid IK chains reference pole bones (`elbow_*`, `knee_*`) that aren't
  in the skeleton template.
- There are no cancel windows or combo branches in the state machine.
- Dodge `i_frames` are seconds in the template. They aren't converted to
  frames or validated against the dodge clip.
- Locomotion clips have no foot-contact events (see §5.4).
