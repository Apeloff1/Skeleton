# V6 live crossfade: source-bound joint mixing and mesh-contact qualification

The V6 Pathfinder and Archivist corrective GLBs were measured to eliminate newly induced tail–hindleg contacts in selected **individual orbit and landing poses**. That is **not** a cross-clip transition qualification. The browser implementation in `atelierStage.web.ts` uses `action.crossFadeFrom(previous, .22, false)`. The updated tail-root rotation is constant within the two corrected clips, so the incoming/outgoing crossfade interpolates between *different* tail configurations. Silently switching from source to candidate or automatically replacing the pinned V4 viewer model is prohibited.

## Implemented offline transition screen

`scripts/emerald_v6_crossfade_screen.py` requires exact original V6 SHA-256 bytes and the five SHA-256-pinned audited geometry sources from the retained contact-evidence archive. It samples the actual 108 weighted joints with original glTF LINEAR/spherical interpolation, then applies a joint-wise local translation lerp and shortest-path quaternion slerp over a **0.22-second** envelope. The resulting 365,997 skinned vertices feed an exact triangle-pair narrow phase across the three previously discovered welded/penetration regions.

Six transition directions are explicitly screened:

| Outgoing | Incoming |
|---|---|
| Ground idle 1 | Takeoff 1 |
| Takeoff 1 | Orbit 01 |
| Orbit 01 | Landing 1 |
| Landing 1 | Ground idle 1 |
| Orbit 01 | Orbit 02 |
| Orbit 02 | Landing 1 |

For each sample the report retains original shared-vertex bind-seam candidates, independent new triangle contacts, and near-margin pairs at an **8 mm** review margin. It does **not** discard contacts because they are geometrically inconvenient. Unknown source hash, tool hash, wrong joint count, unexpected clip, incomplete sample, runtime budget exhaustion, or false approval flags cause a fail-closed result.

Example source-bound execution, from a trusted checkout:

```sh
python scripts/emerald_v6_crossfade_screen.py \
  --stage pathfinder \
  --model /verified/pathfinder-v6.glb \
  --source-tools /retained/source-and-contact-evidence/Tools \
  --steps 5 \
  --time-budget-seconds 600 \
  --output /new-evidence/pathfinder-v6-blends.json
python scripts/verify_emerald_v6_crossfade_evidence.py \
  --stage pathfinder --receipt /new-evidence/pathfinder-v6-blends.json
```

Repeat with `--stage archivist` and the exact Archivist V6 model. The source tool directory must contain unchanged `contact_audit.py`, `contact_geometry.py`, `contact_geometry_accel.py`, `fast_wing_witness.py`, and `analyze_seams.py`; the runner validates every file's original SHA-256 before import. Do not supply unreviewed substitutes.

## Interpretation

This is **an approximation** of the Three.js animation mixer. It evaluates local-joint slerp and translation interpolation at selected fade phases with an outgoing clip sampled in its last 0.22 seconds and an incoming clip sampled in its first 0.22 seconds. The actual browser mixer may differ in playhead phase, weighted action scheduling, loop wrap, interpolation details and frame timing. Repeating/interrupting transitions, arbitrary ground or orbit loop phase, frame-to-frame swept motion, and all other anatomical pairs are **not** certified.

**Required remaining acceptance:**
- Exact observed real Three.js mixer crossfade traces, with real original V6 bytes, transition playheads, and independent device/device-loss qualification
- Full continuous collision and adapted speed/pressure controls over non-linear skinned motion intervals, including mixed-influence faces and equipment
- Artistic and hand-painted poster parity, removal of residual adult geometry, Unreal build and physical RTX
- Actual GitHub publication of both complete V6 original GLBs; exact-head checks and release provenance

New model auto-adoption, equipped ornaments, merges and release remain disabled. Neither a clean synthetic test nor a clean sampled offline transition scan is sufficient to remove those holds.


## Actual V6 root-joint measurements and resumable contact scan

An independent reading of **both exact SHA-256-verified V6 original GLBs** checked tail-root joint 34 at the six outgoing/incoming clip boundaries. Measured relative orientation changes (degrees) are identical across both stages: ground-idle → takeoff **0.00017**, takeoff → orbit **10.539709**, orbit → landing **2.407554**, landing → idle **10.313266**, orbit-01 → orbit-02 **12.34307**, and orbit-02 → landing **8.029266**. The 12 signed source comparisons are stored in `assets/emerald/evolution-v6/root-crossfade-angles.json`. These joint angles identify meaningful transitions to inspect; they do **not** prove skinned-mesh clearance.

A first independent approximate skinned-contact trial reached **11 of 18 Pathfinder blend poses** before the command runtime budget expired. Those 11 completed samples had zero newly introduced non-welded contacts in the *three selected* contact pairs, but still had thousands of 8-mm near-margin pairs per sample. **The remaining seven Pathfinder samples and all Archivist blend samples were not qualified by that partial trial.** The original trial did not persist a machine-readable completed report and cannot be counted as a finished crossfade test.

To avoid losing evidence during long high-density screens, the new operator runner writes an *atomic incomplete progress journal after every completed blend*. Fresh runs use `--checkpoint /new-evidence/pathfinder.partial.json`; after a timed-out run, use the same original model, audited tools, step count and journal with `--resume --checkpoint ...`. It rejects changed hashes, reordered clip transitions, forged source policy, false release flags and existing unrequested output files. A partial journal is always marked `completed: false`, even when its last sample is present; it must never be accepted as continuous CCD or final artistic evidence. The final separately written full report is verified by `scripts/verify_emerald_v6_crossfade_evidence.py`.

The 0.22-second sampled slerp model still does not capture arbitrary active-loop playheads, interrupted fades, the exact Three.js mixer, equipment interference, or continuous-time collision. Acceptance remains review-only.
