"""
apk_inspector.py — Deep introspection of generated APKs.

Endpoints:
  GET  /api/binary/inspect/{build_id}  — full structural analysis
  GET  /api/binary/verify/{build_id}   — apksigner verify pass
  POST /api/binary/rebuild/{build_id}  — force a fresh APK rebuild
  GET  /api/binary/toolchain           — report on installed Android SDK

Surfaces evidence to the user that the APK is genuinely runnable
(classes.dex present, manifest references MainActivity, v2/v3 signed).
"""
from __future__ import annotations
import os
import zipfile
import hashlib
import subprocess
import shutil
from pathlib import Path
from fastapi import APIRouter, HTTPException
from motor.motor_asyncio import AsyncIOMotorClient
# ★ Consolidated 2026-02 — shared MongoDB client (lazy connect, fast timeouts)
from core.databases import client as _SHARED_MONGO_CLIENT

from services import binary_builder

router = APIRouter()

_MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
_DB_NAME = os.environ.get("DB_NAME", "test_database")
_client: AsyncIOMotorClient | None = None


def _db():
    global _client
    if _client is None:
        _client = _SHARED_MONGO_CLIENT  # consolidated → core.databases.client
    return _client[_DB_NAME]


# ─────────────────────────────────────────────────────────────────
# Toolchain status
# ─────────────────────────────────────────────────────────────────
@router.post("/binary/install-toolchain")
async def install_toolchain():
    """Manually trigger the Android SDK + qemu + JDK installer.
    Useful when the background startup install failed silently.
    Returns immediately; the installer runs detached in the background."""
    import subprocess
    import os
    installer = "/app/scripts/install_android_toolchain.sh"
    if not os.path.exists(installer):
        raise HTTPException(500, "installer script missing")
    if binary_builder._have_full_apk_toolchain():
        return {"status": "already_installed", "message": "toolchain is fully present"}
    # Fire and forget
    subprocess.Popen(
        ["bash", installer],
        stdout=open("/tmp/android_install.log", "ab"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    return {"status": "started", "message": "installer running in background — poll /api/binary/toolchain or /api/binary/install-toolchain/status"}


@router.get("/binary/install-toolchain/status")
async def install_toolchain_status():
    """Report on installer progress by reading the log tail."""
    log_path = "/tmp/android_install.log"
    if not os.path.exists(log_path):
        return {"running": False, "log_exists": False, "complete": binary_builder._have_full_apk_toolchain()}
    try:
        with open(log_path, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - 4096))
            tail = fh.read().decode("utf-8", errors="replace")
    except Exception as e:
        tail = f"(log read error: {e})"
    return {
        "running":   not binary_builder._have_full_apk_toolchain() and "=== DONE ===" not in tail,
        "complete":  binary_builder._have_full_apk_toolchain(),
        "log_tail":  tail[-2000:],
    }


@router.delete("/binary/artifact/{build_id}")
async def delete_artifact(build_id: str):
    """Delete the on-disk zip+apk artifacts for build_id. Used to clear out
    stale/non-runnable placeholders from /api/binary/list."""
    deleted = []
    for kind in ("zip", "apk"):
        p = binary_builder.ARTIFACTS_ROOT / f"{build_id}.{kind}"
        if p.exists():
            p.unlink()
            deleted.append(kind)
    return {"build_id": build_id, "deleted": deleted}


@router.get("/binary/list")
async def list_apks():
    """List all APK artifacts on disk with summary metadata (no signature
    verification, fast). Used by the APK Inspector + Tools Arena pickers."""
    root = binary_builder.ARTIFACTS_ROOT
    rows = []
    if root.exists():
        for p in sorted(root.glob("*.apk"), key=lambda x: x.stat().st_mtime, reverse=True):
            build_id = p.stem
            try:
                with zipfile.ZipFile(p) as zf:
                    names = set(zf.namelist())
                    has_dex = "classes.dex" in names
                    has_manifest = "AndroidManifest.xml" in names
                    dex_size = zf.getinfo("classes.dex").file_size if has_dex else 0
            except Exception:
                has_dex = has_manifest = False
                dex_size = 0
            rows.append({
                "build_id":    build_id,
                "size_bytes":  p.stat().st_size,
                "modified_at": p.stat().st_mtime,
                "has_classes_dex": has_dex,
                "has_manifest":    has_manifest,
                "classes_dex_size": dex_size,
                "is_likely_runnable": bool(has_dex and has_manifest),
                "download_url": f"/api/binary/download/{build_id}/apk",
            })
    return {"count": len(rows), "apks": rows}


@router.get("/binary/recent")
async def recent_artifacts(limit: int = 5):
    """Most-recently-built artifacts (zip + apk) across all builds, newest
    first. Powers the Hub 'Recent Artifacts' strip for one-tap re-download."""
    root = binary_builder.ARTIFACTS_ROOT
    rows = []
    if root.exists():
        for kind, pattern in (("apk", "*.apk"), ("zip", "*.zip")):
            for p in root.glob(pattern):
                try:
                    st = p.stat()
                except Exception:
                    continue
                rows.append({
                    "build_id":     p.stem,
                    "kind":         kind,
                    "size_bytes":   st.st_size,
                    "modified_at":  st.st_mtime,
                    "download_url": f"/api/binary/download/{p.stem}/{kind}",
                })
    rows.sort(key=lambda r: r["modified_at"], reverse=True)
    sliced = rows[: max(1, min(limit, 20))]
    return {"count": len(sliced), "total_available": len(rows), "artifacts": sliced}


@router.get("/binary/toolchain")
async def toolchain_status():
    """Report on the installed Android SDK / qemu / JDK."""
    bt = binary_builder.BUILD_TOOLS
    aj = binary_builder.ANDROID_JAR
    ks = binary_builder.DEBUG_KEYSTORE
    has_javac = shutil.which("javac") is not None
    needs_qemu = binary_builder._need_qemu()
    qemu = "/usr/bin/qemu-x86_64-static" if binary_builder.QEMU_X86_64.exists() else None

    def _tool_info(name: str):
        if not bt:
            return {"available": False}
        p = bt / name
        if not p.exists():
            return {"available": False, "path": str(p)}
        return {
            "available": True,
            "path": str(p),
            "is_x86_64_elf": binary_builder._is_elf_x86_64(p),
            "size": p.stat().st_size,
        }

    return {
        "android_sdk_root": str(binary_builder.ANDROID_SDK),
        "build_tools_version": bt.name if bt else None,
        "android_jar": str(aj) if aj else None,
        "android_jar_exists": bool(aj and aj.exists()),
        "debug_keystore": str(ks),
        "debug_keystore_exists": ks.exists(),
        "javac_available": has_javac,
        "qemu_required": needs_qemu,
        "qemu_path": qemu,
        "tools": {n: _tool_info(n) for n in ("aapt2", "d8", "zipalign", "apksigner")},
        "have_full_toolchain": binary_builder._have_full_apk_toolchain(),
    }


# ─────────────────────────────────────────────────────────────────
# Per-APK inspection
# ─────────────────────────────────────────────────────────────────
def _inspect_apk(apk_path: Path) -> dict:
    """Pull structural facts out of an APK without unpacking it."""
    if not apk_path.exists():
        return {"exists": False}

    out: dict = {"exists": True, "size_bytes": apk_path.stat().st_size}

    # sha256
    sha = hashlib.sha256()
    with apk_path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            sha.update(chunk)
    out["sha256"] = sha.hexdigest()

    # zip structure
    try:
        with zipfile.ZipFile(apk_path) as zf:
            names = zf.namelist()
            out["entry_count"] = len(names)
            out["has_classes_dex"] = "classes.dex" in names
            out["has_manifest"] = "AndroidManifest.xml" in names
            out["has_resources_arsc"] = "resources.arsc" in names
            out["asset_count"] = sum(1 for n in names if n.startswith("assets/"))
            out["asset_paths"] = [n for n in names if n.startswith("assets/")][:20]
            out["dex_files"] = [n for n in names if n.endswith(".dex")]

            if out["has_classes_dex"]:
                dex_info = zf.getinfo("classes.dex")
                out["classes_dex_size"] = dex_info.file_size
                # Read DEX magic to confirm it's a real Dalvik file
                with zf.open("classes.dex") as fh:
                    head = fh.read(8)
                    out["dex_magic"] = head[:3].decode("latin1", errors="replace") if head[:3] == b"dex" else "invalid"
                    out["dex_version"] = head[4:7].decode("latin1", errors="replace") if head[:3] == b"dex" else ""

            if out["has_manifest"]:
                mfx = zf.read("AndroidManifest.xml")
                # AAPT2 binary XML — strings encoded UTF-16LE
                def _has(s: str) -> bool:
                    enc = s.encode("utf-16le")
                    return s.encode() in mfx or enc in mfx
                out["manifest_size"] = len(mfx)
                out["manifest_is_binary_xml"] = mfx[:4] == b"\x03\x00\x08\x00"
                out["has_main_activity"] = _has("MainActivity")
                out["has_launcher_intent"] = _has("android.intent.category.LAUNCHER")
                out["has_internet_permission"] = _has("android.permission.INTERNET")

            # META-INF signing presence
            out["has_v1_signature"] = any(n.startswith("META-INF/") and (n.endswith(".SF") or n.endswith(".RSA")) for n in names)
    except Exception as e:
        out["zip_error"] = f"{type(e).__name__}: {e}"

    return out


def _apksigner_verify(apk_path: Path) -> dict:
    if not binary_builder._have_full_apk_toolchain():
        return {"available": False}
    cmd = [
        str(binary_builder.BUILD_TOOLS / "apksigner"),
        "verify", "--verbose", str(apk_path),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return {
            "available": True,
            "exit_code": r.returncode,
            "verifies": r.returncode == 0,
            "stdout": r.stdout[-800:],
            "stderr": r.stderr[-400:],
        }
    except Exception as e:
        return {"available": True, "error": f"{type(e).__name__}: {e}"}


@router.get("/binary/inspect/{build_id}")
async def inspect_apk(build_id: str):
    """Structural + signature analysis of the most recent APK for build_id."""
    apk_path = binary_builder.ARTIFACTS_ROOT / f"{build_id}.apk"
    structure = _inspect_apk(apk_path)
    if not structure.get("exists"):
        raise HTTPException(404, f"no apk for build_id {build_id} — call /api/binary/package first")
    sig = _apksigner_verify(apk_path)
    # Derive a clear runnability score
    runnable = (
        structure.get("has_classes_dex") and
        structure.get("has_manifest") and
        structure.get("has_main_activity") and
        structure.get("has_launcher_intent") and
        sig.get("verifies", False)
    )
    return {
        "build_id":  build_id,
        "path":      str(apk_path),
        "structure": structure,
        "signature": sig,
        "is_installable_apk":  runnable,
        "diagnostic": _diagnostic(structure, sig),
    }


def _diagnostic(structure: dict, sig: dict) -> list[str]:
    """Human-readable list of pass/fail bullets."""
    bullets = []
    if structure.get("has_classes_dex"):
        bullets.append(f"✓ classes.dex present ({structure.get('classes_dex_size', 0)} bytes, magic={structure.get('dex_magic','?')}{structure.get('dex_version','')})")
    else:
        bullets.append("✗ classes.dex MISSING — APK will not launch")
    if structure.get("has_main_activity"):
        bullets.append("✓ MainActivity declared in manifest")
    else:
        bullets.append("✗ no MainActivity reference in manifest")
    if structure.get("has_launcher_intent"):
        bullets.append("✓ LAUNCHER intent-filter present (visible in app drawer)")
    else:
        bullets.append("✗ no LAUNCHER intent-filter — won't appear in app list")
    if structure.get("manifest_is_binary_xml"):
        bullets.append("✓ AndroidManifest is binary XML (aapt2 output)")
    else:
        bullets.append("⚠ manifest is plaintext — Android requires binary XML")
    if structure.get("has_resources_arsc"):
        bullets.append("✓ resources.arsc compiled")
    else:
        bullets.append("⚠ no resources.arsc — resources may not resolve")
    if sig.get("verifies"):
        bullets.append("✓ apksigner verify PASSED — installable")
    else:
        bullets.append(f"✗ signature verification failed: {sig.get('stderr','')[:200]}")
    return bullets


@router.get("/binary/verify/{build_id}")
async def verify_apk(build_id: str):
    apk_path = binary_builder.ARTIFACTS_ROOT / f"{build_id}.apk"
    if not apk_path.exists():
        raise HTTPException(404, f"no apk for build_id {build_id}")
    return _apksigner_verify(apk_path)


@router.post("/binary/rebuild/{build_id}")
async def rebuild_apk(build_id: str):
    """Force a fresh re-package (deletes existing artifacts first).
    
    Falls back to a synthesized minimal build dict if galaxy_builds is missing
    the source doc — useful for APKs that were created via the direct
    binary_builder path (test harness, ad-hoc builds)."""
    db = _db()
    build = await db.galaxy_builds.find_one({"build_id": build_id}, {"_id": 0})
    if not build:
        # Try to reconstruct from existing build_artifacts metadata or fall
        # back to a minimal stub so the rebuild can still succeed.
        art = await db.build_artifacts.find_one({"build_id": build_id, "kind": "apk"}, {"_id": 0})
        if art:
            build = {
                "build_id": build_id,
                "title": f"Rebuild {build_id}",
                "files": [
                    {"path": "rebuild.json", "content": '{"note":"synthesized minimal build for rebuild"}'},
                ],
            }
        else:
            # Last resort — synthesize a stub so the user can still invoke rebuild
            build = {
                "build_id": build_id,
                "title": f"Galaxy {build_id}",
                "files": [
                    {"path": "index.txt", "content": f"Galaxy build {build_id} (synthesized stub)"},
                ],
            }
    # Delete existing artifacts on disk
    for kind in ("zip", "apk"):
        p = binary_builder.ARTIFACTS_ROOT / f"{build_id}.{kind}"
        if p.exists():
            p.unlink()
    out = await binary_builder.package_build(build, kinds=["zip", "apk"])
    # Persist
    for art in out.get("artifacts", []):
        await db.build_artifacts.update_one(
            {"artifact_id": art["artifact_id"]}, {"$set": art}, upsert=True,
        )
    return {"build_id": build_id, "rebuilt": True, "source": "galaxy_builds" if await db.galaxy_builds.find_one({"build_id": build_id}, {"_id": 1}) else "synthesized", **out}
