# Offline visual comparison of playable histories

The canonical game-project CLI renders two replay-verified alternate game
histories on the same source tilemap. It uses a read-only ASCII overlay:

    python -m skeleton app game-project --render-play-comparison first.json --other-session second.json --session-capsule original.json --at-frame 2

Marker 1 is the first player, marker 2 the second player and X indicates
both avatars occupy the same cell. The requested zero-based frame must be
present in BOTH saves. No extrapolated or invented movement is displayed.
Both saves are independently verified against the original capsule before
rendering, and the output contains source and session identity digests.

The renderer never writes saves or contacts a network. It does not assert
native 2D/3D rendering, legal release clearance, or a signed game export.
