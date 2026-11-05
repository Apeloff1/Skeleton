# Local Jeeves durable operator terminal

The single-model operator session is an additive, reason-only control loop
for the first usable approved GGUF on a laptop. It launches the existing
source-verified isolated GGUF backend once, then accepts bounded JSON-lines
commands over stdin. It never downloads model bytes, escalates tool grants,
contacts a hosted provider, or converts generated model text into commands.

## Source-bound startup (requires an independently approved real model)

Run from a trusted operator terminal:

```bash
python -m skeleton.jeeves.agent.native_operator_session_cli \
  --model-root /private/models/approved \
  --state-dir /private/ai \
  --tenant local --subject operator \
  --approve-native --commands-stdin \
  --max-output-tokens 512 \
  --maximum-reserved-model-calls 64 \
  < /private/commands.jsonl
```

The paths above are placeholders. The actual source bundle, signed installer
receipt, user rights, source GGUF shard digests, native Python wheels,
local resource admission and protected SQLite identity must exist. No source
CI run qualifies these prerequisites on any physical device.

## Explicit commands

Each line is a standalone canonical-compatible UTF-8 JSON document,
with unique keys and a 32 KiB limit. There is no model-authored command
parser, shell, network endpoint or implicit tool authority.

```jsonl
{"schema":"jeeves.native_operator_command.v1","operation":"status"}
{"schema":"jeeves.native_operator_command.v1","operation":"start","run_id":"local_task_001","task":"Explain the approved original source context without inventing sources.","max_steps":8,"max_model_calls":8,"max_wall_seconds":180}
{"schema":"jeeves.native_operator_command.v1","operation":"inspect","run_id":"local_task_001","task":"Explain the approved original source context without inventing sources.","max_steps":8,"max_model_calls":8,"max_wall_seconds":180}
{"schema":"jeeves.native_operator_command.v1","operation":"replay","run_id":"local_task_001","task":"Explain the approved original source context without inventing sources.","max_steps":8,"max_model_calls":8,"max_wall_seconds":180}
{"schema":"jeeves.native_operator_command.v1","operation":"quit"}
```

`resume` is an explicit operator-only action, not a startup default. It uses
the exact original run ID, goal text, model, principal, budget and bound
working-memory scope. A terminal or uncertain native inference intent
cannot be regenerated. Each fresh run is a new canonical SQLite planner
checkpoint journal, native inference receipt chain, and sealed terminal
answer. Inspect and replay do not call GGUF again.

Resource controls are conservative: model-call reservations are charged
BEFORE execution and are not refunded merely because a native call timed
out. When the session reaches its command count, time or output ceiling,
or receives a native-effect error, it stops rather than guessing whether
an external effect completed.

All answers go only to the invoking operator-controlled stdout. Logs,
errors and diagnostics expose no private task or untrusted model response.
The terminal explicitly prevents automatic tool grants; signed read-only
source retrieval remains a separate gated path, and mutating tools are
not authorized in this mode.

## Evidence boundaries

Source-only CI exercises the complete command parser and run loop with a
scripted synthetic model that uses the actual protected SQLite/WAL
execution spine. This proves neither genuine GGUF accuracy nor tokenizer
identity on a laptop, memory-pressure headroom, native cancellation,
actual Windows 11/WSL2 installation, code signing, independent model rights
or consumer release readiness. Draft PR #4700 remains held until exact-head
mandatory gates and physical device checks are separately successful.
