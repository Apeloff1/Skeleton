# Corrective Control Segment

This segment is the quality-and-repair control plane that now spans the active generation surfaces in Skeleton. It did not replace the forge, plan, or pipeline layers; it sits around them and makes them self-checking, historically visible, and selectively self-correcting.

## What this segment is

The segment joins six capabilities into one operating lane:

1. **Verification** — each surface can score its own output against a bounded contract.
2. **Persistence** — quality results and repair attempts are written into the organism ledger area.
3. **Targeting** — the system can identify the latest failure, recurring failures, and the most common repair targets.
4. **Bounded repair** — selected surfaces can attempt one conservative repair pass, then re-verify.
5. **Operator visibility** — runtime cards expose quality, failures, repairs, and recent activity.
6. **Operator diagnostics commands** — direct CLI/HTTP surfaces query the control plane without going through larger status cards.

## Surfaces covered now

| Surface | Verify | Persist quality | Persist repair | Optional repair |
|---|---|---|---|---|
| Forge / Godot materialisation | Yes | Yes | Yes | Yes |
| Plan / command deck | Yes | Yes | Yes | Yes |
| Game logic pipeline | Yes | Yes | Yes | Yes |
| NPC pipeline | Yes | Yes | Yes | Yes |
| Dialogue tree path | Yes | Yes | Yes | Yes |

## Direct diagnostics surfaces

### CLI

- `python -m skeleton failures [--surface SURFACE]`
- `python -m skeleton repairs [--surface SURFACE]`
- `python -m skeleton activity [-n N] [--surface SURFACE] [--kind quality|repair]`
- `python -m skeleton recurring [--surface SURFACE]`

### HTTP

- `GET /api/v1/cortex/failures?surface=`
- `GET /api/v1/cortex/repairs?surface=`
- `GET /api/v1/cortex/activity?surface=&kind=&limit=`
- `GET /api/v1/cortex/recurring?surface=`

## Current state

The control segment is now active, integrated, directly queryable, and filterable by surface on its diagnostics paths. The next natural segment is live threshold and repair-policy steering.
