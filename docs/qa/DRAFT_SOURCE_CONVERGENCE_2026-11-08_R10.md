# R10 — playable game, physics and Godot source-source reconciliation

**DRAFT / NO MERGE / NO AUTO-MERGE / NO RELEASE**. Parent #5089 exact `7e39c1637341a0d510ff9675a40e062e30afe9d0`. Git objects from 5092, 5093, 5095, 5096, 5097, 5099, 5100 are selectively copied with original SHA identity. Their primary branches and all quarantine/security/device holds remain. Source presence is not a runtime or device certificate.

Included 19 original donor files, plus two explicitly required source-identical `skeleton/ai/simulation/physics/vehicle.py` and `skeleton/ai/runtime/ecs/ai.py` mirrors. Context pipeline modifications are byte-identical on source and canonical AI mirror, and were rebased over an unchanged historical `9161ccac...` source snapshot. Other new Forge files also ship with both source + AI equivalents.

Retained semantic conflicts (to reconcile without overwrite): #5097 backend image digest/CLI import changes, #5099 Unicode-only world validation on #5089's newer world canon, #5100 no-clobber export on already expanded Godot runner. Do not blindly replace current implementations; source-level surgical compatibility repair is required in a second source tree stage. #5094 and #5101 setup/native bridge updates also need independent review; not included in this file extraction.

Git-provenance ledger:
- #5092 `skeleton/simulation/physics/vehicle.py` added blob `6c3c99790258d9094d6a4769ee3c9d5e19f0aae4` (+810 donor lines)
- #5092 `skeleton/testing/test_simulation_physics_vehicle.py` added blob `845ef84c94cb3dd83637a56905247ab697cd39e9` (+392 donor lines)
- #5092 `skeleton/testing/test_simulation_physics_vehicle_quarantine.py` added blob `f5ac77ba66534a6442f27b34bd022e9ce7bb75a0` (+41 donor lines)
- #5093 `skeleton/ecs/ai.py` added blob `0f77e4ab9ec93d9786e28e473be1167e62595eaa` (+389 donor lines)
- #5093 `skeleton/testing/test_ecs_ai.py` added blob `0acf81cec338e7665d6d41556057db77e72b1891` (+179 donor lines)
- #5093 `skeleton/testing/test_ecs_ai_quarantine.py` added blob `ef1c99fbf16860dddfc06133e90b842988e13deb` (+54 donor lines)
- #5095 `skeleton/ai/forge/archetype_content.py` added blob `3de1b5356b65bb4608ab0e29c679a076a12bb4b9` (+258 donor lines)
- #5095 `skeleton/ai/runtime/context/pipeline.py` modified blob `409f09f9953190bb5db2a5cd4ddad169e3744d86` (+15 donor lines)
- #5095 `skeleton/context/pipeline.py` modified blob `409f09f9953190bb5db2a5cd4ddad169e3744d86` (+15 donor lines)
- #5095 `skeleton/forge/archetype_content.py` added blob `3de1b5356b65bb4608ab0e29c679a076a12bb4b9` (+258 donor lines)
- #5095 `skeleton/testing/test_archetype_playable_e2e.py` added blob `6c5eee97791e0847df93c2103acce9da6a2c1aa7` (+92 donor lines)
- #5095 `skeleton/testing/test_archetype_playable_quarantine.py` added blob `d9bcb3ee2a3b39078e9e88052ce19f77cdac494e` (+44 donor lines)
- #5096 `skeleton/ai/forge/export.py` added blob `1bbf42691c36652db243bddb862931075554951a` (+241 donor lines)
- #5096 `skeleton/forge/export.py` added blob `1bbf42691c36652db243bddb862931075554951a` (+241 donor lines)
- #5096 `skeleton/testing/test_forge_export.py` added blob `88db0f64666b86b59bf1f2620f6ec6e4c9c272be` (+59 donor lines)
- #5096 `skeleton/testing/test_forge_export_quarantine.py` added blob `ce8a92b418427bdcf5b14c7a291599e44d121146` (+53 donor lines)
- #5097 `tests/test_backend_docker_python_pin.py` added blob `8dc51fd1dd8d370b2aa7714a14a24f1bb6b0cc5b` (+23 donor lines)
- #5099 `tests/test_jeeves_world_unicode_ingress.py` added blob `7a0f5bd2df21a61b39102ab60ef8a7681e8f520a` (+49 donor lines)
- #5100 `tests/test_godot_export_verified.py` added blob `ddccc33561bbaadd41db71e4ea38679aa7171f60` (+69 donor lines)

Acceptance: check pinned AIFT-FORGE, AIFT-SIMULATION, AIFT-EC S-ADAPTER (id `AIFT-ECS-ADAPTER`), AIFT-CONTEXT and AIFT-JEEVES mapping identities; unique source and mirror bytes; focused original adversarial tests, full CI and independent Godot/Windows/hardware qualification. No ancestor, synthetic, skipped or queued pass may be claimed.
