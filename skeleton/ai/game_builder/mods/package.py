"""Mod packaging in the project bundle format, signed and installed via B099.

A mod is saved as a bundle project ``mod-<id>`` (genre ``mod``) with files
``mod.json`` (manifest), ``hooks.json`` (declarative ops) and optional
``assets/*``; the B099 HMAC signature rides in the ``mod_signature`` bundle
section. Unpacking verifies the bundle end to end (``bundle_io.import_bundle``)
and then runs B099 ``install`` (signature, SDK, permissions, native code,
moderation) before any hook is built.
"""
from __future__ import annotations

import json
from typing import Any, Callable, Mapping

from skeleton.ai.game_builder.project_bundle import bundle_io
from skeleton.ai.game_builder.project_bundle.project_save import ProjectSaver
from skeleton.gameforge.batch_b09x.b099_ugc_sandbox import ModPackage, install, sign
from skeleton.kernel.game_save_plane import GameSavePlane

from .hooks import DeclarativeHook
from .manifest import ModError, ModManifest

GENRE = "mod"
SIG_SECTION = "mod_signature"


def _project_id(mod_id: str) -> str:
    return f"mod-{mod_id}"


def _package(manifest: ModManifest, files: Mapping[str, str], signature: str = "") -> ModPackage:
    return ModPackage(manifest.mod_id, str(manifest.version), manifest.sdk_api,
                      tuple(manifest.permissions), dict(files), signature)


def pack_mod(manifest: ModManifest, hooks: list[Mapping[str, Any]], key: bytes,
             codec: bundle_io.BundleCodec, *, assets: Mapping[str, str] | None = None) -> str:
    """Validate, sign and export a mod as a ``.gfbundle.json`` string."""
    DeclarativeHook.from_list(manifest, list(hooks))  # reject bad hooks before shipping
    files = {"mod.json": json.dumps(manifest.to_dict(), sort_keys=True, indent=2),
             "hooks.json": json.dumps(list(hooks), sort_keys=True, indent=2)}
    for path, body in sorted((assets or {}).items()):
        if not path.startswith("assets/"):
            raise ModError("extra mod files must live under assets/")
        bundle_io.safe_member_path(path)
        files[path] = body
    sig = sign(_package(manifest, files), key)
    saver = ProjectSaver(GameSavePlane())
    saver.save_files(_project_id(manifest.mod_id), GENRE, files, label=str(manifest.version),
                     extra_sections={SIG_SECTION: {"hmac_sha256": sig}})
    return bundle_io.export_bundle(saver, _project_id(manifest.mod_id), codec)


def unpack_mod(raw: str, key: bytes, codec: bundle_io.BundleCodec,
               moderate: Callable[[ModPackage], bool] = lambda _p: True,
               grant: Callable[[str, str, str], object] | None = None,
               ) -> tuple[ModManifest, DeclarativeHook, list]:
    """Verify and install a packed mod. Returns manifest, hook and B099 grants."""
    saver = ProjectSaver(GameSavePlane())
    bm = bundle_io.import_bundle(raw, codec, saver)
    if bm.genre != GENRE or not bm.project_id.startswith("mod-"):
        raise ModError("bundle is not a mod package")
    v = saver.load(bm.project_id)
    try:
        manifest = ModManifest.from_dict(json.loads(v.files["mod.json"]))
        ops = json.loads(v.files["hooks.json"])
    except (KeyError, json.JSONDecodeError) as exc:
        raise ModError("mod package lacks a readable mod.json/hooks.json") from exc
    if _project_id(manifest.mod_id) != bm.project_id:
        raise ModError("mod id disagrees with bundle project")
    sig = v.sections.get(SIG_SECTION, {}).get("hmac_sha256", "")
    kwargs = {} if grant is None else {"grant": grant}
    status, caps = install(_package(manifest, v.files, sig), key, moderate, **kwargs)
    if status != "installed":
        raise ModError(f"mod install {status}")
    return manifest, DeclarativeHook.from_list(manifest, ops), caps
