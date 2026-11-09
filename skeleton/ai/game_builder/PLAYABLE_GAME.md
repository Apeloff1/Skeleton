# Original playable-game compiler — executable milestone

This game-builder capability generates **working, original, offline HTML5
games** from a validated design intent. It does not pretend that a document,
checklist, random code snippet or a browser mock is a working playable game.

Canonical owner: skeleton/ai/game_builder. Game assets are programmatic
geometric shapes; no third-party game expression or crawler excerpts are
embedded as executable code.

## Fastest complete path

Save a JSON intent in project-intent.json:

~~~json
{
  "project_id": "my-maze",
  "title": "Crystal Expedition",
  "subtitle": "An original maze about exploration and planning.",
  "seed": 2034,
  "width": 19,
  "height": 15,
  "levels": 3,
  "collectibles_per_level": 3,
  "hazards_per_level": 5,
  "theme": "forest",
  "starting_health": 3
}
~~~

The trusted local CLI runs real maze generation, complete per-level
collectible/exit search, replay execution and a browser export.

~~~bash
python -m skeleton.ai.game_builder.playable_cli \
  --intent ./project-intent.json --trusted-local-operator \
  build --output ./crystal-expedition.html
~~~

Open crystal-expedition.html in an ordinary modern browser. The page requires
no local HTTP server, CDN, package manager, provider account or network access.
It includes keyboard arrow/WASD movement, touch-friendly directional buttons,
a fully responsive canvas, an accessible text-map alternative, collected
objectives, locked exits, hazards, limited health, score, level progression,
undo for the last 256 moves, original themes and replay export.

The experience is **turn-based**. Every directional input is one logical game
turn. Players navigate the original generated maze and collect all its
crystals before reaching each level's exit. Hazards remove health. Losing all
health ends the run; finishing the final level wins the game.

No JS dependencies are fetched. Executable code and style are pinned by
SHA-256 Content-Security-Policy hashes. Imported titles are HTML-escaped,
and embedded JSON has script-tag-significant characters encoded. Source data
cannot inject JavaScript. It is still a small original 2D adventure, not a
general 3D engine or a compiled desktop installer.

## Deterministic generation and independently replayable gameplay

For every requested level, the builder:

1. Generates an original connected grid maze with deterministic seeded DFS.
2. Places one start point and a distant exit.
3. Places 1–6 collectible objects, with enough navigable paths to each.
4. Places optional hazards outside a protected feasible-route network.
5. Runs bounded BFS over player coordinates and collectible-bitset state,
   considering hazards impassable for its safety proof.
6. Replays the resulting move sequence against the actual gameplay state
   machine, requiring a win with all starting health intact.
7. Exports an HTML browser runtime using those same tile/action/objective rules.

The proof path is a real executable sequence of movement actions, not a
test-only placeholder or a claim that a map merely looks solvable.

~~~bash
python -m skeleton.ai.game_builder.playable_cli \
  --intent ./project-intent.json --trusted-local-operator solve
~~~

Browser users can click "Export my run" to download a JSON action trace.
The browser's assertion is **untrusted** until verified independently in
Python against the identical content-addressed world. A malicious or
incorrect client cannot claim verified success just by editing the trace.

~~~bash
python -m skeleton.ai.game_builder.playable_cli \
  --intent ./project-intent.json --trusted-local-operator \
  verify-replay --input ./game-play-replay.json
~~~

The verifier re-executes every action, computes the final objective, health,
score and step state, and emits hash-chained replay evidence. Client replay
files cannot run arbitrary commands, inject game state or bypass the
game-world digest check.

## Actual gameplay-analysis feedback

The following command turns a browser action trace into reproducible
playability metrics:

~~~bash
python -m skeleton.ai.game_builder.playable_cli \
  --intent ./project-intent.json --trusted-local-operator \
  analyze-replay --input ./game-play-replay.json
~~~

Analysis reports per-level completion, visited tiles, move counts, contacts
with walls, backtracks, repeated visits, hazards encountered, collectible
progress and the comparison with the independently verified safe route.
It emits bounded, non-executing UI/UX improvement suggestions such as checking
wall readability, hazard telegraphing, landmarking or confusing exit goals.

No automatic personality, taste, player identity or preference inference is
performed. These are actionable heuristics, not causal proof of a defect or
empirically calibrated user models. The programmatic
aggregate_playability(world, replays, consent_to_aggregate=True,
authorized=True) recomputes a bounded cohort of 3–1000 distinct replay traces;
duplicates and mismatched game-worlds are rejected to avoid false evidence
inflation. An embedding service must still authenticate players, record
meaningful consent and respect retention and privacy policies.

## Bridge to the reviewed knowledge and source-rights system

A separate entry point compiles the **same original game** while attaching a
human-approved research brief that has passed independent source identity,
content digest, license, use-scope and similarity-risk checks:

~~~python
from skeleton.ai.game_builder import (
    GameBuildIntent,
    ReviewedKnowledgeStore,
    RightsLedger,
    compile_game_from_reviewed_research,
    require_cleared_research_current,
)

intent = GameBuildIntent(
    project_id="my-maze", title="Crystal Expedition",
    subtitle="An original research-informed maze.", seed=2034,
)
rights = RightsLedger()
# The real host must register independently reviewed SourceRecords with
# EvaluatorProvenance in rights before attempting this call.
with ReviewedKnowledgeStore("./reviewed-knowledge.sqlite3") as library:
    brief = library.build_brief(
        "my-studio", "exploration", authorized=True,
    )
    project = compile_game_from_reviewed_research(
        library, brief, rights, intent,
        human_approved=True, authorized=True,
    )
    require_cleared_research_current(
        project.cleared_research, library, rights, authorized=True,
    )
    html_bytes = project.playable.html.encode("utf-8")
    receipt = project.receipt()
~~~

Rights clearance is bound to the generated game **world digest**.
The output HTML digest is recorded separately in the compiler receipt.
Source evidence is displayed only as escaped, user-visible research citations.
It never becomes game logic, privileged assistant instruction, training data,
or copied third-party imagery/music/code. A studio can still use evidence to
make independent **human** design decisions and create original level
parameters. No source text is automatically converted to game mechanics.

If source rights change after compilation, callers must recheck the packet
before downstream game-builder use. The existing RightsLedger remains the
authority for reference clearance and higher-level artifact/release checks.

## Resource and failure boundaries

- Supported maps: odd dimensions 9..41, up to 8 levels, at most 6
  collectibles per level, at most 24 hazards per level, 1..10 starting health.
- Deterministic BFS has a bounded collectible-bitmask search state space.
  Inability to construct a safe winning route aborts generation.
- A replay can contain at most 20,000 actions. A longer or malformed log
  is rejected rather than silently truncated.
- The exporter uses same-directory temporary files, fsync and atomic replace
  for the HTML file. It is not a transactional multi-artifact build system,
  a cloud publication endpoint, or redundant storage.
- Browser actions are local and offline. The engine does not contact an
  inference provider, accept arbitrary scripts, or persist raw input
  telemetry to a remote server.
- Replay hash chaining checks deterministic integrity; it cannot prove a
  person genuinely played, nor independently authenticate an internet source.
- The local --trusted-local-operator switch is an **acknowledgement** that
  external host authorization already occurred, not an authentication system.

## Required qualification

~~~bash
python -m unittest \
  tests.test_game_builder_playable_world \
  tests.test_game_builder_playable_export \
  tests.test_game_builder_research_to_playable \
  tests.test_game_builder_playability_analysis -v
python scripts/check_ai_file_tree.py
python scripts/check_architecture_map.py
python scripts/check_ai_app_construction.py
python scripts/check_capability_interfaces.py
python scripts/check_provider_bootstrap.py
python scripts/check_enterprise_ai_superiority.py --json
python scripts/check_enterprise_ai_implementation_notes.py --json
~~~

The existing "AI Game Builder 500 Levels" workflow compiles the implementation
and runs these game/research tests at the PR's exact head. Passing focused
tests is not equivalent to an independent architecture, release, safety or
end-user UX sign-off. This milestone remains draft until CI and external
verification close.
