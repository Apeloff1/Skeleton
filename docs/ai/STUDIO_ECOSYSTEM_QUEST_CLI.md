# Executable original-studio quest CLI

Use `python -m scripts.studio_ecosystem_cli --project studio_puzzle_expedition_copper_mesa --play-quest`
to inspect available authored stages. Supply `--quest-actions` with a JSON
array of stage ID/alternative text pairs for bounded, deterministic execution.

The simulator verifies source digests, choice membership, stage prerequisites,
and replay integrity. It does **not** perform native genre rendering,
manufacture external evidence, or certify a playable consumer release.
