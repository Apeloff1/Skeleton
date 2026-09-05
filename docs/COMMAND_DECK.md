# Command Deck Reference

The command deck is the unified operator surface for all Skeleton subsystems.

## Usage

```bash
python -m skeleton <command> <subcommand> [options]
```

## Commands

### policy — Policy versioning and control

| Command | Description |
|---------|-------------|
| `policy state` | Show current policy state |
| `policy save --comment "..."` | Save policy version |
| `policy rollback --version-id pv-xxx` | Rollback to version |
| `policy rollback-surface --surface forge` | Rollback surface |
| `policy versions` | List versions |
| `policy diff --a pv-1 --b pv-2` | Diff two versions |
| `policy lineage --version-id pv-xxx` | Show version lineage |
| `policy rollback-preview --version-id pv-xxx` | Preview rollback |

### verify — Verification commands

| Command | Description |
|---------|-------------|
| `verify forge --files f1.gd,f2.gd` | Verify forge output |
| `verify plan --plan plan.json` | Verify plan |
| `verify pipeline --tree tree.json` | Verify pipeline |
| `verify npc --spec spec.json` | Verify NPC spec |
| `verify dialogue --script script.json` | Verify dialogue script |

### repair — Repair commands

| Command | Description |
|---------|-------------|
| `repair orchestrate --surface forge --target-id main` | Orchestrate repair |
| `repair sessions --surface forge` | Show repair sessions |
| `repair effectiveness --surface forge` | Repair effectiveness |
| `repair telemetry --surface forge` | Repair telemetry |
| `repair errors --surface forge` | Repair errors |
| `repair learned` | Learned policy |
| `repair strategy --surface forge --reason low_score` | Strategy suggestion |

### lattice — Pixel lattice layouts

| Command | Description |
|---------|-------------|
| `lattice hud` | HUD layout |
| `lattice editor` | Editor layout |

### steering — Operator steering

| Command | Description |
|---------|-------------|
| `steering register --name mood_dark` | Register vector |
| `steering activate --name mood_dark --weight 0.8` | Activate vector |
| `steering deactivate --name mood_dark` | Deactivate vector |
| `steering composite` | Show composite vector |

### kv — KV cache

| Command | Description |
|---------|-------------|
| `kv stats` | Cache statistics |

### mouth — Mouth binding

| Command | Description |
|---------|-------------|
| `mouth feed --phoneme AA --ts 12345` | Feed phoneme |
| `mouth current` | Current mouth state |

### lora — LoRA adapter

| Command | Description |
|---------|-------------|
| `lora card` | LoRA status |

### decoder — GPU decoder

| Command | Description |
|---------|-------------|
| `decoder card` | Decoder status |

### master — Full system card

| Command | Description |
|---------|-------------|
| `master` | Show master card with all subsystems |

## HTTP API Routes

All commands are also available via HTTP:

- `GET /api/v1/cortex/policy-state`
- `POST /api/v1/cortex/policy-save`
- `POST /api/v1/cortex/policy-rollback`
- `GET /api/v1/cortex/policy-versions`
- `GET /api/v1/cortex/policy-diff`
- `POST /api/v1/cortex/verify-forge`
- `POST /api/v1/cortex/verify-plan`
- `POST /api/v1/cortex/repair-orchestrate`
- `GET /api/v1/cortex/repair-sessions`
- `GET /api/v1/cortex/lattice-hud`
- `POST /api/v1/cortex/steering-register`
- `GET /api/v1/cortex/kv-stats`
- `GET /api/v1/cortex/master-card`
