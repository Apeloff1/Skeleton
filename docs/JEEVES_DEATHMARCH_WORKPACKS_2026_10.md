# Jeeves deathmarch source workpacks — October 13, 2026

**Integration lane:** Existing canonical Jeeves appwide adapter, stacked PR #3738.
**Status:** Implementation pushed for review; no tests were requested or run in this workpass, and no production qualification is claimed.

## DX-09 — parallel source-owned workwaves

The existing \`ai.milestones\` planner derives tasks from eight canonical app construction authorities. \`ai.workwaves\` now constructs deterministic dependency-safe waves for bounded concurrency: prerequisites are placed in earlier waves and no owner is assigned two simultaneous tasks. Page cursors, plan and graph digests, source inventory snapshot, and explicit operator authority limits travel in every response. This is a scheduling **proposal** only and does not dispatch agents, assume worker leases, or mark milestones complete.

## DX-10 — real bounded implementation context

\`ai.workpack\` joins exact task IDs to the Jeeves graph node, canonical owner, acceptance evidence, dependencies, concrete source paths, SHA-256 hashes and UTF-8 bounded source excerpts taken from the scanned checkout. Context assembly honors the inventory's private-path and symlink fences. Oversized, missing, restricted and unlinked files are reported as incomplete context rather than imaginary source coverage. No direct model or provider calls occur.

## DX-11 — declared change blast radius

\`ai.change_frontier\` maps 1–32 real changed checkout paths backward through declared source/plane/service/workstream/volume dependencies. All source byte hashes are labeled separately from the metadata-only inventory digest. Unmapped files are **unknown impact**, not zero impact; the graph does not prove deployment behavior, model quality, or automatic permission.

## Jeeves API

\`\`\`python
from pathlib import Path
from skeleton.ai.game_builder.jeeves_appwide_fabric import AppwideInventory, JeevesAppwideRuntime

inventory = AppwideInventory(Path.cwd())
inventory.scan()
jeeves = JeevesAppwideRuntime(inventory)

waves = jeeves.invoke("ai.workwaves", {"max_parallel": 8, "limit": 12})["result"]
milestones = jeeves.invoke("ai.milestones.page", {"limit": 12})["result"]
tasks = [row["id"] for row in milestones["tasks"][:2]]
packet = jeeves.invoke("ai.workpack", {
    "task_ids": tasks, "source_bytes": 4096, "total_bytes": 32768
})["result"]
impact = jeeves.invoke("ai.change_frontier", {
    "paths": ["skeleton/ai/game_builder/jeeves_appwide_fabric.py"]
})["result"]
\`\`\`

Every invocation remains audited by \`JeevesAppwideRuntime\` with source inventory identity and action receipt. These read adapters intentionally do not run tests or perform any writes. Subsequent separately authorized implementation may use the existing \`source.propose\` and project adapters; actual source commit, CI, runtime smoke and sign-off remain separate governed steps.

## Scope and outstanding acceptance

- 3 new fully wired read adapters, no new runtime service, no new credential boundary and no new durable state owner.
- Regression, load, Windows/Linux behavior, protected review and source-content freshness remain **unverified** for this exact head.
- Upstream stacked dependencies must be consolidated before a mainline release; a draft feature PR is not a production milestone close.

## DX-12 — directory-to-file coverage

Canonical application service and AI owner paths are often directory declarations.
Workpack assembly now indexes real descendant source files, prefers familiar
entrypoints and shallow source modules, skips restricted and oversized sources,
and caps discovery to 256 inspected entries and 6 candidates per directory.
These are labeled *directory samples*, not falsely recorded as proof of ownership.

## DX-13 — change-to-milestone propagation

Impact reconnaissance now incorporates explicit directory ancestor scope and
maps affected graph nodes back to canonical milestone IDs. This surfaces the
acceptance tasks that must be considered when a source changes, even where the
owner declaration is a directory and not a per-file dependency.

**Evidence discipline:** No source is considered safe solely because it lacks a
graph edge. Readiness, runtime fidelity, cross-platform execution and CI still
require separate execution and review. The source context resolver provides
bounded, reproducible inputs for those later passes, not those passes themselves.
