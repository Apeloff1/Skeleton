# Dragon global gaming source federation

## Scope

The archive must not be designed around one kind of live service. EVE Online is a useful reference for public game data, market/fitting tools and persistent worlds. World of Warcraft adds combat analysis, talent simulation, versioned client APIs and addons. GTA V adds roleplay and independent server frameworks, vehicle databases, open-world atlases and community resources. Fallout adds franchise history, record-level RPG mechanics, editor documentation, mods, load orders and plugin conflicts. Super Mario adds a multi-decade franchise, platformer level geometry, course creation, visual archaeology, speedruns and hardware/release variation. GTA VI is a prospective large-world design envelope, not a claim about its real final scale.

## Public research leads

- Warcraft Wiki API and fansites: https://warcraft.wiki.gg/wiki/World_of_Warcraft_API and https://warcraft.wiki.gg/wiki/Fansites
- Warcraft Logs: https://www.warcraftlogs.com/
- Cfx/FiveM scripting and resource documentation: https://docs.fivem.net/docs/scripting-reference/ and https://docs.fivem.net/docs/scripting-manual/introduction/introduction-to-resources/
- GTABase vehicles: https://www.gtabase.com/grand-theft-auto-v/vehicles/
- xEdit repository: https://github.com/TES5Edit/TES5Edit
- Community GECK: https://geckwiki.com/
- Fallout interactive maps: https://fallout-maps.com/
- Fallout modding reference: https://modding.wiki/en/fallout4
- Nintendo Mario history: https://mario.nintendo.com/history/
- Super Mario Wiki: https://www.mariowiki.com/Main_page
- TASVideos Super Mario World: https://tasvideos.org/GameResources/SNES/SuperMarioWorld
- Game Preservation Society catalogue: https://www.gamepres.org/en/dbsearch/
- International preservation resources: https://preserve.games/

The remaining registry entries are curated candidate locators based on known ecosystems. Their resolving URL, availability, terms, robots policy and capture rights require independent verification. The directory is not a populated archive.

## Implementation

- 1,689 distinct source classes across 52 families: concrete mechanics, records, formats, development resources, hardware, media, UGC, competitive analysis, history and region-specific archives.
- 460 curated locator records across 22 groups and 397 distinct host strings. Multi-game directory records deliberately do not represent fake games.
- Exact source directory revision, stable lead identity, group/domain/family/kind/text filters and query-bound pagination.
- Select up to 64 explicit leads, bind to an existing owner-scoped game or to a known franchise/game preset, and durably enqueue normalized catalogue observations. Existing queue idempotency rejects conflicting content for reused operation identities. No authorization to crawl, quote, promote, or train is granted.
- Six stress profiles with distinct examples and nominal design workloads. Do not confuse these design numbers with actual article counts, player counts, game sizes, measured capacity or successful physical qualification.
- Separate classified_sitemap adapter for authorized recurring feeds. Path segments and extensions supply unverified category hints; language is inferred only from a recognized leading locale segment. Existing generic sitemap identities remain unchanged. No sitemap index child or newly found URL is fetched unless separately authorized.
- Browser/native cockpit directory reader, source selection, external link confirmation, selected game or preset binding, durable receipt and import status through existing tools.

## Qualification and limits

Run the focused backend suite in the repository environment:
```
python -m pytest backend/tests/test_dragon_source_directory.py backend/tests/test_dragon_source_library.py
```

Run frontend typecheck/export and canonical source/parity and security qualification at the final head. Confirm actual source access and permission separately. Source-directory search is bounded in-memory over a static seed registry, not a worldwide crawl index, not an exhaustive list of websites, not a language detector, and not a binary downloader. Independent real storage capacity, live discovery and playback require deployed operator configuration. The new draft must be reconciled with concurrent changes to #5439 and the sibling audiovisual/dataset extension #5440. Do not merge or release without exact-head evidence.
