# P0–P3 Game Frontier: Source-Evidenced Chunking and Receipts

Date: 2026-10-19. Integration branch:
`feature/game-frontier-p0-p3-20261019`.
Owner: Jeeves game scene, Forge Studio and existing signed GDD authoring.
All receipts are **candidate source evidence**, never observations of a native
Godot/console GPU or independent operational signoff.

## L00 Scope and why these receipts matter

Older chunk implementations proved content identity, source mesh topology and
total triangle coverage, but exported mostly boolean results. Source-specific
chunk histories were not inspectable for every triangle, actor, frame and GDD
change. This pass adds immutable, content-addressed, replayable, scoped proof
records to **both** registered-era mesh chunking and frame-by-frame object
chunking. It also records evidence when a chunk becomes empty and retires.

## L01 Existing source authority

- Geometry owner remains `game_frontier_chunks.py`: `chunk_mesh`,
  `verify_chunks`, `verify_registered_era_chunks`. No second mesh engine.
- Frame/GDD owner remains `game_frontier_frame_coherence.py`: signed
  `GDDSource`, `FrameObject`, `FrameReceipt`, `GDDFrameNote`,
  independent SHA-256 verifier A and temporal/canon verifier B.
- Evidence adapter: `game_frontier_chunk_evidence.py`:
  `build_mesh_chunk_receipts`, `verify_mesh_chunk_receipts`,
  `build_frame_chunk_receipts`, `verify_frame_chunk_receipts`.
- Scene integration: `game_frontier.py` manifest keys
  `mesh_chunk_evidence` (only with `verify_all_era_chunks=True`) and
  `frame_chunk_evidence` (only with signed GDD/frame inputs).
- RPG Studio integration: `compile_studio_frame(...,
  previous_chunk_evidence=...)` emits the entire evidence bundle,
  `chunk_evidence_digest` and a GDD AI context hash link.
- Independent manifest inspection:
  `game_frontier_realism.py` checks exported receipt hashes, source
  anchors, coverage and migration accounting.
- Godot preview: compact `VerifiedChunkEvidenceInspector` shows the root,
  chunk count, migration count, retirement count, signed-note count and
  A/B claims; the full immutable records remain in Jeeves/Studio receipts.

## L02 Mesh per-chunk proof contents

Every `mesh_chunk_receipt.v1` contains registered engine era and chunk XY,
source geometry digest, source chunk digest, original triangle IDs, original
vertex IDs, exact triangle/vertex counts, 3D axis-aligned bounds, verifier A
(recomputed canonical SHA-256 payload) and verifier B (independent source
vertex/face and centroid reconstruction), plus a digest of its own record.

The `mesh_chunk_evidence_bundle.v1` includes source geometry digest, original
geometry cardinality, exact-once source face coverage, verified result of
both whole-mesh algorithms, ordered child receipts and a bundle root.
Source changes invalidate the corresponding records; no false continuity
can be achieved by copying an old identity into a new geometry snapshot.

## L03 Frame per-chunk proof contents

Every `frame_chunk_receipt.v1` carries frame number, FPS, chunk XY, source
frame and GDD digests, actor IDs, source asset digests, 3D bounds, stable
entity count, moved-within-chunk IDs, arriving/departing IDs, previous
frame digest, GDD law-index and signed-note hash links, independent
A/B algorithm names and independently computed record digest.

`frame_chunk_evidence_bundle.v1` exposes total source actors and chunk
counts, migration count, note count, signed GDD ID, current/prior source frame
IDs, optional previous evidence root, ordered per-chunk receipts and new
bundle root. Incremental mode checks actual previous actor and asset identity
and prevents replacing valid older receipts with rehashed forged entities.

## L04 Emptied / retired chunk tombstones

When the last actor exits a cell, that source chunk no longer appears among
current active chunks. A `retired_frame_chunk_receipt.v1` preserves the
former cell, authenticated prior source frame/chunk, each moving actor's
previous/next cell and immutable asset digest, signed-GDD identity, its own
A/B checks and evidence digest. The total number of actors migrating in
must equal all departures from old active **plus retired** cells.
This does not claim a real engine has unloaded, deallocated or remapped a
GPU chunk until native telemetry verifies it.

## L05 Independent verification and canonical AI context

Do not trust a receipt's `passed` flags or digest text as a standalone
credential. The verifier reconstructs the expected receipts from the actual
typed source mesh or frame/GDD objects and compares the results. A SHA-256
receipt is *integrity-linked*, **not cryptographically signed user approval**;
the signed GDD is a distinct, earlier source of authority. Model-generated
notes can only reference existing signed world-law indices. Source notes and
evidence root may be exposed to existing AI providers as read-only context;
they cannot mutate game canon or execute gameplay.

## L06 Failure cases

- Missing or duplicated faces, mis-mapped source indices, invalid centroid
  membership, corrupted chunk digest or changed source asset → reject.
- Invalid/missing source GDD, changed world-law reference, skipped frame,
  impossible movement, misplaced actor or reused previous frame → reject.
- Missing retired-chunk migration, incomplete in/out conservation, altered
  actor ID or recomputed malicious prior receipt → reject.
- Source/record mismatch or missing B verification → block advancement.
- A failed or unrequested native GPU/engine observation is **not** replaced
  with synthetic proof or assumed 'done'.

## L07 Limits, performance and storage

Current frame evidence is bounded by the underlying 65,536-entity frame
budget, at most 32 signed GDD notes per frame, 30/50/60/120 Hz, the
source frame's explicit chunk size, and exact source-asset digests.
Receipts can grow with entity counts; reference source generation presently
serializes full per-frame records. Production must use existing durable
checkpoint/content-addressed artifact storage, rollups, pagination, retention
and backpressure rather than logging raw high-frequency full frames forever.
For deeply long-running projects, only signed/verified manifests and bounded
AI context cursors should be promoted to provider prompts.

## L08 Verification strategy

The focused suite includes every registered `EngineEra` over the same
source mesh, exact source face/vertex coverage, altered geometry and
false hashes, 30/50/60/120 FPS actor movement, cross-boundary migration,
retired cells, signed-GDD note indices, rehashed-forged prior actors,
independent realism auditor corruption probes and a 40-frame chained
receipt sequence. Tests also check Studio and scene integration.

## L09–L13 Remaining P0–P3

Native engine fixed-step source capture and actual raster/GPU/streaming
receipts are still unimplemented. Need source-to-shader/texture/weather,
physics collision and actor animation cross-checks per chunk; true camera
frame capture and frame timing; rebase/replay of changing terrain and GDD;
durable receipts with privacy/rights retention controls; UI inspection
and filtered chunk note timeline; multi-engine shader/chunk profiling and
save/reload/rollback consistency. True production closure requires
measured native runtime artifacts, not source-only verification.
