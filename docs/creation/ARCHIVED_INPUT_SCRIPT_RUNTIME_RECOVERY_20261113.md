# Historical control and sandbox recovery — B023 / B024

Source-preserving port from archival heads
`archive/pre-rebase-gf-b023-script-runtime-20261113-9e45335e`
and
`archive/pre-rebase-gf-b024-input-actions-20261113-80e57ea7`.

## Restored
- Cross-device semantic actions for keyboard, mouse, gamepad and touch
- Validated remaps, conflict detection, explicit per-context actions,
  deterministic input-frame button edges and analog axis values
- Legacy sandboxed ECS host with explicit capability grants, cumulative
  script call/step quotas, bounded diagnostics, quarantine, atomic reload
  and narrowly carried persistent state
- Canonical `skeleton/game/presentation` and `skeleton/ecs`
  source parity mirrors in `skeleton/ai/runtime`

## Hardening and real app integration

- Old `InputState.feed` accepted positive infinity despite its finite-number
  claim; now rejects infinite and NaN samples.
- Invalid remap rows were silently dropped; now fail as invalid and do not
  partially mutate existing profiles. Enforce bounded numbers of rows.
- Genre-specific action profile catalog covers all 36 existing GameForge
  questionnaire genres **and all 67 original Galaxy Studio genres** plus
  archive-era racing/sandbox where applicable, mapped to 8 input families
  and exposed through `GET /api/skeleton/controls/genres` and
  `GET /api/skeleton/controls/genres/{genre}`.
- Static introspection has no dynamic provider, command execution or
  filesystem writes. The existing `input_router` and `input_gameplay_bridge`
  remain authoritative for completed gameplay replays; this recovered input
  system is an additional creator-facing semantic control contract.

## Qualification

`python -m pytest -q skeleton/game/presentation/test_input_actions.py skeleton/game/presentation/test_genre_action_profiles.py skeleton/ecs/test_script_runtime.py skeleton/ai/runtime/input/test_input_actions.py skeleton/ai/runtime/ecs/test_script_runtime.py backend/tests/test_gameforge_control_profiles.py`.

Run full security, backend, architecture, mirror, E2E and device input qualification
before claiming installed game playability; static profile availability
does not imply actual native physical controllers were tested.
