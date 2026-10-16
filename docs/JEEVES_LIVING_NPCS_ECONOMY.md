# Jeeves Living NPCs and Original Economy — Implementation Volume

**Scope:** deterministic schedules, canonical dialogue choices, original cast
relationships, trust-gated routes, bounded shop stock, economic conservation,
Godot client integration, Dragon empirical study and adversarial simulations.

These capabilities live inside the existing original-game Director engine.
They do **not** replace the Jeeves language model, synthesize voice acting,
train a production model, grant permission for copyrighted content or prove a
high-fidelity graphical game has been shipped.

## 1. How the new system changes the world

A campaign can now contain an *optional* `world.dynamics.society` block:

- **Residents:** unique original NPC IDs; authored character names,
  greet-lines and four-phase home/work schedules; persistent trust; faction
  reputation effects; named world flags that unlock at specified trust;
  multiple mutually exclusive per-period authored conversation choices.
  Exact choices are recorded in the canonical persistent dialogue history;
  authored one-time revelations cannot be repeated merely by resting.
- **The calendar:** a reviewable number of canonical game turns per phase;
  dawn, day, dusk and night rotate deterministically. A `rest:rest`
  action advances game time without touching the wall clock. NPC attendance
  changes solely because the actual Director turn count changed.
- **Trade:** real local shops operated by characters who must physically be
  scheduled at the correct market scene; unique merchandise, finite stock,
  inventory quantity, buy/sell prices, persistent wallet and transaction
  history. Sales of source-authored quest rewards are prohibited; tradeable
  goods have separate item identities.
- **Branching dialogue:** `discuss:resident_topic` offers actual authored
  prompts and replies, not merely chat labels. Options can raise or lower
  trust, influence factions, unlock an event, or require a real quest outcome
  before appearing. A character can only be spoken to once per original
  calendar cycle. A generic `speak:resident` greeting remains available
  to actors without authored options.
- **Integrated access:** a `Requirements.trust` condition can guard walking
  links or special transit. A merchant ticket purchased with real currency
  can be required and consumed on a ferry. The transit remains unavailable
  until its condition is satisfied.

Every such action goes through `available_director_actions` and
`director_step`, then the existing locked append-only journal. A stale
HTTP action or counterfeit dialogue selection cannot become game progress.

### Compatibility

Legacy Director worlds keep the same world payload and digest. Old
`WorldDynamics` documents, `Requirements` records and saves omit society
and trust unless those features are actually authored. Existing saves are not
silently migrated or overwritten.

The society schema uses a strict JSON allowlist. An unknown source field,
duplicate NPC, unknown location, unowned shop, duplicate merchandise, unsafe
resource ID, impossible item provenance or undefined faction is rejected.

## 2. Generate a reviewable character-and-commerce world

```bash
python -m skeleton dev game jeeves director-society-design \
  --project ./original_game \
  --source design/director_campaign_source.json \
  --intensity 5
```

The source may already have original dynamic faction/transit rules, but must
not already have a society block. Jeeves creates a **deterministic candidate**
with schedules, original NPC names, shop locations, goods, and a pair of
mechanically relevant transitions:

1. A resident-guided shuttle unavailable until player-earned trust meets
   an explicit minimum.
2. A separate original ferry requiring a purchased market ticket, which
   is consumed by the actual transit action.

Its five authoring intensities expand resident counts, shops, merchandise,
conversation alternatives and calendar richness where the original scenes
allow them.

Each character gets a positive and skeptical authored dialogue option;
complexity levels 3–5 also add a retrospective conversation available only
after a real authored quest outcome. The candidate has
`author_review_acknowledged=false` until reviewed. These mechanical drafts
are **not** Hollywood-grade automatically written dialogue.

The preview returns the complete source and `design_sha256` without writing.
After reviewing every resident, narrative voice, economics and gate condition:

```bash
python -m skeleton dev game jeeves director-society-publish \
  --project ./original_game \
  --source design/director_campaign_source.json \
  --intensity 5 \
  --approve <exact_design_sha256>
```

This creates a **new** `design/director_society_<digest>.json` source.
It never rewrites the source game, a previous generated project, an existing
save file, or an earlier Dragon research receipt.

## 3. Play the authored social systems

```bash
python -m skeleton dev game jeeves director-session-begin \
  --project ./original_game \
  --source design/director_society_<digest>.json \
  --session pioneer
```

Inspect the session to see a source-verified `society` object with
`calendar`, `present_residents`, `open_merchants`, `wallet`,
`owned_goods` and relationships. Only currently legal actions appear.

These choices must still be submitted against the exact current sequence and
state digest. The following are example action names, not guaranteed options
for every authored world or every time of day:

```bash
python -m skeleton dev game jeeves director-session-step \
  --project ./original_game --session pioneer \
  --choice discuss:resident_1_offer_help

python -m skeleton dev game jeeves director-session-step \
  --project ./original_game --session pioneer \
  --choice buy:bazaar_1_trade_1_good_1

python -m skeleton dev game jeeves director-session-step \
  --project ./original_game --session pioneer \
  --choice transit:ticketed_bazaar_passage
```

The transaction example transfers real currency, decrements merchant stock,
adds the purchased item and consumes it when the ferry is used. Selling the
item back has a real resale value no greater than its original price; it can
never mint unlimited coins by repeatedly buying and selling.

Dialogue branches can have different outcomes despite meeting the same NPC;
conversation cooldowns require a new in-game calendar cycle for further
conversation. NPC location changes with canonical turns, not UI animations or
system wall-clock time.

## 4. Search a legitimate socially unlocked route

```bash
python -m skeleton dev game jeeves director-route \
  --project ./original_game --session pioneer \
  --destination scene_04 --route-profile fastest --alternatives 4
```

State-space navigation now accounts for:

- Actual scheduled NPC presence and once-per-cycle conversation permissions.
- Player decisions that increase/decrease trust or change original-world flags.
- Wallet balance, merchant availability, finite stock and purchased tickets.
- Original walking gates, factual transit routes, time cost and consumed items.
- The timing effects of rest and travel, including NPC relocation.

The solver can return a valid route with dialogue and shopping actions
*before* movement. The witness includes each action's prior/after state hash,
resulting trust, market spending, transport and destination.

There are finite **per-query** budgets to protect a low-resource machine
against exponential exploration. No search limit is a game-duration limit.
If it cannot prove a path within that budget, it must not claim the destination
is permanently inaccessible.

The existing full-campaign witness generator also uses real permissions
when a society is attached, so it cannot secretly walk through locked exits
while claiming to complete an authored game.

## 5. Godot v7 visual client and narrative receipts

```bash
python -m skeleton dev game jeeves director-atlas-export \
  --project ./original_game \
  --source design/director_society_<digest>.json
```

The new, separate `-live-v8` export preserves all earlier v1–v6 source
projects. The native client displays:

- The authoritative current dawn/day/dusk/night period.
- NPCs actually scheduled in the current scene, with their authored greetings.
- Available conversation prompts, without leaking unreached option responses.
- Relationship trust, finite merchant stocks, prices, wallet and bought goods.
- Trust-gated movement and purchased-ticket transit alongside existing
  faction/world flags.

The procedural Godot stage visually marks confirmed NPC arrivals and departures
without inventing actual full-body animation, performance or generated voices.
Source-verified action receipts expose the character's exact authored reply
*after* the player's discussion choice, together with actual trust/wallet
consequences.

As with the rest of the prototype, **Godot runtime launch, real controller
testing and final native visual completion are not certified by source alone**.

## 6. Canon and Dragon's empirical evidence

```bash
python -m skeleton dev game jeeves director-causality \
  --project ./original_game --session pioneer

python -m skeleton dev game jeeves dragon-society-study \
  --project ./original_game --session pioneer

python -m skeleton dev game jeeves dragon-society-contrast \
  --project ./original_game --session pioneer \
  --other-session alternate_choice
```

The causality auditor now records the actual scene/time, NPC trust change,
option selection, faction reaction, spent currency, item movement and world
event that followed each real action. The new Dragon society researcher
independently replays the complete session against its source/receipts, counts
NPC encounters by game period, selected dialogue branches, merchant actions,
depleted stock, real wallet transfers and unlocked events.

For long histories, the complete counts remain authoritative. Only returned
human-readable examples are bounded (first 100 event highlights).

To admit a reviewed research receipt without training or promoting any model:

```bash
python -m skeleton dev game jeeves dragon-society-study \
  --project ./original_game --session pioneer \
  --approve <exact_study_sha256>
```

Receipts are content-addressed and create-only. No hidden user feelings,
personal satisfaction, conversational intimacy, unauthorized third-party
character dialogue or production AI weights are inferred or fabricated.

Dragon's existing empirical policy context also distinguishes different
NPC trust, shop stock, wallet, owned goods and current game-time situations.
It cannot reuse post-unlock advice as though nothing had changed.

## 7. Societal scrutiny and adversarial economics

```bash
python -m skeleton dev game jeeves director-society-audit \
  --project ./original_game \
  --source design/director_society_<digest>.json

python -m skeleton dev game jeeves director-society-stress \
  --project ./original_game \
  --source design/director_society_<digest>.json \
  --routes 8 --intensity 5
```

The static audit reviews all NPC schedules and world location identities,
available conversation unlocks, faction effects, shops that are never open,
nonexistent or unaffordable goods, negative and positive trust paths, market
stock issues and locked transit requirements.

The stress harness runs up to eight deterministic adversarial profiles:
market roundtrips, relationship building, skeptical dialogue, travel,
liquidity pressure, calendar advancement, mixed action choices and unlock
experiments. Every simulated game action is validated against the canonical
engine and then replayed **again** from genesis with matched state hashes.

It explicitly verifies conservation of wallet money, absence of buy/sell
profit exploits, monotonic world events, finite stock and inventory, and
consistent NPC trust. The simulation does not create a player save or impose
limits on lifetime game actions. The per-probe action count is bounded for
diagnostics and safe use on low-resource hardware.

No automatic or recurring GitHub CI workflow has been created.

## 8. Specialized verification and unresolved production gaps

```bash
python -m unittest tests.test_jeeves_director_society
python -m unittest tests.test_jeeves_director_dynamic_world
python -m unittest tests.test_jeeves_director_labyrinth_causality
python -m unittest tests.test_jeeves_director_media_e2e
```

Additional native checks remain mandatory before release: install startup
on actual hardware, real renderer and controller playthroughs, native save
recovery, continuous animation, accessibility, voice casting, original
score mastering, professional narrative continuity review, actual trained
production LLM checkpoint inference and full game start-to-ending QA.

**Status:** code-level implementation and specialized tests. The presence of
test source does not mean the tests were executed or passed. Production
game-completion and checkpoint-training certificates remain unsigned.
