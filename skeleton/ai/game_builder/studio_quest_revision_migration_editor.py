"""CSP-locked offline editor for explicit source-leased quest save migration.

The browser is an untrusted authoring surface. Only the canonical migration
compiler may interpret an exported remap after validating both source leases.
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
from .studio_ecosystem_scene_schedule import _lease, _open_directory
from .studio_quest_revision_migration import (
    compile_quest_revision_migration, replay_quest_revision_migration,
)

EXPORT_SCHEMA = "skeleton.game_builder.studio_quest_revision_migration_editor_export.v1"
MAX_EXPORT_BYTES = 32768
MAX_HTML_BYTES = 128 * 1024

_SCRIPT = """(() => {
  'use strict';
  const byId = id => document.getElementById(id);
  byId('export').addEventListener('click', () => {
    try {
      const authoring = JSON.parse(byId('authoring').value);
      if (!authoring || Array.isArray(authoring) ||
          typeof authoring !== 'object' ||
          !Array.isArray(authoring.actions) ||
          !Array.isArray(authoring.remaps) ||
          authoring.actions.length > 64 || authoring.remaps.length > 64) {
        throw Error('invalid bounded migration authoring');
      }
      const payload = {
        schema: 'skeleton.game_builder.studio_quest_revision_migration_editor_export.v1',
        project_id: byId('project').value,
        old_quest_source_digest: byId('source').value,
        initial_session_digest: byId('session').value,
        baseline_migration_digest: byId('baseline').value,
        authoring
      };
      const raw = JSON.stringify(payload);
      if (new TextEncoder().encode(raw).length > 32768) {
        throw Error('oversized migration export');
      }
      const url = URL.createObjectURL(new Blob([raw], {type:'application/json'}));
      const link = document.createElement('a');
      link.href = url;
      link.download = 'studio_quest_revision_migration_edit.json';
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      byId('status').textContent = 'Exported; canonical source replay required.';
    } catch (error) {
      byId('status').textContent = 'Invalid migration plan; nothing exported.';
    }
  });
})();"""


def render_quest_migration_editor(
    documents: Mapping[str, Any], baseline: object, *, authorized: bool,
) -> tuple[bytes, dict[str, Any]]:
    checked = replay_quest_revision_migration(
        documents, baseline, authorized=authorized)
    plan = json.dumps(
        checked["authoring"], sort_keys=True, indent=2,
        ensure_ascii=True, allow_nan=False)
    hash_value = b64encode(sha256(_SCRIPT.encode("utf-8")).digest()).decode("ascii")
    csp = ("default-src 'none'; script-src 'sha256-" + hash_value +
           "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
           "base-uri 'none'; form-action 'none'; object-src 'none'")
    def hidden(key: str, value: str) -> str:
        return ('<input type="hidden" id="' + key + '" value="' +
                escape(value, quote=True) + '">')
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="' + csp + '">'
        '<title>Original quest save migration editor</title></head><body><main>'
        '<h1>Source-bound original quest save migration</h1>'
        '<p>Only explicit reviewed old-choice to new-choice remaps may '
        'preserve a save across authored revisions. Browser export is not proof.</p>'
        + hidden("project", checked["project_id"])
        + hidden("source", checked["old_quest_source_digest"])
        + hidden("session", checked["initial_session_digest"])
        + hidden("baseline", checked["migration_digest"])
        + '<label for="authoring">Typed revision and remap plan</label>'
        '<textarea id="authoring" rows="22" cols="100">'
        + escape(plan, quote=True) + '</textarea>'
        '<button id="export" type="button">Export reviewed remaps</button>'
        '<p id="status" role="status" aria-live="polite"></p>'
        '<p>Recompile in canonical CLI; external rights, native gameplay '
        'and release remain unverified.</p>'
        '</main><script>' + _SCRIPT + '</script></body></html>'
    ).encode("utf-8")
    if len(html) > MAX_HTML_BYTES:
        raise StudioQuestError("migration editor HTML exceeds byte budget")
    return html, {
        "schema": "skeleton.game_builder.studio_quest_revision_migration_editor.v1",
        "baseline_migration_digest": checked["migration_digest"],
        "html_sha256": sha256(html).hexdigest(), "html_bytes": len(html),
        "authoring_export_only": True, "file_write_performed": False,
        "release_certified": False,
    }


def import_quest_migration_editor_export(
    documents: Mapping[str, Any], baseline: object, path: Path, *,
    authorized: bool, expected_source_digest: str,
    expected_initial_session_digest: str,
) -> dict[str, Any]:
    if authorized is not True:
        raise PermissionError("migration editor import requires authorization")
    _lease(expected_source_digest, "migration editor source")
    _lease(expected_initial_session_digest, "migration editor session")
    checked = replay_quest_revision_migration(
        documents, baseline, authorized=True)
    if (checked["old_quest_source_digest"] != expected_source_digest
            or checked["initial_session_digest"] != expected_initial_session_digest):
        raise StudioQuestError("stale migration editor baseline lease")
    if (not isinstance(path, Path) or path.name in ("", ".", "..")
            or len(str(path).encode("utf-8", "strict")) > 4096):
        raise StudioQuestError("invalid migration editor export path")
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
                raise StudioQuestError("migration editor export must be private")
            raw = os.read(handle, MAX_EXPORT_BYTES + 1)
            after = os.fstat(handle)
            if (len(raw) != before.st_size
                    or (before.st_size, before.st_mtime_ns, before.st_ctime_ns,
                        before.st_ino) !=
                    (after.st_size, after.st_mtime_ns, after.st_ctime_ns,
                     after.st_ino)):
                raise StudioQuestError("migration editor export changed during read")
        finally:
            os.close(handle)
    finally:
        os.close(fd)
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise StudioQuestError("duplicate migration editor JSON key")
            result[key] = value
        return result
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"), object_pairs_hook=unique,
            parse_constant=lambda _: (_ for _ in ()).throw(
                StudioQuestError("nonfinite migration editor JSON")))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise StudioQuestError("invalid migration editor export JSON") from exc
    expected = {
        "schema": EXPORT_SCHEMA, "project_id": checked["project_id"],
        "old_quest_source_digest": expected_source_digest,
        "initial_session_digest": expected_initial_session_digest,
        "baseline_migration_digest": checked["migration_digest"],
    }
    if (type(value) is not dict or set(value) != set(expected) | {"authoring"}
            or any(value[key] != item for key, item in expected.items())):
        raise StudioQuestError("forged or stale migration editor export")
    return compile_quest_revision_migration(
        documents, value["authoring"], authorized=True,
        expected_source_digest=expected_source_digest,
        expected_initial_session_digest=expected_initial_session_digest)
