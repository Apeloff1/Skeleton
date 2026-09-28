# complete

Jeeves AGB landing tree on Apeloff1/Skeleton.

## Trees
- `cbm26-agent` — planner, WM, store, BM25, CLI
- `cbm26-ai` — transformer + n-gram + context 2026/2027
- `master-omega` — conductor that boots the agent and runs cycles

## Run
```bash
node complete/cbm26-agent/src/cli.js status
node complete/master-omega/bin/run-cycle.js "The residual"
```

```js
import { createIntegratedAI } from "./cbm26-ai/src/index.js";
import { createCBM26 } from "./cbm26-agent/src/index.js";
import { createSystem } from "./master-omega/src/index.js";
```
