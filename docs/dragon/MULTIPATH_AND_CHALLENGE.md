# Dragon: genuinely branching games and challenge direction

**Implemented scope:** original finite-grid native Sokoban game production.
**Not claimed:** completion across every game genre, console or platform.

## A game is not one solved path

Dragon now separates four systems, with independently checkable evidence:

1. **Within-level solutions:** BFS, A*, lexicographic push-first Dijkstra,
   safer-push Dijkstra and novelty-seeking Dijkstra. Every returned sequence
   physically completes the original board. Alternative winning paths are
   accepted only if their crate-push order or navigation footprint changes.
   Merely shuffling identical inputs is not a new design.
2. **Between-level choices:** a real 1–8-stage chapter DAG. Every stage is
   reachable, edges lead forward, cycles and phantom destinations are
   prohibited. A 3+-stage branching release can have different endings;
   1–2-stage releases never falsely claim two endings.
3. **Difficulty pacing:** measurable shortest moves, number of pushes,
   explored states, alternative routes, wall-adjacent pushes, fork counts,
   actual solver complexity and recovery chapters.
4. **Player experience:** human enjoyment, frustration and preference
   observations are separate, voluntary evidence. Solver difficulty is
   not a substitute for player ratings.

All real native C99 game source packages include independently replayable
original route reports, the content-addressed progression DAG, objective
search metrics and an explicit challenge plan in the source evidence.

## Multiple solver objectives

- **Exact BFS:** authoritative shortest walking trace; bounded to 120k
  distinct abstract states and 400 gameplay moves.
- **A-star:** crate-goal optimal assignment Manhattan heuristic; ignoring
  walls gives an admissible lower bound. A full solution should have the
  same shortest walking length as the exact BFS.
- **Push-first:** lexicographically fewest pushes, then shortest walk.
- **Risk-aware:** soft penalties for pushing crates alongside wall surfaces.
- **Novelty-seeking:** positively penalizes reused state-action transitions
  from earlier accepted routes, then measures actual winning-route diversity.

Static non-goal corner deadlocks are pruned. A candidate that exceeds the
fixed search budget, detour budget or legal gameplay constraints is rejected.
No result assumes exploration is exhaustive. Missing alternatives are
explicitly unknown, not automatically proven impossible.

### Real game chapter branching

Default native fixed-screen 3+-stage campaigns contain actual player-selectable
forks (input 1/2, or N for primary option). SDL2 offers keyboard and gamepad
alternatives. The game shows next-stage destinations and measured tension.
The native C99 branch selftest solves source stages, transitions through every
fork and checks each ending. The independent release verifier recomputes
graph transitions and the actual source header.

A chapter's first option is ordered by its *measured* destination difficulty,
not a fabricated style adjective. Gentle/balanced usually put the easier
measured route first, challenging/spicy the harder route first. Both
alternatives remain available; the player decides.

## Deliberate challenge, occasional frustrating peaks, fair recovery

Challenge selection is **active generation**, not just analytics.
For non-default difficulty profiles Dragon evaluates at most five distinct
original homebrew world candidates per stage, every one bounded and checked
by the authoritative grid BFS before selection.

- Gentle favors lower measured difficulty.
- Balanced preserves original legacy map geometry.
- Challenging favors a demanding board but offers a solver-vetted recovery
  every third stage.
- Spicy offers *occasional* opt-in difficulty spikes with neutral exploration
  and an easier solver-vetted recovery every fourth stage.

Exact geometry, selected seed, level-intent score and all candidate counts
are stored in the release evidence. Authored original levels are **never
silently replaced**. If the chosen candidates still miss the requested
tension target, the evidence flags the mismatch.

Undo, reset, on-demand shortest hints, shortest-path walkthroughs and
lower-tension chapter alternatives are always retained. Do not covertly
maximize anger, trap accessibility settings, or inflate level penalties
to improve engagement metrics.

A challenge director evaluates whole campaigns using independent measured
quantities plus declared intent. It can *optionally* evaluate voluntary,
anonymous aggregated playtest counts and ratings. No identifying gameplay
records are needed or automatically stored, promoted to Wiki/Hoag memory,
used for LLM training, or made public. No real human playtest evidence
currently exists in this work, so no enjoyment is asserted.

## Original creator routes

The authenticated creator has bounded APIs for exact original-level
validation, current-game shortest hints, independent alternate routes,
and whole-campaign analysis. The full-campaign review reports the actual
number of traversable chapter routes, distinct endings, stage challenge
estimates, solver variants and fairness warnings. Client route choices
can be replayed locally; no client hint substitutes for compiled C99 playtest.

Original authored games stay source-only in browser API exports. Real Linux,
macOS or Windows native compilation belongs at an authorized local build
boundary with separate runtime and evidence requirements.

## Known limitations and next genre adapters

This is **not** a general-purpose FPS/RTS/RPG/open-world solver.
Beyond these bounded original puzzle mechanics, each game genre requires a
real transition model, alternative planning objectives, agency metrics,
fair recovery mechanics, graph interpretation and complete playable native
runtime verification. A graphical menu showing choice options does not
by itself prove different experiences exist.

Future lanes include stochastic adversarial AI bots, open-world quest
dependency graphs, enemy adaptation, skill-conditioned path valuations,
speedrunning route diversity, racing trajectories and player preference
models, with independent evaluation for each genre.

## Research used to guide—not certify—challenge design

- Entertainment Computing (2024), Rethinking Dynamic Difficulty Adjustment
  for Video Game Design; DOI: 10.1016/j.entcom.2024.100663.
  Design explicit goals rather than blindly optimizing generic flow.
- Entertainment Computing (2025), Solutions for Dynamic Difficulty
  Adjustment in Digital Games: A Systematic Literature Review;
  DOI: 10.1016/j.entcom.2025.101041. Prefer modular, verifiable adjustment.
- AAAI AIIDE (2012), A Temporal Data-Driven Player Model for DDA;
  DOI: 10.1609/aiide.v8i1.12504. Temporal evidence matters for player fit.
- Entertainment Computing (2013), Effects of Game Difficulty on Player
  Enjoyment; DOI: 10.1016/j.entcom.2012.09.001. Experience and measured
  ability are not equivalent.
- WWW Companion (2017), DDA for Maximized Engagement in Digital Games;
  DOI: 10.1145/3041021.3054170. Game progression is a graph, not one path.

These citations motivate measurable, separately testable mechanisms.
No copyrighted maps, proprietary ROMs, source code, or unlicensed game
assets are fetched or distilled by this generator.
