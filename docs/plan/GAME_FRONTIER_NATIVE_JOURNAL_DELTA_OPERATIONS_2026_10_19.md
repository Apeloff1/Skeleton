# L00–L13 Native Game-Frame Capture, Source Delta and Replay Milestone

**Scope:** 2026-10-19 game-frontier continuation in
`feature/game-frontier-p0-p3-20261019`. Add usable state capture and
durable verification on top of the existing canonical signed GDD, in-game
physics, frame chunking, and Forge game exporter, without a second
game-state authority.

## L00: Operational workflow

1. Forge/Jeeves compiles an advanced game scene with a qualified
   `RigidBody`, signed `frame_gdd`, one source `FrameObject` whose ID
   matches that rigid-body, and double-verified source chunk evidence.
2. Call `emit_frontier_godot_overlay(scene, enable_native_capture=True,
   native_capture_max_frames=6000)`. The source overlay is still candidate
   code and **does not** become a production game automatically.
3. Authorize Forge materialisation with the existing project/file ownership
   controls; import/run it using the actual installed Godot 4 binary.
   Explicit opt-in initializes the built-in, fixed Godot 4 GDScript physics
   recorder and `Engine.physics_ticks_per_second` from the 30/50/60/120
   game-frame source configuration. The native rigid body is sampled on
   `_physics_process`, and frame 0 begins at the first post-ready physics
   callback. Each tick is recorded into the sandboxed engine file
   `user://frontier_native_physics.jsonl`, including engine-relative
   `Time.get_ticks_usec()`. Exporter itself does not run Godot.
4. Supply the actual signed GDD JSON, Forge
   `frontier/data/scene.json`, and a copy of the explicit engine capture
   to the operator-run importer:

   `python scripts/run_game_frontier_capture.py ingest
   --signed-gdd signed_gdd.json --scene-json frontier/data/scene.json
   --capture-jsonl frontier_native_physics.jsonl --journal frames.sqlite`

5. Independently verify and reopen the existing journal:

   `python scripts/run_game_frontier_capture.py verify
   --signed-gdd signed_gdd.json --scene-json frontier/data/scene.json
   --journal frames.sqlite`

6. Roll back **without deleting any old evidence** by forking a source
   prefix, choosing an existing verified checkpoint:

   `python scripts/run_game_frontier_capture.py fork
   --signed-gdd signed_gdd.json --scene-json frontier/data/scene.json
   --journal frames.sqlite --fork-track alternate_timeline --through 100`

   A new run must choose the new `--track`; default main history remains
   read-only and structurally intact.

## L01: Source and runtime authority

`game_frontier_frame_coherence.py` remains the unique signer-aware
engine-neutral frame verifier (independent A/B). `game_frontier_chunk_evidence.py`
reconstructs per-chunk actor movement, source IDs, retired chunk tombstones
and signed design notes. `game_frontier_receipt_journal.py` is a
**transactional persistence adapter**, not a new source of physics or
story canon. `game_frontier_native_capture.py` reads an explicitly
supplied native observation file; the real engine remains the source of
the measured kinematic values. No live real-world GPS is involved.

## L02: Protocol, formats and independent identity

- SQLite journal uses WAL and `synchronous=FULL`, one immediate
  transaction per committed frame, deduplicated SHA-256 content blobs and
  normalized frame/evidence/native/delta source references.
- Full source `FrameReceipt` is committed even when compact actor deltas
  are enabled; recovery therefore never **depends** on a lossy delta.
- Native physics observation declares schema, Godot 4 physics owner,
  source candidate digest, signed-GDD digest, fixed tick ID, monotonic
  engine microsecond clock, frame rate, actor/source asset digest, game
  XYZ position and game XYZ velocity. Its `authority` explicitly
  declares it an **untrusted** imported measurement, not a GPU
  certification or a cryptographic signature.
- `game_frontier_delta.py` records only actors whose pose/velocity/source
  changed, plus touched/retired chunk cells, signed GDD note context,
  source frame digest and previous frame digest. Reconstitution rebuilds
  typed `FrameObject`, runs the canonical frame builder, rechecks
  source identity and the **complete expected delta**.
- Every normalized reference is auditable through journal `replay()`;
  optional deltas can be selected with
  `FrameReceiptJournal.advance(..., include_delta=True)`.

## L03: Failure policy and replay

Unknown actors, incorrect asset provenance, duplicate native actor IDs,
nonfinite geometry, mismatched GDD/scene, missing frame, stale timestamp,
invalid FPS, physically impossible motion, source-chunk corruption,
tampered native data, altered delta, duplicate track/index and failed
independent verification are rejected before the journal advances.

A fork copies selected CAS references and verified frame indices, not a
mutable source-state snapshot. Both branches are reconstructible. WAL
transactions roll back all rows on error.

## L04: Limits and recovery

A fixed per-frame budget, 30/50/60/120Hz clock and an operator-selected
upper capture bound prevent unbounded capture through the Godot adapter.
JSONL input is streamed rather than executed. SQLite retains full source
receipts for independently verified replay; optional delta payloads make
unchanged actor data compact and are hashed back to their full source.
One frame retains one durable full frame, one per-chunk evidence bundle,
optional native measurement, and optional delta.

Production-scale save management, retention/compaction/remote backup and
crash reopening are separate existing owner concerns; this module does
not silently delete or rotate the only verified journal.

## L05: Explicitly out of scope

A successful Python replay **does not** demonstrate successful
Godot 4 parsing, import, Jolt physics, camera screenshots, shadow rendering,
cloth motion, correct interaction or actual 120 FPS sustained on any GPU.
Source-reported native JSONL is not remote attestation and could be
fabricated by a hostile client. Production signoff requires separately
measured engine binary provenance, native game state capture, renderer
screenshots and physically based acceptance against ground truth.

Only one Godot `RigidBody3D` is supported by the current native exporter.
A multi-actor frame may be recorded by the engine-neutral journal, but the
Godot capture path will reject unrecognized actors and requires an explicit
per-scene allow-list; it is not a complete multi-actor native engine hook.

## L06–L13: Remaining qualifications

- **P0:** actual binary Godot headless parse/playback; pre/post native
  contact proof; explicit inspector UI and authorized Forge app activation.
- **P1:** full multi-body native actor capture, physics callbacks, chunk
  streaming, shader/material and collision sensor fields; actor spawn/
  despawn only with signed event/canon authority.
- **P2:** batched multiworld replay, optical scene coherence and neural
  game agent critique of frame evidence without invented sensor state.
- **P3:** hardware FPS throughput and save durability, months-long
  replay/rollback, snapshots, proper retention, checksum scrubbing,
  provenance attestation and independent engine/installer qualification.

Do not mark P0–P3 complete until actual engine and long-run evidence
exists. The reference regression suite demonstrates executable source
contracts, not deployment.
