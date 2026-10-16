# apps/jeeves

Repository tooling for the operator-facing tree. This JavaScript entrypoint is
separate from the full studio application. Install the application using the
[root first-install guide](../../README.md#first-install), then open `/product`
for Jeeves chat, Studio and Dragon capture.

```bash
node apps/jeeves/bins/jeeves.js status
```

```js
import { createApp } from "./src/index.js";
const app = await createApp();
await app.cycle("The residual");
```
