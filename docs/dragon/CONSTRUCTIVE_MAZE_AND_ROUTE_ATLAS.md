# Dragon Constructive Maze and World Atlas

**Implementation:** October 2026 original-game routing lane.

**Current runtime scope:** original game-world graph and Python game-state engine; source-emittable actual C99 single-region maze; C99 checkpoint probes for every room; authenticated playable portal runtime across regions. This is not a claim of a single 576-room compiled native game or universal console SDK support.

## One rule: construct completion before optional difficulty

Dragon now builds an actual winning spine **before** adding any secret, obstacle, dead end, long detour, scenic circuit or weather-dependent route. This is not an unconstrained random graph that happens to be checked later.

For each 4x4 to 8x6 original maze, the builder:

1. Connects the start and goal by a permanent, weather-independent serpentine backbone.
2. Adds reverse corridors so players can retrace movement in both directions.
3. Connects every remaining room as a rewarding side chamber with a return passage.
4. Adds optional braid links, scenic detours and route shortcuts without deleting the original safe win.
5. Places secret clues in early side chambers whose players can actually return to an accessible secret passage.
6. Adds rain, snow, wind, ferries, taxis, tram and magic routes with real time, cost and weather conditions.
7. Generates deliberately long, inefficient multi-lap doubleback witnesses in addition to short wins.
8. Executes exact game-state replay for the main winner, every-room recovery path and selected side routes.
9. Verifies the main winner under clear, rain, wind, storm, snow and high-tide conditions.
10. Independently regenerates the entire world from its source seed and exact settings before accepting the content-addressed completion certificate.

Each native C99 source includes actual room-specific replay probes. The compiled game must enter the **claimed room at a declared action index**, not merely run the same main route under another test name, and subsequently reach the goal.

### What completion means

- **Guaranteed:** A source-defined winning path exists, actually executes, and remains available across every supported climate.
- **Guaranteed:** Every room is reachable from start along an ordinary valid history, and after visiting it the generator proves a path from that history to the final goal.
- **Guaranteed:** Source-only releases are rejected if world identity, clue gates, path choices, room evidence or weather proofs differ.
- **Not claimed:** Every arbitrary action sequence remains winnable after completely exhausting stamina, money, oxygen, fuel, elapsed time or the hard move cap. Restart remains available.
- **Not claimed:** A 2D world graph alone simulates vehicles, tides, spaceflight, 3D collision, psychological enjoyment or console hardware.

These are necessary distinctions for honest playability certification.

## Expanded route variants and actual semantics

Dragon separates *the shape of a route* from *how it is traversed*.

**Shapes:** mandatory, branched, braided, switchback, doubleback, retrace, return trip, dead end, rewarded cul-de-sac, panoramic loop, long excursion, impractical wandering, multi-lap route, shortcut, hidden clue passage, secret unlock, free roam, maze junction, hub, vertical path, multi-layer route, weather gate, fuel gate, oxygen gate, skill gate, timed route, public-transport transfer and regional portal.

**Modalities:** walk, run, climb, cableway, taxi, metro, tram, bus, train, boat, ferry, surf, dive, aircraft, glider, updraft, rainy or icy passage, magic, dream, teleportation, wormhole, orbital shuttle and interstellar ship.

Travel conditions in the world graph have actual bounded resource effects: minutes, departures, price, fatigue, risk, one-time discovery, token prerequisites, fuel, oxygen, mana and weather. The existence of a label does not assert dedicated vehicle or environmental physics.

Original Route Worlds include a genuinely replayable multi-decade space itinerary alongside ordinary transport, scenic alternatives and clue-gated secrets. The maze generator adds actual longer repeated detour variants even when they are less efficient than the protected main corridor.

## Beyond one 48-room world

Individual C99 route games deliberately cap the per-world graph at 48 places and 192 edges. Large worlds therefore use composition, not unbounded arrays masquerading as native support.

Dragon's certified World Atlas can combine **2 to 12 independently verified mazes**, representing up to **576 genuinely playable rooms**.

- Each sub-maze has its own original seed, room-by-room completion witnesses, secrets, optional scenic paths and all-climate winning corridor.
- Inter-region portals are real moves; a player must first finish the current region.
- The region progression is a directed acyclic graph with ordinary and skip-ahead paths to the common final goal.
- Fast and visit-every-region scenic journeys are independently replayed through genuine regional actions and portal decisions.
- The exact number of regional paths is computed by dynamic programming, without enumerating millions of fake path names.
- The authenticated Atlas creator allows free play, regional portal choices, guided quick paths, guided long scenic paths and move undo.

**Runtime boundary:** Portal gameplay currently runs in the Python product backend. C99 source is available for individual regions; one combined compiled 576-room executable has not yet been implemented or certified.

## Difficulty and player agency

The source-level Challenge setting changes actual spine traversal length and shortcut density. Gentle introduces additional alternatives; harder profiles reduce easy braids and lengthen core travel. Side chamber clues, secrets, return routes, reset and optional hint/walkthrough features remain compatible.

Intentionally frustrating choices must retain accessible alternatives and recoverable detours. Machine-measured route complexity is not proof of human enjoyment. Collect consenting, aggregated player feedback and verify difficulty perception empirically before claiming adaptive fun.

## Production scale and legal safeguards

A design ambition exceeding 1.6 million original game titles is not achieved simply by enumerating seeds. Dragon's route-world candidate batch mechanism records genuine proposed world graphs, hashes and duplicate rejections. A candidate must not be counted as a distinct published, independently licensed game.

Production release requires independently reviewed originality, source/code rights, art, story, music, trademarks, patents when relevant, platform redistribution rights, playable native binaries and real end-user playtests. The current source-production lane does **not** grant third-party legal clearance automatically or import commercial levels or proprietary ROMs.

## Validation entry points

Run locally from the repository root:

    python -m compileall -q skeleton/ai/webcrawler/dragon_route_maze.py skeleton/ai/webcrawler/dragon_route_atlas.py
    python -m pytest -q tests/test_ai_dragon_route_maze.py tests/test_ai_dragon_route_maze_native.py tests/test_ai_dragon_route_maze_integration.py tests/test_ai_dragon_route_atlas.py
    python -m pytest -q backend/tests/test_dragon_route_maze_routes.py backend/tests/test_dragon_route_atlas_routes.py

The native CI workflow also builds a real C99 maze and checks its last-room, secret, long doubleback and all-climate proof requirements. Tests being listed is not evidence that the exact-head Actions have passed.

## Research pointers

- Linden, Lopes & Bidarra (AIIDE 2013), Designing Procedurally Generated Levels: https://doi.org/10.1609/aiide.v9i3.12592
- Horswill & Foged (AIIDE 2012), Fast Procedural Level Population with Playability Constraints: https://doi.org/10.1609/aiide.v8i1.12511
- The Dungeon Variations Problem Using Constraint Programming (CP 2021): https://doi.org/10.4230/LIPIcs.CP.2021.27
- Majercik et al. (September 2026), Providing Rapid Design Feedback for 3D Obstacle Course Games Using Constrained Solvability Queries: https://arxiv.org/abs/2609.36225
- Adaptive Level Modification via Player Skill Classification and Large Language Models (Scientific Reports 2026): https://www.nature.com/articles/s41598-026-63084-z

These sources inform constraint modeling and review practice; they do not grant rights to copy published examples or certify this implementation's player experience.
