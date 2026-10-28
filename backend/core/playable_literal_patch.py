"""Bounded runtime-repair proposals over the canonical exact-anchor edit owner.

Model output is inert JSON data. This adapter never executes code, accesses a
filesystem, creates a provider, or grants publication/ownership authority.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re

from skeleton.automation.build_contracts import BuildBudget
from skeleton.automation.build_edits import AppliedEdit, FileEditPlan, TextEdit, apply_edit_plan

MAX_RESPONSE_BYTES = 32 * 1024
MAX_SOURCE_BYTES = 64 * 1024
MAX_CANDIDATE_BYTES = 64 * 1024
MAX_ANCHOR_BYTES = 4 * 1024
MAX_TOTAL_EDIT_BYTES = 16 * 1024
MAX_EDITS = 8
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_PATH = "playable.html"  # Server-owned logical path; never used for filesystem I/O.
_BUDGET = BuildBudget(max_files=1, max_total_bytes=MAX_SOURCE_BYTES,
                      max_file_bytes=MAX_CANDIDATE_BYTES, max_context_bytes=MAX_SOURCE_BYTES,
                      max_model_calls=1, max_rounds=1)

RESPONSE_SCHEMA = {
    "type": "object",
    "required": ["schema_version", "edits"],
    "additionalProperties": False,
    "properties": {
        "schema_version": {"type": "integer", "enum": [1]},
        "source_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "edits": {
            "type": "array", "minItems": 1, "maxItems": MAX_EDITS,
            "items": {
                "type": "object", "required": ["find", "replace"],
                "additionalProperties": False,
                "properties": {
                    "find": {"type": "string", "minLength": 1, "maxLength": MAX_ANCHOR_BYTES},
                    "replace": {"type": "string", "maxLength": MAX_ANCHOR_BYTES},
                },
            },
        },
    },
}


class LiteralPatchError(ValueError):
    """A source-bound proposal failed a stable, content-free safety check."""

    def __init__(self, code: str):
        self.code = code
        super().__init__("Runtime repair proposal was rejected (" + code + ").")


@dataclass(frozen=True, slots=True)
class LiteralPatchResult:
    candidate: str
    before_digest: str
    after_digest: str
    patch_fingerprint: str
    edit_count: int
    evidence: tuple[AppliedEdit, ...]


def _fail(code: str):
    raise LiteralPatchError(code)


def _encoded(value: object, *, limit: int, allow_empty: bool = False) -> bytes:
    if not isinstance(value, str) or "\0" in value or not allow_empty and not value:
        _fail("literal_patch_invalid_text")
    # Reject enormous strings before allocating their encoded representation.
    if len(value) > limit:
        _fail("literal_patch_limit_exceeded")
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        raise LiteralPatchError("literal_patch_invalid_utf8") from None
    if len(encoded) > limit:
        _fail("literal_patch_limit_exceeded")
    return encoded


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail("literal_patch_duplicate_field")
        result[key] = value
    return result


def _nonfinite(_value):
    _fail("literal_patch_invalid_json")


def _finite_float(value):
    number = float(value)
    if not math.isfinite(number):
        _fail("literal_patch_invalid_json")
    return number


def _response(response: object) -> dict:
    if isinstance(response, bytes):
        if len(response) > MAX_RESPONSE_BYTES:
            _fail("literal_patch_limit_exceeded")
        try:
            response = response.decode("utf-8")
        except UnicodeDecodeError:
            raise LiteralPatchError("literal_patch_invalid_utf8") from None
    _encoded(response, limit=MAX_RESPONSE_BYTES)
    try:
        proposal = json.loads(response, object_pairs_hook=_unique_object,
                              parse_constant=_nonfinite, parse_float=_finite_float)
    except LiteralPatchError:
        raise
    except (ValueError, RecursionError):
        raise LiteralPatchError("literal_patch_invalid_json") from None
    if not isinstance(proposal, dict) or set(proposal) not in (
        {"schema_version", "edits"}, {"schema_version", "edits", "source_sha256"},
    ):
        _fail("literal_patch_invalid_schema")
    if type(proposal["schema_version"]) is not int or proposal["schema_version"] != 1:
        _fail("literal_patch_invalid_schema")
    return proposal


def _one_anchor(source: str, anchor: str) -> int:
    start = source.find(anchor)
    if start < 0:
        _fail("literal_patch_anchor_missing")
    # str.count misses overlapping occurrences: "aaa" occurs twice in "aaaa".
    if source.find(anchor, start + 1) >= 0:
        _fail("literal_patch_anchor_ambiguous")
    return start


def apply_literal_patch(source: str, response: str | bytes, *, expected_source_sha256: str) -> LiteralPatchResult:
    """Apply all edits to a trusted exact source snapshot, or return no candidate.

    The server supplies the source digest. A model's optional echo never grants
    authority. Every original anchor is unique, ranges may not overlap, and
    later replacements cannot silently retarget an earlier original anchor.
    """
    before = _encoded(source, limit=MAX_SOURCE_BYTES)
    before_digest = hashlib.sha256(before).hexdigest()
    if not isinstance(expected_source_sha256, str) or _DIGEST.fullmatch(expected_source_sha256) is None:
        _fail("literal_patch_invalid_source_digest")
    if before_digest != expected_source_sha256:
        _fail("literal_patch_source_changed")
    proposal = _response(response)
    if "source_sha256" in proposal:
        echo = proposal["source_sha256"]
        if not isinstance(echo, str) or _DIGEST.fullmatch(echo) is None:
            _fail("literal_patch_invalid_source_digest")
        if echo != before_digest:
            _fail("literal_patch_source_changed")
    raw_edits = proposal["edits"]
    if not isinstance(raw_edits, list) or not 1 <= len(raw_edits) <= MAX_EDITS:
        _fail("literal_patch_invalid_edits")
    located = []
    seen, total = set(), 0
    for item in raw_edits:
        if not isinstance(item, dict) or set(item) != {"find", "replace"}:
            _fail("literal_patch_invalid_schema")
        anchor, replacement = item["find"], item["replace"]
        total += len(_encoded(anchor, limit=MAX_ANCHOR_BYTES))
        total += len(_encoded(replacement, limit=MAX_ANCHOR_BYTES, allow_empty=True))
        if total > MAX_TOTAL_EDIT_BYTES:
            _fail("literal_patch_limit_exceeded")
        if anchor == replacement:
            _fail("literal_patch_no_change")
        if anchor in seen:
            _fail("literal_patch_duplicate_edit")
        seen.add(anchor)
        position = _one_anchor(source, anchor)
        located.append((position, position + len(anchor), TextEdit("replace", anchor, replacement)))
    located.sort(key=lambda value: value[0])
    if any(left[1] > right[0] for left, right in zip(located, located[1:])):
        _fail("literal_patch_overlapping_edits")
    located.reverse()
    plan = FileEditPlan(_PATH, tuple(item[2] for item in located), intent="Source-bound runtime repair")
    current, evidence = source, []
    for original_position, _end, edit in located:
        # Canonical apply_edit_plan deliberately edits in listed order. Strict
        # prechecks additionally catch overlapping ambiguity introduced by a
        # previous replacement, instead of relying on its non-overlap count.
        if _one_anchor(current, edit.anchor) != original_position:
            _fail("literal_patch_anchor_changed")
        single = FileEditPlan(_PATH, (edit,), intent=plan.intent)
        try:
            candidate, applied = apply_edit_plan(current, single, budget=_BUDGET)
        except Exception:
            # Canonical errors must not expose source or proposal contents.
            raise LiteralPatchError("literal_patch_apply_failed") from None
        current = candidate.content
        _encoded(current, limit=MAX_CANDIDATE_BYTES, allow_empty=True)
        evidence.append(applied)
    after_digest = hashlib.sha256(current.encode("utf-8")).hexdigest()
    if after_digest == before_digest:
        _fail("literal_patch_no_change")
    return LiteralPatchResult(current, before_digest, after_digest, plan.fingerprint, len(located), tuple(evidence))
