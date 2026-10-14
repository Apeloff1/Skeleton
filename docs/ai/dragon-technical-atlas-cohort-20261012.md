# Dragon advanced source atlas — production cohort expansion

**Editorial timestamp:** 2026-10-12 UTC. **Status:** Candidate-only registry; source contents not automatically downloaded or approved.

## Delivered expansion

The curated Dragon technical-source registry now consists of **55 original entries + 193 new entries = 248 research candidates**. The additional 193 entries span **169 URL hostnames**, and the combined atlas covers **22 research families**. This is a *source-metadata* milestone, not evidence that each page is currently reachable, independently authoritative, legal for training, or representative of all gaming knowledge.

New cohort source counts by research family:

| Family | Added candidates | Example research objective |
| --- | ---: | --- |
| Engine/editor | 21 | GameMaker, Construct, GDevelop, Godot editor plugins |
| Coding/compiler | 23 | JavaScript, TypeScript, GCC-adjacent diagnostics, LLDB, build systems |
| Console/homebrew | 14 | Dreamcast/KallistiOS, Sega SGDK/SMS, PS2/PSP, N64/libdragon |
| Assets and art | 12 | Blender, Krita, Aseprite, Tiled, LDtk, USD |
| Graphics | 11 | Direct3D, Metal, SPIR-V, KTX, materials, geometry optimization |
| AI and evaluation | 10 | ONNX, Gymnasium, PettingZoo, agent evaluation |
| Multiplayer/networking | 9 | ENet, Nakama, matchmaking, replication |
| Runtime/input | 8 | SDL3, GLFW, WebAssembly, OpenXR, gamepads |
| Audio/music | 8 | FMOD Studio, Wwise, DSP, codecs, sound pipelines |
| Physics/simulation | 8 | Box2D, Jolt, Rapier, Bullet, constraints |
| Security | 8 | OWASP, supply chain, secure build, static analysis |
| Performance | 8 | RenderDoc, Tracy, Perfetto, GPU profiling |
| Formats | 8 | SPDX, JSON Schema, Protocol Buffers, PNG, WebVTT |
| QA/validation | 7 | Pytest, Hypothesis, Playwright, fuzzing |
| Research | 6 | Graphics, HCI, AI and game scholarship |
| Shipping/platform policy | 6 | Itch, Epic, Xbox, Nintendo, store policies |
| Production | 6 | Reproducible builds, versioning, collaborative pipelines |
| Animation | 5 | Rigging, skeletal animation, timeline editors |
| Narrative | 5 | Ink, Yarn Spinner, Twine, dialogue systems |
| Localization | 5 | Unicode/ICU/CLDR, gettext, translation |
| Rights/legal references | 5 | Licensing, copyright and EU legal references |

## How the system uses the new cohort

1. `dragon_technical_source_seeds.py` keeps the original 55 entries in `BASE_SEEDS` and appends `ADDITIONAL_SEEDS` from `dragon_technical_source_cohort_20261012.py`. Original canonical URL/source identities are not rewritten.
2. `dragon_technical_source_atlas.py` adds review-cadence defaults for physics, networking, asset pipelines, animation, narrative, QA, performance, localization, formats, and studio production. All inputs must remain canonical public HTTPS URL metadata; unknown availability, unknown rights and training disabled are preserved.
3. `DragonTechnicalSources.import_catalog` preserves the owner-scoped metadata journal and existing stage-zero policy queue, adding only previously absent candidates. Records include digest-chained editorial timestamps and parent revisions; repeated imports of unchanged candidates are idempotent.
4. Additional task-adjacency terms connect NPC, RPG, maze, editor, console porting, multiplayer, shaders, localization, accessibility, and compiler errors to appropriate research categories without claiming the information is verified.
5. `dragon_nest_source_feed.py` now caps its source-portfolio request to the supported 100-result budget even when the registry contains more than 100 entries. Hatchlings still receive bounded, idle-only proposals, not automatic fetches.

## Operator dry-run sequence

```sh
python -m skeleton.ai.game_builder.dragon_technical_source_cli census \
  --database /approved/studio.sqlite --owner studio --trusted-local-operator

python -m skeleton.ai.game_builder.dragon_technical_source_cli import \
  --database /approved/studio.sqlite --owner studio --trusted-local-operator \
  --recorded-at "$(date -u +%s)"

python -m skeleton.ai.game_builder.dragon_technical_source_cli plan \
  --database /approved/studio.sqlite --owner studio --trusted-local-operator \
  --query "homebrew dreamcast console porting" --limit 30
```

Import is a trusted, local, user-scoped metadata operation, not a network crawl. If the original 55 were previously imported, the new 193 are *eligible to be introduced* on the next explicit trusted import; they are not assumed already present in a running database.

## Review and custody restrictions

- The listed URLs are discovery leads. Individual response status, redirects, present-day authority, source independence, reproduction rights, robots exclusions and available licensing must still be checked before network use.
- Proprietary console SDKs and platform-specific programs are included only as **public documentation/application-entry leads**. Restricted developer materials require platform-holder approval; this atlas does not grant it.
- A homebrew tutorial does not authorize use of proprietary firmware, copied games, protected assets, console security bypasses, or unauthorized hardware key extraction.
- Videos and online articles require media-specific permissions. The existing Wiki/HOAG adversarial review remains responsible for independent factual verification. Neither catalogue inclusion nor popularity constitutes weight-promotion evidence.
- Editorial timestamps represent the time a candidate record is created or changed, not a remote content-revision timestamp. Change history improvement notes remain parenthesized and digest-bound.

## Quantifiable acceptance

- 193 added metadata candidates, 169 hostnames represented by the cohort, 248 candidates overall, 22 subject families.
- New regression module asserts size, no duplicate source identity, legacy seed stability, minimum console and editor coverage, 9 task-specific retrieval scenarios, operator authorization and tenant isolation, and the idempotent policy-stage queue.
- The dedicated source-expansion test module is included in the Dragon Python verification workflow. Its actual pass/fail status must be obtained from exact-head execution; a CodeQL-only run does not certify these tests.

## Next substantive acquisition pass

Move beyond breadth by batching operator-approved *availability checks* (DNS and robots), source-specific rights review, content-version hashing, task-weighted claims, cross-source fact comparison and sandbox measurements. Promote no source to permanent AI weights without documented improvement on independent original game-building benchmarks.
