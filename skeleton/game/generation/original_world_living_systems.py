"""Ten original, stateful living-system laws for the next 10x world layer.

These are authored system rules, not cosmetic labels. Every mode has three
different consequential player commands, an autonomous world-turn process,
material/energy budgets, and persistent consequences. Abstract simulation only.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class LivingSystemLaw:
    system_id: str
    title: str
    world_premise: str
    actor_model: str
    autonomous_process: str
    scarce_resource: str
    critical_failure: str
    intervention_contract: str
    commands: tuple[str, str, str]


SYSTEMS = (
    LivingSystemLaw(
        "trophic", "The Hungry Web",
        "Predators and grazers transform living habitat rather than spawning from nothing",
        "Grazers forage vegetation; predators require prey; seed stores regrow on a clock",
        "Vegetation regenerates slowly, herbivores graze, then predators hunt",
        "vegetation and tracked animal births",
        "Starvation or predation breaks the trophic chain",
        "Protect habitat, guide grazing, or cull prey with measurable ecological costs",
        ("reseed", "graze", "protect"),
    ),
    LivingSystemLaw(
        "settlement", "The Settlement That Remembers",
        "Households migrate, consume food, form trust and retain civic obligations",
        "Families occupy shelter; arrivals cannot exceed population support",
        "Citizens consume stores, stability draws newcomers, shortage drives departures",
        "housing, meals, civic supplies",
        "An overcrowded town falls into hunger, abandonment and social distrust",
        "Construct housing, admit refugees or allocate finite rations",
        ("house", "welcome", "ration"),
    ),
    LivingSystemLaw(
        "caravans", "The Clock of Traveling Markets",
        "Merchant caravans physically carry stocks along limited logistical routes",
        "Convoys move cargo between a source warehouse and a distant port",
        "Outbound consignments settle after real world-turn travel intervals",
        "cargo, trade credit, escorts",
        "Unescorted shipments can be lost while public demand remains unmet",
        "Load a shipment, escort its travel or sell delivered stock",
        ("dispatch", "escort", "unload"),
    ),
    LivingSystemLaw(
        "watershed", "The Borrowed River",
        "Reservoir gates govern water shared by farmers and floodplain communities",
        "Dams store rainfall, fields draw irrigation and flood danger persists",
        "Rainfall fills reservoirs; evaporation and overflow compete with irrigation",
        "rainwater, field fertility, flood tolerance",
        "Drought kills harvests while uncontrolled overflow destroys downstream trust",
        "Allocate water to fields, raise a dam or release a dangerous surplus",
        ("irrigate", "dam", "release"),
    ),
    LivingSystemLaw(
        "power", "The Night Grid",
        "Generators, local battery storage and the public grid have limited throughput",
        "Generators supply electricity; battery buffers demand spikes",
        "Demand consumes generation and charged reserves each turn",
        "fuel, charge, grid integrity",
        "Blackouts grow persistent infrastructure wear and social discontent",
        "Generate power, charge finite batteries or prioritize civic load",
        ("generate", "charge", "route"),
    ),
    LivingSystemLaw(
        "spores", "The Fictional Spore Accord",
        "Invented spores circulate in a finite fantasy biome with reversible treatment",
        "Susceptible, affected and recovered fictional organisms form tracked cohorts",
        "Contact spreads spores unless isolation or recovery interrupts transmission",
        "medicine, isolation capacity, unaffected organisms",
        "Untreated spores reduce productive participation in the world",
        "Isolate a cohort, deliver finite remedies, or study immunity",
        ("isolate", "remedy", "study"),
    ),
    LivingSystemLaw(
        "fabrication", "The Patient Machines",
        "Limited autonomous builders turn recovered material into structures",
        "Robots require parts, durable designs and repair; they cannot mint resources",
        "Builders work each turn and suffer wear; unfinished orders persist",
        "robot parts, blueprints, upkeep",
        "Neglect stops production and makes unfinished builds a real liability",
        "Design structures, commission builders or repair fatigued machines",
        ("design", "assemble", "service"),
    ),
    LivingSystemLaw(
        "knowledge", "The Evidence Commons",
        "Research cannot be promoted into public knowledge without corroboration",
        "Independent observers test claims, teach supported findings and pay for review",
        "Open questions accumulate; validated discoveries slowly diffuse to residents",
        "evidence tokens, peer review, public trust",
        "Unchecked claims increase skepticism and waste scarce research",
        "Investigate observations, verify through independent cost, or teach findings",
        ("observe", "verify", "teach"),
    ),
    LivingSystemLaw(
        "diplomacy", "The Treaty of Three Valleys",
        "Three factions negotiate incompatible yet nonzero-sum resource claims",
        "Factions have separate influence; negotiated pledges carry real obligations",
        "Unreconciled grievances compound unless aid and valid treaties succeed",
        "legitimacy, real offerings, outstanding promises",
        "Rising tension forces trust loss and inter-faction disruption",
        "Petition, make a cost-backed pledge or mediate competing interests",
        ("petition", "pledge", "mediate"),
    ),
    LivingSystemLaw(
        "echoes", "The Debt of Repeated Mornings",
        "Events leave causal echoes that cannot erase already verified event history",
        "Actions create delayed gains and future debts without rewriting old receipts",
        "Pending echoes mature, while unresolved temporal debts build instability",
        "chronal energy, deferred obligations, immutable causality",
        "Debt beyond equilibrium triggers a paradox hazard",
        "Record an echo, accelerate maturation or reconcile outstanding obligations",
        ("record", "hasten", "reconcile"),
    ),
)
SYSTEM_BY_ID = {law.system_id: law for law in SYSTEMS}
if len(SYSTEMS) != 10 or len(SYSTEM_BY_ID) != 10:
    raise RuntimeError("ten distinct living laws required")
if len({c for s in SYSTEMS for c in s.commands}) != 30:
    raise RuntimeError("living-world interventions must be distinct action verbs")
if any(not all((s.world_premise, s.actor_model, s.autonomous_process,
                s.critical_failure, s.intervention_contract))
       for s in SYSTEMS):
    raise RuntimeError("incomplete authored living-system foundations")
