# End-to-end tests

`app-foundation/` holds the Playwright browser cases for the app foundation
flows (F1–F5, see `docs/qa/APP_FOUNDATION_E2E_TEST_PLAN.md` from #4098). They
run in `.github/workflows/app-foundation-e2e.yml` against the docker-compose
stack, after the Tier 2 live API flow in
`frontend/scripts/test-app-foundation-flows.mjs`.

Playwright is installed into this folder at run time (`--no-save
--no-package-lock`), so no frontend dependency or lockfile changes are needed.

Local run against a running stack:

```bash
cd tests/e2e
npm install --no-save --no-package-lock @playwright/test@1.56.1
npx playwright install chromium
SKELETON_E2E_WEB_URL=http://localhost:3000 \
SKELETON_E2E_BASE_URL=http://localhost:8001 \
npx playwright test --config playwright.config.mjs
```

On CI failure the HTML report and traces are uploaded as the
`app-foundation-e2e-playwright` artifact.
