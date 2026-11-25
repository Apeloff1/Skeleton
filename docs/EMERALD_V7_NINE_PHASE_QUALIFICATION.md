# V7 nine-point transition qualification — 108 actual exported poses

Both Pathfinder and Archivist V7 models were re-read from complete, exact-SHA GLBs and evaluated by the original independently reviewed triangle-distance pipeline. This extends the earlier three-phase pass to **nine equally spaced points in each 0.22-second transition**. Six source clip transitions × nine fractions × two models = **108 actual skinned-pose screens**.

| Actual exported V7 model | Samples | New non-welded contacts | 8-mm near-margin pair occurrences | Inherited shared-index seam occurrences |
| --- | ---: | ---: | ---: | ---: |
| Pathfinder | 54 | **0** | 267,234 | 29,754 |
| Archivist | 54 | **0** | 147,920 | 29,754 |
| **Total** | **108** | **0** | **415,154** | **59,508** |

This materially expands evidence for the V7 orbit-02 correction, which removed 20 previously detected source-bound contacts in the preceding 36-pose V6 screen. It remains **sampled geometric evidence**, not a continuous-time proof or validation of all anatomical collisions. Existing binding seams and near contacts are not silently discounted.

The exact full 54-pose-per-model JSON reports are supplied separately as `pathfinder-nine-phase-contact-report.json` (SHA-256 `78953a55fa755c986ab196553fd4c1bfacee8cf9aeb9766b92eb6af6301359ee`) and `archivist-nine-phase-contact-report.json` (SHA-256 `3710a5b66e6158e5695f4f441c78a29001bb3f26ffe5b3a71c2a498c1c1c8dbf`). The repository retains the 108 per-sample near-margin counts in `assets/emerald/evolution-v7/nine-phase-complete-evidence.json`, and its verifier can check **either source-only consistency or both external full reports** by exact SHA and detailed per-region witness counts.

## Actual resumable execution

The Pathfinder scan lost its process after 42 of 54 poses. Its exact-source checkpoint retained the 42 completed pose witnesses, and the same model/9-phase policy resumed at pose 43. All 54 Pathfinder and all 54 Archivist poses finished without introducing new contacts. Neither skipped nor repeated poses are counted. The checkpoint is always incomplete evidence until the separately generated full report passes the source-bound verifier.

Reproduce independently on a trusted host using the exact original V7 GLBs and five reviewed geometry-source Python files:

```sh
python scripts/emerald_v7_crossfade_screen.py \
  --stage pathfinder \
  --model /verified/pathfinder-v7.glb \
  --source-tools /reviewed/contact/Tools \
  --steps 9 --time-budget-seconds 600 \
  --checkpoint /new-evidence/pathfinder.partial.json \
  --output /new-evidence/pathfinder-nine-phase-contact-report.json

python scripts/emerald_v7_crossfade_screen.py \
  --stage archivist \
  --model /verified/archivist-v7.glb \
  --source-tools /reviewed/contact/Tools \
  --steps 9 --time-budget-seconds 600 \
  --checkpoint /new-evidence/archivist.partial.json \
  --output /new-evidence/archivist-nine-phase-contact-report.json

python scripts/check_emerald_v7_nine_phase.py \
  --reports-dir /new-evidence
```

If a run times out, rerun with `--resume` using exactly the same verified GLB, source tools, step count, and checkpoint. The independent summary verifier rejects missing/changed reported samples, changed model SHA or swapped stage, modified auditor SHA, tampered full reports, suppressed near-margin contacts, and false approval flags. It reports separately whether external full report bytes were actually validated.

## Explicit remaining holds

The crossfade approximation uses local quaternion slerp and translation lerp at fixed outgoing-end/incoming-start playhead positions. It does **not** reproduce arbitrary director-loop phase, interrupted/resumed Three.js actions, real browser frame timing, GPU skinning, or actual 3D renderer/device contexts. Only **three** anatomical pair types were screened; mixed-skin regions, full body/wing self-collision, optional equipment, continuous-time swept geometry and art acceptance remain open. Human-authored textures/sculpting, approved poster likeness, true Unreal and physical RTX, exact remote GitHub binary publication, full mandatory CI, and release provenance are still unqualified.

No automatic V7 adoption, equipment activation, merging or release is authorized by this measured report.
