# Dragon expanded modding source federation

## Scope and census

Expands the previous directory (460 records, 457 unique canonical locators) with 14,320 new seed records. The union is 14,702 distinct HTTPS locators after trailing-slash normalization and exclusion of 75 legacy overlaps. Construction-time source census: 10,370 Steam game-specific surfaces, 1,404 mod provider surfaces, 2,304 GitHub tool repository surfaces, and 242 specialist site records. Of these, 7,000 records are mod-related, including update and compatibility references, not solely individual mods. 610 candidate Steam identities, 384 tool repository candidates, 243 mod-provider community slugs, 530 distinct hosts. The registry contains 1,958 source categories across 60 families.

Every generated route and curated locator is a candidate. No claim is made that each app ID/title mapping, Nexus domain, Thunderstore slug, optional Workshop or repository section, or third-party route is current and accurate. The census counts locators, not harvested webpages, unique games, verified mods, licensed assets, or physical capacity. Existing directory and expanded catalogue are distinct browse surfaces with a deduplicated combined census. The route registry is source-controlled and bounded; additional source discovery remains a separate operational function.

## Public design leads

- Steam Community describes game hubs and their content sections: https://steamcommunity.com/communitycontent/
- Nexus Mods hosts an expansive game/mod directory: https://www.nexusmods.com/
- Example Nexus category listing: https://www.nexusmods.com/skyrimspecialedition/mods/categories
- Thunderstore game communities: https://thunderstore.io/communities/
- SteamDB moddable games: https://steamdb.info/charts/?tagid=1669

These public examples justify route families; they do not verify every candidate URL. The bundled app, GitHub project and community slugs are curated candidates, not downloaded provider exports.

## Runtime

The code generates the exact deduplicated locator index from versioned JSON inputs. Revision-bound pagination supports game IDs, providers, content kinds, families and full-text substring filters. Explicit import admits up to 128 application candidates into one durable metadata queue batch and preserves each Steam identity independently. Attach up to 256 selected neutral tool or community sources to an existing owner game; app-specific sources cannot be attached across a different identity. Reusing an operation key with different content is rejected by the queue. Shared Nexus domains across editions are kept unbound rather than guessing an alias. No crawler grants, automatic downloads or executable mod installation occur.

Source areas include mod release/version history, compatibility and dependency constraints, mod authoring SDKs, package formats, asset pipelines, community support, total conversions and modifications, rights changes, security notices and historical archives. Native/browser cockpit uses authenticated scope, explicit operator acknowledgement, external link confirmation and validated receipts.

## Acceptance

Focused regression commands (repository backend environment):
```
python -m pytest backend/tests/test_dragon_mod_seed_catalogue.py backend/tests/test_dragon_source_directory.py
```

Require exact-head test/CI, frontend typecheck and export, package data availability in installation, canonical mirror/security qualification, realistic queue pressure tests, provider identity and reachability checks with explicit permissions, and independent live/physical deployment evidence. Do not auto-fetch binary assets, execute mods, bypass authentication, or interpret any candidate route as a right to download or train. Review-only; no merge or release. Reconcile with #5441 and sibling #5440 plus parent storage work before shipment.
