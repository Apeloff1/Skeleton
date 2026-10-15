# Skeleton frontend

Expo/React Native web application for the product hub, Jeeves chat, Dragon crawler
and game studio. Routes live in `app/`; stateful workspaces live in `features/`.

## First install

Use the [root first-install instructions](../README.md#first-install). The production
Compose profile builds Expo once and serves it through Nginx. Open `/setup` to inspect
readiness and `/product` to navigate the app. The frontend never owns provider keys
or loads backend model weights.

## Host development

Use Node 24 and Yarn, matching the pinned [Dockerfile](Dockerfile). From this directory:

```bash
yarn install --frozen-lockfile
yarn start
```

Run the canonical backend/engine/Mongo services first. `python -m skeleton app up --hot`
from the repository root selects the existing hot-reload profile instead.

```bash
yarn lint
yarn export:web
```

Public endpoints resolve through the existing API resolver. Compose derives default
browser URLs from published service ports at build time and in development. After
changing production `EXPO_PUBLIC_*` URLs, rebuild the frontend; restarting Nginx does
not rewrite an already exported JavaScript bundle. Never expose provider/API secrets
through public Expo variables.

## Application surfaces

- `/setup`: first-run readiness, useful before login or while a service is unavailable.
- `/product`: capability navigation; Studio links directly to `/game-learning`.
- `/jeeves-chat` and `/ai-chat`: existing canonical/governed chat workspaces.
- `/crawler`: bounded capture, source library, review and withdrawal.
- `/game-learning`: editors, observation, training, review and exports.

Session checks share initial token loading and fence real account changes. Public
registration gives viewer access; create the owner through the documented bootstrap
for editing, capture and administration. Do not run the Expo starter reset command
on this application: it replaces application routes with a blank starter project.

See [studio operations](../docs/ai/STUDIO_CRAWLER_BUILDER_TRAINING.md) and
[AI/crawler setup](../docs/ai/FIRST_INSTALL_AI_AND_CRAWLER.md).
