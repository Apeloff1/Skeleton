"""CSP-bound offline editor for source-leased original quest cause plans.

The browser can select target endings and record human review, but it cannot
grant canonical source authority or compile an ending. Exported JSON is
rechecked by the CLI against current source and the initial quest session.
"""
from __future__ import annotations

from base64 import b64encode
from hashlib import sha256
from html import escape
import json
from typing import Any, Mapping

from .studio_ecosystem_quest import (
    StudioQuestError, compile_quest_program, start_quest,
)
from .studio_ecosystem_scene_schedule import _canonical
from .studio_quest_cause_trace import (
    MAX_PLAN_BYTES, PROMPT, propose_quest_cause_trace,
)

MAX_HTML_BYTES = 128 * 1024

_SCRIPT = """(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const original = JSON.parse($('source-plan').textContent);
  $('export').addEventListener('click', () => {
    try {
      const targets = Array.from(document.querySelectorAll(
        'input[name="ending"]:checked')).map(input => input.value);
      if (!targets.length || targets.length > 16 ||
          new Set(targets).size !== targets.length)
        throw Error('select between 1 and 16 distinct endings');
      const plan = Object.assign({}, original, {
        target_endings: targets,
        reviewed: $('reviewed').checked === true
      });
      if (!plan.reviewed) throw Error('explicit review required');
      const raw = JSON.stringify(plan);
      if (new TextEncoder().encode(raw).length > 49152)
        throw Error('plan exceeds byte limit');
      const url = URL.createObjectURL(new Blob([raw], {
        type: 'application/json'
      }));
      const link = document.createElement('a');
      link.href = url;
      link.download = 'quest-cause-plan.json';
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      $('status').textContent = 'Plan exported; canonical CLI replay still required.';
    } catch (_) {
      $('status').textContent = 'Plan not exported; review selection and limits.';
    }
  });
})();"""


def render_quest_cause_editor(
    documents: Mapping[str, Any], plan: object, *, authorized: bool,
) -> bytes:
    if authorized is not True:
        raise PermissionError("causal editor requires operator authorization")
    if type(plan) is not dict or len(_canonical(plan)) > MAX_PLAN_BYTES:
        raise StudioQuestError("invalid bounded causal editor plan")
    program = compile_quest_program(documents)
    initial = start_quest(documents, authorized=True)
    base = propose_quest_cause_trace(
        documents, PROMPT, plan.get("actions"), authorized=True,
        expected_source_digest=program.source_digest,
        expected_initial_session_digest=initial.digest)
    for key in base:
        if key not in ("reviewed", "target_endings") and plan.get(key) != base[key]:
            raise StudioQuestError("causal editor source or session lease changed")
    if set(plan) != set(base) or type(plan.get("reviewed")) is not bool:
        raise StudioQuestError("causal editor plan schema changed")
    targets = plan.get("target_endings")
    known = set(base["target_endings"])
    if (type(targets) is not list or not 1 <= len(targets) <= 16
            or any(type(name) is not str or name not in known for name in targets)
            or len(set(targets)) != len(targets)):
        raise StudioQuestError("causal editor targets are not authored endings")
    choices = "".join(
        '<li><label><input type="checkbox" name="ending" value="' +
        escape(name, quote=True) + '"' +
        (' checked' if name in targets else '') + '>' +
        escape(name, quote=True) + '</label></li>'
        for name in base["target_endings"])
    serialized = json.dumps(base, sort_keys=True, ensure_ascii=True,
                            separators=(",", ":"), allow_nan=False)
    # JSON script data is not HTML-escaped; encode every HTML delimiter and
    # U+2028/U+2029 before embedding it in a script-data element.
    serialized = (serialized.replace("<", "\\u003c")
                  .replace(">", "\\u003e")
                  .replace("&", "\\u0026")
                  .replace("\u2028", "\\u2028")
                  .replace("\u2029", "\\u2029"))
    hash64 = b64encode(sha256(_SCRIPT.encode("utf-8")).digest()).decode("ascii")
    csp = ("default-src 'none'; script-src 'sha256-" + hash64 +
           "'; connect-src 'none'; img-src 'none'; style-src 'none'; "
           "base-uri 'none'; form-action 'none'; object-src 'none'")
    html = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta http-equiv="Content-Security-Policy" content="' + csp + '">'
        '<title>Quest cause authoring review</title></head><body><main>'
        '<h1>Review authored ending causes</h1>'
        '<p>Only selected authored ending predicates will be explained. '
        'Unmet predicates are never invented or awarded.</p>'
        '<fieldset><legend>Target endings</legend><ul>' + choices +
        '</ul></fieldset>'
        '<label><input type="checkbox" id="reviewed"'
        + (' checked' if plan["reviewed"] else '') +
        '>I reviewed the canonical quest action history and source lease.</label>'
        '<button type="button" id="export">Export reviewed plan</button>'
        '<p id="status" role="status" aria-live="polite"></p>'
        '<script type="application/json" id="source-plan">' + serialized +
        '</script><script>' + _SCRIPT + '</script>'
        '<p>Export is not approval of external evidence, native gameplay or release.</p>'
        '</main></body></html>'
    ).encode("utf-8")
    if len(html) > MAX_HTML_BYTES:
        raise StudioQuestError("causal editor HTML exceeds budget")
    return html
