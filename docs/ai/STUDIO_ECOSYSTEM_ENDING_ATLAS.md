# Source-bound authored ending atlas

The ending atlas is a deterministic **editor/assurance preview**, not a
completed playable-game or native ending certificate. It compares the complete
set of original authored endings from a canonical blueprint, showing which
stage/reward obligations the quest simulator can satisfy and which narrative
predicates remain outside its evidence model.

## Entry points

The operator obtains a source lease using the existing canon audit, then runs:

    python -m scripts.studio_ecosystem_cli \
      --project studio_arena_fighting_glacial_fjord \
      --ending-atlas --ending-atlas-expected-source <64-hex-source-digest> \
      --quest-actions '[]'

The typed Jeeves tool is \`studio_authored_ending_atlas\`, with request schema
\`skeleton.jeeves.studio_ending_atlas_request.v1\`. Its \`actions\` field is
a bounded original quest history. Optional \`expected_session_digest\` binds
the output to an exact previously replayed history.

Each ending includes its deterministic route, simulated session digest,
original stage choice opportunities, external predicate obligations, and
underlying single-ending plan digest. Pairwise overlap identifies shared
prerequisite stages and route-exclusive stages. The system **never** claims
that selecting a particular alternative causes an ending unless the authored
contract actually proves it. It never mints external witness, runtime, device,
or release evidence.

## Safety and continuity

Both source and session leases fail closed on mismatches. Invalid history,
contradictory canon, noncanonical JSON, oversized receipts, and unauthorized
operators fail without changing source. The atlas performs no filesystem
writes. Original narrative revisions and playable compilation continue
through the existing authoring/revision compiler; this atlas provides a
source-bound review gate before those edits are committed.

Focused regression:

    pytest -q tests/test_studio_ecosystem_ending_atlas.py

Exact-head repository checks and actual consumer gameplay qualification remain
required before release.
