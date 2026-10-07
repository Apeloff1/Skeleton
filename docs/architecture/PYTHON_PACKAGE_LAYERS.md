# Python Package Layers

<!-- machine-git-blob: machine/python_package_layers.json@49f16db1c5bf6a7cf136994eb5699bbccc11dbb1 -->

Machine authority: `machine/python_package_layers.json`

This P2 control implements the masterplan's VOL-052/VOL-053 package-layer and import-graph gaps for a selected high-risk Skeleton surface.

The manifest defines ordered foundation, contract, runtime-service, orchestration, and adapter layers. Classified modules may depend on the same layer or a lower layer, never a higher layer. Runtime `sys.path` or `PYTHONPATH` mutation is rejected in classified production modules.

Coverage is intentionally explicit: internal imports to modules not yet classified are reported rather than silently treated as approved. Later P2 work can widen classification after current edges are understood.
