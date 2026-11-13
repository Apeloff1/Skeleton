# Game Frontier heavyweight branch reconciliation — 2026-11-13

## Origin / immutable source custody

Historical branch: `feat/gf-n-jenkins-20261024`, exact historical head
`dada3f1b4c05761492b44ac93c8b036fa7dc9a59` (377 commits ahead,
578 behind main before reconciliation). Source material was independently
compared with exact main `d5275f6cff2b660ec6b41455fedb51567b113ad5`.

The full 207-path delta consists of 205 additions and two modified paths.
The draft integrates **202 exact historical new file blobs**, including
59 canonical Jeeves Game Frontier modules mirrored byte-for-byte in the
AI source tree, three canonical and three mirrored Forge modules,
58 game-system regression tests, 10 CLI/qualification utilities,
eight architectural runbooks and two frontend surfaces.

All 59 Jeeves mirror pairs were checked by Git blob SHA to match exactly;
the 202 original source blobs were retrieved from the immutable historical
Git tree, not regenerated, squashed into placeholder files, or rewritten.

## Non-destructive exceptions

Five paths are intentionally **not** copied over new main source:

- `BACKLOG.md` contains historical state and is not authoritative.
- `skeleton/ai/runtime/inference/local.py` has diverged; the newer local-only
  inference runtime is retained, and runtime compatibility needs independent
  regression/patch qualification rather than overwriting the model engine.
- `.github/workflows/game-frontier-native-smoke.yml` and
  `.github/workflows/game-frontier-validation.yml` are new historical
  workflows. These require independent workflow-input, token permissions,
  runner and action-pin security review before activating.
- `TODO.md` is an old root task list, not an engine capability.

The complete original branch history remains reachable as the first parent;
the exact main head is attached as second parent. Historical versions of
the five withheld paths remain addressable by historical SHA.

## Admission and release holds

**Draft/review-only** until focused validation demonstrates these newly
restored modules can import and run in the current Python/package layout.
Do not count source presence as playable device qualification.

Priority gates:
- Syntax/source mirrors, 58 recovered tests, Jeeves frontend navigation,
  deterministic scene/quest/physics, bounded file writes, Godot dispatch;
- Native GGUF/local-model admission: no remote fallback, Python version
  compatibility, CPU/GPU pressure, stream cancellation, resource caps;
- Source-tree generation and authoritative canonical AI index parity;
- Security, malware, secrets, dependency, workflow-input, artifact and
  repository hygiene checks; exact-head Backend Quality and Merge Readiness;
- Windows 11/WSL2, Android/Expo, Linux, Docker/Godot and device tests separate.

Do not auto-merge, release, or disable safety gates. Failed, queued, skipped,
cancelled, stale, ancestor or mock results do not prove release readiness.
