# Original asset production briefs

This Studio A vertical connects canonical visual design recipes to actual
source-replayed scene asset bindings and creates operator-editable original
asset work orders. It covers every referenced recipe, validates the exact
scene/asset/source/visual/quest-session ancestry, rejects unknown or duplicate
recipe IDs, and preserves deterministic priority and target-platform choices.

Use `scripts/studio_original_asset_briefs_cli.py` with `--project`,
`--expected-source`, `--expected-visual`, `--actions`, `--bindings`,
and either `--prompt` or `--authoring`. The typed shape is
`{"briefs":[{"recipe_id":"...","brief":"...","priority":1,"platform":"html5_reference"}]}`.
The prompt derives original work-order text from the registered visual source;
operator changes are **unverified design intent**, not evidence of rights.

`--editor-directory` publishes a private CSP-hashed offline HTML editor;
`--import-authoring` plus `--baseline-briefs` checks source, visual,
session, binding and baseline digests before recompilation. `--publish` and
`--restore` use descriptor-anchored immutable private receipts. The Jeeves
static router exposes `studio_original_asset_briefs`.

The optional playable manifest verifies the existing original offline HTML5
game and separately hashes the work-order companion HTML. **No meshes,
textures, production artifact bytes, originality audit, rights attestation,
native runtime or device/release certification are claimed.**

Focused regression contract:
`pytest -q tests/test_studio_original_asset_briefs.py`.
