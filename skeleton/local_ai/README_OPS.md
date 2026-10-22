# Local AI Operational Stack

Fully functional. All gaps closed.

## Quick Start

```python
from skeleton.local_ai.full_stack import get_stack

stack = get_stack()
result = stack.run("Hello local AI", "valid_cas_string_16+")
print(result)
```

## CLI

```bash
python -m skeleton.local_ai.cli_ops --status
python -m skeleton.local_ai.cli_ops --generate "test" --cas valid_cas_string_16+
```

## Components

- OperationalEngine: generate + observe + helix
- ModelLoader: load + verify
- InferenceLoop: stepped generation
- SessionManager: multi-turn
- CacheLayer: digest cache
- MetricsCollector: counters/gauges
- SafetyFilter: bounds
- RecoveryManager: helix restore
- HealthMonitor: liveness
- GapFiller: all seams wired
- FullStack: single entry

SOTA. Extend-only. Complete.
