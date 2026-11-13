# Typed Jeeves production plan from verified original world sources

\`world-plan\` derives a deterministic, bounded production DAG from the actual
authored scene graph, choice consequences, ending witnesses, reviewed asset
briefs, and causal timeline. No static 100-task catalog, fabricated LLM
reasoning, or automatic approvals are involved.

\`\`\`sh
python -m skeleton world-plan --store ./private-worlds propose --world-id harbor
python -m skeleton world-plan --store ./private-worlds inspect --world-id harbor
python -m skeleton world-plan --store ./private-worlds review \
  --world-id harbor --expected-digest <CURRENT_PLAN_DIGEST> \
  --task-id scene_opening --decision approved \
  --note 'Reviewed against source and playable witness.'
\`\`\`

Approve each prerequisite before its dependents. A blocked task holds the
handoff. The plan is source-digest leased; any world, asset or timeline change
invalidates it. After every task is explicitly approved and the playable bundle
is independently verified:

\`\`\`sh
python -m skeleton world-plan --store ./private-worlds compile \
  --world-id harbor --expected-digest <FINAL_PLAN_DIGEST>
\`\`\`

Compilation verifies the bundle's source and artifact hashes and recompiles
the actual engine-facing handoff. The output is a machine-readable ordered
task execution manifest, not proof that downstream work or device release has
already occurred. Human approval is provenance metadata, not an external
security attestation.

Focused tests:
\`\`\`sh
python -m pytest -q skeleton/testing/test_jeeves_world_plan.py
\`\`\`
