"""Eight independently authored mechanic hypotheses for each technical domain."""
ROWS = {
    "computation": [
        "Deterministic Replay|After recording a canonical seed|Reproduce state transitions at the same version|Upgrades may require migration",
        "Rule Compilation|When accepting a new mechanic|Convert typed actions into bounded runtime operators|Unverifiable rules are rejected",
        "Branch Snapshot|At a significant choice|Create a separately identified world fork|Branch storage incurs cost",
        "Execution Budget|Before each simulation step|Allocate bounded CPU and memory|Some work must wait",
        "Consensus Check|When distributed results disagree|Select a validated reconciliation protocol|Some partitions cannot progress",
        "Model Confidence|After evaluating a prediction|Update calibrated uncertainty|Overconfidence is penalized",
        "Rollback Receipt|When deployment violates safety conditions|Restore the last verified stable state|Intervening actions may need reapply",
        "Postrelease Update|After a successful build|Offer reviewed world-rule extensions|Compatibility constraints apply"
    ],
    "robotics": [
        "Actuator Bound|Before moving a mechanical body|Check safe torque and collision envelopes|Unsafe commands are refused",
        "Swarm Coordination|When robots share a task|Assign separate resource-limited roles|Communication delay causes drift",
        "Consent Interface|When a service robot contacts a person|Require context-appropriate authorization|Tasks may be denied",
        "Component Maintenance|After wear indicators rise|Schedule repair and part replacement|Downtime affects services",
        "Distributed Body Sync|When a robot occupies several machines|Reconcile conflicting observations|Perfect sync is unavailable",
        "Battery Arbitration|At low charge|Negotiate critical shared tasks|Nonessential work is deferred",
        "Skill Transfer|After independent demonstration|Promote a learned safe procedure|Demonstrations are expensive",
        "Robot Retirement|At equipment end-of-service|Transfer duties and preserve historical evidence|Some capabilities are lost"
    ],
    "networks": [
        "Reliable Handshake|Before two nodes communicate|Establish authenticated compatible channel state|Connection setup costs time",
        "Packet Routing|When links are congested|Choose alternate bounded transport paths|Latency may increase",
        "Partition Recovery|After islands reconnect|Reconcile diverged state with provenance|Conflicts can require human input",
        "Bandwidth Admission|Before streaming data|Reserve measured transfer capacity|Low-priority messages may queue",
        "Privacy Relay|When sensitive data crosses nodes|Minimize content and permissions|Observability is reduced",
        "Cache Freshness|On reading cached information|Check version and time-to-live|Stale results need refetch",
        "Replay Protection|When receiving repeated packets|Reject duplicates under scoped identities|Extra storage tracks receipts",
        "Network Continuation|After a major outage|Develop new routes and resilience communities|Maintenance is indefinite"
    ],
    "energy": [
        "Conservation Ledger|Before energy conversion|Account for inputs, useful output and loss|Free energy is forbidden",
        "Storage Dispatch|When demand spikes|Draw from measured reserves|Capacity decreases",
        "Peak Shaving|When consumption threatens a grid|Defer selected noncritical work|Convenience is reduced",
        "Renewable Forecast|Before scheduling loads|Estimate solar and wind availability|Weather uncertainty persists",
        "Thermal Recycling|When equipment generates heat|Redirect recoverable heat to nearby users|Transport loses energy",
        "Blackstart Sequence|After complete grid loss|Restart services in dependency order|Startup power is scarce",
        "Demand Reciprocity|During energy shortage|Allocate voluntary community reductions|Participants incur opportunity costs",
        "Lifecycle Emissions|Before constructing a generator|Estimate construction and operating impacts|A cheap build may be costly later"
    ],
    "industry": [
        "Assembly Scheduling|When production orders arrive|Allocate station capacity and materials|Congestion creates backlog",
        "Quality Gate|Before releasing a part|Inspect measured conformity|Failures cause repair work",
        "Worker Safety Lock|On detecting hazardous conditions|Suspend affected equipment|Production slows until safe",
        "Scrap Recirculation|When defects are recovered|Return viable material to the supply pool|Processing incurs loss",
        "Provenance Stamp|At each production stage|Record source and transformation history|Traceability requires bookkeeping",
        "Factory Retrofit|When older machinery underperforms|Replace limited subsystems incrementally|Installation interrupts production",
        "Supply Shock|When inputs become unavailable|Replan alternate components with constraints|Quality and cost may change",
        "Community Redevelopment|After a factory closes|Convert buildings to verified new civic uses|Transition requires investment"
    ],
    "chemistry": [
        "Reaction Balancer|Before combining substances|Verify conservation and bounded reaction feasibility|Invalid reactions are rejected",
        "Catalyst Dispatch|When compatible reactants are present|Increase reaction speed under declared limits|Catalysts can degrade",
        "Separation Column|After mixed compounds form|Partition compatible materials through staged process|Energy and time are spent",
        "Corrosion Shield|When exposed materials react|Apply protection or reroute utility|Protection must be maintained",
        "Temperature Rate|When reaction environments heat or cool|Change kinetics according to a declared model|Side reactions can increase",
        "Controlled Synthesis|Before introducing new material|Verify known handling limits|Unknown properties require experiments",
        "Chemical Provenance|After synthesis|Record reagent identities and conversion paths|Trace data adds overhead",
        "Cleanup Reaction|When residues accumulate|Apply safe neutralization and recovery|Cleanup produces its own waste"
    ],
    "materials": [
        "Stress Analysis|Before loading a structure|Evaluate material response and failure bounds|Inadequate geometry is rejected",
        "Elastic Recovery|After a temporary deformation|Restore shape within declared limits|Hysteresis dissipates energy",
        "Fatigue Accumulation|When materials cycle through loads|Increase wear and failure risk|Frequent reuse reduces lifetime",
        "Microstructure Craft|During controlled processing|Modify grain or fiber organization|Process conditions cost energy",
        "Surface Friction|When materials meet|Calculate contact resistance|Heat and abrasion accumulate",
        "Composite Repair|On localized damage|Replace compatible layers without full rebuild|Bond quality constrains strength",
        "Recycling Grade|After dismantling structures|Recover materials by verified purity|Some compounds cannot be separated cheaply",
        "Adaptive Material|When temperature or pressure changes|Alter bounded properties according to constitution|Transition delay may threaten stability"
    ],
    "astronomy": [
        "Orbit Propagator|Given a declared gravitational model|Forecast bounded orbital positions|Approximation errors grow",
        "Launch Window|Before departing a planet|Choose an energy-efficient trajectory|Waiting sacrifices opportunities",
        "Signal Delay|When communicating between stars|Account for finite light-travel time|Replies may arrive generations later",
        "Habitat Survey|After observing a new body|Estimate environment and exploration risks|Remote sensing is uncertain",
        "Tidal Transfer|When moon orbits change|Update coastal and internal stress effects|Altered gravity affects settlements",
        "Stellar Resource|Before extracting planetary material|Measure impacts on orbits and habitats|Extraction has irreversible effects",
        "Long Voyage Succession|During multigenerational travel|Transfer crew expertise and civic authority|Skills may be lost",
        "Cosmic Exploration|When a survey frontier expands|Generate bounded new sectors with persistent identities|No final edge is promised"
    ]
}
