# Original mesh and skin binary audit

With the original independently pinned GLB:
```sh
python scripts/audit_emerald_skin.py /trusted/emerald_continuum.glb > mesh-skin-audit.json
```
This audit checks actual source accessors (not filenames or a manifest claim), finite geometry, local bounds, normal norms, triangle indices, referenced skin palettes, inverse-bind finiteness, normalized integer weight encodings and aggregate skin weights. It reports repeated triangle indices without calling them a complete degeneracy test. Unsupported sparse/compressed geometry must be separately reviewed rather than silently skipped. The audit reads bounded chunks and fails closed on structural inconsistencies. No changes to texture, tessellation, original joint weights or archive bytes are made.

These measurements do not evaluate posed self-intersection, wing membrane strain, contact, continuous deformation, actual shader execution, handcrafted artwork, or physical RTX. Independent hardware and artistic observations remain mandatory.
