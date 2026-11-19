# Portable recovered GLB wing animation

A review-only source exporter now consumes actual computed membrane positions
from the canonical solver, not synthetic screenshots or a receipt-only stub.
It constructs glTF 2.0 binary meshes with triangle indices, Y-up geometry,
area-weighted vertex normals, per-frame position and normal morph deltas,
and time-keyed one-hot animation weights. Each GLB contains a bounded local
clip; adjacent pages share an exact boundary sample. ZIP members and manifest
are deterministic and SHA-bound. Independent verify rebuilds the entire
archive from the pinned original simulation order. Export refuses invariant
failures unless explicitly admitted for review, and never overwrites a target.
No engine imports, shader execution, native rendering, art approval or
production asset release are claimed. All tests remain to be executed.
