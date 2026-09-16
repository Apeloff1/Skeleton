# Build augmentation note — B001 repository intelligence spine

- **Batch IDs:** B001, B006, B081
- **Area:** repository layout, build intelligence, agent handoff, dependency/security visibility
- **Author/agent:** ChatGPT
- **Intent:** Replace ad-hoc repository discovery with a fast machine-readable index, force build-affecting work to leave useful notes, and expose structural gaps that can feed later SOTA game-creation batches.

## What changed

Added a stdlib-only repository intelligence scanner driven by the Git index; subsystem/build contracts; a structural SOTA game-creation capability envelope; a dependency-aware 100-batch execution graph; and a mandatory augmentation-note format. The scanner will emit a full tracked-file index, subsystem build map, capability gaps, security/quality findings, and a concise human notes page under `.cache/repo-intel/`.

The scanner uses Git blob metadata for clean files and only hashes unstaged working-tree files. This deliberately avoids repeatedly reading the whole repository during routine agent/build startup.

## Validation evidence

Configuration validation is designed to enforce exactly 100 unique batch IDs, unique subsystem IDs, unique capability IDs, and presence of the build/security/quality/gameplay/AI work lanes. The CI workflow in this change will run the same checks on every relevant pull request.

## Security impact

The existing repository already tracks Dependabot configuration for GitHub Actions, root/backend Python, frontend npm, and root/backend/frontend Docker ecosystems. Existing workflow surfaces also include CodeQL, dependency review, dependency security, secret scanning and gitleaks configuration. The repo-intelligence security report records whether these controls remain present and CI will optionally enrich notes with live Dependabot alert data when the workflow token is authorized.

A significant repository-performance/supply-chain review point is the tracked `backend/godot` binary (roughly 103 MB in the current tree). This batch intentionally does not remove it; B006/B091 should determine whether it remains a justified first-class tracked runtime, moves to Git LFS/release assets, or becomes a verified fetch-on-demand toolchain input.

## Quality/performance impact

The index is content-addressed by Git blob state and avoids source parsing as the default discovery mechanism. That keeps it cheap enough to run at agent startup and CI while still exposing large tracked artifacts, subsystem file/byte counts, build entry points and structural feature gaps.

The main quality risk is structural detection false confidence. To prevent that, capability status is explicitly named `present-surface`, `partial-surface`, or `missing-surface`; a matching path is not treated as proof of functional or competitive readiness.

## Dependabot/dependency note

No runtime dependency is added by this batch. The scanner is Python 3.11 stdlib-only. Dependabot remains the dependency-update source; repo-intelligence consumes its configuration and CI-visible alert/PR metadata rather than replacing it.

## Noticeable gaps / next augmentation

Current high-leverage gaps include a proper physics integration surface, multiplayer/netcode, deterministic replay, large-world streaming, live preview, visual/semantic editing, 3D asset validation, generated-code sandboxing, and a reproducible concept-to-release benchmark. The 100-batch graph assigns these to independent lanes so work can proceed concurrently without collapsing into one giant refactor.

The current root layout also mixes core runtime, backend product code, gameforge, frontend, satellites, memory and extensive CI/tooling. The new subsystem map should be used before any physical directory moves; layout rework should follow measured import/build dependencies instead of renaming folders first.

## Build handoff

- [x] repo-intel scanner and configs added
- [x] 100 large batches mapped
- [x] security/quality and Dependabot integration contract defined
- [ ] CI execution on the branch/PR
- [ ] measure generated index and critical-path timings
- [ ] B006/B091 decision on the tracked Godot binary
