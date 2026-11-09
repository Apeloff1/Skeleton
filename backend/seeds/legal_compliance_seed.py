"""
Legal & Compliance knowledge base.
Collection: `legal_compliance`
"""
import hashlib, logging, itertools
from datetime import datetime, timezone

RULES = [
    ("GDPR",            "EU data privacy",        "Provide opt-in consent, data export + deletion endpoints"),
    ("CCPA",            "California privacy",     "Honour 'do not sell my data', provide deletion request"),
    ("COPPA",           "US children <13",         "No personal data collection without parental consent"),
    ("PIPL",            "China privacy",          "Local data residency, additional consent"),
    ("PEGI",            "EU age rating",          "Submit content review; declare loot-box presence"),
    ("ESRB",            "NA age rating",          "Submit content review; loot-box info disclosure"),
    ("USK",             "DE age rating",          "Stricter on violence/sexual content"),
    ("ACB",             "AU age rating",          "R18+ available; gambling-style loot triggers RC"),
    ("CERO",            "JP age rating",          "Voluntary; cross-cultural sensitivities"),
    ("Section508",      "US accessibility",       "Subtitles, key remapping, colour-blind modes required"),
    ("EN-301-549",      "EU accessibility",       "Equivalent to WCAG 2.1 AA, captions + alt-text"),
    ("WCAG-2.2-AA",     "web a11y",                "4.5:1 contrast, focus indicators, no keyboard traps"),
    ("Belgium-loot-boxes","BE loot-ban",           "Loot boxes purchasable with real money illegal"),
    ("Netherlands-loot","NL loot-ban",             "Marketable rewards in loot boxes treated as gambling"),
    ("China-publishing-license","CN release",     "Requires ISBN + content review for paid release"),
    ("Apple-AppStore",  "iOS",                     "Sign in with Apple, IAP only, no external links to purchase"),
    ("Google-Play",     "Android",                 "Target API ≥ 34; data safety form; in-app billing fee"),
    ("Steam-onboarding","PC",                      "App credit signing, content tags, depots, betas"),
    ("Xbox-cert",       "Microsoft store",        "XR rules, cross-progression, controller support required"),
    ("PlayStation-cert","Sony",                    "TRC checklist, trophy support, save-data backups"),
    ("Nintendo-Lotcheck","Switch",                 "Lotcheck QA + size/feature gates"),
    ("DMCA-takedown",   "copyright",               "Honour valid takedown within 24h; counter-notice path"),
    ("Bopa-Brazil",     "BR data protection",     "Local DPO required if EU/Brazil users targeted"),
    ("DSA-EU",          "EU online platforms",     "User reporting + trusted flagger pipeline"),
    ("Music-Licensing", "any region",              "Sync + master rights required for radio/ambient music"),
    ("FOSS-attribution","open-source",             "Maintain NOTICE/THIRD_PARTY_LICENSES alongside binary"),
    ("Crypto-Token",    "if blockchain",           "Howey test / MiCA / MAS license checks before launch"),
    ("Tax-VAT",         "EU sales",                "VAT MOSS / OSS scheme registration"),
]
REGIONS = ["global","EU","US","UK","JP","CN","KR","BR","AU","CA"]

def _lid(*p): return "legal_" + hashlib.md5("|".join(p).encode()).hexdigest()[:14]

def build_legal_compliance():
    out = []
    for (rule, scope, action), region in itertools.product(RULES, REGIONS):
        out.append({"id":_lid(rule,region),"rule":rule,"scope":scope,"region":region,"action_required":action,
                    "description":f"{rule} ({scope}) — {action}","tags":[rule.lower(),region.lower(),"legal","compliance"]})
    return out

async def seed_legal_compliance(db):
    docs = build_legal_compliance()
    try:
        await db.legal_compliance.create_index("id", unique=True)
        await db.legal_compliance.create_index("rule")
        await db.legal_compliance.create_index("region")
        await db.legal_compliance.create_index([("tags", 1)])
    except Exception: pass
    now = datetime.now(timezone.utc).isoformat(); inserted = 0
    for d in docs:
        d["indexed_at"] = now
        try:
            r = await db.legal_compliance.update_one({"id":d["id"]},{"$set":d},upsert=True)
            if r.upserted_id is not None: inserted += 1
        except Exception: pass
    return {"inserted": inserted, "total": await db.legal_compliance.count_documents({})}
