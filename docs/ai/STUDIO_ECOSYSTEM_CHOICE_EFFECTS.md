# Source-authored choice-specific narrative consequences

The canonical quest engine accepts optional \`choice_effects\` on a stage:
a mapping from existing authored alternatives to bounded lists of simulation
predicates in the \`choice:<stage-id>:<lowercase_slug>\` namespace.

An ending can explicitly require one of these predicates. Replay earns it
**only** after the corresponding alternative was selected. The ending planner
chooses the required alternative, rejects incompatible preferences, refuses
conflicting ending requirements, and never rewrites completed history.
The canon audit recognizes authored predicates without treating them as
external witness or native-runtime evidence. The choice impact matrix and
ending atlas now expose real branch-specific sandbox consequences.

No new effect is allowed to claim unverified external evidence. Unknown
\`choice:\` predicates are rejected; malformed effect mappings, duplicate
tokens and cross-stage token injection fail closed. The source digest covers
all effect data, invalidating stale sessions. Existing original projects with
no \`choice_effects\` preserve their previous behavior without migration.

The existing original authoring revision pipeline remains the persistence
boundary. This contract does not certify real gameplay, consumer devices,
external witnesses or release. Focused regression:

    pytest -q tests/test_studio_ecosystem_choice_effects.py \
      tests/test_studio_ecosystem_quest.py \
      tests/test_studio_ecosystem_ending_plan.py
