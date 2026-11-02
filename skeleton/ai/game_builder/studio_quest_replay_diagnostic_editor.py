"""CSP-hashed offline quest replay editor with strict source-leased import.

Browser output is untrusted. Canonical Python recompiles every imported plan
under the current operator's out-of-band authorization and source/session lease.
"""
from __future__ import annotations

from base64 import b64encode
from hashlib import sha256
from html import escape
import json
import os
from pathlib import Path
import stat
from typing import Any, Mapping

from .studio_ecosystem_quest import StudioQuestError
from .studio_ecosystem_scene_schedule import _canonical, _lease, _open_directory
from .studio_quest_replay_diagnostic import (
    compile_replay_diagnostic, replay_replay_diagnostic,
)

EXPORT_SCHEMA = "skeleton.game_builder.studio_quest_replay_diagnostic_editor_export.v1"
MAX_EXPORT_BYTES = 32768
MAX_HTML_BYTES = 65536

_SCRIPT = """(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  byId('export').addEventListener('click', () => {
    try {
      const authoring = JSON.parse(byId('authoring').value);
      if (!authoring || Array.isArray(authoring) ||
          typeof authoring !== 'object' || !Array.isArray(authoring.actions) ||
          authoring.actions.length > 64) {
        throw Error('invalid typed diagnostic authoring');
      }
      const payload = {
        schema: 'skeleton.game_builder.studio_quest_replay_diagnostic_editor_export.v1',
        project_id: byId('project').value,
        source_digest: byId('source').value,
        initial_session_digest: byId('session').value,
        baseline_diagnostic_digest: byId('baseline').value,
        authoring
      };
      const raw = JSON.stringify(payload);
      if (new TextEncoder().encode(raw).length > 32768) {
        throw Error('oversized diagnostic export');
      }
      const url = URL.createObjectURL(new Blob([raw], {type:'application/json'}));
      const link = document.createElement('a');
      link.href = url;
      link.download = 'studio_quest_replay_diagnostic_edit.json';
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      byId('status').textContent = 'Exported; canonical CLI recompile required.';
    } catch (error) {
      byId('status').textContent = 'Invalid typed plan; no export produced.';
    }
  });
})();"""


def render_replay_diagnostic_editor(
    documents: Mapping[str, Any], baseline: object, *, authorized: bool,
) -> tuple[bytes, dict[str, Any]]:
    checked = replay_replay_diagnostic(documents, baseline, authorized=authorized)
    script_hash = b64encode(sha256(_SCRIPT.encode("utf-8")).digest()).decode("ascii")
    csp = ("default-src 'none'; script-src 'sha256-" + script_hash +
           "'; connect-src 'none'; style-src 'none'; img-src 'none'; "
           "base-uri 'none'; form-action 'none'; object-src 'none'")
    raw_plan = json.dumps(
        checked["authoring"], sort_keys=True, indent=2,
        ensure_ascii=True, allow_nan=False)
    def hidden(key: str, value: str) -> str:
        return ('<input type="hidden" id="' + key + '" value="' +
                escape(value, quote=True) + '">')
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="' + csp + '">'
        '<title>Quest replay diagnostic editor</title></head><body><main>'
        '<h1>Source-bound quest replay editor</h1>'
        '<p>Author an original quest replay and select a target ending. '
        'The browser cannot grant authorization or certify gameplay.</p>'
        + hidden("project", checked["project_id"])
        + hidden("source", checked["source_digest"])
        + hidden("session", checked["initial_session_digest"])
        + hidden("baseline", checked["diagnostic_digest"])
        + '<label for="authoring">Typed diagnostic plan</label>'
        '<textarea id="authoring" rows="18" cols="96">'
        + escape(raw_plan, quote=True) + '</textarea>'
        '<button id="export" type="button">Export for canonical replay</button>'
        '<p id="status" role="status" aria-live="polite"></p>'
        '<p>All browser exports are untrusted until imported, replayed, '
        'and source-leased by the canonical engine.</p>'
        '</main><script>' + _SCRIPT + '</script></body></html>'
    ).encode("utf-8")
    if len(html) > MAX_HTML_BYTES:
        raise StudioQuestError("diagnostic editor HTML exceeds byte budget")
    return html, {
        "schema": "skeleton.game_builder.studio_quest_replay_diagnostic_editor.v1",
        "baseline_diagnostic_digest": checked["diagnostic_digest"],
        "html_sha256": sha256(html).hexdigest(), "html_bytes": len(html),
        "authoring_export_only": True, "file_write_performed": False,
        "release_certified": False,
    }


def import_replay_diagnostic_editor_export(
    documents: Mapping[str, Any], baseline: object, path: Path, *,
    authorized: bool, expected_source_digest: str,
    expected_initial_session_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("diagnostic editor import requires authorization")
    _lease(expected_source_digest, "diagnostic editor source")
    _lease(expected_initial_session_digest, "diagnostic editor session")
    checked = replay_replay_diagnostic(documents, baseline, authorized=True)
    if (checked["source_digest"] != expected_source_digest
            or checked["initial_session_digest"] != expected_initial_session_digest):
        raise StudioQuestError("stale diagnostic editor baseline lease")
    if (not isinstance(path, Path) or path.name in ("", ".", "..")
            or len(str(path).encode("utf-8", "strict")) > 4096):
        raise StudioQuestError("invalid diagnostic editor export path")
    fd = _open_directory(path.parent)
    try:
        handle = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                         dir_fd=fd)
        try:
            before = os.fstat(handle)
            if (not stat.S_ISREG(before.st_mode)
                    or not 0 < before.st_size <= MAX_EXPORT_BYTES
                    or (os.name == "posix" and (
                        before.st_uid != os.getuid() or before.st_mode & 0o077
                        or before.st_nlink != 1))):
                raise StudioQuestError("diagnostic editor export must be private")
            raw = os.read(handle, MAX_EXPORT_BYTES + 1)
            after = os.fstat(handle)
            if (len(raw) != before.st_size
                    or (before.st_size, before.st_mtime_ns, before.st_ctime_ns,
                        before.st_ino) !=
                    (after.st_size, after.st_mtime_ns, after.st_ctime_ns,
                     after.st_ino)):
                raise StudioQuestError("diagnostic editor export changed during read")
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise StudioQuestError("duplicate diagnostic editor JSON key")
            result[key] = value
        return result
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                StudioQuestError("nonfinite diagnostic editor JSON")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid diagnostic editor export JSON") from exc
    expected = {
        "schema": EXPORT_SCHEMA, "project_id": checked["project_id"],
        "source_digest": expected_source_digest,
        "initial_session_digest": expected_initial_session_digest,
        "baseline_diagnostic_digest": checked["diagnostic_digest"],
    }
    if (type(value) is not dict or set(value) != set(expected) | {"authoring"}
            or any(value[key] != item for key, item in expected.items())):
        raise StudioQuestError("forged or stale diagnostic editor export")
    return compile_replay_diagnostic(
        documents, value["authoring"], authorized=True,
        expected_source_digest=expected_source_digest,
        expected_initial_session_digest=expected_initial_session_digest)
