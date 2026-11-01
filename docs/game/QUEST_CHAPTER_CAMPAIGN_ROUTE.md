# Playable Chapter Campaign Route Planner

`python -m skeleton quest-campaign-route --demo` plans the authored Lantern
Harbor chapters using the real quest engine. A checkpoint can be supplied
with `--session-json`; use `--max-states` and `--max-depth` to bound each
chapter's route search. The result is deterministic and includes exact
source/state digests, earned chapter flags, action witnesses and a portable
campaign checksum. `--verify-json` recomputes the route, replays the campaign
and checks export/import against the authored source.

A `found` route is a replayed victory. `inconclusive` means the search or
campaign action budget was exhausted and is never treated as proof of
unreachability. A completed but blocked campaign cannot be resumed. Saved
games are not silently migrated after source edits. Checksums detect accidental
corruption, not source authenticity or permission to play untrusted packages.
