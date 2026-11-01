# Original quest branch-impact matrix

This feature provides a deterministic **editor-facing choice consequence
preview** for currently executable original quest stages. It replays every
authored alternative on a bounded page of open stages and compares stage
completion, newly available stages, sandbox ending eligibility and unmet
narrative predicates.

The canonical quest engine currently awards a stage's reward independently
of which alternative was chosen. Therefore alternatives often have identical
mechanical outcome digests. The matrix reports that equivalence explicitly
and **does not** pretend that narrative prose, external witnesses, faction
systems or the native game runtime have identical consequences.

## CLI

Obtain a canonical source digest using the existing canon audit, then run:

    python -m scripts.studio_ecosystem_cli \
      --project studio_arena_fighting_glacial_fjord \
      --choice-impact --choice-impact-expected-source <source-sha256> \
      --quest-actions '[]' --choice-impact-limit 4

The Jeeves tool \`studio_authored_choice_impact\` accepts the same
\`project_id\`, \`actions\`, \`expected_source_digest\`, optional
\`expected_session_digest\`, \`offset\`, and \`limit\` values. Pagination is
limited to eight stages and requires an exact session lease on continuation.

## Contract and qualification

No source files or sessions are mutated. Each candidate is checked with the
canonical quest replay and progress calculation. Source and session leases,
bounded JSON, operator authorization, and strict schema checking are
fail-closed. The result is an authoring aid, not a game-play or release
certificate. Use existing original choice authoring and playable compilation
to persist and test a chosen revision; this matrix itself writes nothing.

Focused regression:

    pytest -q tests/test_studio_ecosystem_choice_impact_matrix.py
