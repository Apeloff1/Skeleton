"""Expandable industry research headers; not claims of acquired expertise."""

_HEADERS = """
design|core loops;player agency;difficulty curves;systems interaction;progression;failure recovery
narrative|world rules;character motivation;branch consistency;dialogue;environmental storytelling;adaptation analysis
level_design|spatial grammar;encounter pacing;navigation;teaching;gating;procedural validation
player_research|experimental design;sampling;telemetry;qualitative interviews;causal inference;uncertainty
accessibility|motor access;visual access;hearing access;cognitive access;assistive devices;inclusive playtesting
graphics|rendering pipelines;lighting;materials;visibility;temporal stability;performance budgets
animation|locomotion;blending;inverse kinematics;facial systems;procedural motion;readability
physics|collision;rigid bodies;soft bodies;fluids;determinism;simulation limits
game_ai|navigation;planning;behavior selection;opponent modeling;coordination;debugging
audio|music systems;spatial sound;mixing;dialogue playback;latency;audio accessibility
input|device mapping;latency;buffering;gesture recognition;haptics;alternative controls
user_interface|information hierarchy;menus;HUD;onboarding;error recovery;controller navigation
networking|replication;prediction;rollback;matchmaking;latency compensation;disconnect recovery
online_operations|hosting;capacity;observability;incident recovery;regional routing;service retirement
security|untrusted content;save integrity;anti-cheat;authentication;supply chain;privacy
engine_architecture|scene graphs;entity systems;scheduling;serialization;hot reload;plugin boundaries
tools|editors;import pipelines;asset validation;profiling;build automation;creator workflows
compilers|language runtime;optimization;target ABI;linking;debug symbols;reproducible builds
storage|save formats;transactions;migrations;cloud conflicts;compression;recovery
hardware|CPU behavior;GPU behavior;memory;storage bandwidth;display timing;power and thermals
historical_platforms|native toolchains;cartridge constraints;disc media;controllers;regional variants;hardware verification
homebrew|original code;asset provenance;SDK provenance;device deployment;community documentation;distribution rights
porting|behavioral fidelity;target adaptation;input translation;rendering translation;save portability;cross-platform validation
quality_assurance|unit behavior;integration;property testing;fuzzing;long-duration testing;release regression
production|scoping;dependencies;milestones;budgeting;outsourcing;change management
business|pricing;distribution;market research;unit economics;forecast uncertainty;postlaunch support
monetization|purchase flows;time costs;reward transparency;regional restrictions;player wellbeing;refund behavior
community|moderation;creator tools;user content;competitive rules;dispute handling;community preservation
localization|text systems;translation;fonts;bidirectional layout;cultural review;regional testing
preservation|version history;source archives;media provenance;emulation context;rights chains;missing works
criticism|review methods;reviewer expertise;disclosures;satire context;cross-review disagreement;correction history
video_analysis|creator identity;episode identity;timecodes;editing context;observed mechanics;transcript rights
legal|copyright;patent claims;trademarks;trade secrets;contracts;territorial distribution
research_integrity|primary evidence;source dependence;replication;negative results;retractions;synthetic-data lineage
machine_learning|dataset rights;deduplication;train-test separation;model evaluation;quantization;rollback
delivery|packaging;installation;patching;certification;support;retirement and archival export
"""

INDUSTRY_DOMAINS = tuple((name, tuple(headers.split(";")))
                         for line in _HEADERS.strip().splitlines()
                         for name, headers in [line.split("|", 1)])

ALMANAC_SECTIONS = ("Source evidence", "Machine findings", "Prototype lessons",
                   "Product lessons", "Contradictions", "Rights")
