# Original Million-World Forge — executable breadth, not numerical inflation

**Version:** `original-world-million-forge.v1`  
**Status:** Verified abstract offline Python gameplay after the PR-specific workflow
has passed; native game deliverables remain separate engineering milestones.

## Cardinality with a precise denominator

| Inventory | Count | What it actually represents |
| --- | ---: | --- |
| Individually written causal-root worlds, including earlier atlas | 1,424 | Individually described world rules and player intervention; NOT all independently playable |
| Prior causal-law compositions | 10,240 | 128 newer authored roots × 80 authored consequence regimes, each connected by an authored domain-specific bridge |
| **Gameplay-mode-bound foundation entries** | **102,400** | 10,240 law compositions × 10 distinct rule-executing genre forms |
| **Advanced configurations** | **1,228,800** | 102,400 mode-bound foundations × 12 distinct stateful progression laws |
| New separately written form designs | 10 | Three interaction verbs and distinct win, failure, resource and control mechanics per design |
| New separately written progression laws | 12 | Separately stated continuity contracts and working bounded progression clocks |
| Native shipped game builds | 0 verified | No claim that any of the million configurations has native assets, binary, device certification or commercial-quality design |

**The last three inventory levels are nested, not additive.**
The 1,228,800 are structured configurations, not 1.2 million individually
hand-written stories. Visual style, eras, themes, random seeds, console
targets and difficulty sliders contribute **zero** to this count. One
configuration has an explicit, inspectable root premise, authored
consequence regime, authored domain interaction, playable game form,
and playable continuation rule.

Any proposal to label the count as *1.2 million fully built games*, or
as *1.2 million independently original world narratives*, would be
incorrect. Coverage of common game genres requires a separate inventory
of interactions, quality and hardware tests; cardinality alone does not
prove coverage.

## The ten actually executable reference-game forms

| Form | Three player controls | Executed challenges |
| --- | --- | --- |
| Platform | step, jump, brace | Spatial progress, collisions with gaps, vertical movement and finite stamina |
| Puzzle | toggle, pass, inspect | A bounded three-bit circuit and actual closed gate that opens only under correct switch conditions |
| Tactics | strike, guard, parley | Enemy health, guard, counterattack damage, negotiation and energy/trust costs |
| Survival | drink, shelter, scavenge | Water scarcity, dehydration, weather warmth, finite deposits, damage and safe shelter |
| Colony | construct, cultivate, maintain | Material-backed housing, farms, daily food production, consumption and housing-limited population |
| Racing | accelerate, brake, corner | Bounded speed, track distance, corner wear, lap and vehicle condition |
| Stealth | sneak, distract, hide | Patrol suspicion, physical progress and alert-triggered injury |
| Commerce | buy, sell, forecast | Market stock, real debit/credit of currency and finite sale inventory at changing prices |
| Exploration | explore, resupply, chart | Navigable existing world edges, discovery ledger and finite expedition support |
| Rhythm | tap, hold, sync | Beat-pattern accuracy, tempo progression, lost combos, stamina and score |

These reference systems are intentionally simple and bounded. They
demonstrate executable genre mechanics with deterministic game state,
not polished 2-D animation or complete 3-D physics. FPS ballistics,
RTS thousands-of-units simulation, fighting-game input frames,
open-source legal console ports, MMO networking, sandbox voxels,
Minecraft-scale destructible streaming, VR locomotion, AAA character
animation, networked racing and modern GPU rendering remain
**unimplemented or unverified** here.

## Twelve living continuation laws

`chapters`, `endless`, `roguelite`, `dynasty`, `factions`,
`sandbox`, `mystery`, `seasonal`, `rescue`, `campaign`,
`civilization`, `branching`.

Each is more than a naming tag:

- Chapters: real genre clearance gates a completed episode, followed by
  optional postgame.
- Endless: world difficulty grows periodically; no artificial final win.
- Roguelite: expedition runs reset while verified persistent experience
  survives.
- Dynasty: households and institutions inherit generational obligations.
- Factions: consequential care/power alignment changes material risks.
- Sandbox: finite resource sites regenerate and self-directed building
  remains legal without a mandatory ending.
- Mystery: insufficiently supported assertions impose a measurable
  credibility cost; evidence-backed theories can be promoted.
- Seasonal: cycling climates change survival preparations over time.
- Rescue: unresolved external needs arrive faster than any claim that all
  people can finally be rescued; actual aid consumes materials.
- Campaign: completed genre missions can authorize logistical territorial
  progress.
- Civilization: long-term public investment and its neglect affect
  legitimacy.
- Branching: irreversible choices keep shaping long-run trust and risk.

The `original_world_million_objectives.py` director tracks five
evidence-derived quest stages for every combination: learn the original
world law; enact a causal intervention; complete a genre milestone;
develop the selected arc; continue into a supported aftermath.
A local genre success never becomes a false global win for an
unwinnable or open world. Previously completed genre goals do not lock
the player out of further genre actions, including after a chapter.

## Exact indexed compiler

```text
Base = 10,240 causal-root/regime/bridge combinations
Mode index = base_index * 10 + form_index
Configuration index = (mode_index * 12) + arc_index

range(mode_index)          = 0 .. 102,399
range(configuration_index) = 0 .. 1,228,799
```

The `advanced_id` and SHA-256 `design_id` are stable for a given
version. Every entry is resolved lazily and validated with immutable
typed structures. This does not allocate 1.2 million world instances
in RAM. The old 1,296 individually drafted catalog foundations and
10,240 compositional foundation indices retain their own identities
and semantics.

Event receipts chain a deterministic state digest and actual player
actions; saves validate nested causal state and the selected rulebook.
A SHA checksum protects accidental integrity, **not adversarial
authentication against deliberate recomputation**.

## Try the actual prototype

```bash
# Inspect the exact inventory without counting texture/style variations.
python -m skeleton.game.generation.original_world_million_cli --inventory

# Page through the final entries without allocating a million objects.
python -m skeleton.game.generation.original_world_million_cli \
  --page 1228796 --limit 4

# Play a puzzle objective with a genuine three-switch circuit.
python -m skeleton.game.generation.original_world_million_cli \
  --base 0 --form puzzle --arc chapters --interactive

# Demonstrate a puzzle solution and an endless continuation.
python -m skeleton.game.generation.original_world_million_cli \
  --base 0 --form puzzle --arc endless \
  --actions-json '[{"layer":"mode","verb":"toggle","target":0},{"layer":"mode","verb":"toggle","target":2},{"layer":"mode","verb":"pass"},{"layer":"causal","verb":"end_turn"}]' \
  --objectives

# Develop an actual colony population from built shelter and agriculture.
python -m skeleton.game.generation.original_world_million_cli \
  --base 9999 --form colony --arc civilization \
  --actions-json '[{"layer":"mode","verb":"construct","amount":2},{"layer":"mode","verb":"cultivate"},{"layer":"causal","verb":"end_turn"},{"layer":"causal","verb":"end_turn"}]' \
  --show-map

# Replay, persist or load an exactly indexed world.
python -m skeleton.game.generation.original_world_million_cli \
  --index 1228799 --save advanced-world.json --interactive

python -m skeleton.game.generation.original_world_million_cli \
  --load advanced-world.json --interactive --save advanced-world.json

# Discover the million-layer identity from the original atlas interface.
python -m skeleton.game.generation.original_world_cli \
  --advanced-index 1228799 --brief

python -m skeleton.game.generation.original_world_cli \
  --mode-index 102399
```

Interactive commands: `mode VERB`, `arc VERB`,
`causal VERB`, `objectives`, `status`, `help`, `quit`.
For example `mode toggle 0`, `mode tap 2`, `arc choose care`,
`causal intervene`, `causal end_turn`.

## Verification and delivery boundary

The focused workflow tests the immutable 102,400-index registry
bijection, million-index exact/unranked round trips, ten mode state
machines, twelve continuation clocks, all 120 intersections,
genre objectives, physical inventory debits, consent/choice,
win-versus-postgame separation, score/progress transitions and
nested save/replay. It also runs actual CLI scripts and the earlier
world-simulator regressions. The PR must remain draft until
current exact-head CI and review are complete.

The next *real* completion tasks are native editor screens and useful
visual previews; complete independent scenario laws for the other
1,424 handwritten world premises; 2D/3D physics tier adapters,
interaction graphs and entity AI; native game packaging and console
homebrew where licensed/legal; playable art/audio generation;
playtest and originality review; low-resource fallback profiles;
and progressive rendering and streaming of enormous worlds. Until then,
the literal claim is **a million addressable rule-composed abstract game
configurations**, not a million finished products.


## Systemic genre × world-law × narrative synergy

`original_world_million_synergy.py` adds **160 explicitly governed
cross-domain balancing cells**, connecting each of sixteen causal
disciplines to each of ten actually executable gameplay modes. Twelve
continuation policies translate physical difficulty pressure into
long-run effects. That is **1,920 defined interaction pathways**, not
1,920 more independent games.

Every checkpoint evaluates physical state: a platformer's gaps and
damage; a logic puzzle's unresolved switch circuit; a tactician's
enemy pressure; a survivor's hydration and warmth; settlement food and
housing deficits; actual vehicle wear; guard alertness; market
liquidity; unrevealed reachable territory; and recorded offbeat
performances.

The authored world domain adjusts how those pressures matter.
Continuation then determines the *kind of setback*: additional duties,
hazards, lost public legitimacy or reserves, lingering uncertainty,
generational responsibilities, and rescue needs. A high-pressure
simulation world running an endangered colony can therefore generate
a different measurable failure trajectory than a gentle governance
world running the same initial player actions.

The coefficients are **balancing hypotheses**, not claims of
playtested optimality; they remain bounded, deterministic,
inspectable, and excluded from the world count. They do not override
player consent or conjure free physical resources.

The real playable reference game additionally checks that a
platformer's grounded path cannot skip a physical gap without a jump
or consumed brace, and that racing requires completing two marked
course bends with a still-functional vehicle rather than earning
a lap merely by repeatedly accelerating. These constraints are
critical to actually differentiating genres in execution.

### Tests for cross-system fidelity

```bash
python -m pytest -q --noconftest \
  tests/test_original_world_million_compiler.py \
  tests/test_original_world_million_cli.py \
  tests/test_original_world_million_objectives.py \
  tests/test_original_world_million_synergy.py
```

The game-specific workflow also runs legacy atlas tests and actual
scripted world demonstrations on the exact PR head.
