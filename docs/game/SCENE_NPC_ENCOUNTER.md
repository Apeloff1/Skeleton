# Offline NPC encounters over playable scenes

The NPC encounter runtime composes the canonical scene-travel engine with
author-defined NPC itineraries, one-time dialogue choices, earned reputation
and source-bound ending requirements. It is playable through the installed
Skeleton CLI without a model provider or network connection.

    python -m skeleton scene-npc demo
    python -m skeleton scene-npc simulate --source-json '...' --actions-json '[...]'
    python -m skeleton scene-npc resume --session-json '...' --actions-json '[...]'
    python -m skeleton scene-npc verify --session-json '...'
    python -m skeleton scene-npc export --session-json '...'
    python -m skeleton scene-npc import --bundle-json '...'

An authored NPC has an ID, ordered scene route and two to four offers. Its
location at a particular encounter tick is route[tick % route_length].
Only nonterminal authored scenes can contain NPCs. Each NPC can be answered
once per playthrough. An offer may award an original flag and a bounded
reputation change; it cannot directly mutate scene inventory or teleport the
player. The existing scene engine owns pickups, exits and terminal outcomes.

Endings require a terminal scene outcome and may additionally require earned
flags and minimum reputation. Unavailable NPCs, repeated choices, missing
flags, unsupported source schemas, excessive resources, forged journal entries
and altered save lineage fail closed. Replay rebuilds both the nested scene
save and NPC consequences. Portable exports include the full replay witness.

Source data is bounded to 128 KiB, sessions and bundles to 2 MiB, and the
encounter to 96 actions. Integrity digests are not signatures or evidence of
authorship. Host applications must separately authenticate content, authorize
players and isolate private saves. Tests cover victory and alternate endings,
split checkpoints, invalid source, forgery and canonical CLI dispatch.
