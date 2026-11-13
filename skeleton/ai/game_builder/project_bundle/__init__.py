"""Game project bundles on the GF-B save plane.

Persists :class:`~skeleton.ai.game_builder.game_project_workspace.GameWorkspace`
projects through :class:`~skeleton.kernel.game_save_plane.GameSavePlane`
(file contents as content-addressed chunk receipts), with version history,
file/design diffs, deterministic single-file import/export and bundle-level
schema migrations. Existing interfaces are used unchanged.

Scope note: migrations here version only the *bundle* sections
(``bundle``/``files``). Gameplay-state section schemas are owned elsewhere
(B025) and are passed through untouched.
"""
