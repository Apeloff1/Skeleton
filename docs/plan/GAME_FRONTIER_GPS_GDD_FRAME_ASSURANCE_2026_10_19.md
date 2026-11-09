# Skeleton Game Frontier: Live GPS, Survey and GDD Frame Coherence

2026-10-19 | Development branch: `feature/game-frontier-p0-p3-20261019`

## L00 — scope

Implement bounded, consent-only, foreground positioning (actual web browser
geolocation; native adapter interface pending binary integration), engineering
surveyed positions from human-verified WGS84 controls, 30/50/60/120 Hz frame
chunk verification and immutable between-frame AI notes rooted in the signed
Game Design Document. Do not assume actual user location is available. The
user's current device and permissions have not been interrogated from this
repository development activity.

## L01 — canonical owners

- Location ingestion: `skeleton/jeeves/game_frontier_geoposition.py`.
- UI browser location source: `frontend/src/product/frontierLiveGPS.ts`;
  `frontend/app/frontier-navigation.tsx`.
- Frame observation/proof: `skeleton/jeeves/game_frontier_frame_coherence.py`.
- Existing source-of-truth GDD: `skeleton/ai/game_builder/story_canon_fabric.py`
  with `validate_story_bible`, `sign` and `story_bible_template`.
- Existing RPG project owner: `skeleton/forge/game_frontier_studio.py`.
- Existing scene owner: `skeleton/jeeves/game_frontier.py`.
- Read-only realism observer: `skeleton/jeeves/game_frontier_realism.py`.
- No second GDD writer, provider router, location store, frame store or AI agent
  has been introduced. Durable operations still use existing system owners.

## L02 — GNSS and survey contracts

`LocationConsent`: explicit user acknowledgement and single
`foreground_precise_session` permission with start/end UTC milliseconds,
purpose and session ID. Host operating system remains final permission
authority. `DeviceGPSFix`: WGS84 geodetic location, altitude, separate
horizontal and vertical uncertainty, host timestamp, monotone sequence and
attested `host_os_gnss` origin. Stale, coarse, future, replayed, or
implausibly fast fixes are rejected before receipt promotion.

`SurveyControl`: user-verified WGS84 control; `SurveySighting`:
true horizontal azimuth, angular uncertainty and optionally independent
range. At least two nonparallel sight lines are required. The local tangent
solver accepts <=50 km control geometry, excludes polar/antimeridian use,
measures weighted least-squares cross-track RMS and line separation, checks
optional ranges independently, and produces a horizontal engineering
position with altitude deliberately unknown.

`reconcile_live_and_survey` compares the independent positions against
combined uncertainty (default 3σ), never silently overwriting either
source or claiming legal cadastral surveying. Professional fixes still
require known surveyed benchmarks, a precise geodesic datum and geoid
model, independently checked elevation, calibration and human signoff.

## L03 — live acquisition / trust boundary

Browser: explicit Start button -> browser GPS watch -> accuracy/freshness
filter -> ephemeral screen display; Stop/Clear removes watcher and erases
the last in-memory screen reading. The watcher ends when page visibility
is lost. No network transmission, analytics or local storage are performed
by this implementation. Existing device OS may still have separate location
history; this source makes no claims about OS retention.

Mobile Expo SDK 54 Android/iOS: a typed
`ForegroundNativeAdapter` injection surface is implemented, but no
`expo-location` dependency or native prebuild permission plugin is
installed here. Native device GPS therefore remains **unverified/open**
until the platform-owner binary is built and tested with user permissions,
AppState pause and revocation. Do not claim native positioning is active.

## L04 — per-frame source chunking and coherence

`FrameObject` contains stable entity ID, physical position and velocity,
immutable source digest. `advance_frame` uses deterministic XY chunk
partition and stable ordering. A frame owns monotone frame index, a
presentation-timing timestamp, signed-GDD digest, prior receipt digest,
and optional between-frame notes. Supported presentation rates:
30, 50, 60, 120 frames per second.

Verifier A independently regenerates canonical SHA-256 hashes of each
chunk and the entire frame; it also checks recorded source identity and
receipt integrity. Verifier B independently checks GDD version, frame
clock/index, exact prior digest, object identity conservation, velocity-
bounded movement, correct chunk keys, duplicates and note law indices.
Both verifiers must pass before the candidate advances; invalid frames
fail closed. The per-frame system is currently **opt-in to the scene and
Studio candidate builders**, not yet activated in every native engine
render loop. Existing era-neutral mesh dual verification remains distinct.

## L05 — between-frame AI context and GDD law

`bind_signed_gdd` reuses the canonical
`story_canon_fabric.validate_story_bible`, verifying rights/status fields
and SHA-256 signature. Notes have explicit category, author type and
`world_law_index` referencing one of the signed document's immutable
laws. An AI-written note is never promoted to canon merely because a frame
passed integrity checks; human GDD signoff remains independent.

`ai_design_context` reconstructs a readable evidence-limited context from
verified frame history. For long workflows, `advance_context_cursor`
stores at most 64 recent notes with digest-linked source and a running total,
avoiding repeated complete frame rescans; its own digest is checked before
advancing. A frame or note mismatch rejects further AI-context propagation.
Only the existing Jeeves provider runtime may actually call models.

## L06 — build and studio integration

`game_frontier.py` accepts optional consented GPS, survey stations, source
frames, previous receipt, signed GDD and notes; coordinates are ephemeral
function-local objects only. The emitted scene manifest stores non-sensitive
position/uncertainty evidence and verified frame hashes and notes, and
the cognition section references the exact GDD and frame digest.

`compile_studio_frame` uses actual authored `StudioProject` placements,
stable prefab asset digests and source speed observations. It rejects
cross-project GDD substitution, skipped frames, unverified predecessors and
object disappearance without explicit owner authority. Efficient cursor
mode requires exact prior verified receipt and cursor lineage. This does not
run a game, modify the GDD, or save a world.

## L07 — security and privacy

Raw GPS or surveyed lat/lon must not enter scene hash inputs, AI model
prompts, issue bodies, logs or analytics by default. Redacted receipts
contain source, uncertainty, coarse metadata and a consistency judgement.
Sensitive location is shown to the consenting user only inside the active
front-end session. No background permissions requested; no automatic
startup, retention, external geocoding or IP/geolocation fallback.

Survey controls can themselves disclose sensitive points; they are
explicitly supplied by the operator and must be treated as private,
not posted to telemetry or learned weights. Current source has no
persistent survey repository and cannot claim data deletion at provider/
OS level.

## L08 — failure, replay and recovery

- GPS permission absent/expired, accuracy too low, future/stale timestamp,
  out-of-order sequence, impossible displacement -> reject, do not guess.
- Survey controls insufficient, near-parallel, out of local tangent range,
  uncertain or conflicting range -> reject, no invented fix.
- Signed GDD invalid/changed, frame hash or prior link corrupt, motion
  discrepancy or note unknown to world laws -> block advancement.
- Active frame note cursor cannot be replayed from a different source GDD
  or receipt head. Recover through canonical historic receipts.
- Read-only receipts do not authorize changes to game design, game state,
  location stores, player identity, quest or world progression.

## L09 — resource bounds

Frame candidate: <=65,536 objects; 32 between-frame notes; fixed supported
rates. Context cursor retains <=64 notes. Exact source snapshots can be
large; storage/backpressure and network budgets require canonical runtime
admission. GPS watcher updates are generated by OS/browser; no synthetic
high-frequency polling loop.

## L10 — metrics and observability

Report horizontal GPS uncertainty, age/replay rejection, surveyed control
count, angular separation, RMS residual, estimated uncertainty and GPS vs
survey disagreement (without raw coordinates). For each build frame report
two separate verifier results, chunk count, spatial movement, previous/
current receipt digests, signed GDD identity, missing/context truncation and
unapproved note types. Do not compress these into a fictitious SOTA score.

## L11 — operator UI

The `/frontier-navigation` route supports Start foreground GPS, Stop/Clear,
quality readout and visible source status in browser. Surveyed position
authoring UI remains open; current survey solver is callable through typed
Jeeves/Studio inputs, not a user-visible full field-survey instrument yet.
The project author must approve any use of real position in game assets.

## L12 — release and canary validation

Focused GitHub regression covers synthetic GPS permission failures,
replay/spoof/outlier rejection, nonparallel control resection, conflicting
range, redaction, GDD source tampering, 30/50/60/120 per-frame chunk movement
and double verification, an 80-frame cursor stress pass, scene and RPG Studio
integration. The CI suite does not exercise a device GPS sensor, install
the native Expo location package, execute a complete Godot renderer or
run a 6-month world build. These tests must happen before release.

## L13 — adversarial and signoff

Independent source audit must attempt GPS source spoof, mixed datum,
antimeridian, insufficient control geometry, leaked coordinates,
time reversal, frame receipt mutation, GDD substitution, AI canon
promotion, missing frames, chunk-boundary migration and checkpoint
corruption. Production signoff requires a legal/privacy review,
operator-controlled retention and opt-out, calibration uncertainty,
engine-wide frame-time evidence and real device operation.
