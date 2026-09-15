"""
Security, Anti-Tamper & Cryptographic recipes.
Collection: `security_crypto`
"""
import hashlib, logging, itertools
from datetime import datetime, timezone

THREATS = [
    ("memory-edit",         "Tools like Cheat Engine read/write process memory"),
    ("speedhack",           "Manipulating game clock to gain advantage"),
    ("packet-replay",       "Captured network packets replayed by attacker"),
    ("packet-injection",    "Forged messages injected at network layer"),
    ("man-in-the-middle",   "TLS bypassed via custom root CA"),
    ("save-tampering",      "Save file edited offline to modify currency/items"),
    ("dll-injection",       "Custom DLL injected into game process"),
    ("reverse-engineering", "Static analysis of decompiled binary"),
    ("clone-account",       "Account cloning via stolen credentials"),
    ("botting-automation",  "Headless client automating grinding"),
    ("piracy-cracking",     "DRM bypass for unlicensed play"),
    ("wallet-drainer",      "Phishing attack on in-game wallet credentials"),
]
MITIGATIONS = [
    ("hmac-payload",        "HMAC-SHA256 over (state || nonce) with server secret"),
    ("server-authoritative","State held server-side; client predicts + reconciles"),
    ("hwid-fingerprint",    "Composite fingerprint from CPU + GPU + MAC + disk"),
    ("vac-eqU",             "User-mode anti-cheat scanning known signatures"),
    ("eac-kernel",          "Kernel-mode driver (BattlEye/EAC style) with rootkit detection"),
    ("crc-save-integrity",  "CRC32 + version + monotone nonce on every save"),
    ("tls-cert-pin",        "Certificate pinning hard-coded; reject other roots"),
    ("signed-binaries",     "Authenticode/codesign + Apple notarization"),
    ("runtime-attestation", "Periodic challenge-response between client and server"),
    ("obfuscated-bytecode", "IL2CPP / VM-protect / control-flow flattening"),
    ("rate-limit-actions",  "Server-side action rate cap to defeat botting"),
    ("captcha-on-suspicion","Adaptive CAPTCHA on high-suspicion accounts"),
    ("deterministic-replay","Server replays inputs to catch impossible states"),
    ("trusted-execution",   "SGX/TrustZone enclave for high-value secrets"),
    ("keyed-asset-encryption","AES-256-GCM on asset bundles, key per-session"),
]
GENRES = ["fps","mmo","moba","arpg","rts","survival","gacha","ccg","sandbox","sim","any"]

def _sid(*p): return "sec_" + hashlib.md5("|".join(p).encode()).hexdigest()[:14]

def build_security_crypto():
    out = []
    for (name, desc), genre in itertools.product(THREATS, GENRES):
        out.append({"id":_sid(name,genre,"threat"),"category":"threat","name":name,"genre":genre,
                    "description":desc,"tags":[name,genre,"threat","security"]})
    for (name, desc), genre in itertools.product(MITIGATIONS, GENRES):
        out.append({"id":_sid(name,genre,"mitigation"),"category":"mitigation","name":name,"genre":genre,
                    "description":desc,"tags":[name,genre,"mitigation","security"]})
    return out

async def seed_security_crypto(db):
    docs = build_security_crypto()
    try:
        await db.security_crypto.create_index("id", unique=True)
        await db.security_crypto.create_index("category")
        await db.security_crypto.create_index("genre")
        await db.security_crypto.create_index([("tags", 1)])
    except Exception: pass
    now = datetime.now(timezone.utc).isoformat(); inserted = 0
    for d in docs:
        d["indexed_at"] = now
        try:
            r = await db.security_crypto.update_one({"id":d["id"]},{"$set":d},upsert=True)
            if r.upserted_id is not None: inserted += 1
        except Exception: pass
    return {"inserted": inserted, "total": await db.security_crypto.count_documents({})}
