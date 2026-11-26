# Interactive Control-Point Gameplay

`python -m skeleton arena-control-interactive demo` starts the original
Lantern Harbor capture match. It emits newline-delimited JSON with the
active player actor, legal canonical actions, score and replay digest.
Enter one JSON action per line, such as
`{"kind":"move","actor_id":"scout","direction":"east"}`.
Opposing teams use deterministic canonical tactical decisions, not input
supplied by the player. Capture scoring follows the actual legal positions.

`play --source-json ... --team wayfarers [--resume-json ...]
[--max-inputs 64]` runs an authored match or continues a verified checkpoint.
The last JSON line always contains a durable replay-verifiable checkpoint
on completion, EOF, input exhaustion or rejected player command. An invalid
action never advances the checkpoint; a rejected command exits nonzero.
A clean EOF is a resumable checkpoint, not a victory claim.

Input is limited to 8192 bytes per command and 64 player decisions per
invocation; the canonical arena also enforces its turn budget. JSON parsing
rejects duplicate keys, invalid actions, forged opponent control and
out-of-turn moves. The checkpoint can be exported through
`arena-control pack` and replay-verified through `arena-control verify`.

The interface is a deterministic CLI gameplay surface, not an assertion of
graphical UI, network multiplayer security or qualified device performance.
