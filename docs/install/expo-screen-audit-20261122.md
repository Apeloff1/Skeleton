# Expo frontend screen audit (static, 2026-11-22)

Scope: every route file under `frontend/app/` (208 screens, excluding layouts and
`+html`). The audit is **static**. A script read each route file and the screen
module it imports, then flagged the patterns below. Nothing was clicked through.
These are heuristics that show where to look first, not verdicts.

Method: `fetch(`, `axios`, `apiClient`, `skeletonAPI`, `forgeOperator`, `useQuery`
or a literal `/api/` counts as **API-backed**. `ActivityIndicator`/`isLoading`/
`loading` counts as a **loading state**, and `catch (`/`isError`/`error` as an
**error state**. **a11y attrs** counts `accessibilityLabel`, `accessibilityRole`,
`accessibilityHint` and `aria-label`, and **pressables** counts
`TouchableOpacity`/`Pressable`/`Button`/`TouchableHighlight` elements.

## Summary

| Measure | Screens |
| --- | --- |
| API-backed | 128 / 208 |
| No loading state detected | 38 |
| No error handling detected | 24 |
| Pressables but no accessibility attributes | 74 |
| Mock/fake/sample markers present | 6 |
| Calls the canonical `POST /api/v1/game/build` | 0 |

## Findings on the main journey

1. **No Expo screen calls the canonical builder.** `/ai-game-generator`,
   `/create-mode`, `/studio` and `/gameforge-studio` use other endpoints, and
   no API call was detected in `/skeleton-studio`. The only single game-build executor
   (`skeleton.forge.game_builder.build_playable_game` behind
   `POST /api/v1/game/build`) has no Expo client. The native install therefore ships
   **Local Studio** (`skeleton/app/local_studio.py`), which covers prompt, live
   build, editor, playtest, export and settings against the canonical API, with
   pytest and Playwright/axe coverage.
2. **Seal custody.** `forgeOperator`/`OperatorScreen` asks the user to paste an
   HMAC seal, and `skeletonAPI` (default `:8010`) sends none, so sealed routes return
   401 from the Expo app unless a gateway adds the seal. Local Studio avoids this by
   keeping the seal on the server and giving the browser only a per-launch token.
3. **No dedicated onboarding, editor or playtest routes** were found by name. `/setup`
   is the closest to onboarding, but no API call was detected in it.
4. **Accessibility.** 74 screens have pressables with no accessibility
   attributes, including `/ai-game-generator` (3 pressables). WCAG 2.2 AA
   (4.1.2 Name, Role, Value; 2.5.8 Target Size) needs a per-screen pass.

## Recommended follow-ups (not done in this lane)

- Add an Expo `gameBuild` client that calls `POST /api/v1/game/build` through a
  server-side seal (BFF), and point `/ai-game-generator` and `/create-mode` at it.
- Make `accessibilityRole` and `accessibilityLabel` required on shared button
  primitives, then sweep the 74 flagged screens.
- Add loading and error states to the 38 and 24 flagged screens.
- Consolidate the overlapping studio routes (`/studio`, `/gameforge-studio`,
  `/skeleton-studio`, `/build-hub`, `/my-builds`).

## Per-screen table

| Route | Lines | API | Loading | Error | Pressables | a11y attrs | Mock markers |
| --- | ---: | :-: | :-: | :-: | ---: | ---: | ---: |
| `/(account)/account` | 40 | — | — | — | 2 | 2 | 0 |
| `/(account)/app/forge` | 21 | — | — | — | 2 | 0 | 0 |
| `/(account)/app` | 89 | yes | — | — | 1 | 6 | 0 |
| `/(account)/app/projects` | 47 | yes | — | — | 1 | 2 | 0 |
| `/(account)/app/settings` | 36 | — | — | — | 3 | 2 | 0 |
| `/achievements` | 135 | — | yes | yes | 0 | 0 | 0 |
| `/advanced` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/agent-memory` | 1133 | yes | yes | yes | 6 | 0 | 0 |
| `/agent-review` | 1231 | yes | yes | yes | 3 | 0 | 0 |
| `/agentCodex` | 891 | yes | yes | yes | 2 | 0 | 0 |
| `/agents` | 522 | yes | yes | yes | 7 | 0 | 0 |
| `/ai-chat` | 311 | — | yes | yes | 8 | 5 | 0 |
| `/ai-game-generator` | 683 | yes | yes | yes | 3 | 0 | 0 |
| `/ai-interactions` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/ai-models` | 675 | yes | yes | yes | 13 | 12 | 0 |
| `/ai-pipeline` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/ai-router` | 1177 | yes | yes | yes | 4 | 0 | 0 |
| `/ai-suggestions` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/anti-cheat` | 1181 | yes | yes | yes | 2 | 0 | 0 |
| `/apk-build` | 1138 | yes | yes | yes | 6 | 0 | 1 |
| `/apk-inspector` | 1205 | yes | yes | yes | 7 | 0 | 0 |
| `/asset-genesis` | 1528 | yes | yes | yes | 11 | 2 | 0 |
| `/assets` | 528 | yes | yes | yes | 6 | 0 | 0 |
| `/audit-routes` | 1533 | yes | yes | yes | 8 | 0 | 0 |
| `/bible` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/boot-log` | 850 | yes | — | yes | 6 | 0 | 0 |
| `/bugfix-library` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/build-hub` | 836 | yes | yes | yes | 7 | 2 | 0 |
| `/camera-director` | 567 | yes | yes | yes | 4 | 0 | 0 |
| `/canon-graph` | 1343 | yes | yes | yes | 11 | 1 | 0 |
| `/capabilities` | 1191 | yes | yes | yes | 3 | 0 | 0 |
| `/capability` | 782 | yes | — | yes | 6 | 0 | 0 |
| `/certificate` | 503 | — | yes | yes | 2 | 0 | 0 |
| `/challenges` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/champions` | 1170 | yes | yes | yes | 2 | 2 | 0 |
| `/class-week` | 1433 | yes | yes | yes | 13 | 6 | 0 |
| `/code-to-app` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/collab` | 530 | yes | yes | yes | 9 | 0 | 0 |
| `/collaboration` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/collections` | 1288 | yes | yes | yes | 8 | 2 | 0 |
| `/command-center` | 1583 | yes | yes | yes | 22 | 0 | 0 |
| `/compiler` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/compose-scene` | 939 | yes | yes | yes | 18 | 4 | 0 |
| `/construct-forge` | 1205 | yes | yes | yes | 18 | 0 | 0 |
| `/control-plane` | 298 | yes | yes | yes | 7 | 1 | 0 |
| `/cover-studio` | 332 | yes | yes | yes | 4 | 0 | 0 |
| `/crawler` | 254 | — | yes | yes | 16 | 14 | 0 |
| `/create-mode` | 1086 | yes | yes | yes | 6 | 1 | 0 |
| `/creator` | 1226 | yes | yes | yes | 5 | 3 | 0 |
| `/cs-academy` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/curriculum` | 558 | yes | yes | yes | 11 | 0 | 0 |
| `/daily-challenges` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/dashboard` | 1212 | yes | yes | yes | 6 | 0 | 0 |
| `/debugger` | 546 | yes | yes | yes | 11 | 0 | 0 |
| `/design-review` | 1265 | yes | yes | yes | 12 | 13 | 0 |
| `/design-spec` | 1134 | yes | yes | yes | 3 | 0 | 0 |
| `/discourse` | 1592 | yes | yes | yes | 6 | 0 | 0 |
| `/discover` | 1259 | yes | yes | yes | 7 | 2 | 0 |
| `/dragon-crawler-pilot` | 866 | — | yes | yes | 28 | 19 | 0 |
| `/dragon-delivery` | 1532 | yes | yes | yes | 10 | 9 | 0 |
| `/dragon-genomic-universe` | 1228 | yes | yes | yes | 19 | 8 | 0 |
| `/dragon-living-world` | 1567 | yes | yes | yes | 26 | 10 | 1 |
| `/dragon-maze-world` | 1149 | yes | yes | yes | 26 | 15 | 0 |
| `/dragon-native-production` | 1336 | yes | yes | yes | 25 | 28 | 0 |
| `/dragon-originals-forge` | 1347 | yes | yes | yes | 25 | 14 | 0 |
| `/dragon-research` | 2037 | yes | yes | yes | 18 | 20 | 0 |
| `/dragon-route-atlas` | 985 | yes | yes | yes | 20 | 8 | 0 |
| `/dragon-route-world` | 1041 | yes | yes | yes | 18 | 18 | 0 |
| `/dragon-world-codex` | 1454 | yes | yes | yes | 31 | 5 | 1 |
| `/ecosystem` | 186 | yes | yes | yes | 2 | 0 | 0 |
| `/edit-gamefiles` | 792 | yes | yes | yes | 4 | 0 | 0 |
| `/education` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/factions` | 1142 | yes | yes | yes | 5 | 0 | 0 |
| `/feature-flags` | 1318 | yes | yes | yes | 11 | 0 | 0 |
| `/flashcards` | 1022 | yes | yes | yes | 8 | 0 | 0 |
| `/forge-hub` | 920 | yes | yes | yes | 7 | 0 | 0 |
| `/forge-operator/beats` | 6 | — | — | — | 0 | 0 | 0 |
| `/forge-operator/cockpit` | 6 | — | — | — | 0 | 0 | 0 |
| `/forge-operator/compose-run` | 7 | — | — | — | 0 | 0 | 0 |
| `/forge-operator/eras` | 6 | — | — | — | 0 | 0 | 0 |
| `/forge-operator` | 21 | yes | — | — | 0 | 0 | 0 |
| `/forge-operator/intake` | 6 | — | — | — | 0 | 0 | 0 |
| `/forge-operator/plans` | 6 | — | — | — | 0 | 0 | 0 |
| `/forge-operator/recovery` | 6 | — | — | — | 0 | 0 | 0 |
| `/forge-operator/report` | 6 | — | — | — | 0 | 0 | 0 |
| `/forge-operator/walk` | 6 | — | — | — | 0 | 0 | 0 |
| `/forge` | 1482 | yes | yes | yes | 25 | 0 | 0 |
| `/frontier-navigation` | 504 | — | yes | yes | 4 | 10 | 1 |
| `/galaxy` | 815 | yes | yes | yes | 0 | 1 | 0 |
| `/gallery` | 1200 | yes | yes | yes | 9 | 5 | 0 |
| `/game-factory` | 129 | — | yes | yes | 0 | 0 | 0 |
| `/game-kb` | 1645 | yes | yes | yes | 20 | 10 | 0 |
| `/game-learning` | 927 | — | yes | yes | 70 | 44 | 0 |
| `/gameforge-studio` | 2165 | yes | yes | yes | 42 | 5 | 0 |
| `/gamification` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/gate/[stage]` | 9 | — | — | — | 0 | 0 | 0 |
| `/group-chat` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/groupchat` | 973 | yes | yes | yes | 3 | 0 | 0 |
| `/health` | 1700 | yes | — | yes | 4 | 0 | 0 |
| `/hub` | 2168 | yes | yes | yes | 31 | 24 | 0 |
| `/hybrid-pipeline` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/imagine` | 528 | yes | yes | yes | 6 | 0 | 0 |
| `/immersive-learning` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/immersive-tutor` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/` | 1870 | — | yes | yes | 6 | 13 | 0 |
| `/intelligence` | 459 | yes | yes | yes | 7 | 0 | 0 |
| `/interactive-quizzes` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/item-foundry` | 1455 | yes | yes | yes | 15 | 0 | 0 |
| `/jeeves-audio-test` | 832 | yes | yes | yes | 6 | 2 | 0 |
| `/jeeves-chat` | 436 | — | yes | yes | 49 | 22 | 0 |
| `/jeeves-eq` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/jeeves-hub` | 1179 | yes | yes | yes | 10 | 17 | 0 |
| `/jeeves-level` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/jeeves-workbench` | 127 | — | yes | yes | 0 | 2 | 0 |
| `/jeeves` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/journeys` | 1738 | yes | yes | yes | 12 | 16 | 0 |
| `/jury-room` | 1071 | yes | yes | yes | 5 | 0 | 0 |
| `/knowledge-databases` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/lang-recommend` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/language-academy` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/language-track` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/leaderboard` | 135 | — | yes | yes | 0 | 0 | 0 |
| `/learning-hub` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/liveops` | 1444 | yes | yes | yes | 4 | 0 | 0 |
| `/marketplace` | 1322 | yes | yes | yes | 11 | 2 | 0 |
| `/masterclass` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/math-academy-full` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/math-academy` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/media-studio` | 1195 | yes | yes | yes | 6 | 0 | 0 |
| `/mega-academy` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/menu` | 1228 | — | — | — | 6 | 4 | 0 |
| `/mirror-room` | 1098 | yes | yes | yes | 4 | 0 | 0 |
| `/mission-control` | 1734 | yes | yes | yes | 21 | 2 | 0 |
| `/multi-agent` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/multiplayer` | 1194 | yes | yes | yes | 13 | 0 | 0 |
| `/music` | 554 | yes | yes | yes | 7 | 0 | 0 |
| `/my-builds` | 1194 | yes | yes | yes | 16 | 5 | 0 |
| `/my-classes` | 1398 | yes | — | yes | 14 | 0 | 0 |
| `/notes` | 953 | yes | — | yes | 14 | 2 | 0 |
| `/offline-sync` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/operation` | 587 | yes | yes | yes | 3 | 0 | 0 |
| `/ops` | 1037 | yes | yes | yes | 1 | 0 | 0 |
| `/organism` | 389 | — | — | — | 0 | 0 | 0 |
| `/perf` | 585 | yes | yes | yes | 5 | 0 | 0 |
| `/physics-academy` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/physics-studio` | 348 | yes | yes | yes | 4 | 0 | 0 |
| `/playable` | 2982 | yes | yes | yes | 67 | 3 | 0 |
| `/playground` | 616 | yes | yes | yes | 11 | 0 | 0 |
| `/polish` | 346 | yes | yes | yes | 6 | 1 | 0 |
| `/pomodoro` | 924 | yes | — | yes | 7 | 5 | 0 |
| `/product` | 1245 | yes | — | yes | 7 | 20 | 0 |
| `/profile` | 904 | — | — | yes | 8 | 0 | 0 |
| `/progress` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/quality-control` | 346 | yes | yes | yes | 6 | 1 | 0 |
| `/reading-corner` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/readingLibrary` | 141 | — | yes | — | 1 | 0 | 0 |
| `/reference` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/refine` | 346 | yes | yes | yes | 6 | 1 | 0 |
| `/render-compare` | 283 | yes | yes | yes | 3 | 2 | 0 |
| `/rosetta-playground` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/rosetta` | 1234 | yes | yes | yes | 8 | 0 | 0 |
| `/safe-mode` | 1206 | yes | — | yes | 6 | 4 | 0 |
| `/safety` | 1146 | yes | yes | yes | 2 | 1 | 0 |
| `/scheduler` | 1041 | — | yes | yes | 14 | 3 | 0 |
| `/scorecard` | 1418 | yes | yes | yes | 12 | 1 | 0 |
| `/search` | 1075 | yes | yes | yes | 1 | 0 | 0 |
| `/settings/academy` | 208 | yes | — | — | 3 | 0 | 0 |
| `/settings/api` | 278 | yes | — | yes | 3 | 0 | 0 |
| `/settings/appearance` | 108 | — | — | — | 3 | 0 | 0 |
| `/settings/coding` | 164 | — | — | — | 4 | 0 | 0 |
| `/settings/feature-flags` | 354 | — | — | — | 6 | 3 | 0 |
| `/settings/galaxy-studio` | 432 | yes | — | yes | 9 | 0 | 0 |
| `/settings/haptics` | 134 | — | — | yes | 1 | 0 | 0 |
| `/settings` | 480 | yes | — | yes | 8 | 3 | 0 |
| `/settings/jeeves-voice` | 197 | — | yes | — | 6 | 0 | 0 |
| `/settings/jeeves` | 169 | yes | — | yes | 4 | 0 | 1 |
| `/settings/offline` | 296 | — | yes | yes | 5 | 0 | 0 |
| `/setup` | 62 | — | yes | yes | 1 | 3 | 0 |
| `/sign-in` | 200 | yes | yes | yes | 8 | 5 | 0 |
| `/skeleton-forge` | 832 | yes | yes | yes | 0 | 1 | 0 |
| `/skeleton-studio` | 316 | — | yes | yes | 0 | 0 | 0 |
| `/snowball` | 1894 | yes | yes | yes | 30 | 0 | 0 |
| `/sota-extended` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/sota` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/stages` | 1296 | yes | yes | yes | 9 | 0 | 0 |
| `/storage` | 1051 | yes | yes | yes | 2 | 0 | 0 |
| `/story-` | 1647 | yes | yes | yes | 0 | 15 | 0 |
| `/studio-prefs` | 1383 | yes | yes | yes | 5 | 0 | 0 |
| `/studio` | 1866 | yes | yes | yes | 19 | 9 | 0 |
| `/study-paths` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/swarm-planner` | 1179 | yes | yes | yes | 6 | 0 | 0 |
| `/systems-forge` | 1235 | yes | yes | yes | 15 | 4 | 0 |
| `/telemetry` | 957 | yes | yes | yes | 2 | 0 | 0 |
| `/thermal` | 124 | — | yes | yes | 0 | 0 | 0 |
| `/tools-arena` | 1277 | yes | yes | yes | 7 | 1 | 0 |
| `/tools-hub` | 995 | yes | yes | yes | 8 | 0 | 0 |
| `/top` | 1547 | yes | yes | yes | 23 | 2 | 0 |
| `/tournaments` | 1247 | yes | yes | yes | 7 | 2 | 0 |
| `/trophy-case` | 444 | yes | yes | yes | 2 | 0 | 0 |
| `/vault` | 344 | yes | yes | yes | 10 | 2 | 0 |
| `/welcome` | 569 | yes | — | yes | 2 | 0 | 0 |
| `/world-workbench` | 1457 | yes | yes | yes | 14 | 15 | 0 |
| `/worldforge-map` | 271 | yes | — | yes | 3 | 0 | 0 |
| `/worldforge-vault` | 1368 | yes | yes | yes | 14 | 2 | 0 |
| `/worldforge` | 2144 | yes | yes | yes | 44 | 1 | 0 |
| `/worlds-gallery` | 1133 | yes | yes | yes | 2 | 2 | 0 |
| `/zaibatsu` | 1081 | yes | yes | yes | 2 | 0 | 0 |
| `/zip-export` | 1357 | yes | yes | yes | 7 | 1 | 1 |
