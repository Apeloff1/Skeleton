# Independent Emerald V7: four original ZIPs and complete binary-prefix custody

The original Pathfinder and Archivist **V6 and V7** model archives were independently read and SHA-256 checked again in the current qualification pass. Each contained its exact expected full GLB file, and each model was parsed separately as glTF 2.0 with embedded BIN, original donor, 108 skin joints and 381 animations. Both V7 models retained exactly the original V6 embedded BIN bytes, mesh/skin/material/node declarations, existing growth animation and all motion clips other than `orbit-02`; precisely one appended 160-key quaternion output corresponds to the reviewed +0.18 radian local-Y tail-root correction.

| Model | V6 original size | V7 original size | Embedded V6/V7 BIN prefix SHA-256 |
|---|---:|---:|---|
| Pathfinder | 114,693,124 | 114,696,520 | `6b6e4f45eee5f5fd7c58599298fff2e84aa5920364acde7197ea8a91369a4c60` |
| Archivist | 114,815,776 | 114,819,168 | `eec290d8759efcd53c2e74bb8425fc2f1d118e79a0e7ec306018341fb5d414a5` |

The four exact archive/GLB SHA-256 digests, complete model lengths, and source-structure results are retained in `assets/emerald/evolution-v7/independent-original-zip-custody-20261117.json`. This is *actual original-byte evidence* from a separate archive/GLB-reading pass, not model fidelity inferred from a manifest alone.

## Re-run with the independent Python-standard-library-only auditor

The new `scripts/audit_emerald_v7_original_zip_pair.py` implements the same source structure audit independently of both the model exporter and the earlier independent NumPy verifier. It validates the ZIP container SHA, every archive member path and type, the exact GLB complete original SHA and byte length, all original model declarations and the exact unmodified BIN prefix, and every one of the 160 corrected quaternion values against the source GLB. No `numpy`, GPU, model provider, Git write or network access is required.

```sh
python scripts/audit_emerald_v7_original_zip_pair.py \
  --v6-zips /retained/emerald-v6-tail-delivery \
  --v7-zips /retained/emerald-v7-orbit02-delivery \
  --out /new-evidence/independent-original-glb-recheck.json
```

It will write only to a trusted unused output path and uses temporary private scratch files for the original GLBs; the source ZIPs and originals are never modified. Invalid GLB structure, changed whole-file hash or prefix, missing clip, altered target quaternion/timebase, forged source annotation, unsafe ZIP paths or false release/hardware flags fail closed. A separate source-only CI checks hostile synthetic tiny GLBs and verifies the pinned recorded receipt; this **does not substitute for re-running the four large ZIPs** in the operator environment.

The two complete V7 ZIPs are still only supplied as conversation artifacts. No successful remote Git binary publication has been observed. The earlier sampled 108-pose contact audit still covers only three anatomical pair types, retains 415,154 near-margin pair occurrences and 59,508 inherited attachment seam occurrences. Full continuous skinned geometry collision, arbitrary real browser Three.js transitions, human-authored art/approved poster match, original Unreal and RTX, device, security, merge and release qualification remain **held**.
