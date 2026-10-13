# Original-world NPC density across forty eras — consumer-grade LOD

**Implemented game milestone.** Era-aware population is attached to the same
original-world `ProductSession` as the physical terrain, independent NPC
minds, social relationships, civic votes, schools, family generations and
material economy. It does not fabricate millions of complete NPC minds from
an aggregate population figure.

## The three actual runtime fidelity layers

| Layer | State stored | Per-turn work | Agency and causality |
| --- | --- | --- | --- |
| Active fully embodied residents | Individual body, position, finite goods, health, learned cognitive policy, own memories, relationships, identity and contracts | Bounded expensive goal selection, perception, physical pathfinding, labor, patient care | Real NPC actions; pays and moves actual resources |
| Passive fully embodied residents | **Same real body and identity**, without running expensive goal/route planning on this particular turn | Constant-time hunger, aging, illness progression and energy recovery | Cannot teleport, gather, fabricate stock, create friendships, or claim learned actions when inactive |
| Regional background cohorts | One compact district record per remote settlement, stored pantry, census, hardship, morale and material shipments | Only the selected district subset is updated each turn; elapsed needs settled arithmetically | Conserved district food, travel-time-backed caravans and actual resident migration to a free full-mind slot; not one mind per census member |

Era-defined budgets are fictional authored-game presets rather than historical
population estimates. Their purpose is to increase believable settlement
density as gameplay technology, society and hardware scope advance.

`ERA_LEVELS` contains forty precisely identified original eras, from
`primordial-earth` and `paleolithic`, through antique, medieval, steam,
electrical and early digital periods to `near-future`,
`interstellar` and `cosmic-epoch`. The earliest two eras expose a
minimal one-entity simulation rather than falsely depicting modern humans
as inhabitants of primordial Earth.

Full high-fidelity local NPC capacity is capped at **32 named physical
residents** and reserves a small number of slots for independent later
generations. Higher-level eras add populated regional districts (up to
16,384 aggregated background inhabitants in the current runtime), not
16,384 full-memory agents. The current runtime does not support unlimited
worldwide NPC minds or independently simulated 16,384-person relationships.

## Device-oriented cognitive budgets

All expensive *local* NPC decisions obey a player-selected preset.
The actual number run may be below the ceiling when an era has fewer
residents.

| Preset | Maximum local individual brains advancing per world turn | Other fidelity work |
| --- | ---: | --- |
| Economy (`economy`, legacy `eco`) | 3 | At most one regional district catch-up update; at most four regional visual markers |
| Balanced | 7 | Era-authored bounded regional updates and visual budget |
| Vivid (`vivid`, legacy `rich`) | 16 | Up to eight regional updates; bounded larger graphical crowd |
| Unrestricted | 32 | Full local brains up to physical roster size; regional update and display remain finite |

The scheduler respects life-threatening hunger and injury first, followed by
active personal commitments such as real resource orders, funded construction,
mentorship and dependent-care obligations. It then prioritizes player-near
residents and reserves a rotating fair-share slot for an otherwise perpetually
backgrounded healthy resident where no urgent protected duty would be displaced.
An inactive person does not gain skill, memories of events they did not see, or
physical material rewards. Their needs continue to progress.

This is **deterministic time-slicing**, not an automatic hardware benchmark
or proven real-time multithreading. The source world, player turns and
persistent receipts are unchanged by wall-clock machine timing. The preset
is stored in the save file, allowing exact replay of the chosen fidelity
policy. It can also be changed explicitly in game without rewriting past
actions or inventing a prior simulation history.

## World vibrancy without heavyweight false agents

Districts have genuine passable map locations and compact demographic and
food state. Vector/raster/ASCII exports and the native Tk desktop draw
bounded additional crowd *impressions* near district locations, separately
from individually instantiated NPCs. An ambient marker is labelled
`render-only`, has no personal agency or inventory, cannot vote or trade,
and cannot be clicked as an actual persistent citizen.

The number of those proxies is capped by the selected regional rendering
budget and viewport radius. Creating 16,384 background residents therefore
does **not** allocate 16,384 physics bodies, cognition plans or sprites.
SVG, PPM and the ASCII view preserve distinctive local citizen symbols;
the user sees nearby people, district locations, and ambient street activity.

Unlike purely decorative crowd counters, the underlying *districts* have
finite food. Scheduled districts settle accumulated consumption with a
fractional 1/16-ration carry to prevent rounding away a daily requirement.
A shortage lowers morale and can reduce real aggregate census, with the
mortality evidence recorded in the save. No local supply is secretly minted
to maintain a visual crowd.

Players can dispatch small caravans between the local depot and a selected
district. Dispatch debits the real sending warehouse, arrival requires
elapsed distance-dependent world time, and a full destination leaves cargo
in transit instead of silently discarding it or double-crediting it.
When a player reaches an anchored district, a regional member may be
promoted into a real body only if a physical NPC slot is available; the
regional census is debited and the new person's identity and original-world
memory are stored.

## Player commands

```bash
# Early-era smaller town with the smallest cognition workload.
python -m skeleton.game.generation.original_world_product_cli \
  --base 0 --form puzzle --architecture lattice --system trophic \
  --arc sandbox --era iron-age --npc-fidelity economy \
  --population-report --show-map

# Later-era settlement with active people and compact remote census.
python -m skeleton.game.generation.original_world_product_cli \
  --base 0 --form puzzle --architecture lattice --system trophic \
  --arc sandbox --era digital-network --npc-fidelity vivid \
  --actions-json '[{"layer":"causal","verb":"end_turn"}]' \
  --npc-report --population-report

# Turn a real regional resident into a fully embodied local citizen
# only after traveling to a district and making a lawful in-game action.
# population recruit DISTRICT_ID

# Require finite caravan stock and world-time travel.
# population dispatch_food DISTRICT_ID to-region 2
# population dispatch_food DISTRICT_ID to-player 2

# Reconfigure consumer-resource usage without a fictitious past replay.
# population set_detail economy

# Measure, don't speculate about device performance.
python -m skeleton.game.generation.original_world_npc_cost_lab \
  --era digital-network --preset economy --turns 3 --trace-memory

# Compare to high-fidelity mode on the same available hardware.
python -m skeleton.game.generation.original_world_npc_cost_lab \
  --era digital-network --preset unrestricted --turns 3 --trace-memory
```

The benchmark records **actual local host wall-clock nanoseconds**, optional
traced Python heap high-water mark, exact game-save checksum, real physical
NPC count, number of decisions made and avoided, region census, district
updates and final event receipts. Wall-clock costs are noisy and depend on
machine, load and operating system; the engine does not claim an unmeasured
universal 10× or 100× speedup. Structural cognitive work reduction is
independently measurable even if a particularly small test has timer noise.

## Completed and outstanding engineering

This milestone has real four-tier CPU budget controls, era-scaled local and
remote populations, role availability, region logistics, physical migration,
resource-conserving regional survival, bounded crowd visualization, session
saves, a deterministic cognition scheduler, fairness and survival priorities,
headless CLI, native renderer integration and a host-measured profiling lab.

**Next difficult engineering beyond this specific milestone:** streaming
multiple separately authored live settlements into the same 3D scene;
real offscreen individual biographies and interpersonal events; robust
100,000-entity networking and spatial partitioning; more complex local
economics and labor markets; deep character animation, audio, facial
expressions, conversations and path-planned traffic; independently simulated
societies without homogeneous proxy populations; legal console-specific
builds and platform release certification.

The implementation must not be presented as a finished commercial
population simulator or proof that the enormous game-configuration address
space contains separately authored and playtested games.
