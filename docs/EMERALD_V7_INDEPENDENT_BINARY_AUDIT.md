# Emerald V7 independent four-archive and full GLB custody audit

This is a **separate, pure Python standard-library** verifier of the two original V6 GLB archives and two newly exported V7 original-donor archives. It complements the NumPy exporter, the original five-tool contact stack, and the 108-pose crossfade evidence. It does not depend on those source implementations for its geometry/animation identity conclusion.

## Four pinned original ZIP envelopes

| Stage | Generation | Original GLB bytes | Exact whole-GLB SHA-256 |
|---|---|---:|---|
| Pathfinder | V6 | 114,693,124 | `20d6a6a62b3ff232572e1b25d799f1461d4e343ce3b7d30a328faed8837c4063` |
| Pathfinder | V7 | 114,696,520 | `27e1a6a22fad045d26edf4dc2813292829aab8dcaa129fac407f80ee83229ade` |
| Archivist | V6 | 114,815,776 | `8d72d43773a98444133ab628db552bddad06ea0f101cfe223897bf8ba0944973` |
| Archivist | V7 | 114,819,168 | `f224671cf6d0886365f081faa29f9dcf2509d52211677d2a83152a389389acaf` |

Before reading source bytes, the auditor requires each ZIP's exact length and SHA-256; then it rejects encrypted, linked, duplicate-case, traversal and nonfile entries, enforcing member and decompression quotas. It streams only the expected model member to new scratch storage with bounded blocks, verifies the **complete 114–115 MB GLB SHA**, and parses the original embedded BIN.

For each actual source V6→candidate V7 pair, independent structural verification requires **identical original embedded BIN SHA-256**, unchanged source nodes, meshes, materials, skin, base buffer views/accessors, glTF extensions and original per-clip channels. It permits exactly one new 160-quaternion stream, indexed to tail joint 34 in `orbit-02` with the +0.18-radian local-Y Hamilton postrotation. All unchanged animation clips, especially growth, must remain verbatim. It rejects unexpected new top-level glTF sections, modified provenance extras, injected or re-targeted binary views, forged renderer/device/release claims, repinned original donor and altered timebases.

The measured original-byte receipt committed at `assets/emerald/evolution-v7/independent-original-zip-custody-20261117.json` identifies all four complete ZIP/GLB digests and the actual V6/V7 prefix digests. The **source-only CI** tests the auditor against hostile synthetic GLBs and validates that receipt. It must **not** be represented as a re-execution of the large original archives.

## Offline original-byte reproduction

```sh
python scripts/audit_emerald_v7_original_zip_pair.py \
  --v6-zips /verified/emerald-v6-archives \
  --v7-zips /verified/emerald-v7-archives \
  --out /new-evidence/v7-independent-original-audit.json
```

The two source directories must contain the exact filenames `pathfinder-v6-tail-clearance.zip`, `archivist-v6-tail-clearance.zip`, `pathfinder-v7-orbit02-clearance.zip` and `archivist-v7-orbit02-clearance.zip`. The output must be a **new** file. No remote network access or Git credentials are required. A successfully written receipt explicitly keeps physical Unreal/RTX, actual Three.js mixer, continuous collision and launch approval false.

## Unqualified gates

This audit proves the previously measured V6/V7 *binary relationship*, not visual quality or collision clearance. The separately retained 108 skinned crossfade samples cover only three anatomical pair types; **415,154 near-margin pair occurrences** and **59,508 inherited attachment contacts** remain unresolved. Original raw GitHub GLB parts remain unpublished in their dedicated payload drafts, and actual browser/device, handcrafted poster fidelity, GPU, security and final release-provenance gates remain open. No auto-adoption, merge or release.
