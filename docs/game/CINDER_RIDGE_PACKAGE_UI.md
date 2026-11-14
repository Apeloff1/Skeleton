# Cinder Ridge — offline source package and terminal scene renderer

The Cinder Ridge package is a portable JSON game source artifact with a deterministic manifest. `python -m skeleton.game.gameplay.ridge_rescue.package_cli build --output ridge.game.json` builds a package from a validated reachable source world; `verify --package ridge.game.json` recomputes source/manifest digests and rejects mismatched contracts. `play --package ridge.game.json --actions '[...]' --output ridge.run.json` runs the actual embedded source through the canonical engine and emits a replay-verified save. The package does not require an online service or a generated binary.

The terminal renderer shows the actual grid, finite resource nodes, civilians, raiders, shelter and player. It uses bounded Manhattan-distance vision by default, with a separate explicitly requested reveal mode for testing and editing. ASCII-symbol overlays are deterministic and do not change game state. No graphical renderer, Windows installer or device qualification is claimed.

Manifest SHA-256 is a corruption/integrity check, not a trusted signature or supply-chain provenance attestation. Only original authored game data is included. Tests cover source-to-package-to-runtime-to-replay, rehashed manifest forgery, invalid source, bounded sizes, player visibility and CLI integration.
