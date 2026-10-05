## Lint setup for the Expo frontend

This project ships a TypeScript-aware ESLint config (`.eslintrc.cjs`) but
**deliberately does not pin any lint packages in `package.json`**. This is
because `eslint-config-expo` was removed in Feb 2026 — it ran
`expo install --check` inside the EAS CI build pipeline and caused the
cloud Android builds to fail by overriding the pinned
`@react-native-async-storage/async-storage` version.

### How to run lint locally

```bash
cd /app/frontend
npx --yes \
  -p eslint@9 \
  -p @typescript-eslint/parser@8 \
  -p @typescript-eslint/eslint-plugin@8 \
  -p eslint-plugin-react-hooks@5 \
  eslint . --ext .ts,.tsx
```

Or, the most common one-liner used in CI / dev:

```bash
cd /app/frontend
npx -y eslint . --ext .ts,.tsx
```

`npx` fetches the peers on first run, caches them locally, and never
mutates `node_modules/.bin` — so the EAS build path stays clean.

### Autofix a single file

```bash
npx -y eslint app/hub.tsx --fix
```

### Continuous integration

If a CI runner needs to enforce lint, install the four peer packages there
(not in `package.json`):

```yaml
- run: npm i -g eslint@9 @typescript-eslint/parser@8 @typescript-eslint/eslint-plugin@8 eslint-plugin-react-hooks@5
- run: eslint . --ext .ts,.tsx
```

### What this config catches

* **`react-hooks/rules-of-hooks`** — wrong hook ordering / conditional hooks
* **`react-hooks/exhaustive-deps`** — missing useEffect/useCallback dependencies
* **`@typescript-eslint/no-unused-vars`** — unused locals (ignored if `_`-prefixed)
* **`eslint:recommended`** — common bugs (no-undef-init, no-irregular-whitespace, etc.)
* TypeScript-aware rules from `@typescript-eslint/recommended`

### What this config intentionally does **not** catch

* `no-explicit-any` — too many existing usages in the codebase; flipped off.
* Style rules — leave that to prettier / editor settings.

### Adding new rules

Edit `.eslintrc.cjs`. Avoid extending `eslint-config-expo` — it pulls in
the broken `expo install --check` hook (see top of file).
