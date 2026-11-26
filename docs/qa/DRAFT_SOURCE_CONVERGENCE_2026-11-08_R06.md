# Reconciliation R06 — game, Godot, replay and first-install regression custody

**DRAFT / NO MERGE / NO RELEASE / NO AUTO-MERGE.** Exact parent PR #5089 at `752646d6613a8147447b52c323015f52c5ba750d`. 14 original file blobs and 3 matching governed simulation mirrors staged from #4891, #5006, #5007, #5002, #4995, #4900. All independent CI, source security, replay, native, Windows and physical-device acceptance holds remain. This stage does not validate game quality or release readiness.

Original Git blobs:
- #4891: added `skeleton/install/loopback_readiness.py` `af165abd1fb6e3828408b8e08e8a63c1634789a9`
- #4891: added `skeleton/testing/test_loopback_readiness.py` `e5930086a8ad09c1f55c435ff67b13073077b694`
- #5006: added `skeleton/godot_export/artifact_custody.py` `ec9aaabadeaa5a79f05db72ac93ae61b2d0e84bd`
- #5006: added `skeleton/testing/test_godot_export_artifact_custody.py` `54bf887efec7cd384e1a41554ccb6d0c554f2d40`
- #5007: modified `skeleton/game/simulation/character_controller.py` `0304558e0ef991d19f6f2b0aedcffe0586c1c648`
- #5007: added `skeleton/game/simulation/input_collision.py` `aba8f794392a6b21096ae0e3e0bbb9b674619111`
- #5007: added `tests/test_game_input_collision.py` `6294b6fdb981c99f13cccc6a238572718b9b7f95`
- #5002: modified `skeleton/simulation/game/replay.py` `43b70afc05d1d32fca73bf01d120e5dcf5588bb8`
- #5002: added `skeleton/testing/test_game_replay_ratio_bounds.py` `8aa12b4e156bda5867a7e966ef26ef7acef92312`
- #4995: modified `skeleton/simulation/game/__init__.py` `299fb3bcc931f0bc3f3dc4e29b43462815808d81`
- #4995: added `skeleton/simulation/game/golden_grid.py` `b0c6f9b6247be37872ebf9d699c8e6368450504f`
- #4995: added `tests/test_golden_grid_v6.py` `b8e32c7076002a2a1fe53da79847ff6ef6e238a7`
- #4900: added `tests/game/test_b026_atomic_grid_save.py` `3caca4dd0efc960f76951167459805f6329f7cdb`
- #4900: added `tests/game/test_b027_keyboard_campaign.py` `76e1ef9b07ad8c5f2d1f30b25222c44d0bc8cf5e`

Excluded conflicting source:
- #4891: `skeleton/install/wizard_10000x.py` — Wizard patch held to avoid installer regression
- #4900: `scripts/game/offline_grid_campaign.py` — Campaign CLI already modified by parent composite

Recalculate AIFT-SIMULATION and AIFT-GAME source Git-tree pins from this exact resulting tree, preserving source/mirror exact blobs. All historic original branches and parent #5081/#5074 untouched. Tests for new/modified standalone code and original gameplay E2E are mandatory. Source-only presence is not proof of real hardware, full end-to-end operation, or a green CI gate.
