# Jeeves natural-language game authoring bridge — October 2026

**DX-47–50: From typed prompt intent to real reviewed game editor sources.**

The existing \`game_prompt_router\` already understands installed engine,
NPC, narrative, cinematography, platform and many other original design axes.
Instead of creating another prompt parser or pretending an external language
model has generated code, this feature binds selected **installed system
editors** to \`JeevesProductionWave\`.

\`studio.production.prompt_plan\` returns selected actual editor configuration
source hashes and identifies non-editor work (lore, original dialogue, rights,
visual assets, external AI generation) as **unfulfilled rather than fabricated**.

\`studio.production.prompt_stage\` uses the exact original prompt receipt
and the canonical reviewed multi-file Studio proposal mechanism to stage
actual engine configuration sources, subject to explicit human approval.
Optional settings overrides must target only editors genuinely matched by
the original prompt. No generic file writes, unknown model calls or new
provider boundaries are introduced.

\`\`\`python
args = {
    "project": "my_original_game",
    "prompt": "Build a large moving maze, deep RPG quests and NPC society.",
    "editor_overrides": {
        "rpg": {"quest_depth": 32},
        "maze": {"topology": "moving"}
    }
}
plan = runtime.invoke(
    "studio.production.prompt_plan", args, authorized=True
)["result"]
staged = runtime.invoke(
    "studio.production.prompt_stage", {
        **args,
        "expected_prompt_plan_digest": plan["digest"],
        "reason": "Implement the reviewed RPG, maze and NPC original systems."
    }, authorized=True
)["result"]
\`\`\`

Unknown, ambiguous or purely story/art requests do not become dummy game
systems. Individual source changes still require canonical workspace human
diff review and commit. **No tests run** during this build-only pass.
