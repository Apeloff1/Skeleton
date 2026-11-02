"""Deterministic CSP-locked offline editor for source-leased quest softlock plans.

The browser is an untrusted authoring surface. Only the canonical Python
compiler may accept an exported plan, after revalidating the original receipt.
"""
from __future__ import annotations

from base64 import b64encode
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import secrets
import stat
from typing import Any, Mapping

from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import (
    _canonical, _lease, _open_directory, _write_all,
)
from .studio_quest_softlock_audit import replay_quest_softlock_audit

EXPORT_SCHEMA = "skeleton.game_builder.studio_quest_softlock_editor_export.v1"
EDITOR_FILENAME = "studio_quest_softlock_editor.html"
MAX_EDITOR_BYTES = 64 * 1024
MAX_EXPORT_BYTES = 32768

# Source is static and the exact bytes are hashed into the inline CSP.
_SCRIPT = """(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  const status = byId('status');
  byId('export').addEventListener('click', () => {
    try {
      const authoring = JSON.parse(byId('authoring').value);
      if (!authoring || Array.isArray(authoring) || typeof authoring !== 'object') {
        throw new Error('Authoring must be an object');
      }
      const envelope = {
        schema: 'skeleton.game_builder.studio_quest_softlock_editor_export.v1',
        baseline_digest: byId('baseline').value,
        source_digest: byId('source').value,
        initial_session_digest: byId('session').value,
        authoring
      };
      const raw = JSON.stringify(envelope);
      if (new TextEncoder().encode(raw).length > 32768) {
        throw new Error('Export exceeds byte budget');
      }
      const url = URL.createObjectURL(new Blob([raw], {type: 'application/json'}));
      const link = document.createElement('a');
      link.href = url;
      link.download = 'studio_quest_softlock_edit.json';
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      status.textContent = 'Export created; recompile with canonical CLI before trusting.';
    } catch (error) {
      status.textContent = 'Export rejected: ' + String(error.message || error);
    }
  });
})();"""


def render_quest_softlock_editor(
    documents: Mapping[str, Any], baseline: object, *, authorized: bool,
) -> bytes:
    checked = replay_quest_softlock_audit(
        documents, baseline, authorized=authorized)
    raw_plan = json.dumps(checked["authoring"], sort_keys=True, indent=2,
                          ensure_ascii=True, allow_nan=False)
    script_hash = b64encode(sha256(_SCRIPT.encode("utf-8")).digest()).decode("ascii")
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="default-src '
        "\'none\'; script-src \'sha256-" + script_hash
        + "\'; style-src \'none\'; connect-src \'none\'; "
        'img-src \'none\'; form-action \'none\'; base-uri \'none\'">'
        '<title>Quest softlock editor</title></head><body><main>'
        '<h1>Offline authored quest softlock editor</h1>'
        '<p>Edit typed JSON, export, and recompile through the canonical CLI.</p>'
        '<input id="baseline" type="hidden" value="'
        + checked["audit_digest"] + '"><input id="source" type="hidden" value="'
        + checked["source_digest"] + '"><input id="session" type="hidden" value="'
        + checked["initial_session_digest"] + '">'
        '<label for="authoring">Typed authoring plan</label>'
        '<textarea id="authoring" rows="20" cols="85">'
        + escape(raw_plan, quote=True) + '</textarea>'
        '<button id="export" type="button">Export typed plan</button>'
        '<p id="status" role="status"></p>'
        '<p>Browser export grants no authority. No native gameplay or release proof.</p>'
        '</main><script>' + _SCRIPT + '</script></body></html>'
    ).encode("utf-8")
    if len(html) > MAX_EDITOR_BYTES:
        raise StudioQuestError("softlock editor HTML exceeds byte budget")
    return html


def publish_quest_softlock_editor(
    documents: Mapping[str, Any], baseline: object, directory: Path, *,
    authorized: bool,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("softlock editor publication requires authorization")
    checked = replay_quest_softlock_audit(
        documents, baseline, authorized=True)
    raw = render_quest_softlock_editor(documents, checked, authorized=True)
    fd = _open_directory(directory)
    temp = ".softlock-editor-" + secrets.token_hex(16) + ".tmp"
    created = False
    try:
        out = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                      os.O_NOFOLLOW, 0o600, dir_fd=fd)
        created = True
        try:
            _write_all(out, raw)
            os.fsync(out)
        finally:
            os.close(out)
        os.link(temp, EDITOR_FILENAME, src_dir_fd=fd, dst_dir_fd=fd,
                follow_symlinks=False)
        os.fsync(fd)
    finally:
        try:
            if created:
                os.unlink(temp, dir_fd=fd)
        finally:
            os.close(fd)
    return {"path": str(Path(directory) / EDITOR_FILENAME),
            "bytes": len(raw), "baseline_digest": checked["audit_digest"],
            "file_write_performed": True, "release_certified": False}


def _read_export(path: Path) -> dict[str, Any]:
    if not isinstance(path, Path):
        raise StudioQuestError("softlock editor export path must be typed")
    fd = _open_directory(path.parent)
    try:
        handle = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=fd)
        try:
            before = os.fstat(handle)
            if (not stat.S_ISREG(before.st_mode)
                    or not 0 < before.st_size <= MAX_EXPORT_BYTES
                    or (os.name == "posix"
                        and (before.st_uid != os.getuid()
                             or before.st_mode & 0o077 or before.st_nlink != 1))):
                raise StudioQuestError("softlock editor export must be private")
            raw = os.read(handle, MAX_EXPORT_BYTES + 1)
            after = os.fstat(handle)
            if (len(raw) != before.st_size
                    or (after.st_size, after.st_mtime_ns, after.st_ctime_ns,
                        after.st_ino) !=
                    (before.st_size, before.st_mtime_ns, before.st_ctime_ns,
                     before.st_ino)):
                raise StudioQuestError("softlock editor export changed during read")
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise StudioQuestError("duplicate softlock editor JSON key")
            result[key] = value
        return result
    try:
        value = json.loads(raw.decode("utf-8", "strict"),
                           object_pairs_hook=unique,
                           parse_constant=lambda _: (_ for _ in ()).throw(
                               StudioQuestError("nonfinite softlock editor JSON")))
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise StudioQuestError("invalid softlock editor export JSON") from exc
    if type(value) is not dict:
        raise StudioQuestError("softlock editor export must be an object")
    return value


def load_quest_softlock_editor_export(
    documents: Mapping[str, Any], baseline: object, export_file: Path, *,
    authorized: bool, expected_source_digest: str,
    expected_initial_session_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("softlock editor import requires authorization")
    _lease(expected_source_digest, "softlock editor source")
    _lease(expected_initial_session_digest, "softlock editor session")
    checked = replay_quest_softlock_audit(
        documents, baseline, authorized=True)
    if (checked["source_digest"] != expected_source_digest
            or checked["initial_session_digest"] != expected_initial_session_digest):
        raise StudioQuestError("softlock editor baseline lease drift")
    value = _read_export(export_file)
    if (set(value) != {"schema", "baseline_digest", "source_digest",
                       "initial_session_digest", "authoring"}
            or value["schema"] != EXPORT_SCHEMA
            or value["baseline_digest"] != checked["audit_digest"]
            or value["source_digest"] != expected_source_digest
            or value["initial_session_digest"] != expected_initial_session_digest):
        raise StudioQuestError("stale or forged softlock editor export")
    if type(value["authoring"]) is not dict or len(_canonical(value["authoring"])) > MAX_EXPORT_BYTES:
        raise StudioQuestError("invalid bounded softlock editor authoring")
    # Caller must pass this authoring through compile_quest_softlock_audit;
    # a browser-exported plan is not a trusted compilation or authority.
    return value["authoring"]
