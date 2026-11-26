# Original scene asset binding — Studio A

The operator supplies a complete typed map from each authored scene's
`assets` and `interactive_objects` identifiers to an existing original
visual `jobs` or `asset_recipes` entry. No unregistered recipe, missing
reference, duplicate asset or unsupported source field is silently accepted.

The compiler checks the canonical four-section story/cast/scene/quest digest,
the **separate visual source digest**, and optional exact quest session digest.
It replays the canonical quest engine and emits per-scene asset bindings and
per-recipe work orders, with immutable source and content digests. Each output
explicitly states that no native asset, rights review or playable asset binding
has been verified. Source design intent is not a manufactured mesh or texture.

CLI: `python -m scripts.studio_scene_asset_cli --project PROJECT
--expected-source CANON_DIGEST --expected-visual VISUAL_DIGEST
--assignments '{"origin":{"survey_beacon":"biome_kit",...},...}'`

Use `--publish-directory EXISTING_DIR` to write an exclusive private
`scene_asset_bindings.json`, or `--verify-directory EXISTING_DIR` to
replay a saved manifest. The private writer uses no-follow directory
descriptors, a fsynced temporary file and atomic no-overwrite publication.
`--compile-preview` invokes the existing deterministic 2D HTML5 game
compiler and includes its actual receipt, **without** asserting that the
native assets were generated or bound to that preview.

Jeeves discovers the static operator-gated
`studio_authored_scene_asset_bindings` tool, whose typed request performs
read-only source verification. The CLI's persistence permission is separate.
