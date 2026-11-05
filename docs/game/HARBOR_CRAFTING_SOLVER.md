# Lantern Quay — bounded replay-verified game solver

The solver closes the source-to-playable acceptance loop by producing actual
legal player actions, not a synthetic winning receipt. It uses the same
deterministic player movement, tile collision, NPC patrol, finite resource
stock, merchant trading, crafting, dock delivery and choice consequence
rules as the human-played campaign.

Generate a winning plan from the original authored world:

    python -m scripts.game.harbor_crafting solve --choice signal > plan.json

Verify the full source, action list, game replay, terminal win and deterministic
solver result:

    python -m scripts.game.harbor_crafting verify-plan --plan plan.json

Use --choice shelter to solve the alternate earned ending. Use --source to
solve an edited world. The planner derives recipe dependencies, gathers finite
resources, trades with the NPC when materials are exhausted and coins permit,
uses bounded time-expanded BFS for collision-aware navigation, delivers the
required cargo, and executes the final player choice. It rejects crafting
cycles, insufficient currency, unavailable items, unreachable destinations,
tick exhaustion and excess route states. The route search has a hard 4096
state budget and source tick limits are preserved.

The solver is deterministic and its plan is verified against the real game
transition function and complete replay bundle. It does not prove all
possible authored worlds solvable or optimize every route. It is not an
unbounded search service, remote authority or signed release artifact.

Focused acceptance:

    pytest -q skeleton/testing/test_harbor_crafting_planner.py
