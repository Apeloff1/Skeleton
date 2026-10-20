# Seven advanced navigation production milestones — 2026-10-20

Owner: `skeleton/jeeves/`. Authority: canonical `ExpeditionWorld`,
`assess_travel`, `find_route`, and `ExpeditionEpisode`. This adds a
derived, source-bound campaign export, **not** a new engine or navigation owner.

| Milestone | Runtime deliverable | Adversarial/source acceptance |
| --- | --- | --- |
| N1 3D world atlas | Every XYZ landmark, altitude layer, directed link, safety/rest node, source digest | Reject over-budget worlds rather than silently dropping geography |
| N2 playable route portfolio | Four original navigation strategies actually replayed against the game engine, Pareto comparison | Reject unreachable links, tired traveler, locked movement and source mismatch |
| N3 game-only instrument trace | Compass bearing, bubble-sextant reference, trig-altitude, slant ranges, waypoint fixes | Reject edge discontinuities; never label authored fixes as real GNSS |
| N4 fog and exploration journal | Canonical action steps, visited/revealed frontier, linked receipt history and game-event restore | Reject forged visits and divergent game state |
| N5 environmental itinerary | Canonical per-edge terrain/weather/weight stamina, damage and traction and recovery rests | No crossing marked passable without canonical `assess_travel` and actual step |
| N6 original encounter director | Waypoint-specific source cues and safe recovery locations, without side effects | No quest grants, equipment minting, invented dialogue authority |
| N7 compiled cross-axis assurance | All six source reports, seventh receipts/index gate, complete original game export and independent recompile | Source change invalidates hashes; legal and hardware signoff remains blocked |

`compile_original_campaign` includes `game/frontier/advanced_navigation.json`
in its complete file-hash closure, exposes `advanced_navigation_receipt`, and
`verify_original_campaign` repeats compilation to catch changes. Targeted
tests exercise all seven engines as well as candidate tampering.

**Limitations:** These are engine-neutral fictional-game route and map tools.
They do not claim measured GNSS, native-rendered HUD, GPU performance, actual
physical gamepad input, real-world safety forecasts or external copyright review.
Live Godot HUD visualization should bind its actor position to the canonical
game-state owner, not to this derived plan. Long-duration reliability and product
release remain independent acceptance gates.
