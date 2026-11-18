# Emerald V7 — independent two-model actual-Three evidence revalidation

The operator-only `scripts/run_emerald_v7_real_three_qualification.py` can **execute** both real Three.js 0.186.1 source mixers and the reviewed triangle contact analyzer on the actual original V7 GLBs. When it completes, it writes a collection of JSON and GLB-source SHA receipts. A positive execution claim must not be accepted merely because a JSON field is true; it needs an independently rechecked evidence inventory.

This draft adds `scripts/revalidate_emerald_v7_three_execution.py`, a **read-only second-pass validator** requiring the exact two-original-model and two-source-report tree. It does not invoke Node, re-run geometry, install the models or assert release readiness.

## Required source tree

- `/trusted/v7-originals/pathfinder.glb` and `archivist.glb`, respectively exactly **114,696,520** and **114,819,168** bytes with their original pinned SHA-256.
- `/trusted/original-reviewed-tools` with the same five SHA-reviewed Python contact sources and `source-custody.json`.
- Original operator evidence directory containing `sampled-execution-receipt.json`, `source-report-consistency.json`, `traces/pathfinder-three-mixer.json`, `traces/archivist-three-mixer.json`, plus each stage's actual contact report and checkpoint under `contacts/`. Unknown files or linked input entries cause failure.

## Operator command

```sh
python scripts/revalidate_emerald_v7_three_execution.py \
  --models /trusted/v7-originals \
  --reviewed-tools /trusted/original-reviewed-tools \
  --evidence /trusted/independent-source-execution-evidence \
  --output /unused/independent-v7-evidence-revalidation.json
```

The tool performs the following *independent read-only consistency* checks:

1. Rehash both **complete** original model binaries by nofollow file descriptors and verify both exact source pins, before examining either JSON report.
2. Require the exact original 109 glTF-node/108-skin-joint preflight receipts, model stage order, 381-clip identity, full binding source fingerprint manifest SHA and both original-source SHA flags.
3. Rehash all operator/trace/paired evidence scripts and the installed Three 0.186 runtime files against the *previous operator receipt*. The five independently inspected original geometry tool SHA pins must still be intact.
4. Inspect the exact two Three motion traces and their independent 54-pose joint consistency contracts, including the true source trace SHA.
5. Reconcile each source-bound skinned-triangle report against its respective trace, each anatomical pair, all per-pose contact/near-margin/bind-seam counts and the independent world-matrix tolerance.
6. Cross-check the previously generated paired source-only receipt (which deliberately remains **non-admitting**), both stage results, all complete source hashes, sample totals and explicit non-release flags.

Any modified same-length GLB, altered contact count, missing stage, extra evidence file, changed Python/Three source, false source-binding preflight, forged GPU/artist/release approval, inconsistent trace/report digest or missing operator field causes failure. The tool writes only a **new** independent validation JSON file if explicitly requested; it never edits the original evidence or active installed Emerald assets.

## Boundary of this assurance

A completed independent report confirms all recorded **108 sampled pose/contact data** are byte-consistent with the operator's source files and exact model pins. It **does not prove that the previously recorded processes actually executed**: the receipt explicitly states `actual_mixer_and_geometry_reexecuted_by_this_validator: false` and `independent_proof_of_process_execution: false`. Authentic execution evidence still depends on the controlled operator run and a trusted external device/runtime observer. Cross-model sampled contact consistency is not continuous collision detection.

It cannot certify other anatomical pair types, 171,165 mixed-influence seam-risk faces, arbitrary browser mixer playheads, WebGL timing, native Unreal, artist poster fidelity, original hand-painted textures, physical RTX, all eight original GitHub binary transport objects, security, install readiness, merge or release. The original Hoarder and installed Emerald model pins are unchanged.

Source-only CI uses deliberately tiny **synthetic** fixtures to prove rejection of forged evidence. It does not execute or qualify the actual two 114–115 MB original models.
