# Exact original animation keyframe audit

Run after original-asset preflight:
```sh
python scripts/audit_emerald_animation.py /trusted/emerald_continuum.glb > animation-audit.json
```
The tool hashes the full original file and reads animation keyframe bytes through the same descriptor. It validates animation accessors, channel references, time ordering, output cardinality, finite values and near-unit rotation keys. It examines shared accessors only once per compatible interpretation and reports all 380 actual original clip names, key counts and time ranges. It intentionally rejects unsupported animation representations instead of silently ignoring channels. Morph target counts and cubic interpolation tangents have explicit handling. Synthetic regression data never counts as original asset evidence.

The audit is not continuous collision verification, GPU skinning, artistic clearance, native texture provenance, or real-time hardware performance. Its finite keyframes do not prove the previously reported 86,294 pose samples or 138.2 mm clearance. Review source and actual animation traces independently; the original 463,149,740-byte asset must be supplied.
