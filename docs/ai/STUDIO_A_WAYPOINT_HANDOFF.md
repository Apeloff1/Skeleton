# Verified waypoint-to-playable handoff

This Studio A vertical converts a source-leased hazard-aware route into an
**actual deterministic walk replay and health replay**. It does not mutate
authored quest choices, run native hardware, or claim release certification.

A new session can be compiled and published privately:

```sh
python -m scripts.studio_waypoint_handoff_cli \
  --project ORIGINAL_PROJECT --expected-source SHA256 \
  --new-session --waypoints '[]' --max-hazard-contacts 0 \
  --html-sha256 --publish /path/to/private-0700-directory
```

To resume, provide an authoritative prior walk receipt JSON with
`--session-json` and its `--expected-session` SHA-256. Restore requires
`--restore` and `--expected-session`, and replays the complete source.

The read-only Jeeves tool `studio_original_waypoint_handoff` accepts
`session_receipt`, `expected_source_digest`, `expected_session_digest`,
`waypoints`, and `max_hazard_contacts`. Operator authorization remains
out-of-band; the tool never writes files. The CLI alone can publish an
immutable, private receipt after canonical replay. A static CSP-restricted
HTML route summary is available for review. Both paths produce the same
typed `handoff` receipt for identical source and inputs.

Safety invariants: no symlink-following file reads, descriptor-anchored
private publication, no overwrite, duplicate JSON key rejection, finite
bounded payloads, source/session leases, exact collision and health replay,
no action after defeat, no implicit quest choice, and no claims about native
devices or external evidence. Run focused tests and exact-head CI before
promoting or merging this WIP branch.

## Offline editor round trip

Add `--editor-directory /path/to/private-0700-directory` to a successful
CLI compilation. Open the private HTML file, paste the source/session SHA-256
leases and canonical walk receipt, edit waypoint coordinates and hazard budget,
then copy the exported typed JSON into `--request-json`. The CLI verifies the
request's project and source against its explicit arguments, replays collision
and health, and optionally publishes the new immutable playable handoff. The
editor never runs game logic or sends data over a network. Its inline script
and CSS are CSP hash-bound; all dynamic output uses textarea values.
