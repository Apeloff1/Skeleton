# Corrective Control Segment

This segment is the quality-and-repair control plane that now spans the active generation surfaces in Skeleton. It did not replace the forge, plan, or pipeline layers; it sits around them and makes them self-checking, historically visible, and selectively self-correcting.

## What this segment is

The segment joins eight capabilities into one operating lane:

1. **Verification** — each surface can score its own output against a bounded contract.
2. **Persistence** — quality results and repair attempts are written into the organism ledger area.
3. **Targeting** — the system can identify the latest failure, recurring failures, and the most common repair targets.
4. **Bounded repair** — selected surfaces can attempt one or more conservative repair passes, then re-verify.
5. **Operator visibility** — runtime cards expose quality, failures, repairs, and recent activity.
6. **Operator diagnostics commands** — direct CLI/HTTP surfaces query the control plane without going through larger status cards.
7. **Policy enforcement** — dynamic thresholds and repair toggles gate all verification and repair.
8. **Multi-pass autonomy** — the system can attempt multiple repair passes, learn from history, and stop when improvement ceases.

## Surfaces covered now

| Surface | Verify | Persist quality | Persist repair | Multi-pass repair | Policy gate |
|---|---|---|---|---|---|
| Forge / Godot materialisation | Yes | Yes | Yes | Yes | Yes |
| Plan / command deck | Yes | Yes | Yes | Yes | Yes |
| Game logic pipeline | Yes | Yes | Yes | Yes | Yes |
| NPC pipeline | Yes | Yes | Yes | Yes | Yes |
| Dialogue tree path | Yes | Yes | Yes | Yes | Yes |

## Direct diagnostics surfaces

### CLI

- `python -m skeleton failures [--surface SURFACE]`
- `python -m skeleton repairs [--surface SURFACE]`
- `python -m skeleton activity [-n N] [--surface SURFACE] [--kind quality|repair]`
- `python -m skeleton recurring [--surface SURFACE]`
- `python -m skeleton repair-sessions [--surface SURFACE] [-n N]`
- `python -m skeleton repair-effectiveness [--surface SURFACE]`
- `python -m skeleton repair-telemetry [--surface SURFACE] [-n N]`
- `python -m skeleton repair-errors [--surface SURFACE]`
- `python -m skeleton learned-policy`
- `python -m skeleton repair-orchestrator`

### HTTP

- `GET /api/v1/cortex/failures?surface=`
- `GET /api/v1/cortex/repairs?surface=`
- `GET /api/v1/cortex/activity?surface=&kind=&limit=`
- `GET /api/v1/cortex/recurring?surface=`
- `GET /api/v1/cortex/repair-sessions?surface=&limit=`
- `GET /api/v1/cortex/repair-effectiveness?surface=`
- `GET /api/v1/cortex/repair-telemetry?surface=&limit=`
- `GET /api/v1/cortex/repair-errors?surface=`
- `GET /api/v1/cortex/learned-policy`
- `GET /api/v1/cortex/repair-orchestrator`

## Current state

The control segment is now active, integrated, directly queryable, and filterable by surface on all diagnostics paths. Policy enforcement gates every verification and repair. Multi-pass repair autonomy with learned policies and telemetry is now live.

The next natural segment is adaptive threshold adjustment or cross-surface policy inheritance.
