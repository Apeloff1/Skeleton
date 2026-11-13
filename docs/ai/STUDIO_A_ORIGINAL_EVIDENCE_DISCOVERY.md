# Studio A — original evidence discovery

`world-evidence` connects a user's original mystery premise to a typed clue
catalog, explicit author review, durable source-leased edits, canonical player
choice replay and verified browser-playable handoff.

Propose:
`python -m skeleton world-evidence --store PRIVATE propose --world-id archive
--prompt "Find the hidden note" --clue-id note --title "A note"
--detail "A secret code" --unlock-choice pursue_goal`.

Use `inspect` for a digest, `edit --expected-digest DIGEST
--operation-json '{"action":"add","value":{...}}'` for a typed edit,
`approve --expected-digest DIGEST --note "Reviewed"` to authorize, then
`compile --expected-digest DIGEST` and `verify`. Each edit revokes approval.

A real player session created by `world-session` can be inspected with
`world-evidence --store PRIVATE player --world-id archive --slot SLOT`.
Uncollected clue titles and details are withheld. Clues unlock only from
actual legal choices; prerequisites are a bounded, acyclic DAG. A bounded
state-space search must produce a replay-verifiable ending witness containing
every required clue before compilation succeeds. Inconclusive search is not
treated as unreachable proof.

The handoff contains the canonical browser HTML, typed clue/ending witness,
and a deterministic receipt verified byte-for-byte. A digest is not a
signature. No independent release, device, rights, or performance certification
is implied. The source is `skeleton/jeeves/worlds/evidence.py`; regression
fixtures are `skeleton/testing/test_jeeves_world_evidence.py`.
