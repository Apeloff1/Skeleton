# Original browser and Godot game output — 2026-10-13

**DX-37–42: Real generated games into real Studio review custody**

Jeeves is now wired to the **existing** original-game compiler, playable
HTML renderer, Python winning-gameplay replay, native Godot 4 source renderer,
and original GameWorkspace review mechanism. This is productive game-source
generation, not merely indexing or planning.

- \`studio.production.release_plan\` creates the original 1–3 level game
  within bounded dimensions, demonstrates a winning trace in the canonical
  simulation, renders the offline browser game and all Godot project source.
  It returns the content hashes, proof digest, exact native package manifest,
  and current source versions for every member.
- \`studio.production.release_stage\` re-generates against the reviewed
  original intent, requires an exact matching plan digest, and calls the
  canonical GameWorkspace proposal method to stage the entire package for
  individual human review. Stage does not silently publish any game file.
- GameWorkspace permits original \`.godot\` project-source files in its
  existing strictly reviewed UTF-8 extension allow-list so the canonical
  native exporter can materialize without renaming the file incorrectly.

\`\`\`python
args = {
  "project": "my_original_game",
  "release_id": "demo_01",
  "intent": {
    "title": "Original Game", "subtitle": "An original playable adventure",
    "seed": 12027, "width": 19, "height": 15,
    "levels": 2, "theme": "forest"
  },
}
plan = runtime.invoke("studio.production.release_plan", args,
                      authorized=True)["result"]
staged = runtime.invoke("studio.production.release_stage", {
  **args, "expected_plan_digest": plan["digest"],
  "reason": "Review original browser and Godot output for intended project"
}, authorized=True)["result"]
\`\`\`

This process creates source for an **offline browser game** and **Godot 4
project**, including geometry/world JSON, authoritative gameplay action
proof and tile editor, under \`game/releases/<release_id>/\` once every file
has been separately human committed.

**Important scope:** The Python game proof is executed by the compiler as
part of *game generation*, but no repository test suite was run in this
workpass. Godot binaries are not built or executed, hardware compatibility
is not asserted, and no external game publication is performed.
