# Dragon Wave 17 — Real hypermedia API pagination through canonical crawler

The actual bounded Dragon CrawlRun worker now recognizes five JSON API
pagination families: JSON:API, HAL, OData, Hydra collection JSON, and
Collection+JSON. They are parsed as finite structured navigation, not
general JSON evidence, scripts, API clients or source-provided instructions.

Navigation is intentionally limited to top-level next/prev links (OData
only nextLink). Collection item URLs, JSON:API relationship URLs, HAL
_embedded links, OData delta links, Hydra context/last links and
Collection+JSON templates/queries remain inert. The typed parser checks
duplicate JSON keys, finite numbers, collection counts and maximum bytes.

Even where the owner allows several hosts, API-discovered pagination is
limited to the *exact source origin*. URL credential parameters, userinfo,
non-HTTP schemes and out-of-scope hosts fail closed. The canonical run_slice
subsequently performs the normal fresh consent, robots, DNS/socket admission,
redirect, host pacing and pre-I/O reservation before any follow-up request.

No API request method besides the existing canonical GET, authentication,
remote schema resolution, subscription, data publication or provider calls
are added. Every source-only API run verifies robots + initial page exactly
once, finite queue admission, no embedded actions and snapshot replay.

This code changes canonical source discovery behavior and implementation hash.
It is a draft, dependent on exact-head qualification; no device, distributed
lease, production Mongo or live Internet signoff is claimed.
