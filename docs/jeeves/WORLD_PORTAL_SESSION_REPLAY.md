# Reviewed multi-world browser session replay

The portal player now exposes **Export session JSON**. The offline browser
maintains a bounded 256-move trace, per-world flags and exact source digests.
Copy the exported JSON into an operator-reviewed `world-portals record-session`
request; browser content is untrusted until the server-side replay succeeds.

`python -m skeleton world-portals --store PRIVATE record-session --network-id journey --slot save1 --create --expected-network-digest DIGEST --session-json 'JSON'`

`python -m skeleton world-portals --store PRIVATE verify-session --network-id journey --slot save1`

The recorder checks the current approved network, all canonical world source
leases, the exact compiled HTML5 playable and its receipt, then replays every
choice and portal against current source. It rejects fabricated state, early
portal crossings, unearned choices, missing endings, duplicate/unknown fields,
stale revisions and unauthorized overwrite. Records are fsynced under sorted
exclusive network/world/slot locks. Revisions require an expected session
digest. Source changes invalidate prior replay proof; recompile and re-review
rather than accepting stale session state.

Jeeves `world.portals_session_preview` is strictly read-only and never
records or approves a browser session. A verified browser trace is not
hardware, device, payment, or release certification.

The player also offers **Import session JSON**. Its bounded local restoration
replays each step against the embedded reviewed source, rejects fabricated
flags, source revisions and impossible crossings, and never treats an imported
JSON object as a trusted receipt. Operator `record-session` and
`verify-session` remain the authoritative persisted verification path.
