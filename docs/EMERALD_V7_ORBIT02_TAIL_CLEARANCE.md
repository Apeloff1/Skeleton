# Emerald V7: source-locked orbit-02 tail clearance

**Status:** original-donor candidate; review-only. The approved Sanctuary poster remains the artistic target. The original Hoarder and the V4, V5 and V6 assets are never modified or automatically repinned.

## Root cause

The 17 November exported-GLB 0.22-second offline crossfade screen finished 18 poses per model across six representative transitions, sampling each at 0%, 50%, and 100%. Pathfinder V6 had **15** and Archivist V6 had **5** newly observed non-welded tail-versus-hindleg intersections. **All 20 occurred at 100% of orbit-01 → orbit-02**, where the original V6 builder had not corrected the orbit-02 tail track. The other 34 sampled blends had no newly observed intersections across the selected three region pairs. Neither the raw contacts nor the relative joint angles are by themselves a continuous-time collision proof.

## V7 corrective implementation

Append **one** new quaternion VEC4 stream for each model: 160 keys in `orbit-02` for tail joint 34, postrotated by +0.18 radians about local Y. This retains the earlier V6 orbit-01 and landing-1 correction untouched and does not modify any of the other 380 clips, their key times, the next-form growth clip, model geometry, skin weights, UV/PBR materials, or the original binary source prefix.

| Asset | Exact V7 size | SHA-256 |
|---|---:|---|
| Pathfinder | 114,696,520 bytes | `27e1a6a22fad045d26edf4dc2813292829aab8dcaa129fac407f80ee83229ade` |
| Archivist | 114,819,168 bytes | `f224671cf6d0886365f081faa29f9dcf2509d52211677d2a83152a389389acaf` |

The actual models were exported, and an independent verifier confirmed each original full GLB binary prefix, one exact appended rotation accessor, 160 changed keys and **44,512 unchanged animation channels** per form, while retaining the growth animation verbatim.

## New exported V7 skinned-contact evidence

The same independent source-bound geometry pipeline processed all **36** crossfade poses on the *actual newly exported V7 bytes*, not merely an in-memory patch.

| Measure | Pathfinder | Archivist |
|---|---:|---:|
| New non-welded contacts | **0** | **0** |
| Remaining near-margin (8 mm) pair occurrences | 89,988 | 49,477 |
| Pre-existing shared-vertex seam occurrences | 9,918 | 9,918 |

The **139,465 near-margin occurrences** and **19,836 pre-existing seams** are explicit unresolved acceptance cases. Only three anatomical pair types and a fixed outgoing-final/incoming-initial 0.22-second fade window were screened. No other loop phase, interrupted crossfade, unclassified anatomical region, equipment or continuous interval is declared safe.

Exact local reproduction from the supplied original V6 GLBs:

```sh
python scripts/emerald_v7_orbit02.py pathfinder --source /trusted/v6/pathfinder.glb --output /new/v7/pathfinder.glb
python scripts/verify_emerald_v7_orbit02.py pathfinder --source /trusted/v6/pathfinder.glb --candidate /new/v7/pathfinder.glb
python scripts/emerald_v7_orbit02.py archivist --source /trusted/v6/archivist.glb --output /new/v7/archivist.glb
python scripts/verify_emerald_v7_orbit02.py archivist --source /trusted/v6/archivist.glb --candidate /new/v7/archivist.glb
```

`scripts/emerald_v7_crossfade_screen.py` reuses the vetted, source-hashed geometric library with *separate* immutable V7 pins; source-only CI checks syntax and hostile fixtures, not the 229.52 MB private binary payload. The measured summary lives at `assets/emerald/evolution-v7/orbit02-exported-crossfade-summary.json`. The complete 18-pose-per-model reports and actual binaries are in separately verified ZIP deliveries.

## Remaining holds

- Actual Three.js AnimationMixer timing and arbitrary real event-driven loop-phase qualification, not an approximate offline SLERP model.
- Full adaptive continuous skinned-mesh CCD and the additional anatomical/weight-blended regions, equipment/cloth clearance, contact seam topology and transition back to original Hoarder.
- Studio-standard hand-sculpted/painted poster resemblance, no inherited baked adult equipment, real Unreal compilation, Windows/device and physical RTX rendering.
- Exact complete GLB GitHub publication, all mandatory final-head CI and independent release provenance.

Automatic V7 adoption, enabling equipment, mass merge and release remain **unauthorized**. Neither this PR nor the sample receipt clears these gates.
