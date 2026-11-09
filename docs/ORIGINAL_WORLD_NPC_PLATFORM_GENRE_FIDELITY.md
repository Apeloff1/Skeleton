# NPC Fidelity by Console, PC Generation, Genre and World Era

## Product decision

**Replace the old 16,384-person *default* regional census.** It represented
a simplified abstract population in a bounded demonstration world—not
16,384 fully interactive agents, sprites, or an appropriate density for an
ordinary game. The existing old save files remain readable with their old
regional records intact, but **new games use much smaller budgets**.

The new implementation in
`skeleton/game/generation/original_world_npc_platform_profiles.py`
uses four independent axes:

1. The **exact supported console/PC/homebrew target** (41 registered options),
   each explicitly mapped to one conservative hardware tier.
2. The **PC generation and equipment capability** (nine categories from
   early 8-bit home computers through contemporary integrated, mainstream
   and high-end systems). The game never assumes a modern CPU simply because
   the target label says Windows, macOS or Linux.
3. The **actual gameplay genre** (ten independently authored play forms),
   including platform, puzzle, tactics, survival, colony, racing, stealth,
   commerce, exploration and rhythm. Genres alter NPC *requirements*, not
   cosmetic appearances.
4. The **world-history/technology era** (all 40 authored world-era policies),
   affecting how many settlements and professions make sense within the
   game. A modern console running a Stone Age adventure is still a Stone
   Age game; a futuristic story does not grant 8-bit hardware unlimited CPU.

The resulting counts are conservative **engineering design caps**, not a
statistically measured mean of comparable commercial games. They aim to
deliver a slightly more socially detailed reference environment than a
minimal genre prototype, while reserving CPU time for gameplay, graphics,
world simulation, audio and input. Calibrating exact performance requires
repeatable profiling on target hardware.

### Representative high-ceiling configurations

| Game target / genre / era | Full persistent local NPC slots | Starting local NPC bodies | Resource-accounted regional census cap | Active full planners per turn |
|---|---:|---:|---:|---:|
| NES / colony / futuristic | 3 | 2 | 2 | 2 |
| PlayStation 2 / colony / futuristic | 10 | 8 | 24 | 5 |
| PlayStation 5 / colony / futuristic | 24 | 22 | 120 | 12 |
| Integrated modern PC / colony / futuristic | 15 | 13 | 54 | 7 |
| High-end modern PC / colony / futuristic | 24 | 22 | 144 | 14 |
| Integrated modern PC / exploration / futuristic | 13 | 11 | 35 | 7 |
| Integrated modern PC / puzzle / futuristic | 8 | 6 | 10 | 7 |
| 8-bit console / platform game / futuristic | 2 | 1 | 0 | 2 max; 1 initially |

These are **different counts**. There is no legitimate shortcut from
"up to 144 people regionally tracked" to "144 individual autonomous
AI characters moving in the game viewport." For compact rhythm,
racing, and puzzle levels the world may need no regional census at all.
For survival, commerce or colony games, remote stores and social logistics
become more important than crowded screenshots.

Across **all newly generated supported configurations**:

- **1–24 individually identifiable, physically embodied NPC slots**, with
  up to two reserved for later births or actual immigration.
- **0–144 remote cohort residents** tracked through a handful of real
  finite-stock regional ledgers, never individual neural minds.
- **Up to 14 actually planning local minds per world turn**, dependent on
  hardware and the selected economy/balanced/vivid/unrestricted preset.
- **Up to 10 inexpensive visual-only crowd impressions**, often zero.
- **At most eight anchored abstract regions**, often one to four, with at
  most three budgeted region ledger updates per turn.
- **Zero human population assigned to primordial-earth or early-life
  regions**. The one local reference-game observer on those eras is
  only a compatibility interface, not an invented prehistoric human.

A game may render fewer sprites than its local NPC count based on
viewport and location, and a particular situation may have no reason
to spawn additional inhabitants. The engine's world/console profile
never obligates it to fill all its capacity.

### Quality, not inflated social density

Full NPCs retain the same physical-world systems already implemented:
named identity, finite health/hunger/inventory, autonomous priorities,
individual observation and memory, social bonds, jobs, medical care,
actual resource-based construction, in-person government participation,
earned apprenticeships, and persistent intergenerational family
relationships. Lower hardware targets constrain quantity first;
they do not make the resident's inventory imaginary or waive
causal validation.

Only eligible nearby, endangered, contracted or family-dependent citizens
receive one of the limited expensive cognitive action slots on each day,
with rotating fairness across otherwise idle locals. Passive citizens
remain actual persistent people with survival needs and can become
fully active on another turn.

Regional residents have resource-and-population ledgers but **not**
independently instantiated biographies, NPC cognition, personal votes
or interactions until an actual player-authorized migration makes one
a full named resident and deducts one from the regional count.

The low-detail crowd/proxy visual layer is never part of the denominator
of actually simulated identities. It cannot spend resources, vote, give
interviews or complete worker tasks.

### Runnable examples

```bash
# Restrained original-game colony on Nintendo Entertainment System class.
python -m skeleton.game.generation.original_world_product_cli \
  --base 0 --form colony --architecture lattice \
  --system trophic --arc sandbox \
  --era bronze-age --hardware-target nes \
  --npc-fidelity economy --population-report

# Modern PC: independently choose device generation and genre.
python -m skeleton.game.generation.original_world_product_cli \
  --base 0 --form stealth --architecture labyrinth \
  --system trophic --arc endless \
  --era early-ai --hardware-target pc-windows \
  --pc-generation 2020s-integrated \
  --npc-fidelity balanced --population-report

# More CPU available, but still bounded by platform, gameplay and reality.
python -m skeleton.game.generation.original_world_product_cli \
  --base 0 --form colony --architecture lattice \
  --system trophic --arc dynasty \
  --era interstellar --hardware-target pc-windows \
  --pc-generation 2020s-highend \
  --npc-fidelity vivid --population-report

# List every registered platform and all canonical era policies.
python -m skeleton.game.generation.original_world_product_cli --inventory
```

The **target profile is a design/port constraint**, *not* proof that a
Sony/Nintendo/Microsoft console homebrew binary or licensed SDK package
has actually been produced. The working reference implementation is
Python-based and separately smoke-tested on supported Windows/Linux
packaging paths.

### Past archives and reversible user controls

Legacy `original-world-era-population.v1` saves without the newer
`profile` field continue to decode against the older regional
census law; their people and stocks are not quietly overwritten
during load. Newly generated worlds record the complete canonical
`PopulationProfile` in their checksummed save.

The `population set_detail economy|balanced|vivid|unrestricted`
control changes scheduling work, not the persistent census, actual
available professions, histories, or source world. An attempt to
reload a world while simultaneously overriding its established
hardware, PC generation, era or NPC configuration is rejected instead
of covertly mutating a running playthrough.

### Reference games and numerical honesty

Games can display impressive crowds. For example, Game Informer
reported a 12,000-character *Assassin's Creed Unity* developer demo,
and contemporary coverage of *Hitman* distinguishes simplified
crowds from full-behavior targetable NPCs. A screen full of figures
should not be equated with thousands of full cognitive agents.

- https://www.gameinformer.com/b/features/archive/2014/08/25/watch-the-largest-crowd-assembled-in-assassins-creed-unity.aspx
- https://gamesbeat.com/square-enix-reveals-marrakesh-as-latest-episode-for-hitmans-assassination-tourism/

No industry-wide per-platform/genre NPC average has been empirically
calculated or published by this game engine. All reference caps are
reviewable conservative design settings. They must be validated against
real target-device frame times, memory and gameplay usefulness
before they can be marketed as objectively "above average."
