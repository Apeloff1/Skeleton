"""
Automated Publishing & Storefront Asset Materializers.
Collection: `publishing_assets`
"""
import hashlib, logging, itertools
from datetime import datetime, timezone

STOREFRONTS = [
    ("Steam",          {"icon":"460x215","library_hero":"1920x620","capsule_main":"616x353","page_bg":"1438x810"}),
    ("Epic",           {"tall_capsule":"1200x1600","wide_capsule":"2560x1440","logo":"800x600"}),
    ("GOG",            {"banner":"1600x900","thumb":"720x900"}),
    ("itch.io",        {"cover":"630x500","screenshot":"1920x1080"}),
    ("GooglePlay",     {"feature_graphic":"1024x500","hi_res_icon":"512x512","screenshot":"1080x1920"}),
    ("AppStore-iOS",   {"app_icon":"1024x1024","screenshot_6.5in":"1284x2778","screenshot_5.5in":"1242x2208"}),
    ("Nintendo-eShop", {"hero":"2560x1440","icon":"1024x1024"}),
    ("PSN",            {"keyart":"3840x2160","icon":"512x512"}),
    ("Xbox-MS-Store",  {"hero":"1920x1080","poster":"720x1080"}),
    ("Meta-Quest",     {"hero":"2160x1080","icon":"512x512"}),
]
ASSET_KINDS = ["icon","key-art","banner","screenshot-set","trailer-30s","trailer-60s","description-short","description-long","tagline","genre-tags","age-rating","system-requirements"]
LOCALES = ["en-US","en-GB","de-DE","fr-FR","es-ES","pt-BR","it-IT","ja-JP","ko-KR","zh-CN","zh-TW","ru-RU","pl-PL","tr-TR","ar-SA"]

def _pid(*p): return "pub_" + hashlib.md5("|".join(p).encode()).hexdigest()[:14]

def build_publishing_assets():
    out = []
    for store, sizes in STOREFRONTS:
        for slot, dims in sizes.items():
            out.append({"id":_pid(store,slot,"size"),"category":"storefront-spec","storefront":store,
                        "slot":slot,"dims":dims,"description":f"{store} requires {slot} at {dims}",
                        "tags":[store.lower(),slot,"storefront","spec"]})
    for store, kind, locale in itertools.product([s[0] for s in STOREFRONTS], ASSET_KINDS, LOCALES):
        out.append({"id":_pid(store,kind,locale,"asset"),"category":"asset-recipe","storefront":store,
                    "kind":kind,"locale":locale,
                    "description":f"Recipe to generate {kind} for {store} in {locale}",
                    "tags":[store.lower(),kind,locale,"asset","materializer"]})
    return out

async def seed_publishing_assets(db):
    docs = build_publishing_assets()
    try:
        await db.publishing_assets.create_index("id", unique=True)
        await db.publishing_assets.create_index("category")
        await db.publishing_assets.create_index("storefront")
        await db.publishing_assets.create_index([("tags", 1)])
    except Exception: pass
    now = datetime.now(timezone.utc).isoformat(); inserted = 0
    for d in docs:
        d["indexed_at"] = now
        try:
            r = await db.publishing_assets.update_one({"id":d["id"]},{"$set":d},upsert=True)
            if r.upserted_id is not None: inserted += 1
        except Exception: pass
    return {"inserted": inserted, "total": await db.publishing_assets.count_documents({})}
