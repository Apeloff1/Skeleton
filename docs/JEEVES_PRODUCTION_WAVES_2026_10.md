# Jeeves multi-engine original game production waves — 13 October 2026

**DX-31–35.** This work builds an *actual original game authoring pipeline*
around the already canonical GameWorkspace. Unlike file inventory or static
graph-only milestones, Jeeves can produce valid typed sources and register
durable reviewed proposals for multiple installed game engines.

1. **DX-31: \`studio.production.plan\`** turns 1–24 installed editor
   specifications into real, normalized, checksummed \`systems/*.json\`
   source candidates. Every previous file SHA and selected workspace revision
   is recorded; identical already-published sources are not re-proposed.
2. **DX-32: \`studio.production.stage\`** performs an exact-plan optimistic
   identity preflight, then stages actual operator-approved source proposals
   in the existing \`reviews/proposals\` custody directory using
   \`GameWorkspace.propose\`. It does **not** silently commit game source.
3. **DX-33: multi-engine scene authoring** supports typed scene templates
   via the existing \`advanced_level_scenes\` family, preserving scene seed,
   geometry layout and original scene ID.
4. **DX-34: approved-system identity** validates every scene against a
   *previously human-committed* matching system configuration. An unsigned
   editor template cannot unlock authored scene production.
5. **DX-35: active-project and CAS boundary** rejects wrong projects,
   expired source hashes, stale plan receipts, duplicates and unbounded
   requests before staging actual review proposals.

\`\`\`python
params = {
    "project": "my_original_game",
    "phase": "systems",
    "items": [
        {"editor": "rpg", "settings": {"quest_depth": 24}},
        {"editor": "maze", "settings": {"topology": "moving"}}
    ],
}
planned = runtime.invoke("studio.production.plan", params)["result"]
staged = runtime.invoke("studio.production.stage", {
    **params,
    "expected_plan_digest": planned["digest"],
    "reason": "Author original game systems with selected reviewed settings."
}, authorized=True)["result"]
# A person independently reviews each returned proposal_id and commits it
# through the existing authenticated GameWorkspace.commit boundary.
\`\`\`

The UI and API remain local-session scoped. Model-generated proposal text
never grants write permission. Neither a pending proposal nor a signed editor
proves runtime playability, production parity or release acceptance.

**Validation:** Tests intentionally not executed in this build-only pass.
