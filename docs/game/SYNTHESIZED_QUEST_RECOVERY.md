# Recovered constraint-to-quest execution

The synthesized-quest command is distinct from the existing authored
chapter campaign commands. It connects B028 objective runtime, B030
mechanic composition and B037 synthesis in one strict operator workflow.
A bounded explicit directed world and NPC map, content/reward policy and
mechanic registry are validated before synthesis. Generated objectives
must have traversable routes in sequence. Movement is edge-gated,
NPC conversations are active-objective-gated and reward completion is
location-gated. Abandonment has actual terminal effects. Local save
restore independently reconstructs the source plan and the full action
log, then compares the original objective runtime and reward ledger.

The separate GameForge command runs all seven declared planning stages,
verifies artifact bytes against the manifest and repeats the conductor.
Its region graph uses the same undirected link interpretation as the
original WorldPlan validator. The adapter then runs the actual quest
journey. Declarative conductor assets are not native engine artifacts.
The new commands operate on explicit local input and emit JSON to
stdout without overwriting files. Qualification reconstructs logs in
process, not a full device or process restart. Source, native, security,
device and release holds remain.
