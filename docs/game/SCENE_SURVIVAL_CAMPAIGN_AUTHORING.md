## Authoring, route verification and interactive play

`scene-survival-campaign-author` supports new, verify, edit, preview, solve
and demo. The editor uses an exact source digest and revision lease. Every
edit is replayed from the original source; stale edits, duplicate stage IDs,
unattainable score targets and malformed nested survival maps are rejected.

`scene-survival-campaign-route` searches each stage through the existing
bounded canonical survival solver and returns a portable replay witness.
Search budget exhaustion means **inconclusive**, not impossible. The verify
command reruns the deterministic search and replays the winning actions.

`scene-survival-campaign-play` offers only legal canonical actions and emits
newline-delimited started, prompt, accepted, checkpoint and terminal events.
EOF, invalid input and turn-budget exhaustion emit the last verified
checkpoint without granting rewards. Resume pins the trusted source digest.
