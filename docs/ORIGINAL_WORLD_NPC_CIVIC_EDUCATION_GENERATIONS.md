# Original-World NPCs: Resident Government, Education, and Generational Play

## Status and truth of the deliverable

This is executable offline NPC gameplay integrated into `original_world_product_session.py`, not an additional game-count multiplier, an external pretrained LLM, or human cognitive equivalence. The three engines below extend the individually embodied, finite-world, persistent-memory NPC v2 system; all changes are replayable and included in native Windows/Linux source bundles.

### Public institutions — votes that genuinely change gameplay

`original_world_npc_civics.py` implements resident proposals, one-vote-per-citizen named ballots, eligibility from actual physical attendance, a quorum, majority approval, historically recorded meeting time, an expiring active mandate, and material-backed policy interventions.

A player must be at the common depot, spend one actual warehouse provision and one civic-trust unit, and sponsor an existing conscious resident. Each physically present citizen votes independently based on current health, hunger and persistent personality traits. They can reject a policy; absence, incapacity, a tie, or insufficient quorum cannot be faked into approval.

| Proposed law | Actual execution |
| --- | --- |
| `food-aid` | Feed at most one physically present hungry resident a day, debiting one actual food unit |
| `medical-aid` | Restore a specific reachable patient's health, debiting real clean water |
| `conservation` | Suppress unaffordable spontaneous construction and preserve scarce civic resources |
| `expedition` | Change NPC goal utility toward actual local surveying rather than minting discoveries |

Each approved policy lasts twelve game-world turns unless replaced, then expires without pretend reauthorization. Public assistance records exact resident, day, material debit and actual need before and after intervention. The settlement has a bounded historic ballot archive and no invisible voting population.

### Apprenticeships — real earned and transferable professional competency

`original_world_npc_apprenticeships.py` establishes a professional mentorship between two identifiable residents. A teacher must have earned at least three real work-experience units in one supported profession, while a learner must have a different profession. Both must meet physically.

The learning contract persists across turns and requires **three distinct dated lessons**, with both people present near the common depot, healthy enough, able to spare stamina, and one unit of actually stocked food per lesson. A single day cannot count twice. The learner gains actual experience only after a funded meeting and changes profession only after all three lessons are complete.

Supported professions include forager, forester, mason, healer, engineer and scout. Interrupted lessons remain pending. Cancelling a noncompleted mentorship preserves the real paid historical lessons but prevents any future credential. Mentoring does not count as proof of deep language-model learning, school curricula, higher education or professional accreditation.

### Households — intergenerational world play

`original_world_npc_households.py` adds a bounded, voluntary generational-household simulation with stable caregiver identities, ages, historical sponsorship, finite shelter and food/water escrow, three elapsed world turns, delayed arrival, and independent new NPC minds and bodies.

Two healthy adult caregivers need a mutually demonstrated, positive relationship (at least two earned trust and affinity units), to be physically present at a *built* hearth, have sufficient warehouse provisions, clean water, and room for a new resident. Sponsoring a household consumes three food and two water units, reserves a shelter and receives no instant extra worker. After three physically simulated days, a new dependent is added with an original deterministic personality derived from the parent traits and world seed. Parental and child identities are immutable; old residents and historical records remain present.

Young dependents cannot harvest, build, or perform the duties of an adult worker during the first four personal world turns. They grow older one actual turn at a time. Dependent welfare costs real food; caregivers can feed physically present hungry children from their own carried stock or available public stores, and one child cannot receive multiple credited parent meals on the same turn. After sufficient growth, an inhabitant can transition into regular role-specific work.

Household cancellation prior to arrival refunds exactly the food and water escrow and never inserts a phantom resident. This is an abstract fictional-game family simulation, not biologically accurate reproduction, clinical childcare advice or a human family model.

## Commands that actually run

```bash
# Run a genuine bounded society with inspectable minds and material ledgers.
python -m skeleton.game.generation.original_world_product_cli \
  --base 0 --form puzzle --architecture lattice \
  --system trophic --arc sandbox --npc-report

# Interactive original-world session (all actions spend actual game AP).
python -m skeleton.game.generation.original_world_product_cli \
  --base 0 --form puzzle --architecture lattice \
  --system trophic --arc sandbox --interactive

# Available once preconditions and public costs are met:
# npc propose 0 food-aid
# npc propose 1 medical-aid
# npc propose 0 conservation
# npc propose 1 expedition
# npc mentor 0 1
# npc cancel_mentorship 0
# npc household 0 1
# npc cancel_household 0

# Replayable physical stress tests including actual votes and new dependents.
python -m skeleton.game.generation.original_world_npc_laboratory \
  --scenario civic-food-aid --turns 8 --population 12
python -m skeleton.game.generation.original_world_npc_laboratory \
  --scenario family-expansion --turns 8 --population 12
```

Other scenarios cover real food shortages, injury, social isolation, cooperative buildings and the baseline persistent society. The laboratory reports actual civic voters, public aid, resources, completed lessons, earned professions, new physical residents, direct memories, morale, health, hunger, policy adjustments, event receipts and the final state SHA-256.

## Validation and product maturity

Each new action is a durable game transaction, with historical validation of voter identity, depleted stocks, physical reachability, citizen education credentials, preserved witnesses, generational ages, and duplicate-free participant IDs. Old saves without the added optional cognition ledgers use version-aware migration that introduces no invented historical civic votes, apprenticeships or dependents. A checksummed save prevents accidental alteration, **not malicious tampering by a client who can recompute SHA-256**.

This implementation handles local populations of at most 32 actual embodied inhabitants and bounded histories. It does **not** yet supply real-time 3D skeletal animation, fluent unrestricted dialogue, individually trained transformer minds, deep psychometric personality research, thousands of independent offscreen entities, economics across multiple towns, adaptive global politics, legal status, signed anti-cheat accounts, realistic multi-century genealogy, or a commercially polished life simulator. Those remain explicitly unfinished major engineering work.

The existing massive original-game indexes are not counted as individual playable authored worlds, and NPC trait combinations are **not** counted as completed independent AI characters. Completion claims should be tied to exact-head tests and real executable scenario and native binary evidence.
