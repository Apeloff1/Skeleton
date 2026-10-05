"""
Build, Compilation, & Packaging Recipes.

Collection: `build_recipes`

For every (engine × target_platform × mode) we record a runnable shell-recipe
that covers prepare → compile → package → sign → publish. The agent uses these
as templates when generating CI/build configs.
"""
from __future__ import annotations
import hashlib, logging, itertools
from datetime import datetime, timezone

log = logging.getLogger("knowledge.build_recipes")

ENGINES = ["Unity", "Unreal", "Godot", "Bevy", "Phaser", "Three.js", "LÖVE", "Pygame", "GameMaker", "Cocos", "Defold", "MonoGame", "libGDX", "PixiJS", "Construct"]
PLATFORMS = ["Windows-x64", "Linux-x64", "macOS-Universal", "Android-arm64", "iOS-arm64", "WebGL", "Switch", "PS5", "Xbox-Series", "Steam-Deck"]
MODES = ["debug", "profile", "release", "shipping"]

ENGINE_RECIPES = {
    "Unity": {
        "prepare":  "unity-hub install --version 6000.0.f1\nunity-hub install-modules --version 6000.0.f1 --module {target}",
        "compile":  "Unity -batchmode -quit -projectPath . -buildTarget {target} -executeMethod Build.{mode}",
        "package":  "il2cpp + asset-bundles in StreamingAssets/, output in Builds/{platform}/",
        "sign":     "signtool/apksigner/codesign depending on target",
        "publish":  "steamcmd / Google Play / App Store Connect",
    },
    "Unreal": {
        "prepare":  "RunUAT.bat Setup",
        "compile":  "RunUAT.bat BuildCookRun -project={uproject} -platform={target} -clientconfig={mode} -cook -allmaps -stage -pak",
        "package":  "-package -archivedirectory=Build/{platform}",
        "sign":     "-signexec / iOS provision profiles",
        "publish":  "epic / steamworks publish",
    },
    "Godot": {
        "prepare":  "download export-templates matching engine version",
        "compile":  "godot --headless --export-{mode} '{target}' build/{platform}/game.{ext}",
        "package":  "PCK / EXE / APK / IPA",
        "sign":     "signtool / apksigner / codesign",
        "publish":  "steam / itch / play / app store",
    },
    "Bevy": {
        "prepare":  "rustup target add {triple}",
        "compile":  "cargo build --target {triple} --{mode}",
        "package":  "copy assets/ alongside binary; tar.gz / zip",
        "sign":     "signtool / codesign / apk-signer",
        "publish":  "itch.io butler / steamcmd",
    },
    "Phaser": {
        "prepare":  "npm ci",
        "compile":  "npm run build -- --mode {mode}",
        "package":  "dist/ folder, gzip, deploy to CDN",
        "sign":     "sub-resource integrity hashes",
        "publish":  "itch.io / GitHub Pages / Newgrounds",
    },
    "Three.js": {
        "prepare":  "npm ci",
        "compile":  "vite build --mode {mode}",
        "package":  "dist/ + draco-compressed glTFs",
        "sign":     "SRI hashes",
        "publish":  "static CDN / Vercel / Cloudflare Pages",
    },
    "LÖVE": {
        "prepare":  "download love-{platform}.zip",
        "compile":  "zip -r game.love . -x '.git/*'",
        "package":  "cat love.exe + game.love > GameWindows.exe (Windows fuse)",
        "sign":     "signtool / codesign",
        "publish":  "itch.io butler",
    },
    "Pygame": {
        "prepare":  "pip install pyinstaller",
        "compile":  "pyinstaller --onefile --noconsole main.py --add-data 'assets:assets'",
        "package":  "single executable in dist/",
        "sign":     "signtool / codesign",
        "publish":  "itch.io butler",
    },
    "GameMaker": {
        "prepare":  "Igor.exe -j=8 -options 'options.json' -- Runtime VerifyOnly",
        "compile":  "Igor.exe -options=options.json -- {target} Package",
        "package":  ".YYZ project + platform installer",
        "sign":     "signtool / apksigner / codesign",
        "publish":  "steam / opera gx / poki / itch",
    },
    "Cocos": {
        "prepare":  "cocos creator --headless install-deps",
        "compile":  "cocos creator --headless build --platform {target} --debug {is_debug}",
        "package":  "build/{target}/ assets + native shell",
        "sign":     "platform-specific signing",
        "publish":  "app stores / wechat-mini / facebook-instant",
    },
    "Defold": {
        "prepare":  "download bob.jar",
        "compile":  "java -jar bob.jar --archive --platform {target} --variant {mode} build",
        "package":  "build/default/main.darc + native shell",
        "sign":     "apksigner / codesign",
        "publish":  "app store / play / steam",
    },
    "MonoGame": {
        "prepare":  "dotnet workload install",
        "compile":  "dotnet publish -c {mode} -r {rid} --self-contained",
        "package":  "publish/ folder + content",
        "sign":     "signtool / codesign",
        "publish":  "itch / steam",
    },
    "libGDX": {
        "prepare":  "gradle wrapper",
        "compile":  "./gradlew {platform}:dist",
        "package":  "jar / apk / ipa / native bundle",
        "sign":     "apksigner / codesign",
        "publish":  "google play / steam / itch",
    },
    "PixiJS": {
        "prepare":  "npm ci",
        "compile":  "npm run build",
        "package":  "dist/ folder — static web",
        "sign":     "SRI",
        "publish":  "static CDN / itch HTML5",
    },
    "Construct": {
        "prepare":  "open project in Construct 3 editor",
        "compile":  "File → Export → {target}",
        "package":  "HTML5 / Cordova / NW.js",
        "sign":     "platform-specific",
        "publish":  "newgrounds / scirra-arcade / play store",
    },
}

MODE_FLAGS = {
    "debug":    {"strip_symbols": False, "optimize": "-O0", "asserts": True},
    "profile":  {"strip_symbols": False, "optimize": "-O2", "asserts": True,  "include_profiler": True},
    "release":  {"strip_symbols": True,  "optimize": "-O3", "asserts": False},
    "shipping": {"strip_symbols": True,  "optimize": "-O3 -flto", "asserts": False, "shrink_resources": True},
}


def _bid(e, p, m): return "build_" + hashlib.md5(f"{e}|{p}|{m}".encode()).hexdigest()[:14]


def build_build_recipes() -> list[dict]:
    out = []
    for engine, platform, mode in itertools.product(ENGINES, PLATFORMS, MODES):
        recipe = ENGINE_RECIPES.get(engine, {})
        target = platform.split("-", 1)[0].lower()
        out.append({
            "id": _bid(engine, platform, mode),
            "engine": engine,
            "platform": platform,
            "mode": mode,
            "prepare":  recipe.get("prepare", ""),
            "compile":  recipe.get("compile", "").replace("{target}", target).replace("{platform}", platform).replace("{mode}", mode),
            "package":  recipe.get("package", "").replace("{platform}", platform),
            "sign":     recipe.get("sign", ""),
            "publish":  recipe.get("publish", ""),
            "flags":    MODE_FLAGS.get(mode, {}),
            "description": f"Build recipe — {engine} on {platform} in {mode} mode.",
            "tags": [engine.lower().replace(" ","-"), platform.lower(), mode, "build-recipe"],
        })
    return out


async def seed_build_recipes(db) -> dict:
    docs = build_build_recipes()
    try:
        await db.build_recipes.create_index("id", unique=True)
        await db.build_recipes.create_index("engine")
        await db.build_recipes.create_index("platform")
        await db.build_recipes.create_index("mode")
        await db.build_recipes.create_index([("tags", 1)])
    except Exception:
        pass
    now = datetime.now(timezone.utc).isoformat()
    inserted = 0
    for d in docs:
        d["indexed_at"] = now
        try:
            r = await db.build_recipes.update_one({"id": d["id"]}, {"$set": d}, upsert=True)
            if r.upserted_id is not None: inserted += 1
        except Exception: pass
    total = await db.build_recipes.count_documents({})
    log.info(f"[build_recipes] inserted={inserted} total={total}")
    return {"inserted": inserted, "total": total, "combinations": len(docs)}
