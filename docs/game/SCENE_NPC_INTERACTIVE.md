# Interactive NPC scene play and recovery

The interactive adapter is a real local player interface for the authored
NPC scene runtime. It reads bounded commands from stdin, emits JSON-line
prompts and replay-verifiable checkpoints to stdout, and never reads or
writes arbitrary local paths.

    python -m skeleton scene-npc-play --demo
    python -m skeleton scene-npc-play --source-json '...'
    python -m skeleton scene-npc-play --resume-json '...' --source-digest '<sha256>'

Supported commands are talk NPC OFFER, collect PICKUP, travel EXIT,
finish ENDING, or an equivalent strict JSON object. Each prompt includes
the current scene, available authored actions, reputation and earned flags.
The engine rejects unearned choices, illegal movement, replay mismatches and
forged saves. Source digests may be pinned before accepting a resume.

An EOF or three consecutive invalid commands emits the last verified
checkpoint and returns a nonzero result. Periodic checkpoints are bounded
to intervals of 1 through 64 accepted actions. Terminal output includes a
full verified checkpoint and the final ending. An application may persist
the checkpoint in its own authorized save storage and resume later.

The input is bounded to 128 KiB per line. This offline adapter never calls
a model provider, opens a network socket or evaluates authored code. A
checksum is not a signature; the host must authenticate sources and
authorize the player independently.
