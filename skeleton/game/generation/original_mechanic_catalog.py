"""Authored game-mechanic design registry with explicit action, effect, and cost.

These are *specifications*, not claims that every action is implemented in
each console/game runtime. The compiler chooses compatible mechanisms;
platform adapters must implement/validate the corresponding behavior.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class OriginalMechanic:
    mechanic_id: str
    title: str
    domain: str
    trigger: str
    state_change: str
    drawback: str


_MECHANIC_ROWS = {
    "time": [
        "Future Collateral|When borrowing an extra action|Transfer that action from a future turn|Future turn loses an available action",
        "Retroactive Witness|When observing a prior event|Add a witness to its historical record|All dependent testimonies are reopened",
        "Season Splice|When crossing a seasonal boundary|Join two distant seasons at one location|Other regions inherit the displaced weather",
        "Deferred Injury|When receiving harm|Schedule damage into a later encounter|Future injury becomes harder to prevent",
        "Age Exchange|When touching a willing subject|Transfer biological age between participants|Shared age ledger must balance",
        "Deadline Gardening|When planting a task|Grow rewards only at an agreed deadline|Early collection destroys the crop",
        "Chronal Mortgage|When erecting a lasting structure|Pay construction time from future maintenance|Maintenance debt compounds",
        "Probability Fossil|When recording a possible outcome|Freeze the outcome into a collectible artifact|Other possible outcomes become rarer",
        "Turnback River|When following a reverse-flowing route|Rewind location without rewinding inventory|Temporal inventory conflicts accumulate",
        "Forgotten Tomorrow|When canceling a planned event|Turn the abandoned future into an explorable echo|Echo contains unresolved obligations",
        "Clock Concordat|When multiple clocks conflict|Negotiate a shared tick rate for a district|Neighboring districts drift further apart",
        "Aftermath Crafting|When examining a consequence|Craft plausible causes that must pass consistency checks|Invalid causes consume scarce evidence"
    ],
    "topology": [
        "Fear Doors|When a traveler names a fear|Reconnect a nearby doorway to its feared location|The destination learns the traveler identity",
        "Occlusion Drift|When a sector becomes unobserved|Permute its graph edges deterministically|Old route knowledge expires",
        "Room Folding|When two rooms share a boundary|Fold their interiors into one larger room|External exits may become unreachable",
        "Route Tax|When shortening a path|Lengthen a distinct connected path|Travel savings require a public tradeoff",
        "Live Cartography|When publishing a map|Commit its marked routes as physical corridors|Incorrect markings become hazards",
        "Threshold Vote|When entering a civic building|Let resident votes choose the exit graph|Minority exits require negotiation",
        "Stair Inversion|When a stair is descended twice|Swap up and down for that stair|Altitudes of neighboring rooms diverge",
        "Mirror Corridor|When reflecting a passage|Generate a parallel route with reversed entrances|Reflection duplicates pursuing threats",
        "Knotted Shortcut|When tying two path ends|Create a wormhole between distant tiles|Movement through it adds entanglement",
        "Selective Walls|When declaring a traversal intent|Walls become passable only for compatible intentions|Declared intent is auditable",
        "Breadcrumb Anchor|When leaving a limited anchor|Freeze one graph connection across future shifts|Anchors occupy finite inventory",
        "Moving Goalpost|When a destination is discovered|Relocate it to an unseen reachable sector|World may remain deliberately unfinishable"
    ],
    "ecology": [
        "Trophic Bargain|When introducing a species|Reroute one predator-prey dependency|An existing niche becomes unstable",
        "Rain Herding|When steering cloud-bearing animals|Redirect precipitation corridors|Downwind farms lose rainfall",
        "Pollinator Treaty|When planting a rival crop|Negotiate shared pollination schedules|Late bloomers may be excluded",
        "Symbiotic Lending|When two organisms connect|Temporarily exchange functional senses|Both become fragile on separation",
        "Seed Memory|When a plant survives a hazard|Inherit resistance in local seed cohorts|Adaptation consumes growth budget",
        "Decomposer Commons|When collecting biological waste|Allocate nutrient recovery to habitats|Short-term energy gain can strip soil",
        "Migration Shadow|When moving a keystone herd|Displace predator and seed dispersal routes|Unexpected ecological cascades",
        "Disease Buffer|When eradicating a parasite|Compute lost cross-immunity|Later infections may accelerate",
        "Biome Jury|When changing a habitat rule|Collect votes weighted by ecological dependence|High-dependence minority may block changes",
        "Succession Clock|When removing an old forest stage|Advance succession to a new biome|Young species lose shelter",
        "Fungus Relay|When an underground mycelium is linked|Carry signals across disconnected settlements|Information transfer consumes nutrients",
        "Nest Architecture|When inhabitants construct homes|Turn nesting behavior into terrain features|Homes compete with animal movement"
    ],
    "civilization": [
        "Promise Foundations|When two strangers make a verifiable oath|Unlock a communal building slot|Breaking the oath degrades the structure",
        "Visitor Referendum|When travelers arrive in a district|Add temporary outsider voting power|Residents cannot fully control the vote",
        "Profession Ghosts|When a trade becomes obsolete|Retain its expertise as an autonomous guild|Guild demands relevance and funding",
        "Nomadic Charter|When population crosses a legal threshold|Shift the nation's territory toward its census|Displaced residents dispute sovereignty",
        "Civic Sleep|When a settlement sleeps deeply|Move administrative authority there|Sleep deprivation becomes political risk",
        "Festival Opposition|When rivals honor each other's win|Convert conflict into public trust|Cheap staged celebrations produce little trust",
        "Border Citizenship|When a border landmark moves|Change the border according to the landmark's agency|Territorial stability depends on individuals",
        "Name Succession|When a name is transferred|Pass specific civic rights with it|Previous holders lose named privileges",
        "Mutual Aid Ledger|When a disaster is declared|Redistribute emergency labor commitments|Overcommitted regions demand reciprocity",
        "Reputation Quorum|When a collective decision occurs|Require independent trust paths before enactment|Insular cliques cannot self-certify",
        "Public Memory Vote|When archival evidence conflicts|Vote which records become official without deleting others|Official narrative loses certainty",
        "Dissent Nursery|When a minority proposal is rejected|Fund a sandbox district to evaluate it|Experiments consume shared resources"
    ],
    "identity": [
        "Split Persona|When entering a parallel body|Partition memory and agency into separate selves|Reunification requires reconciling divergent actions",
        "Reflected Veto|When crossing a mirror boundary|Give reflection authority to reject one proposed action|Reflections pursue independent priorities",
        "Ancestor Adoption|When consenting to a lineage|Inherit its skills and unfinished obligations|Inherited debts cannot be selectively ignored",
        "Voluntary Amnesia|When sealing a memory|Gain relief from its burden|Related abilities become inaccessible",
        "Public Mask|When assuming a social role|Gain that role's permissions and expectations|Role liabilities remain attached",
        "Identity Auction|When two identities are exchanged|Swap reputation rather than physical inventory|Relationships may reject the substitution",
        "Dream Council|When multiple players sleep|Merge agency into one negotiated dream avatar|Conflicting commands slow the avatar",
        "Emotional Cultivation|When tending a cultivated temperament|Change decisions available in future dialogue|Extreme moods reduce flexibility",
        "Testimony Collapse|When a witness learns a protected fact|Invalidate one dependent evidentiary path|Knowledge can obstruct justice",
        "Shared Name|When adopting another person's abandoned name|Inherit partial community recognition|Individual achievements blur",
        "Self Audit|When a past self disputes a choice|Open a revision hearing between versions|Revisions propagate to commitments",
        "Social Gravity|When entering a group with distinct norms|Shift mobility and interaction permissions|Assimilation can erode individual options"
    ],
    "economy": [
        "Mass Credit|When purchasing an object's mass|Transfer weight from the regional reserve|Interest is paid in physical load",
        "Food Futures|When holding currency through a maturation date|Turn value into food rather than cash|Spoilage penalizes hoarding",
        "Dawn Auction|When towns bid for sunlight|Allocate the sunrise to winning regions|Losers endure extended darkness",
        "Trust Extraction|When exploiting social influence|Convert accumulated trust into immediate resources|Relationships regenerate trust slowly",
        "Secret Barter|When transferring an object|Demand an associated disclosed secret|Confidentiality is irreversibly reduced",
        "Retro Insurance|When a future risk is predicted|Pay compensation before the disaster|Beneficiary inherits mitigation obligation",
        "Scarcity Lease|When renting a resource constraint|Create artificial scarcity for a chosen market|Market distortions spread to substitutes",
        "Labor Wind|When workers withhold unpaid labor|Change prevailing trade-wind direction|Shipping congestion raises prices",
        "Cooperative Debt|When a group funds a project|Split risk by actual participation|Free riders erode project stability",
        "Inverse Tax|When accumulating unused supplies|Increase storage charges while lowering trade taxes|Long-term reserves become expensive",
        "Price Memory|When a market sees repeated bids|Attach remembered unfairness to future prices|Price corrections lag behind reality",
        "Bankruptcy Rebirth|When an institution collapses|Reallocate its charter to affected communities|New owners inherit essential duties"
    ],
    "physics": [
        "Spoken Gravity|When claims are spoken in an area|Rotate gravity toward the dominant declared vector|Competing voices cause turbulence",
        "Shadow Momentum|When light changes direction|Accelerate attached shadows rather than objects|Shadow collisions can cause secondary harm",
        "Pigment Pressure|When an object is painted|Redirect contact forces along pigment gradients|Paint erodes under repeated stress",
        "Heat Sailing|When thermal gradients form|Move craft along heat-flow vectors|Movement redistributes local heat",
        "Horizon Spring|When approaching a viewing boundary|Store momentum for later release|Stored impulse destabilizes nearby structures",
        "Expected Ignition|When a trusted observer predicts fire|Enable combustion in the observed cell|Contradictory expectations extinguish it",
        "Density Chorus|When sound harmonics converge|Change temporary material density|Silence ends the effect",
        "Directional Entropy|When sorting matter within a zone|Push disorder to connected zones|Local order increases regional instability",
        "Friction Melody|When tuned audio reaches a surface|Set that surface's friction coefficient|Tuning consumes finite performance time",
        "Buoyancy Bargain|When lifting a submerged object|Borrow buoyancy from adjacent objects|Other loads may sink",
        "Angle Harvest|When two surfaces align|Collect angular momentum as an energy resource|Surfaces are left rotationally constrained",
        "Elastic Distance|When traversing a shortened route|Increase another route's effective length|Navigation changes require conservation checks"
    ],
    "machines": [
        "Machine Lineage|When producing a device from an ancestor|Mutate one permitted component behavior|Poor variants still consume materials",
        "Component Referendum|When replacing a part|Require agreement among dependent modules|Maintenance becomes a negotiation process",
        "Absent Gear|When leaving a designed slot empty|Grant a new capability through negative-space resonance|Filling the slot disables the capability",
        "Climate Cartridge|When inserting a biome cartridge|Exchange the climate of two bounded areas|Affected ecosystems require acclimation",
        "Blueprint Selection|When rival plans are compared|Breed a new design from verified useful subgraphs|Structural novelty may reduce reliability",
        "Foundry Courtship|When factories exchange resources|Create a new specialized factory child|Both parents lose capacity temporarily",
        "Purpose Obfuscation|When a device's use remains uncertain|Amplify its experimental output|Explaining the purpose collapses output",
        "Mechanical Consensus|When several machines share a load|Elect a control algorithm from their local proposals|Consensus delay can stall urgent repairs",
        "Repair Ritual|When service is performed in the correct order|Recover function without replacing parts|Incorrect sequence creates wear",
        "Mechanical Fossil|When excavating a dormant device|Recover ancestral parameters and operating habits|Ancient assumptions may be unsafe",
        "Mesh Resonance|When circuits synchronize|Transmit mechanical force between remote nodes|Resonance can amplify faults",
        "Tool Refusal|When a tool detects misuse relative to its charter|Veto that action and propose a safe alternative|Amending charter requires oversight"
    ],
    "law": [
        "Landscape Standing|When development harms a natural feature|Grant that feature legal standing and a remedy claim|Construction faces due process",
        "Seasonal Statute|When a season changes|Expire a subset of laws and activate successor rules|Legal predictability decreases",
        "Appeal Rewrite|When a verdict is successfully appealed|Correct causal evidence within a bounded event|Other witnesses need reconciliation",
        "Jurisdiction Shift|When entering a threshold|Transfer legal authority based on adjacency|Permits may lapse across a single door",
        "Future Victim Jury|When ruling on a hazardous action|Sample potential affected futures as jurors|Probabilistic parties may disagree",
        "Silent Contract|When parties stop stating an agreement verbatim|Keep a pact enforceable through actions|Public explanation can dissolve pact",
        "Causal Exile|When a citizen elects voluntary disappearance|Remove their influence from a bounded chain|Beneficial effects vanish alongside harms",
        "Object Constitution|When using a chartered object|Check whether its declared rights allow the action|Amendment requires legitimate process",
        "Precedent Seed|When resolving a dispute|Generate future default rulings for similar cases|Bad precedent propagates",
        "Legal Fork|When courts disagree across branches|Allow parallel legal outcomes until reconciliation|Travel across branches carries liabilities",
        "Amnesty Ledger|When forgiving an offense|Retain nonpunitive evidence and restitution obligations|Forgiveness does not repair material harm",
        "Consent Horizon|When a policy affects future populations|Reserve deliberative weight for unborn stakeholders|Present projects may slow"
    ],
    "belief": [
        "Constructive Doubt|When players challenge a dominant claim|Create resilient shelter from admitted uncertainty|False certainty weakens structures",
        "Forgotten Deity Labor|When a deity loses followers|Give it a mundane civic profession|Old worship obligations remain",
        "Hope Causeway|When communities share a credible aspiration|Build a temporary road across empty space|Broken trust dissolves the road",
        "Disbelief Ice|When skeptical witnesses gather|Solidify bodies of water temporarily|Faithful travelers experience open currents",
        "Failure Guardian|When a genuine attempt fails|Create a helper tailored to its lesson|Repetitive staged failures earn nothing",
        "Courtesy Resurrection|When unresolved misunderstanding is discovered|Permit a short encounter with the dead|Long-term resurrection remains unavailable",
        "Myth Repayment|When a legend is accepted as communal canon|Create a future event obligation|Unrealistic myths create unsustainable debt",
        "Ritual Keystone|When a public ceremony is abandoned|Recalculate dependent ecological stability|Harmful ritual replacements must be designed",
        "Prayer Consensus|When worshippers choose incompatible hopes|Find a noncoercive shared interpretation|No unanimous goal may exist",
        "Icon Migration|When a sacred symbol moves communities|Transfer an associated social rule|Original community loses cultural anchoring",
        "Uncertainty Orchard|When a prediction admits its error interval|Grow probabilistic options rather than fixed rewards|Results cannot be guaranteed",
        "Secular Miracle|When a practical solution surpasses a prophecy|Transfer social legitimacy from myth to evidence|Old institutions resist change"
    ],
    "infrastructure": [
        "Last Train Rewire|When the final train departs|Permute station destinations deterministically|Late travelers face new routes",
        "Command Reservoir|When water enters an old pipe|Carry a preserved instruction downstream|Unfiltered commands can conflict",
        "Gift Bridge|When settlements exchange meaningful gifts|Grow a new bridge along their trade line|Exploitation causes bridge decay",
        "Darkness Grid|When a night-power cable is activated|Transfer darkness between neighborhoods|Illuminated zones impose shadow burden elsewhere",
        "Clockwater Channel|When canal clocks desynchronize|Reverse water flow in affected basins|Flood risk follows scheduling errors",
        "Renovation Shelter|When housing enters approved repair state|Temporarily increase shelter capacity|Finishing repairs ends special capacity",
        "Mobile Hospital|When a district becomes injured terrain|Move it onto a restoration route|Residents must accept disruption",
        "Road Fatigue|When too many vehicles repeat a route|Increase resistance and generate alternative paths|Established supply lines degrade",
        "Shared Failure Budget|When one utility is overloaded|Borrow capacity from a consenting neighboring utility|Borrowing propagates risk",
        "Street Memory|When a block is demolished|Keep hidden service edges until surveyed|Old utilities may surprise builders",
        "Emergency Weave|When multiple failures coincide|Reroute services through temporary cross-domain links|Improvised links lower efficiency",
        "Resident Load|When population composition changes|Recalculate services by actual need rather than headcount|Rapid migrations cause shortages"
    ],
    "language": [
        "Tense Storm|When a future-tense declaration is accepted|Advance or delay a nearby weather event|Grammar ambiguity creates forecast uncertainty",
        "Unworded Passage|When both players agree a concept has no adequate word|Open a temporary passage|Naming it closes the passage",
        "Dialect Terrain|When a dialect diverges enough|Grow a distinct terrain layer around its speakers|Translation may merge layers",
        "Pronoun Border|When a person chooses an address form|Shift the jurisdiction line around interactions|Misaddress can cause conflict",
        "Letter Masonry|When a written glyph is used as a building block|Instantiate a material based on meaning and syntax|Erasure damages structures",
        "Echo Rights|When a nonhuman being learns a phrase|Grant a specific temporary civic permission|Parroting alone does not establish understanding",
        "Redaction Thicket|When records lose a consequential phrase|Grow an obstacle encoding the omission|Revealing secrets destroys the thicket",
        "Lexicon Caravan|When a rare word migrates between regions|Transfer its associated practical skill|Origin region may lose fluency",
        "Metaphor Bridge|When two communities agree on an analogy|Connect otherwise incompatible knowledge graphs|Misleading metaphors create weak bridges",
        "Grammar Trap|When an ambiguous command is executed|Fork plausible interpretations into different outcomes|Unresolved branches consume attention",
        "Name Repair|When a lost object is accurately renamed|Restore its former functional contract|False renaming worsens damage",
        "Translation Debt|When an imperfect translation is used|Gain immediate cross-cultural access|Semantic mismatches accrue repair obligations"
    ],
    "scale": [
        "Pebble Country|When entering a mineral fragment|Descend into its own nested navigable polity|Actions may change the host object's structure",
        "Status Magnification|When changing physical size|Adjust legal influence according to the local scale law|Resizing alters civil access",
        "Organ Treaty|When body organs trade resources|Negotiate systemic health across rival internal nations|Local gain can harm the host",
        "Tabletop Orbit|When household items receive orbital energy|Enable gravitational travel among their surfaces|Changing orbit threatens inhabitants",
        "Recursive Stair|When ascending beyond a known floor|Enter a scaled replica with altered tick rates|Return routes require scale bookkeeping",
        "Bond Labor|When molecules exchange roles|Reassign chemical bonds as communal labor|Some reactions remain thermodynamically costly",
        "Skin Terrain|When a giant creature moves|Remap settlement slopes and travel corridors|Settlements must migrate safely",
        "Fractal Harvest|When harvesting at one scale|Propagate a proportional change to child scales|Inaccessible child ecosystems may suffer",
        "Scale Inversion|When the observer shrinks|Swap which processes count as slow and fast|Timing errors amplify",
        "Nested Currency|When value passes between scales|Convert resources with dimensional exchange losses|Arbitrage is not free",
        "Perspective Shield|When a threat changes relative scale|Reduce one danger while exposing another|No scale grants universal safety",
        "Recursive Survey|When mapping a world-within-world|Record ancestry and coordinates for each nesting level|Memory budget limits depth"
    ],
    "mortality": [
        "Office of Loss|When a citizen dies|Create a new civic responsibility honoring their role|Vacant responsibilities strain government",
        "Age Burden Transfer|When a resurrection is consensually requested|Redistribute accumulated age burden among volunteers|No free revival exists",
        "Ghost Maintenance|When a ghost repairs invisible machinery|Improve infrastructure integrity|Living workers need indirect proof",
        "Funeral Preview|When a living person rehearses a remembrance|Reveal likely legacy and permit a choice|Preview changes relationships",
        "Species Succession|When an heir is designated|Grant inheritance through habitat preservation|Economic gain depends on conservation",
        "Building Rebirth|When a structure is decommissioned|Reincarnate parts with inherited maintenance history|Designers inherit old defects",
        "Ancestor Habitat|When a memorial is tended|Regenerate a related family ecosystem|Neglect degrades living habitat",
        "Second Loss|When a memory is not renewed|Reduce its physical preservation strength|Constant remembering consumes attention",
        "Restoration Hearing|When conflicting resurrection claims arise|Collect consent across affected people|Some requests must be refused",
        "Grief Cartography|When loss reshapes a relationship network|Generate navigable emotional landmarks|Maps expose private associations",
        "Legacy Gift|When an object outlives its owner|Transfer one intended capability to a chosen beneficiary|Other capabilities dissolve",
        "Mortality Truce|When enemies jointly mourn|Temporarily suspend hostility and open dialogue|Truce cannot erase historical damage"
    ],
    "voyage": [
        "North Pursuit|When migratory navigation markers move|Update directional reference to a tracked creature|Maps decay without fresh observations",
        "Possible Island|When weather and player intent align|Materialize one conditional island|Other islands may become unreachable",
        "Arrival Paradox|When a vessel arrives before departure|Create a reconciliation obligation for cargo and crew|Unresolved paradox blocks trade",
        "Endless Survey|When reaching a frontier edge|Generate new frontier from bounded causal rules|No final victory is implied",
        "Regret Bearing|When crew members disclose a regretted choice|Rotate compass toward a related destination|Navigation can reopen trauma",
        "Contradictory Charts|When rival observers map a route|Retain multiple consistent partial maps|Merged maps may be impossible",
        "Habitat Vessel|When a ship travels between biomes|Evolve its internal ecology with passengers|Ecological degradation restricts range",
        "Single Harbor|When landing at an unvisited port|Mark its services permanently used|Visits are irreversible choices",
        "Generational Crew|When a crew ages during voyage|Transfer duties through apprenticeship rather than level reset|Lost expertise can strand the vessel",
        "Star Memory|When a constellation disappears|Navigate by remembered relative trajectories|Memory drifts with time",
        "Risk Beacon|When an expedition returns from danger|Publish an evidence-backed hazard signal|Public warning may draw competitors",
        "Port of Return|When a lost expedition is found|Offer a route home at a genuine opportunity cost|Homecoming ends some possible journeys"
    ],
    "performance": [
        "Stage Legislation|When a public performance is ratified|Turn one staging rule into a temporary physical law|Audience dissent limits the duration",
        "Dance Vector|When performers form a synchronized pattern|Change local gravity vectors|Broken formation cancels stability",
        "Applause Feeding|When an audience responds authentically|Supply energy to backstage organisms|Manipulated reactions deplete trust",
        "Echo Restoration|When a ruin's original acoustic pattern is reproduced|Repair compatible structural components|Imperfect melody creates brittle repairs",
        "Mask Obligation|When wearing a historical role|Gain its techniques and outstanding duties|Removable mask does not erase responsibility",
        "Finite Rehearsal|When rehearsing a scheduled show|Consume one possible future public performance|Practice competes with actual performance",
        "Spectator Memory|When an act is performed for different audiences|Evolve its content based on consented memories|Memory exposure carries privacy cost",
        "Novelty Engine|When a genuinely new behavior is performed|Unlock one bounded world-rule mutation|Repeated tricks lose novelty",
        "Tempo Truce|When combatants match rhythmic patterns|Create a short negotiation window|Mismatch resumes the conflict",
        "Chorus Architecture|When a group sustains tuned chords|Construct temporary acoustic bridges|Fatigue limits duration",
        "Improvised Ending|When players reject a scripted finale|Generate a continuity-safe epilogue branch|Unresolved consequences remain",
        "Living Critique|When an audience critiques a performance|Change which abilities the next generation inherits|Unfair feedback damages culture"
    ]
}


def _load() -> Mapping[str, OriginalMechanic]:
    mechanics: dict[str, OriginalMechanic] = {}
    names: set[str] = set()
    for domain, rows in sorted(_MECHANIC_ROWS.items()):
        for index, row in enumerate(rows, start=1):
            title, trigger, state_change, drawback = row.split("|")
            if title.casefold() in names:
                raise ValueError(f"repeated mechanic name: {title}")
            names.add(title.casefold())
            identifier = f"{domain}-{index:02d}"
            mechanics[identifier] = OriginalMechanic(
                identifier, title, domain, trigger, state_change, drawback,
            )
    return MappingProxyType(mechanics)


MECHANICS = _load()


def get_mechanic(mechanic_id: str) -> OriginalMechanic:
    try:
        return MECHANICS[mechanic_id]
    except (KeyError, TypeError) as exc:
        raise ValueError("unknown original mechanic") from exc
