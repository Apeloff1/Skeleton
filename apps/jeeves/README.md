# apps/jeeves

Operator face of the complete tree.

```bash
node apps/jeeves/bins/jeeves.js status
```

```js
import { createApp } from "./src/index.js";
const app = await createApp();
await app.cycle("The residual");
```
