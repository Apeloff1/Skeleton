# Repository intelligence and build map

This is the operating guide for the repository intelligence spine introduced in batch B001. The generated source of truth is `.cache/repo-intel/`; this document explains how the pieces fit together and what the current repository layout means operationally.

## Current build topology

### Root / packaging

The root owns Python packaging (`pyproject.toml`, requirements files, setup config), top-level Docker/deployment composition, Make targets and repository policy. The packaged `skeleton` project requires Python 3.11+ and exposes `skeleton` plus `skeleton-dev` command surfaces.

### `skeleton/` — core AI/runtime

The core package contains the engine primitives and higher-level orchestration described by the root README: kernel, memory/retrieval, intelligence, swarm, forge, resilience, observability, API/cortex, developer tooling, deployment, testing, organism/runtime state, pipelines, vault, agents/context/config/content. Treat this as canonical reusable runtime unless an integration explicitly belongs outside the package.

### `backend/` — product/service runtime

The backend contains service/application code, configuration/data/assets and a large `gameforge/` subtree. It also currently tracks a Godot engine binary as `backend/godot`; repo-intelligence flags it because its size is above the large-tracked-file threshold. Do not move/remove it casually: batch B006/B091 must first prove a better verified distribution path and compatible build flow.

### `backend/gameforge/` — game-creation platform surface

Gameforge contains multiple orchestration/product domains including agents, agent tools, API, architecture, assignments, boardroom/approval concepts, bootstrap, communication, database/datasets, deployment and economy-related surfaces. It is a major candidate for parallel SOTA game-creation work, but individual subdirectories are structural evidence only; each capability needs focused validation before readiness claims.

### `frontend/` — creator/client application

The frontend is an Expo/React Native application with app routes, components, features, hooks, assets and mobile build configuration. It has its own Dockerfile, linting/configuration and npm dependency surface. Frontend work should be mapped separately from backend/core Python build work even when a feature spans both.

### `scripts/` — repository/build control plane

The scripts directory already contains architecture/policy/provenance/security checks, quality gates, CI helpers, benchmarks and release tooling. `scripts/repo_intel.py` joins this existing control plane; it is not intended to create a second automation stack.

### `.github/` — automation/security/dependency control plane

The repository has a broad workflow surface including CI, CodeQL, dependency review/security, secret scanning, merge/readiness, branch lifecycle, provenance and other focused gates. Dependabot is configured across GitHub Actions, root/backend Python, frontend npm and root/backend/frontend Docker. Repository intelligence records whether these expected controls remain present and, in CI, attempts to add live Dependabot alert/PR notes when token permissions allow.

### `memory/`, `satellites/`, `tests/`, `docs/`

These surfaces hold persistent knowledge/handoff material, absorbed/integration systems, cross-system regressions and architecture/operating evidence. They are indexed independently so an agent can discover relevant context without globally scanning every source file.

## Fast index design

`python scripts/repo_intel.py snapshot` uses `git ls-files -s` as the primary content database. Clean files reuse the Git index blob SHA. Only unstaged tracked files are re-hashed from the working tree, and file sizes come from metadata. This keeps routine indexing proportional to repository metadata instead of repeatedly parsing source.

The snapshot emits:

- `index.json` — every tracked path with blob identity, size, subsystem and coarse role;
- `build-map.json` — subsystem summaries, entry points, hot paths and agent protocol;
- `gaps.json` — SOTA game-creation capability surfaces and structural evidence;
- `security-quality.json` — expected security controls, Dependabot ecosystem coverage and repository performance findings;
- `notes.md` — concise build-facing gaps/security/quality/handoff guidance;
- `dependabot-notes.md` in CI — live alert/PR summary when APIs are available.

Generated output is written to `.cache/repo-intel/`, which is already ignored by the repository. No generated index needs to be committed; the live Git state is the index source.

## 100-batch concurrent execution

`repo-intel/batches.json` defines exactly 100 large batches across ten lanes: build, creator, gameplay, AI, world, assets, network, quality, security and platform. Every batch has an ID, concurrency wave, declared dependencies and a concrete success condition.

Concurrency rules:

1. A batch may start when its declared dependencies are satisfied or when work is explicitly limited to an independent preparatory contract.
2. Multiple batches in the same wave may proceed concurrently if they do not write the same canonical file/contract.
3. Agents must add an augmentation note naming their batch IDs and remaining gaps.
4. Integration happens through contracts and deterministic tests/evals, not by merging competing duplicate implementations.
5. B100 is the final concept-to-release arena and depends on evidence from all major lanes; it is not a ceremonial milestone.

## Agent/model enforcement

The root `AGENTS.md` is the vendor-independent instruction contract. Tool-specific instruction files point back to it, but the actual enforcement is CI: build-affecting changes must carry an augmentation note under `repo-intel/notes/`. This means a model that ignores prompt instructions still cannot satisfy the repository gate without leaving the required build/security/quality/dependency handoff.

## Missing-feature semantics

The capability scanner intentionally reports only structural status:

- `present-surface` — enough configured path anchors were found;
- `partial-surface` — some structural evidence exists but configured evidence is incomplete;
- `missing-surface` — no configured structural anchor was found.

None of these means production readiness. Functional readiness requires tests/evals. Competitive/SOTA readiness requires versioned benchmark evidence covering the dimension being claimed: correctness, iteration latency, editability, determinism/replay, security, provenance, platform reach, performance, creator control or end-to-end release quality.

## Standard workflow

```bash
# Start every meaningful build session
make repo-intel

# inspect .cache/repo-intel/{notes.md,build-map.json,gaps.json,security-quality.json}
# claim relevant Bxxx IDs and implement focused work
# add/update repo-intel/notes/<date>-<batch-or-topic>.md

# validate handoff
make repo-intel-check
```

Use the generated map to decide whether a physical directory/layout move is justified. The goal is fast discoverability and minimal build/agent work first; renaming or relocating large trees is useful only when import/dependency/build evidence shows a real boundary improvement.
