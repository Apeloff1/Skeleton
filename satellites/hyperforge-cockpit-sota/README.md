# HyperForge Cockpit game-core satellite

Source: `Apeloff1/hyperforge-cockpit-sota` (post-consolidation repo, 2026-08-21 source head).

This satellite intentionally extracts the reusable `src/game` simulation core rather than copying the generated PWA shell, branding/install imagery, package lock, or unrelated app scaffolding.

Included systems:
- fixed-step Three.js flight simulation and camera loop
- glider/craft physics
- procedural terrain and world generation
- deterministic noise helpers
- courses, rings, thermals, collision and progression
- keyboard/touch/gamepad input
- local save, best-time and ghost recording
- audio synthesis and VFX
- Zustand HUD/game state

The source files under `src/game/` retain their upstream Git blob identities where unchanged. This directory is namespaced so it does not alter Skeleton's primary Python/React runtime dependency graph.

## Isolated typecheck

```bash
npm install
npm run typecheck
```
