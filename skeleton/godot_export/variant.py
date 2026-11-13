"""Godot Variant text literal parsing and serialisation.

Godot's ConfigFile/``project.godot``/``.tscn`` formats store values as Variant
text literals: ``"str"``, ``42``, ``1.5``, ``true``, ``null``, ``[a, b]``,
``{"k": v}``, and constructor calls such as ``Vector2(1, 2)`` or
``PackedStringArray("a", "b")``. This module implements a small recursive
descent parser for that grammar.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class VariantParseError(ValueError):
    """Raised when a Variant literal cannot be parsed."""


@dataclass(frozen=True)
class Constructor:
    """A typed constructor literal such as ``Vector3(0, 1, 0)``."""

    name: str
    args: tuple[Any, ...] = field(default_factory=tuple)

    def __str__(self) -> str:  # pragma: no cover - convenience
        return dump(self)


@dataclass(frozen=True)
class StringName:
    """``&"name"`` literal."""

    value: str


@dataclass(frozen=True)
class NodePath:
    """``^"path"`` literal."""

    value: str


_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "'": "'"}


class _Parser:
    def __init__(self, text: str) -> None:
        self.text = text
        self.pos = 0

    def error(self, msg: str) -> VariantParseError:
        return VariantParseError(f"{msg} at offset {self.pos} in {self.text[:80]!r}")

    def skip_ws(self) -> None:
        while self.pos < len(self.text) and self.text[self.pos] in " \t\r\n":
            self.pos += 1

    def peek(self) -> str:
        self.skip_ws()
        return self.text[self.pos] if self.pos < len(self.text) else ""

    def expect(self, ch: str) -> None:
        if self.peek() != ch:
            raise self.error(f"expected {ch!r}")
        self.pos += 1

    def parse_value(self) -> Any:
        ch = self.peek()
        if not ch:
            raise self.error("unexpected end")
        if ch == '"':
            return self.parse_string()
        if ch == "&":
            self.pos += 1
            return StringName(self.parse_string())
        if ch == "^":
            self.pos += 1
            return NodePath(self.parse_string())
        if ch == "[":
            return self.parse_array()
        if ch == "{":
            return self.parse_dict()
        if ch == "-" or ch == "." or ch.isdigit():
            return self.parse_number()
        if ch.isalpha() or ch == "_":
            return self.parse_ident()
        raise self.error(f"unexpected {ch!r}")

    def parse_string(self) -> str:
        self.expect('"')
        out: list[str] = []
        while True:
            if self.pos >= len(self.text):
                raise self.error("unterminated string")
            ch = self.text[self.pos]
            self.pos += 1
            if ch == '"':
                return "".join(out)
            if ch == "\\":
                if self.pos >= len(self.text):
                    raise self.error("dangling escape")
                esc = self.text[self.pos]
                self.pos += 1
                if esc == "u":
                    code = self.text[self.pos:self.pos + 4]
                    if len(code) != 4:
                        raise self.error("bad unicode escape")
                    out.append(chr(int(code, 16)))
                    self.pos += 4
                else:
                    out.append(_ESCAPES.get(esc, esc))
            else:
                out.append(ch)

    def parse_number(self) -> int | float:
        start = self.pos
        if self.text[self.pos] == "-":
            self.pos += 1
        while self.pos < len(self.text) and (self.text[self.pos].isalnum() or self.text[self.pos] in ".+-_"):
            if self.text[self.pos] in "+-" and self.text[self.pos - 1] not in "eE":
                break
            self.pos += 1
        token = self.text[start:self.pos]
        if token in ("-inf",):
            return float("-inf")
        try:
            if any(c in token for c in ".eE") and not token.lower().startswith(("0x", "-0x")):
                return float(token)
            return int(token, 0)
        except ValueError as exc:
            raise self.error(f"bad number {token!r}") from exc

    def parse_ident(self) -> Any:
        start = self.pos
        while self.pos < len(self.text) and (self.text[self.pos].isalnum() or self.text[self.pos] == "_"):
            self.pos += 1
        name = self.text[start:self.pos]
        if name == "true":
            return True
        if name == "false":
            return False
        if name == "null":
            return None
        if name == "inf":
            return float("inf")
        if name == "nan":
            return float("nan")
        if name in ("Array", "Dictionary") and self.pos < len(self.text) and self.text[self.pos] == "[":
            # Typed containers: ``Array[int]([1, 2])`` / ``Dictionary[String, int]({...})``.
            end = self.text.find("]", self.pos)
            if end < 0:
                raise self.error("unterminated container type")
            name += self.text[self.pos:end + 1].replace(" ", "")
            self.pos = end + 1
        if self.peek() != "(":
            raise self.error(f"bare identifier {name!r}")
        self.pos += 1
        args: list[Any] = []
        if self.peek() == ")":
            self.pos += 1
            return Constructor(name, ())
        while True:
            args.append(self.parse_value())
            ch = self.peek()
            if ch == ",":
                self.pos += 1
                continue
            if ch == ")":
                self.pos += 1
                return Constructor(name, tuple(args))
            raise self.error("expected ',' or ')'")

    def parse_array(self) -> list[Any]:
        self.expect("[")
        items: list[Any] = []
        if self.peek() == "]":
            self.pos += 1
            return items
        while True:
            items.append(self.parse_value())
            ch = self.peek()
            if ch == ",":
                self.pos += 1
                if self.peek() == "]":
                    self.pos += 1
                    return items
                continue
            if ch == "]":
                self.pos += 1
                return items
            raise self.error("expected ',' or ']'")

    def parse_dict(self) -> dict[Any, Any]:
        self.expect("{")
        out: dict[Any, Any] = {}
        if self.peek() == "}":
            self.pos += 1
            return out
        while True:
            key = self.parse_value()
            self.expect(":")
            out[_hashable(key)] = self.parse_value()
            ch = self.peek()
            if ch == ",":
                self.pos += 1
                if self.peek() == "}":
                    self.pos += 1
                    return out
                continue
            if ch == "}":
                self.pos += 1
                return out
            raise self.error("expected ',' or '}'")


def _hashable(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(value)
    return value


def parse(text: str) -> Any:
    """Parse one complete Variant literal; trailing garbage is an error."""
    p = _Parser(text)
    value = p.parse_value()
    p.skip_ws()
    if p.pos != len(text):
        raise p.error("trailing characters")
    return value


def parse_prefix(text: str) -> tuple[Any, int]:
    """Parse a Variant literal from the start of ``text``; return value and end offset."""
    p = _Parser(text)
    value = p.parse_value()
    return value, p.pos


def is_complete(text: str) -> bool:
    """True when brackets/quotes in ``text`` are balanced (multi-line values)."""
    depth = 0
    in_str = False
    esc = False
    for ch in text:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
    return depth <= 0 and not in_str


def _fmt_float(value: float) -> str:
    if value != value:
        return "nan"
    if value in (float("inf"), float("-inf")):
        return "inf" if value > 0 else "-inf"
    text = repr(value)
    return text if any(c in text for c in ".e") else text + ".0"


def dump_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")
    return f'"{escaped}"'


def dump(value: Any) -> str:
    """Serialise a Python value back to Godot Variant text."""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return _fmt_float(value)
    if isinstance(value, str):
        return dump_string(value)
    if isinstance(value, StringName):
        return "&" + dump_string(value.value)
    if isinstance(value, NodePath):
        return "^" + dump_string(value.value)
    if isinstance(value, Constructor):
        return f"{value.name}(" + ", ".join(dump(a) for a in value.args) + ")"
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(dump(v) for v in value) + "]"
    if isinstance(value, dict):
        if not value:
            return "{}"
        body = ",\n".join(f"{dump(k)}: {dump(v)}" for k, v in value.items())
        return "{\n" + body + "\n}"
    raise TypeError(f"cannot dump {type(value).__name__}")
