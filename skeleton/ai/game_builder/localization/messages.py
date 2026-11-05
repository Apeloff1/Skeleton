"""Minimal ICU-style message syntax: ``{name}``, plural and select (gender).

  "{count, plural, =0 {No coins} one {# coin} other {# coins}}"
  "{gender, select, female {She} male {He} other {They}} found {item}."

``'`` escapes a brace as in ICU (``'{'``, ``''`` for a quote).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Union

from .plurals import PLURAL_CATEGORIES, categories_for, is_rtl, plural_category, wrap_bidi

MAX_MESSAGE = 4096
MAX_DEPTH = 6


class MessageError(ValueError):
    """Malformed message or missing/invalid argument."""


@dataclass(frozen=True)
class Arg:
    name: str


@dataclass(frozen=True)
class Choice:
    name: str
    kind: str  # "plural" | "select"
    options: dict[str, tuple["Node", ...]]


Node = Union[str, Arg, Choice, "Hash"]


@dataclass(frozen=True)
class Hash:
    pass


class _P:
    def __init__(self, s: str) -> None:
        self.s, self.i = s, 0

    def text(self, depth: int, in_plural: bool) -> tuple[Node, ...]:
        if depth > MAX_DEPTH:
            raise MessageError("message nests too deeply")
        out: list[Node] = []
        buf: list[str] = []
        s = self.s
        while self.i < len(s):
            c = s[self.i]
            if c == "'":
                if s.startswith("''", self.i):
                    buf.append("'")
                    self.i += 2
                    continue
                end = s.find("'", self.i + 1)
                if end > self.i + 1 and s[self.i + 1] in "{}#":
                    buf.append(s[self.i + 1:end])
                    self.i = end + 1
                    continue
                buf.append(c)
                self.i += 1
            elif c == "{":
                if buf:
                    out.append("".join(buf))
                    buf = []
                out.append(self.arg(depth, in_plural))
            elif c == "}":
                break
            elif c == "#" and in_plural:
                if buf:
                    out.append("".join(buf))
                    buf = []
                out.append(Hash())
                self.i += 1
            else:
                buf.append(c)
                self.i += 1
        if buf:
            out.append("".join(buf))
        return tuple(out)

    def _ident(self) -> str:
        self._ws()
        j = self.i
        while self.i < len(self.s) and (self.s[self.i].isalnum() or self.s[self.i] in "_=."):
            self.i += 1
        if j == self.i:
            raise MessageError(f"expected identifier at {j}")
        return self.s[j:self.i]

    def _ws(self) -> None:
        while self.i < len(self.s) and self.s[self.i].isspace():
            self.i += 1

    def _expect(self, ch: str) -> None:
        self._ws()
        if self.i >= len(self.s) or self.s[self.i] != ch:
            raise MessageError(f"expected {ch!r} at {self.i}")
        self.i += 1

    def arg(self, depth: int, in_plural: bool = False) -> Node:
        self._expect("{")
        name = self._ident()
        self._ws()
        if self.i < len(self.s) and self.s[self.i] == "}":
            self.i += 1
            return Arg(name)
        self._expect(",")
        kind = self._ident()
        if kind not in ("plural", "select"):
            raise MessageError(f"unsupported argument type {kind!r}")
        self._expect(",")
        options: dict[str, tuple[Node, ...]] = {}
        while True:
            self._ws()
            if self.i < len(self.s) and self.s[self.i] == "}":
                self.i += 1
                break
            key = self._ident()
            if key in options:
                raise MessageError(f"duplicate option {key!r}")
            if kind == "plural" and key not in PLURAL_CATEGORIES and not (
                    key.startswith("=") and key[1:].isdigit()):
                raise MessageError(f"invalid plural category {key!r}")
            self._expect("{")
            options[key] = self.text(depth + 1, kind == "plural" or in_plural)
            self._expect("}")
        if "other" not in options:
            raise MessageError(f"{name}: '{kind}' needs an 'other' option")
        return Choice(name, kind, options)


def parse_message(text: str) -> tuple[Node, ...]:
    if not isinstance(text, str) or len(text) > MAX_MESSAGE:
        raise MessageError("message must be a string within size limit")
    p = _P(text)
    nodes = p.text(0, False)
    if p.i != len(text):
        raise MessageError(f"unbalanced '}}' at {p.i}")
    return nodes


def _walk(nodes, out: dict[str, set[str]]) -> None:
    for n in nodes:
        if isinstance(n, Arg):
            out.setdefault(n.name, set()).add("arg")
        elif isinstance(n, Choice):
            out.setdefault(n.name, set()).add(n.kind)
            for sub in n.options.values():
                _walk(sub, out)


def arguments(text: str) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    _walk(parse_message(text), out)
    return out


def check_placeholders(source: str, translation: str, locale: str | None = None) -> list[str]:
    """Problems with ``translation`` relative to ``source``; empty list means OK."""
    try:
        src = arguments(source)
    except MessageError as exc:
        return [f"source does not parse: {exc}"]
    try:
        dst = arguments(translation)
        nodes = parse_message(translation)
    except MessageError as exc:
        return [f"translation does not parse: {exc}"]
    problems = [f"missing placeholder {{{k}}}" for k in sorted(set(src) - set(dst))]
    problems += [f"unknown placeholder {{{k}}}" for k in sorted(set(dst) - set(src))]
    problems += [f"placeholder {{{k}}} used as {sorted(dst[k])} but source uses {sorted(src[k])}"
                 for k in sorted(set(src) & set(dst)) if src[k] != dst[k]]
    if locale:
        need = categories_for(locale)
        for ch in _choices(nodes):
            if ch.kind == "plural":
                missing = sorted(need - set(ch.options))
                if missing:
                    problems.append(f"plural {{{ch.name}}} lacks {locale} categories {missing}")
    return problems


def _choices(nodes):
    for n in nodes:
        if isinstance(n, Choice):
            yield n
            for sub in n.options.values():
                yield from _choices(sub)


def format_message(text: str, args: Mapping[str, Any], locale: str, *, isolate: bool = False) -> str:
    """Render ``text`` for ``locale``. ``isolate`` wraps values in bidi isolates."""
    rtl = is_rtl(locale)

    def val(v: Any) -> str:
        s = str(v)
        return wrap_bidi(s) if isolate or (rtl and s.isascii() and s.strip()) else s

    def render(nodes, number=None) -> str:
        out: list[str] = []
        for n in nodes:
            if isinstance(n, str):
                out.append(n)
            elif isinstance(n, Hash):
                out.append(str(number))
            elif isinstance(n, Arg):
                if n.name not in args:
                    raise MessageError(f"missing argument {n.name!r}")
                out.append(val(args[n.name]))
            else:
                if n.name not in args:
                    raise MessageError(f"missing argument {n.name!r}")
                v = args[n.name]
                if n.kind == "plural":
                    if isinstance(v, bool) or not isinstance(v, int | float):
                        raise MessageError(f"plural argument {n.name!r} must be a number")
                    exact = f"={v}" if float(v).is_integer() else None
                    key = exact if exact in n.options else plural_category(locale, v)
                    out.append(render(n.options.get(key, n.options["other"]), v))
                else:
                    out.append(render(n.options.get(str(v), n.options["other"]), number))
        return "".join(out)

    return render(parse_message(text))
