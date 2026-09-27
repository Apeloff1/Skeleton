# complete

Refactored landing for Jeeves AGB workstreams on Apeloff1/Skeleton.

## Packages
- `cbm26-agent` — local consumer agent loop
- `cbm26-ai` — baseline language model + **full context stack integrated**
- `master-omega` — functional lattice core

## Integrated AI
```js
import { createIntegratedAI } from "./cbm26-ai/src/index.js";
const sys = await createIntegratedAI();
await sys.turn("The residual");
sys.snapshot();
```
