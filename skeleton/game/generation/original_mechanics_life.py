"""Eight independently authored mechanic hypotheses for each living-system domain."""
ROWS = {
    "genetics": [
        "Trait Heritage|When lineage history is documented|Project inheritable traits with uncertainty|Predictions cannot dictate personal rights",
        "Variation Safeguard|Before modifying an organism|Apply biosafety and consent checks|Some experiments are disallowed",
        "Adaptation Ledger|After a trait improves survival|Record ecological costs in other niches|Fitness is environment dependent",
        "Allele Exchange|At an approved controlled experiment|Transfer a bounded trait between simulated populations|Compatibility reduces success",
        "Epigenetic Recovery|When environmental stress decreases|Restore some reversible expression changes|Effects have time lag",
        "Genome Audit|Before declaring a stable phenotype|Compare phenotype to independent observations|Hidden factors remain",
        "Diversity Preserve|During selective breeding|Protect minimum population diversity|Short-term specialization is constrained",
        "Ecology Handoff|When a new variant enters habitat|Observe long-term species interactions|Release can be postponed"
    ],
    "evolution": [
        "Selection Pressure|When an environment changes|Alter relative trait survival probabilities|Tradeoffs reduce other fitness dimensions",
        "Behavioral Adaptation|Following repeated meaningful outcomes|Modify an organism's strategy|Learning has energy costs",
        "Niche Allocation|When species overlap in resource use|Create or shrink ecological niches|Competition may displace weaker populations",
        "Mutation Window|During reproduction under safe rules|Introduce bounded heritable variation|Most changes do not help",
        "Speciation Boundary|After sustained divergence|Split compatible populations into separate lineages|Gene flow becomes limited",
        "Cooperative Selection|When cross-species mutual aid succeeds|Favor stable cooperation traits|Free riders and ecology affect stability",
        "Extinction Warning|When a population nears collapse|Trigger rescue and habitat protection options|Restoration is uncertain",
        "Evolutionary Continuation|After a dominant species emerges|Allow other lineages to keep adapting|There is no final perfect creature"
    ],
    "microorganisms": [
        "Quorum Signal|When enough cells emit compatible markers|Activate a group behavior|Signal loss deactivates coordination",
        "Biofilm Layer|Under suitable surfaces|Construct protective microbial colonies|Dense layers can block utilities",
        "Metabolite Exchange|When symbionts share a boundary|Move nutrient compounds between species|Supply is limited",
        "Controlled Culture|During laboratory incubation|Expand a bounded microbe population|Temperature and nutrients constrain growth",
        "Antimicrobial Stewardship|When a harmful outbreak occurs|Apply a proportional mitigation intervention|Resistance pressure may increase",
        "Microbial Trace|After sampling a habitat|Infer past chemical conditions|Sampling is noisy and invasive",
        "Spore Spread|When airflows favor dispersal|Migrate a controlled colony to new locations|Unwanted spread needs containment",
        "Symbiosis Repair|When microbial balance is disrupted|Restore compatible populations|Recovery requires ecological time"
    ],
    "agriculture": [
        "Crop Rotation|After a harvest|Switch soil use to support future fertility|Immediate yield may decline",
        "Pollination Contract|When flowering schedules align|Increase cross-field fertilization|Pollinators require habitat",
        "Seed Reserve|When collecting viable seed|Store future planting capacity|Storage reduces current harvest",
        "Irrigation Balance|On allocating water|Update crop growth and downstream supply|Overdraw harms other fields",
        "Soil Regeneration|After measured restorative practice|Recover long-term fertility|Soil recovery is slow",
        "Harvest Window|At optimal maturity|Gather food with reduced waste|Waiting exposes crops to hazards",
        "Livestock Migration|When pasture health declines|Move herds with tracked ecological load|Transit stresses animals",
        "Farm Continuation|After first successful harvest|Unlock long-term trade, crop evolution and stewardship|There is no terminal perfect yield"
    ],
    "medicine": [
        "Consent Checkpoint|Before applying nonemergency intervention|Verify informed patient preferences|Some actions must be deferred",
        "Care Triage|When demand exceeds treatment capacity|Allocate resources through transparent need criteria|No allocation satisfies everyone",
        "Symptom Investigation|After receiving patient observations|Construct an uncertain causal model|Diagnosis may remain ambiguous",
        "Independent Opinion|Before a high-stakes decision|Seek an alternate validated assessment|Time and resources are spent",
        "Rehabilitation Program|After acute treatment|Restore selected capabilities through ongoing practice|Recovery is gradual",
        "Public Health Shield|When environmental harms spread|Deploy preventive community measures|Restrictions must be proportional",
        "Clinical History|Following a treatment|Append adverse and beneficial outcomes to patient records|Privacy controls limit access",
        "Care After Recovery|When symptoms improve|Open long-term well-being and accessibility activities|No instant universal cure"
    ],
    "metabolism": [
        "Energy Budget|When organisms take action|Spend measurable stored energy|Exhaustion constrains repeated activity",
        "Nutrient Routing|During food processing|Allocate nutrients across dependent systems|Conversion loses some usable energy",
        "Thermal Regulation|When body temperature shifts|Transfer heat to safe sinks|Cooling and heating require resources",
        "Sleep Recovery|After sustained work|Restore bounded physiological capacity|World time advances",
        "Waste Recovery|Following metabolic processing|Recycle compatible outputs into ecosystems|Recycling is never perfectly lossless",
        "Cross-Species Digest|When partners exchange digestive functions|Unlock new nutritional options|Separation requires adaptation",
        "Shared Respiration|When connected habitats exchange gases|Stabilize local breathable supply|Leakage affects both sides",
        "Metabolic Stress|When activity exceeds sustainable limits|Trigger slower performance and urgent rest|Ignoring warning compounds damage"
    ],
    "cognition": [
        "Attention Allocation|When tasks compete|Shift limited concentration between goals|Neglected goals decay",
        "Memory Retrieval|Upon presenting relevant context|Recover bounded prior experience|Recall can be imperfect",
        "Hypothesis Revision|When evidence contradicts belief|Update cognitive model and dependencies|Commitments may need repair",
        "Reflective Pause|After an emotionally intense event|Open a low-pressure decision window|Pacing reduces immediate action speed",
        "Multi-Perspective View|With consented viewpoints|Compare compatible and conflicting interpretations|No universal interpretation guaranteed",
        "Creative Incubation|Following meaningful rest|Generate novel candidate approaches|Quality is not guaranteed",
        "Shared Reasoning|When collaborators pool independent observations|Improve a joint model|Group bias must be checked",
        "Cognitive Continuity|When memory models evolve|Keep provenance and prior versions available|History cannot be overwritten"
    ],
    "symbiosis": [
        "Ability Exchange|At a compatible reversible bond|Borrow one biological capability|Both partners have an energy cost",
        "Habitat Reciprocity|After partners improve each other's habitat|Unlock ecosystem resilience|Neglect degrades benefits",
        "Resource Transfusion|When two organisms connect|Transfer nutrients under bounded flow|One party's reserve decreases",
        "Symbiotic Consent|Before binding intelligent partners|Confirm opt-in and separation rules|Some pairings must be refused",
        "Species Signal|When partners emit compatible cues|Enable shared navigation or sensing|Signals can be disrupted",
        "Partnership Rotation|When seasons change|Reassign ecological partnerships|Transitions temporarily reduce output",
        "Host Recovery|After a harmful bond ends|Restore a host's ecological independence|Recovery takes time",
        "Mutualist Legacy|When partners separate amicably|Preserve learned capabilities in cultural memory|Physical borrowed abilities expire"
    ],
    "aging": [
        "Biological Clock|On elapsed world time|Advance distinct age-related capacities|Not all processes progress equally",
        "Age Exchange|With consent and explicit rules|Transfer bounded age burdens|One partner must receive the burden",
        "Intergenerational Handoff|When elders retire roles|Share practice-proven expertise|Not all tacit knowledge transfers",
        "Long Life Care|After repeated health assessments|Maintain well-being through habits and services|Care remains continuous",
        "Legacy Retirement|When an old institution completes its mission|Move expertise into future civic roles|Past structures lose authority",
        "Seasonal Rejuvenation|In approved restorative environments|Recover selected fatigue-linked abilities|Permanent aging is not erased",
        "Age Diversity Council|Before policies with lifespan effects|Collect perspectives across age groups|Deliberation requires extra time",
        "Life Beyond Level|After a character reaches a traditional age cap|Unlock social and exploratory growth|Numeric leveling is no longer the goal"
    ]
}
