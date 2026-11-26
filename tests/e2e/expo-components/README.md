# Expo screen journeys (react-native-web harnesses)

These are browser journeys for Expo screens. They render the **real** screen
components, hooks, API clients and the app's `apiClient` transport with
`react-native-web`, and run them against the **real** backend routes and the
**real** Skeleton engine. They do not go through the full Metro bundle: a full
`expo export` needs more memory than the shared CI and dev boxes have, so each
harness mirrors its route file without the `expo-router`/`Screen` chrome.

| Harness | Route | Stack |
| --- | --- | --- |
| `new-game.harness.tsx` | `/new-game` | backend forge gateway (`routes/forge_gateway.py`) → engine `POST /api/v1/game/build` |

## Run locally

```bash
# 1. Engine and gateway share one seal secret (generated, never committed).
export GF_SEAL_SECRET="$(python -c 'import secrets;print(secrets.token_hex(32))')"
export SKELETON_GODOT_BIN=/path/to/Godot_v4.6-stable_linux.x86_64   # for playtest=require
python -m uvicorn skeleton.api.server:create_app --factory --port 8721 &
FORGE_GATEWAY_ENGINE_URL=http://127.0.0.1:8721 \
  python tests/e2e/expo-components/serve_gateway_e2e.py --static /tmp/ng-harness --port 8722 &

# 2. Bundle the harness. frontend/node_modules must come from a yarn install;
#    esbuild is installed with --no-save.
cd tests/e2e
npm install --no-save --no-package-lock --ignore-scripts @playwright/test@1.56.1 @axe-core/playwright@4.11.0 esbuild@0.25.12
(cd expo-components && node build-harness.mjs ../../../frontend/node_modules /tmp/ng-harness)

# 3. Run the journeys (desktop and Pixel 7, with axe WCAG 2.2 AA scans).
SKELETON_E2E_CHANNEL=chrome npx playwright test --config playwright.expo-components.config.mjs
```

`serve_gateway_e2e.py` uses the backend's development auth mode (no accounts),
which is local and CI only.
