# R11 — semantic repair merge on source-convergence 2026-11-08

**DRAFT / REVIEW ONLY / NO MAINLINE SQUASH / NO RELEASE**. Parent #5089 exact head `7e39c1637341a0d510ff9675a40e062e30afe9d0` and previously staged R10 raw Git tree `ecbfe49cb6b79d5fb9cf8d5743ccf58a2a5d718b`. All security and independent release checks remain held. Reconcile semantic differences using exact selected modifications, not whole-file overwrites.

- #5099: reject surrogate Unicode scalar values in world text at typed ingress before canonical JSON/HTML publication; identical replacement blob under `skeleton/jeeves/worlds/world_canon.py` and `skeleton/ai/agents/jeeves/worlds/world_canon.py`. Retain all other prior #5089 world canon edits.
- #5100: source-copy the verified nonempty, no-clobber Godot export method into the already-expanded `skeleton/godot_export/runner.py`; retain preexisting `play_scene` behavior. No executable boot or device evidence claimed.
- #5097: exactly pin the three build stages to Docker Python 3.14.10 on Alpine 3.24 with immutable donor digest, retaining the current secure cleanup and other parent Dockerfile content. Keep the production fabric CLI's precise fully qualified `LocalAPI` import without changing program logic.
- #5097 native-flight fixture already uses portable home temp directory on the parent and both missing syntax defects from #5097 are already incorporated; do not redundantly replace them.
- R10 raw source and mirror files remain as immutable Git donor blobs; update AIFT-FORGE, AIFT-CONTEXT, AIFT-SIMULATION, AIFT-ECS-ADAPTER and AIFT-JEEVES pins from the **final** Git object tree after these changes.

Exact-head unit, end-to-end, source/mirror parity, supply-chain and independent device/security approval remain mandatory. The donors are not separately merge-authorized; no source identity or workflow gate was waived.
