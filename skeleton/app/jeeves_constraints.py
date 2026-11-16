"""Independent bounded verification for explicitly contracted local reasoning.

Never executes model code, imports model-generated modules, fetches resources,
or changes authority. Arithmetic is evaluated by a tiny rational interpreter.
Artifacts are inert data with a closed schema; shape validation is not truth.
"""
from __future__ import annotations

import ast
from fractions import Fraction
from hashlib import sha256
import json
import math
import re

SCHEMA = "skeleton.jeeves.independent-constraint.v1"
MAX_EXPR = 256
MAX_BITS = 512
MAX_NODES = 64
MAX_ARTIFACT_BYTES = 12_288
LANGUAGES = {
    "auto": "", "en": "English", "nb": "Norwegian Bokmål", "nn": "Norwegian Nynorsk",
    "de": "German", "fr": "French", "es": "Spanish", "it": "Italian",
    "pt": "Portuguese", "pl": "Polish", "ja": "Japanese", "ko": "Korean",
    "zh": "Chinese", "ar": "Arabic", "hi": "Hindi",
}
ARTIFACT_KINDS = frozenset({"table", "checklist", "series"})


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def text_digest(value):
    return sha256(value.encode("utf-8")).hexdigest()


def _text(value, limit, *, blank=False):
    if (type(value) is not str or (not blank and not value.strip())
            or len(value) > limit or any(ord(c) < 32 and c not in "\n\t" for c in value)):
        raise ValueError("invalid inert text")
    value.encode("utf-8")
    return value


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate object field")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("nonfinite JSON value")


def _integer(value):
    if len(value.lstrip("-")) > 80:
        raise ValueError("oversized integer")
    return int(value)


def _json(text):
    _text(text, MAX_ARTIFACT_BYTES)
    if len(text.encode("utf-8")) > MAX_ARTIFACT_BYTES:
        raise ValueError("artifact bytes exceed limit")
    try:
        return json.loads(text, object_pairs_hook=_unique,
                          parse_constant=_constant, parse_int=_integer)
    except (RecursionError, OverflowError):
        raise ValueError("unsafe JSON geometry") from None


def _bounded(value):
    if not isinstance(value, Fraction):
        raise ValueError("rational arithmetic required")
    if value.numerator.bit_length() > MAX_BITS or value.denominator.bit_length() > MAX_BITS:
        raise ValueError("arithmetic magnitude exceeded")
    return value


def rational(expression):
    """Closed arithmetic AST, exact rational operations, bounded work.

    Allowed: integer literals, parentheses, unary signs, + - * / ** (small
    integral exponent). No names, attributes, calls, floats, or eval.
    """
    if type(expression) is not str or not 1 <= len(expression) <= MAX_EXPR:
        raise ValueError("bounded expression required")
    if not re.fullmatch(r"[0-9+\-*/() \t]+", expression):
        raise ValueError("unsupported arithmetic character")
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except (SyntaxError, RecursionError, ValueError):
        raise ValueError("invalid arithmetic expression") from None
    if sum(1 for _ in ast.walk(tree)) > MAX_NODES:
        raise ValueError("arithmetic node budget exceeded")

    def visit(node, depth=0):
        if depth > 20:
            raise ValueError("arithmetic depth exceeded")
        if isinstance(node, ast.Constant) and type(node.value) is int:
            return _bounded(Fraction(node.value))
        if isinstance(node, ast.UnaryOp) and type(node.op) in (ast.UAdd, ast.USub):
            x = visit(node.operand, depth + 1)
            return x if isinstance(node.op, ast.UAdd) else -x
        if isinstance(node, ast.BinOp):
            a, b = visit(node.left, depth+1), visit(node.right, depth+1)
            op = type(node.op)
            if op is ast.Add:
                return _bounded(a+b)
            if op is ast.Sub:
                return _bounded(a-b)
            if op is ast.Mult:
                return _bounded(a*b)
            if op is ast.Div:
                if not b:
                    raise ValueError("division by zero")
                return _bounded(a/b)
            if op is ast.Pow:
                if b.denominator != 1 or abs(b.numerator) > 16 or (not a and b < 0):
                    raise ValueError("exponent outside arithmetic policy")
                return _bounded(a**b.numerator)
        raise ValueError("unsupported arithmetic operation")
    return visit(tree.body)


def _decimal_answer(value):
    # Only a single integer, decimal, or rational, not explanatory prose.
    if type(value) is not str or len(value) > 160 or not re.fullmatch(
            r"[+-]?(?:[0-9]{1,80}(?:\.[0-9]{1,80})?|[0-9]{1,80}/[0-9]{1,80})",
            value.strip()):
        raise ValueError("strict numeric answer required")
    try:
        return _bounded(Fraction(value.strip()))
    except (ZeroDivisionError, ValueError):
        raise ValueError("invalid rational answer") from None


def artifact(text, requested_kind):
    value = _json(text)
    if type(value) is not dict or value.get("kind") != requested_kind:
        raise ValueError("artifact kind mismatch")
    _text(value.get("title"), 120)
    if requested_kind == "table":
        if set(value) != {"kind", "title", "columns", "rows"}:
            raise ValueError("table schema mismatch")
        columns, rows = value["columns"], value["rows"]
        if type(columns) is not list or not 1 <= len(columns) <= 8:
            raise ValueError("invalid columns")
        if any(type(c) is not str for c in columns) or len(set(columns)) != len(columns):
            raise ValueError("duplicate or invalid columns")
        for column in columns:
            _text(column, 64)
        if type(rows) is not list or not 1 <= len(rows) <= 32:
            raise ValueError("invalid table rows")
        for row in rows:
            if type(row) is not list or len(row) != len(columns):
                raise ValueError("table geometry mismatch")
            for cell in row:
                _text(cell, 300, blank=True)
    elif requested_kind == "checklist":
        if set(value) != {"kind", "title", "items"} or type(value["items"]) is not list or not 1 <= len(value["items"]) <= 32:
            raise ValueError("checklist schema mismatch")
        for item in value["items"]:
            _text(item, 300)
    elif requested_kind == "series":
        if set(value) != {"kind", "title", "unit", "points"}:
            raise ValueError("series schema mismatch")
        _text(value["unit"], 24)
        points = value["points"]
        if type(points) is not list or not 1 <= len(points) <= 48:
            raise ValueError("invalid series length")
        labels = set()
        for point in points:
            if type(point) is not dict or set(point) != {"label", "value"}:
                raise ValueError("invalid series point")
            label = _text(point["label"], 64)
            number = point["value"]
            if (label in labels or type(number) not in (int, float)
                    or not math.isfinite(number) or not -1e12 <= number <= 1e12):
                raise ValueError("invalid or duplicate series point")
            labels.add(label)
    else:
        raise ValueError("unsupported artifact")
    return value


def normalize_policy(value, candidate_tokens):
    if (type(value) is not dict or set(value) != {
        "max_attempts", "maximum_reserved_tokens", "language", "contract"
    } or type(candidate_tokens) is not int or not 1 <= candidate_tokens <= 128):
        raise ValueError("exact adaptive reasoning policy required")
    attempts, total = value["max_attempts"], value["maximum_reserved_tokens"]
    if (type(attempts) is not int or not 1 <= attempts <= 4
            or type(total) is not int or not candidate_tokens <= total <= 512
            or type(value["language"]) is not str or value["language"] not in LANGUAGES):
        raise ValueError("invalid adaptive compute or language budget")
    contract = value["contract"]
    if type(contract) is not dict or type(contract.get("kind")) is not str:
        raise ValueError("explicit verification contract required")
    kind = contract["kind"]
    if kind == "review" and set(contract) == {"kind"}:
        pass
    elif kind == "arithmetic" and set(contract) == {"kind", "expression"}:
        rational(contract["expression"])
    elif kind == "artifact" and set(contract) == {"kind", "artifact_kind"}:
        if type(contract["artifact_kind"]) is not str or contract["artifact_kind"] not in ARTIFACT_KINDS:
            raise ValueError("unsupported artifact contract")
    else:
        raise ValueError("unknown verification contract")
    return {"max_attempts": attempts, "maximum_reserved_tokens": total,
            "language": value["language"], "contract": dict(contract)}


def prompt_suffix(policy):
    contract = policy["contract"]
    kind = contract["kind"]
    language = LANGUAGES[policy["language"]]
    suffix = (" Use " + language + " for natural-language content." if language else "")
    if kind == "arithmetic":
        # Exact expression is explicitly supplied by the operator, not
        # extracted from arbitrary prose or a previous model response.
        suffix += (" Return only the exact numeric result of this expression: "
                   + contract["expression"] + ". No explanation.")
    elif kind == "artifact":
        geometry = {
            "table": '{"kind":"table","title":"...","columns":["..."],"rows":[["..."]]}',
            "checklist": '{"kind":"checklist","title":"...","items":["..."]}',
            "series": '{"kind":"series","title":"...","unit":"...","points":[{"label":"...","value":0}]}',
        }[contract["artifact_kind"]]
        suffix += " Return only one JSON object with this exact shape: " + geometry
    return suffix


def assess(text, contract):
    """Independent check of correctness *only* for the explicit contract."""
    _text(text, 16384)
    kind = contract["kind"]
    verdict = {"schema": SCHEMA, "contract_sha256": digest(contract),
               "output_sha256": text_digest(text), "kind": kind,
               "passed": False, "code": "review_required", "artifact": None,
               "semantic_truth_verified": False}
    try:
        if kind == "arithmetic":
            expected = rational(contract["expression"])
            actual = _decimal_answer(text)
            verdict["passed"] = actual == expected
            verdict["code"] = "exact_arithmetic_match" if actual == expected else "numeric_mismatch"
        elif kind == "artifact":
            verdict["artifact"] = artifact(text, contract["artifact_kind"])
            verdict["passed"] = True
            verdict["code"] = "schema_valid_not_fact_checked"
    except (ValueError, UnicodeError):
        verdict["code"] = "invalid_numeric_format" if kind == "arithmetic" else "invalid_artifact_schema"
    verdict["verifier_sha256"] = digest(verdict)
    return verdict
