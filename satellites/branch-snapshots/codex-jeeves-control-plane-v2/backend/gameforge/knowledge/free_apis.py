"""
gameforge/knowledge/free_apis.py — a large catalog of FREE, no-auth public APIs
that agents + Jeeves can query on demand to acquire knowledge as it is needed,
plus an async fetcher. Results can be folded back into Jeeves' trainable brain.
"""
from __future__ import annotations

import re
from typing import Any, Optional

# key -> {name, category, url (may contain {q}/{lat}/{lon}/{from}/{to}), note}
FREE_APIS: dict[str, dict] = {
    # ── Reference / knowledge ──
    "wikipedia":     {"name": "Wikipedia Summary", "category": "reference", "url": "https://en.wikipedia.org/api/rest_v1/page/summary/{q}", "note": "topic summary"},
    "wikidata":      {"name": "Wikidata Search", "category": "reference", "url": "https://www.wikidata.org/w/api.php?action=wbsearchentities&search={q}&language=en&format=json", "note": "entity search"},
    "dictionary":    {"name": "Free Dictionary", "category": "language", "url": "https://api.dictionaryapi.dev/api/v2/entries/en/{q}", "note": "word definitions"},
    "datamuse":      {"name": "Datamuse Words", "category": "language", "url": "https://api.datamuse.com/words?ml={q}", "note": "synonyms/related words"},
    "numbers":       {"name": "Numbers API", "category": "reference", "url": "http://numbersapi.com/{q}", "note": "facts about a number"},
    # ── Dev / research ──
    "arxiv":         {"name": "arXiv", "category": "research", "url": "http://export.arxiv.org/api/query?search_query=all:{q}&max_results=3", "note": "academic papers (xml)"},
    "hackernews":    {"name": "Hacker News", "category": "dev", "url": "https://hn.algolia.com/api/v1/search?query={q}", "note": "tech discussion"},
    "github":        {"name": "GitHub Repo Search", "category": "dev", "url": "https://api.github.com/search/repositories?q={q}&per_page=5", "note": "open-source repos"},
    "openlibrary":   {"name": "Open Library", "category": "reference", "url": "https://openlibrary.org/search.json?q={q}&limit=3", "note": "books"},
    "spaceflight":   {"name": "Spaceflight News", "category": "science", "url": "https://api.spaceflightnewsapi.net/v4/articles?limit=3&search={q}", "note": "space news"},
    # ── Geo / world ──
    "countries":     {"name": "REST Countries", "category": "geo", "url": "https://restcountries.com/v3.1/name/{q}?fields=name,capital,population,region,currencies,languages", "note": "country data"},
    "geocode":       {"name": "Open-Meteo Geocode", "category": "geo", "url": "https://geocoding-api.open-meteo.com/v1/search?name={q}&count=3", "note": "place -> lat/lon"},
    "weather":       {"name": "Open-Meteo Weather", "category": "geo", "url": "https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true", "note": "needs lat/lon"},
    "nominatim":     {"name": "OSM Nominatim", "category": "geo", "url": "https://nominatim.openstreetmap.org/search?q={q}&format=json&limit=3", "note": "geocoding"},
    "sunrise":       {"name": "Sunrise/Sunset", "category": "geo", "url": "https://api.sunrise-sunset.org/json?lat={lat}&lng={lon}", "note": "needs lat/lon"},
    "iss":           {"name": "ISS Location", "category": "science", "url": "http://api.open-notify.org/iss-now.json", "note": "live ISS position"},
    "universities":  {"name": "Universities", "category": "reference", "url": "http://universities.hipolabs.com/search?name={q}", "note": "universities"},
    "zippopotam":    {"name": "Zip Codes (US)", "category": "geo", "url": "https://api.zippopotam.us/us/{q}", "note": "US zip lookup"},
    # ── Finance ──
    "coingecko":     {"name": "CoinGecko Price", "category": "finance", "url": "https://api.coingecko.com/api/v3/simple/price?ids={q}&vs_currencies=usd", "note": "crypto price"},
    "frankfurter":   {"name": "Frankfurter FX", "category": "finance", "url": "https://api.frankfurter.app/latest?from={from}&to={to}", "note": "currency rates"},
    # ── Media / art / entertainment ──
    "tvmaze":        {"name": "TVMaze", "category": "media", "url": "https://api.tvmaze.com/search/shows?q={q}", "note": "tv shows"},
    "mealdb":        {"name": "TheMealDB", "category": "media", "url": "https://www.themealdb.com/api/json/v1/1/search.php?s={q}", "note": "recipes"},
    "cocktaildb":    {"name": "TheCocktailDB", "category": "media", "url": "https://www.thecocktaildb.com/api/json/v1/1/search.php?s={q}", "note": "cocktails"},
    "pokeapi":       {"name": "PokéAPI", "category": "games", "url": "https://pokeapi.co/api/v2/pokemon/{q}", "note": "pokemon data"},
    "metmuseum":     {"name": "Met Museum", "category": "art", "url": "https://collectionapi.metmuseum.org/public/collection/v1/search?q={q}", "note": "art objects"},
    "artic":         {"name": "Art Institute Chicago", "category": "art", "url": "https://api.artic.edu/api/v1/artworks/search?q={q}", "note": "artworks"},
    # ── Games / trivia / fun ──
    "trivia":        {"name": "Open Trivia DB", "category": "games", "url": "https://opentdb.com/api.php?amount=5", "note": "trivia questions"},
    "deckofcards":   {"name": "Deck of Cards", "category": "games", "url": "https://deckofcardsapi.com/api/deck/new/draw/?count=2", "note": "draw cards"},
    "quotable":      {"name": "Quotable", "category": "reference", "url": "https://api.quotable.io/random", "note": "random quote"},
    "advice":        {"name": "Advice Slip", "category": "fun", "url": "https://api.adviceslip.com/advice", "note": "random advice"},
    "bored":         {"name": "Bored API", "category": "fun", "url": "https://www.boredapi.com/api/activity", "note": "activity idea"},
    "chucknorris":   {"name": "Chuck Norris", "category": "fun", "url": "https://api.chucknorris.io/jokes/random", "note": "joke"},
    "catfact":       {"name": "Cat Facts", "category": "fun", "url": "https://catfact.ninja/fact", "note": "cat fact"},
    "uselessfacts":  {"name": "Useless Facts", "category": "fun", "url": "https://uselessfacts.jsph.pl/api/v2/facts/random", "note": "random fact"},
    "dogimg":        {"name": "Dog Image", "category": "fun", "url": "https://dog.ceo/api/breeds/image/random", "note": "dog image url"},
    # ── Name inference (game NPC utilities) ──
    "genderize":     {"name": "Genderize", "category": "data", "url": "https://api.genderize.io?name={q}", "note": "name -> gender"},
    "agify":         {"name": "Agify", "category": "data", "url": "https://api.agify.io?name={q}", "note": "name -> age"},
    "nationalize":   {"name": "Nationalize", "category": "data", "url": "https://api.nationalize.io?name={q}", "note": "name -> nationality"},
    "jsonplaceholder": {"name": "JSONPlaceholder", "category": "dev", "url": "https://jsonplaceholder.typicode.com/posts/{q}", "note": "mock data"},
}

_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; GameForge-CNS/1.0; +https://gameforge.local)",
            "Accept": "application/json, text/plain, */*"}


def catalog() -> dict:
    by_cat: dict[str, list] = {}
    for k, v in FREE_APIS.items():
        by_cat.setdefault(v["category"], []).append({"key": k, **{kk: v[kk] for kk in ("name", "note")}})
    return {"total": len(FREE_APIS), "categories": sorted(by_cat.keys()), "apis": by_cat}


def _build_url(api: dict, params: dict) -> str:
    url = api["url"]
    placeholders = re.findall(r"\{(\w+)\}", url)
    for ph in placeholders:
        val = params.get(ph, params.get("q", ""))
        url = url.replace("{" + ph + "}", str(val).strip().replace(" ", "%20"))
    # append any extra params not used as placeholders
    extra = {k: v for k, v in params.items() if k not in placeholders and k != "q"}
    if extra:
        sep = "&" if "?" in url else "?"
        url += sep + "&".join(f"{k}={v}" for k, v in extra.items())
    return url


async def fetch(api_key: str, params: dict) -> dict:
    api = FREE_APIS.get(api_key)
    if not api:
        return {"ok": False, "error": f"unknown api '{api_key}'", "available": sorted(FREE_APIS.keys())}
    url = _build_url(api, params or {})
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10, follow_redirects=True, headers=_HEADERS) as c:
            r = await c.get(url)
        ct = r.headers.get("content-type", "")
        body: Any
        if "json" in ct:
            body = r.json()
        else:
            body = r.text[:4000]
        return {"ok": r.is_success, "api": api_key, "name": api["name"], "status": r.status_code, "url": url, "data": body}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "api": api_key, "error": f"{type(e).__name__}: {e}"[:160], "url": url}


# ── heuristic API picker for on-demand knowledge acquisition ──────────────────
def pick_api(query: str) -> tuple[str, dict]:
    q = query.lower().strip()
    m = re.search(r"(?:define|meaning of|definition of)\s+(.+)", q)
    if m:
        return "dictionary", {"q": m.group(1).split()[0]}
    m = re.search(r"(?:synonym|synonyms|related words?)\s+(?:for|of)?\s*(.+)", q)
    if m:
        return "datamuse", {"q": m.group(1)}
    if any(w in q for w in ("crypto", "bitcoin", "ethereum", "coin price", "price of")):
        coin = "bitcoin"
        for c in ("bitcoin", "ethereum", "solana", "dogecoin", "cardano"):
            if c in q:
                coin = c
        return "coingecko", {"q": coin}
    m = re.search(r"country\s+(.+)", q)
    if m:
        return "countries", {"q": m.group(1)}
    if "paper" in q or "research" in q or "arxiv" in q:
        return "arxiv", {"q": re.sub(r"(papers?|research|about|on|arxiv)", "", q).strip() or query}
    if "repo" in q or "github" in q or "library for" in q:
        return "github", {"q": re.sub(r"(repo|repos|github|library for)", "", q).strip() or query}
    if "book" in q:
        return "openlibrary", {"q": re.sub(r"books?|about", "", q).strip() or query}
    # default: encyclopedic lookup
    topic = re.sub(r"\b(who|what|where|when|why|how|is|are|the|a|an|of|about|tell me about|explain)\b", " ", q).strip()
    topic = re.sub(r"\s+", " ", topic)
    return "wikipedia", {"q": (topic or query).strip().title().replace(" ", "_")}


def summarize(api_key: str, data: Any) -> str:
    """Extract a short human-readable text from a raw API result for the brain."""
    try:
        if api_key == "wikipedia" and isinstance(data, dict):
            return data.get("extract", "")[:600]
        if api_key == "dictionary" and isinstance(data, list) and data:
            defs = data[0].get("meanings", [])
            if defs and defs[0].get("definitions"):
                return f"{data[0].get('word')}: {defs[0]['definitions'][0].get('definition','')}"[:600]
        if api_key == "datamuse" and isinstance(data, list):
            return "Related words: " + ", ".join(d.get("word", "") for d in data[:12])
        if api_key == "coingecko" and isinstance(data, dict):
            return "; ".join(f"{k}=${v.get('usd')}" for k, v in data.items())
        if api_key == "countries" and isinstance(data, list) and data:
            c = data[0]
            return f"{c.get('name',{}).get('common')}: capital {c.get('capital',['?'])[0]}, pop {c.get('population')}"
        if api_key == "github" and isinstance(data, dict):
            return "; ".join(f"{it['full_name']} ({it.get('stargazers_count',0)}★)" for it in data.get("items", [])[:5])
        if api_key == "openlibrary" and isinstance(data, dict):
            return "; ".join(d.get("title", "") for d in data.get("docs", [])[:5])
    except Exception:  # noqa: BLE001
        pass
    s = str(data)
    return s[:600]
