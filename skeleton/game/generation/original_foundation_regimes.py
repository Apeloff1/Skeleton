"""Eighty individually authored causal overlay regimes in ten executable classes.

Overlay narratives have real constrained state-machine effects. Crossings with
root laws are composed by a deterministic compiler, not individually written.
"""
REGIME_GROUPS = [
  [
    "echo",
    [
      "Echo Charter of Unpaid Repairs|Every intervention causes its main benefit again one dawn later|Choose when repeated effects are welcome|Delayed benefits also reopen prior duties|persistent",
      "Lantern Echo Bankruptcy|Stored actions replay at night but draw from next day's capacity|Schedule evening labor against tomorrow's energy|Overloaded echoes freeze public services|unwinnable",
      "Tide of Second Decisions|A performed choice returns with half its original force after the next regional change|Allow or interrupt the second consequence|Reruns collide with earlier commitments|looping",
      "Afterimage of the Common Good|Civic acts create delayed ecological replicas in adjacent settlements|Care for recipients before propagation|Unprepared towns inherit unwanted construction|postgame",
      "The Witness Aftershock|Every investigation must be reviewed again after one full world tick|Schedule evidence retesting during crises|Untested repeats spread false accounts|branched",
      "Borrowed Resonant Harvest|Collected yield returns once more after weather shifts but carries material fatigue|Harvest cautiously around delayed abundance|Accumulated fatigue ruins growing land|persistent",
      "Future Choir Refrain|A collective action sings itself again when the next boundary is crossed|Prepare a safe chorus for delayed recurrence|Refrains trap travelers in unresolved loops|open",
      "Receipt of the Second Sun|Public actions are duplicated only after a complete rest cycle|Reserve stamina for later repercussions|Rushed rest amplifies unpaid consequences|persistent"
    ]
  ],
  [
    "levy",
    [
      "Commons Toll of Living Roads|Each private improvement pays a concrete reserve into public transit|Invest while keeping essential passages funded|Unpaid road dues close rescue routes|persistent",
      "Nutrient Sharing Tariff|Each productive action diverts part of its yield to damaged habitat|Budget extraction with restoration|Tariff evasion starves local ecosystems|postgame",
      "Tax of Borrowed Days|Every intervention spends a day from the community's future rest bank|Reserve time for care and regeneration|Unpaid time debt accelerates fatigue|unwinnable",
      "Lantern Revenue Compact|Useful changes deduct lighting supplies for surrounding settlements|Maintain illumination before exercising power|Darkened neighborhoods lose safe transit|branched",
      "Proof Levy|Every gained advantage requires publishing an auditable fragment of evidence|Balance privacy and accountable decision making|Overdisclosure harms vulnerable witnesses|open",
      "Kinship Contribution|Each new capability requires a reciprocal service to strangers|Allocate care before scaling inventions|Ignored reciprocity weakens trust|persistent",
      "Watershed Maintenance Charge|Any reshaped region owes conserved water to downstream safety pools|Fund drought resilience during expansion|Depletion dries allied districts|persistent",
      "Archive Preservation Toll|Every remembered benefit consumes storage capacity for displaced histories|Protect verified old records before acquiring more|Unpaid archives erase minority testimony|persistent"
    ]
  ],
  [
    "reverse",
    [
      "Counterphase Exchange|On every other turn progress moves backward unless citizens invest stabilizers|Time alternating moves around known reversals|Bad parity destroys fragile improvements|looping",
      "Mirror of the Failed Repair|Repairs alternate between strengthening and revealing fresh damage|Choose a sequence that leaves essential structures intact|Repeated work exposes buried vulnerabilities|persistent",
      "Reversed Orchard Bargain|Every second harvest returns nutrients instead of food|Keep reserves during reverse-yield seasons|Overharvest leaves households hungry|open",
      "Northward Inversion|A route improvement alternates between opening and closing a distinct corridor|Preserve parallel passages against inversion|Single-route dependence strands commuters|unwinnable",
      "Court of Contrary Witnesses|Alternate public judgments reopen their preceding legal evidence|Maintain fair historical appeals|Unreviewed reversal restores injustices|branched",
      "Ledger of Opposite Grace|Every second charitable action demands equal reciprocal assistance|Pair generosity with sustainable social support|Unbalanced duty exhausts caregivers|postgame",
      "The Tide That Gives Back|Alternate water diversions restore upstream reserves but erase downstream gains|Plan irrigation around known reverse flows|One-sided schedules flood settlements|persistent",
      "Glass of Contradictory Motion|Every second movement of machinery creates opposing momentum debt|Build safe alternating mechanical cycles|Unpaid backforce fractures foundations|looping"
    ]
  ],
  [
    "threshold",
    [
      "Gate of Seven Public Deeds|New capability appears only after enough verified shared actions|Decide when to cross a public milestone|Premature gate opening exhausts communal capacity|postgame",
      "Critical Orchard of Trust|A social commons changes its laws when trust clears a measurable threshold|Create durable legitimacy before unlocking rights|Manufactured consensus triggers civic backlash|branched",
      "Weather Threshold Assembly|Ecological interventions trigger a new climate regime at specified cumulative load|Budget activity around a tipping point|Crossing blindly causes prolonged drought|unwinnable",
      "The Eightfold Recipe|Crafting unlocks a new tool only after a complete chain of different repairs|Diversify real work instead of grinding repeats|Rushed specialization invalidates the tool|persistent",
      "House of Rising Evidence|Investigations become actionable only when independent evidence reaches a public quota|Collect proof without coercion|Insufficient evidence produces false alarms|open",
      "Pilgrim's Rest Gate|Travel routes open when accumulated rest has been shared fairly|Protect voluntary breaks before expeditions|Unequal rest traps exhausted travelers|persistent",
      "The Civic Carrying Line|Settlement growth alters land rights whenever a population threshold is crossed|Reallocate infrastructure before expansion|Fast growth makes neighborhoods unsafe|persistent",
      "Moon of Counted Warnings|Every eighth verified hazard report changes the world's protection rule|Publish accurate risk evidence before transition|Fraudulent warnings disable shelters|looping"
    ]
  ],
  [
    "migration",
    [
      "Commons of Moving Shelter|Beneficial outcomes migrate from the center toward neglected border hamlets|Plan care as supplies follow need|Oversupply at edges leaves central hospitals exposed|persistent",
      "School of Migrating Knowledge|Discoveries must travel to another settlement before they count as progress|Teach across uneven access|Unshared learning becomes local myth|postgame",
      "The Wandering River Account|Every action redirects one unit of environmental benefit into a neighboring basin|Allocate downstream responsibility|Overconcentration floods fragile coasts|unwinnable",
      "Parcel of Borrowed Heat|Energy improvements move the warmest household to the coldest district|Protect donors while addressing shortages|Unbalanced transfer creates new exposure|branched",
      "The Route of Mobile Law|Each intervention carries a jurisdictional right into another district|Negotiate handoffs without silencing residents|Legal gaps leave travelers unprotected|open",
      "Nest Drift Covenant|Ecological productivity migrates with mobile wildlife populations|Steward relocation habitats|Forced migration extinguishes nurseries|persistent",
      "Festival of Moving Resources|Celebrations transfer their benefits to a different village at each season|Coordinate where public goods will land|Stationary infrastructure becomes obsolete|looping",
      "The Traveling Research Charter|Scientific progress migrates through laboratories in a fixed rotating order|Prepare each research site for new duties|Unchecked handoffs destroy evidence|persistent"
    ]
  ],
  [
    "veto",
    [
      "The Consent of Empty Places|Uninhabited areas can refuse new construction through ecological criteria|Meet habitat safeguards before intervention|Ignored vetoes trigger ecological collapse|persistent",
      "Council of Small Witnesses|Actions require verified endorsement by people most affected|Build trust before changing institutions|Procedural shortcuts deepen alienation|branched",
      "Veto of Finite Daylight|No intervention may pass when public energy reserves fall below a safe floor|Save enough shared power for emergencies|Reckless uses darken shelters|unwinnable",
      "The Silent Union Charter|Workers may refuse unsafe automation until material duties are honored|Reconcile machine schedules with labor consent|Coerced work freezes factories|postgame",
      "Elder River's Refusal|Navigation alterations are blocked when flood-risk evidence is incomplete|Investigate before moving water|Ignoring veto erases villages|persistent",
      "Archive of Privacy Claims|Memory edits require independent permission from the affected record owners|Secure consent before altering history|Unlawful publication invalidates testimony|open",
      "Clinic of Voluntary Aid|Healing technology refuses compulsory treatment absent consent|Offer safer alternatives to reluctant patients|Coercion destroys long-term trust|persistent",
      "The Last Bridge Veto|A proposed shortcut may be refused if no second escape route exists|Demonstrate redundancy before opening a gate|Overconfidence strands critical expeditions|unwinnable"
    ]
  ],
  [
    "cascade",
    [
      "Compounding Commons|Each successful civic intervention makes the next one more effective but more expensive|Stage projects before feedback becomes unsafe|Unchecked amplification destroys reserves|persistent",
      "Avalanche of Tiny Agreements|Small promises trigger growing chains of community obligations|Control cascade depth with explicit limits|Runaway duties exhaust citizens|branched",
      "Ecological Snowball Treaty|Habitat change propagates to every dependent trophic level|Predict and damp cascading adaptations|Small errors devastate food webs|unwinnable",
      "Memory Landslide|Each recovered history uncovers an additional disputed witness|Budget verification against exponential inquiry|Unreviewed claims overwrite protected evidence|open",
      "Factory of Resonant Repairs|Each machine repair increases both output and vibration of its neighbors|Set safe feedback thresholds|Resonance shakes inhabited workshops|persistent",
      "The Growing Farewell|One departure triggers a wider migration with escalating logistical costs|Prepare spare housing before allowing travel|Unplanned movement strands families|postgame",
      "Chain of Unfinished Songs|Creative breakthroughs spread through connected studios and consume shared attention|Choose selective transmission|Cascade burnout silences the arts|persistent",
      "The Second-Dawn Plague|Each cured outbreak reveals a distinct connected disease process|Coordinate layered prevention without forced cure|Runaway response exhausts clinics|looping"
    ]
  ],
  [
    "exchange",
    [
      "Currency of Safe Passages|Route gains require exchanging an equivalent reserve of communal trust|Fund travel without selling social cohesion|Reckless exchange breeds isolation|persistent",
      "The Warmth-for-Rain Accord|Weather control spends stored thermal refuge in another community|Set mutually accepted climate priorities|Donor settlements freeze|unwinnable",
      "Ledger of Remembered Bread|Recovered memories can be exchanged for food but never without explicit consent|Price survival without exploiting witnesses|Memory monopolies erase personhood|branched",
      "Promise-to-Power Grid|Honored obligations become electrical energy only after material verification|Build a fair civic energy market|Fabricated vows black out neighborhoods|postgame",
      "Habitat-for-History Market|Ecological restoration exchanges resources with verified archives of past damage|Allocate effort using real environmental evidence|False histories redirect scarce care|persistent",
      "The Cartographer's Barter|Navigational progress requires a reciprocal gift of usable local knowledge|Trade maps while preserving community privacy|Maps become instruments of extraction|open",
      "The Courage Reservoir|One person's bravery may be traded only for shared protective supplies|Limit heroism to sustainable support|Hero worship exposes responders|persistent",
      "Festival of Balanced Debt|Communal celebrations transfer material debt between rich and poor districts|Design transparent redistribution|Hidden debts cause new scarcity|looping"
    ]
  ],
  [
    "auction",
    [
      "Auction of Public Dawn|Daily changes require bidding time into a finite communal morning pool|Reserve enough dawn for food production|Speculation locks out ordinary workers|persistent",
      "Bid for the Silent Map|Each route alteration requires evidence tokens paid at a public geography auction|Choose where cartographic certainty matters|Rich factions capture all safe roads|branched",
      "The Garden's Reverse Auction|Habitats receive aid from the lowest-cost verifiable restoration proposal|Bid responsibly for ecological repair|Underbidding starves protected species|postgame",
      "Clockwork Housing Tender|Every new home needs a construction bid backed by actual stored material|Balance competition and building safety|Manipulated bids strand families|persistent",
      "Ration Auction of Lost Futures|Uncertain timelines are preserved through costly open bids for archive space|Protect fair access to future evidence|Wealth purchases all possibilities|unwinnable",
      "Civic Oath Market|Promises compete for limited public implementation capacity|Fund honest commitments rather than spectacle|Speculators crowd out essential services|open",
      "Listening Post Exchange|Every intelligence observation requires a bid of protected attention|Prioritize actionable inquiry over surveillance|Mass bidding overwhelms verified evidence|persistent",
      "Harbor of Finite Returns|Every cross-world return costs a bid from scarce expedition supplies|Plan journeys with future rescue margins|Last resources are spent on prestige voyages|branched"
    ]
  ],
  [
    "fork",
    [
      "Two Futures of the Common Well|Choices permanently branch between shared and privately held water stewardship|Choose ownership with known public consequences|Privatization may strand low-income households|branched",
      "The Archive with Many Courts|A legal intervention creates enduring rival precedents rather than one final ruling|Navigate competing appeals and rights|Unchecked forks erase consistent due process|postgame",
      "Wilderness of Splitting Herds|Every habitat intervention creates two inheritable migration strategies|Steward divergent ecologies in parallel|One neglected branch may go extinct|persistent",
      "The Library of Irreversible Dreams|Publishing a dream permanently changes how future citizens learn|Choose whom to invite into the new tradition|Unreviewed branches trap education systems|open",
      "Bridge Between Unequal Cities|Road building splits history into cities that share goods but remember different causes|Trade across contradictory civic records|Divergent memories cause border crises|branched",
      "Factory of Abandoned Plans|Rejected production choices remain as autonomous competing alternatives|Observe alternate output without hiding waste|Forgotten branches consume finite materials|unwinnable",
      "The Last Choice that Continues|After apparent victory players keep governing all surviving consequential branches|Prioritize sustainable postgame responsibilities|Unattended endings become new disasters|postgame",
      "Cathedral of Seven Afterlives|A fictional moral decision branches into distinct persistent afterlife communities|Reconcile choices across consenting mythic realms|Absolutist doctrine strands dissenters|looping"
    ]
  ]
]
