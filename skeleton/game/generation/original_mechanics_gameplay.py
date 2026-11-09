"""Eight independently authored mechanic hypotheses for each gameplay domain."""
ROWS = {
    "puzzles": [
        "Constraint Propagation|When a player changes one puzzle variable|Update dependent legal options|Some formerly viable branches close",
        "Partial Solution|When progress is valid but incomplete|Award useful intermediate access|Full rewards remain locked",
        "Contradiction Detector|After adding conflicting clues|Reveal a minimal inconsistent subset|Analysis uses scarce hints",
        "Mutable Maze|When observation or movement changes topology|Recompute reachable room graph|Known routes become stale",
        "Hint Economy|When requesting assistance|Reveal one justified reasoning step|Hints consume optional support budget",
        "Cooperative Lock|When participants share different knowledge|Combine scoped partial keys|Solo shortcuts are unavailable",
        "Unwinnable Diagnosis|When no solution satisfies all constraints|Explain unsatisfiable conditions without faking victory|Player must choose alternate goals",
        "Puzzle Afterlife|After solving the campaign mechanism|Enable player-generated variants and world consequences|More puzzles remain optional"
    ],
    "combat": [
        "Telegraphed Attack|Before an opponent strikes|Reveal a legible attack commitment|Enemies also learn player patterns",
        "Stamina Budget|After any demanding action|Spend energy with recoverable timing|Continuous aggression causes vulnerability",
        "Environment Mutation|When attacks damage terrain|Persist topology and hazard changes|Civilian routes may suffer",
        "Conflict Deescalation|When opponents disengage|Open negotiated noncombat alternatives|Negotiation is not always accepted",
        "Adaptive Defense|When attacks repeat|Allow opponents to learn bounded counters|Predictable tactics become weaker",
        "Cover Conservation|When a projectile destroys cover|Apply material and structural consequences|Cover is not automatically restored",
        "Fairness Ledger|During encounters with bystanders|Track collateral impact and accountability|High damage carries legal costs",
        "War Aftermath|After enemies are defeated|Open repair, trust and resettlement tasks|Battle victory is not world victory"
    ],
    "stealth": [
        "Suspicion Budget|When agents observe unusual behavior|Update suspicion with explicit evidence|Suspicion decays imperfectly",
        "Occlusion Route|When sightlines break|Enable temporary concealed travel|Moving observers can reveal passage",
        "Acoustic Propagation|After noisy actions|Route audible signals through geometry|Distractions reveal environmental information",
        "Disguise Credibility|When taking a role|Gain permissions only after credible behavior|Errors increase exposure",
        "Evidence Cleanup|After a risky traversal|Repair harmful traces without falsifying public records|Cleanup costs time",
        "Adaptive Patrol|When guards detect exploit patterns|Adjust limited patrol routes|Infinite memorized loops fail",
        "Ethical Exit|When an investigation goal is reached|Provide safe nonharmful departure options|Looting may jeopardize success",
        "Postmission Responsibility|After recovering information|Resolve harms, privacy and restitution|Mission scoring cannot erase damage"
    ],
    "survival": [
        "Resource Intake|When gathering food or fuel|Increase carried resources within ecological bounds|Harvest reduces local reserves",
        "Thermal Shelter|When weather threatens|Exchange materials for protection and warmth|Shelter decays without maintenance",
        "Fatigue Recovery|After strenuous work|Restore effort capacity through rest|Rest spends world time",
        "Water Safety|Before consuming uncertain water|Assess and improve potability|Treatment uses supplies",
        "Shared Inventory|When companions cooperate|Pool selected survival resources|Unfair use degrades trust",
        "World Pressure|As environmental systems evolve|Update hazards independently of player level|Some places remain dangerous",
        "Rescue Objective|When global survival cannot be won|Create local meaningful protection tasks|No fabricated victory condition",
        "Reconstruction Loop|After an emergency ends|Start renewable community-building systems|Ecology still imposes limits"
    ],
    "crafting": [
        "Recipe Compiler|When a design is submitted|Check resource and process constraints|Invalid recipes cannot produce artifacts",
        "Part Inheritance|When upgrading equipment|Preserve applicable behaviors and provenance|Incompatible parts require redesign",
        "Material Budget|Before construction|Reserve exact input resources and tolerances|Scarcity limits output",
        "Repair Workflow|After damage is detected|Offer incremental verified repair actions|Repair consumes labor",
        "Era Porting|When targeting different hardware|Map mechanics to available device features|Some fidelity must scale down",
        "Cross-Hybrid Tool|When combining two original systems|Create a new interface with explicit tradeoffs|Conflicts need resolution",
        "Salvage Recovery|When deconstructing an object|Recover tested reusable material|Some material is unrecoverable",
        "Masterwork Continuation|After completing a rare item|Unlock mentorship, new templates and social uses|No static endgame is assumed"
    ],
    "sport": [
        "Fairness Rule|When a match begins|Instantiate agreed permitted abilities and scoring|Unexpected conditions need arbitration",
        "Physics Ball|On contact with a sports object|Apply declared collision behavior|Energy and direction are constrained",
        "Team Tempo|When teammates synchronize actions|Unlock cooperative movement windows|Miscommunication breaks timing",
        "Dynamic Arena|On approved field transitions|Reconfigure goals or hazards|Participants require warning",
        "Skill Practice|After demonstrated improvement|Increase mastery of a distinct movement skill|Repetition has diminishing returns",
        "Referee Appeal|When a decision is disputed|Review independently recorded evidence|Game may pause",
        "Community League|After a tournament|Start accessible seasonal competition|Facilities and mentors need support",
        "Nonterminal Season|When a champion is crowned|Archive history and create fresh voluntary challenges|Winning is not finishing sport"
    ],
    "mystery": [
        "Evidence Collection|On discovering a relevant object|Record custody and observed properties|Contamination lowers reliability",
        "Hypothesis Graph|When clues become available|Connect causes and possible consequences|Unsupported edges remain uncertain",
        "Witness Consent|Before an interview|Check privacy and willingness|Refusal limits available evidence",
        "Contradiction Challenge|When two accounts conflict|Offer a discriminating investigation|Tests take resources",
        "Cold Case Memory|When investigators change|Carry forward signed case history|Tacit context may be lost",
        "Unknown Culprit|When no unique explanation exists|Maintain uncertainty as a valid outcome|No forced answer reward",
        "Restorative Verdict|After sufficient public evidence|Open fair remediation processes|Punishment is not the sole objective",
        "Aftermath Investigation|When a case closes|Track societal effects of published findings|New problems may emerge"
    ],
    "strategy": [
        "Supply Route|When forces or services move|Calculate capacity and travel cost|Long supply lines are fragile",
        "Fog of Evidence|When a faction lacks observations|Hide uncertain enemy and economic state|Scouting consumes resources",
        "Political Commitment|When declaring an alliance|Create revocable obligations and consequences|Breaking trust reduces credibility",
        "Adaptive Frontline|When topology or weather changes|Update strategic reachability|Existing plans may fail",
        "Resource Governance|When allocating resources|Apply public resource and ecological constraints|Short-term gains impose debt",
        "Nonmilitary Victory|When conflict cannot be decisively won|Promote protected civilian and diplomatic achievements|Hostility may remain",
        "Consequence Forecast|Before major decisions|Show bounded possible downstream effects|Predictions retain uncertainty",
        "Postwar Strategy|After conflict resolution|Unlock reconstruction and long-term governance|Winning does not end simulation"
    ]
}
