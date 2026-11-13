"""Parser for Godot text scene/resource files (``.tscn`` / ``.tres``).

Format: bracketed headers (``[gd_scene ...]``, ``[ext_resource ...]``,
``[sub_resource ...]``, ``[node ...]``, ``[connection ...]``, ``[resource]``)
whose attributes are ``key=Variant`` pairs, each followed by property lines.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import variant

_HEADER = re.compile(r"^\[(?P<tag>[a-z_]+)(?P<attrs>.*)\]\s*$")
_ATTR_KEY = re.compile(r"\s*([A-Za-z_][A-Za-z0-9_]*)=")
_PROP = re.compile(r"^(?P<key>[^=\s][^=]*?)\s*=\s*(?P<value>.*)$")


class SceneParseError(ValueError):
    pass


@dataclass
class Block:
    tag: str
    attrs: dict[str, Any] = field(default_factory=dict)
    props: dict[str, Any] = field(default_factory=dict)
    line: int = 0


@dataclass
class ExtResource:
    id: str
    type: str
    path: str
    uid: str = ""


@dataclass
class Node:
    name: str
    type: str | None
    parent: str | None
    props: dict[str, Any]
    instance: str | None = None

    @property
    def path(self) -> str:
        if self.parent is None:
            return "."
        if self.parent == ".":
            return self.name
        return f"{self.parent}/{self.name}"


@dataclass
class Scene:
    header: Block
    blocks: list[Block]
    path: str = ""

    @property
    def kind(self) -> str:
        return self.header.tag

    @property
    def format(self) -> int | None:
        v = self.header.attrs.get("format")
        return v if isinstance(v, int) else None

    @property
    def ext_resources(self) -> list[ExtResource]:
        out = []
        for b in self.blocks:
            if b.tag == "ext_resource":
                out.append(ExtResource(str(b.attrs.get("id", "")), str(b.attrs.get("type", "")),
                                       str(b.attrs.get("path", "")), str(b.attrs.get("uid", ""))))
        return out

    @property
    def sub_resources(self) -> list[Block]:
        return [b for b in self.blocks if b.tag == "sub_resource"]

    @property
    def nodes(self) -> list[Node]:
        out = []
        for b in self.blocks:
            if b.tag != "node":
                continue
            inst = b.attrs.get("instance")
            inst_id = None
            if isinstance(inst, variant.Constructor) and inst.name == "ExtResource" and inst.args:
                inst_id = str(inst.args[0])
            out.append(Node(str(b.attrs.get("name", "")), b.attrs.get("type"), b.attrs.get("parent"), b.props, inst_id))
        return out

    @property
    def connections(self) -> list[Block]:
        return [b for b in self.blocks if b.tag == "connection"]

    def nodes_of_type(self, type_name: str) -> list[Node]:
        return [n for n in self.nodes if n.type == type_name]

    def root(self) -> Node | None:
        for n in self.nodes:
            if n.parent is None:
                return n
        return None

    def referenced_ids(self) -> set[tuple[str, str]]:
        """All ``ExtResource("id")`` / ``SubResource("id")`` uses in props and attrs."""
        found: set[tuple[str, str]] = set()

        def walk(v: Any) -> None:
            if isinstance(v, variant.Constructor):
                if v.name in ("ExtResource", "SubResource") and v.args:
                    found.add((v.name, str(v.args[0])))
                for a in v.args:
                    walk(a)
            elif isinstance(v, (list, tuple)):
                for a in v:
                    walk(a)
            elif isinstance(v, dict):
                for a in v.values():
                    walk(a)

        for b in self.blocks:
            for v in list(b.attrs.values()) + list(b.props.values()):
                walk(v)
        return found


def _parse_attrs(text: str, line: int) -> dict[str, Any]:
    attrs: dict[str, Any] = {}
    pos = 0
    while pos < len(text):
        if text[pos:].strip() == "":
            break
        m = _ATTR_KEY.match(text, pos)
        if not m:
            raise SceneParseError(f"line {line}: bad attribute near {text[pos:pos+30]!r}")
        key = m.group(1)
        try:
            value, consumed = variant.parse_prefix(text[m.end():])
        except variant.VariantParseError as exc:
            raise SceneParseError(f"line {line}: {exc}") from exc
        attrs[key] = value
        pos = m.end() + consumed
    return attrs


def loads(text: str, path: str = "") -> Scene:
    blocks: list[Block] = []
    current: Block | None = None
    pending: tuple[str, list[str], int] | None = None
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if pending is not None:
            key, buf, start = pending
            buf.append(raw)
            joined = "\n".join(buf)
            if variant.is_complete(joined):
                try:
                    current.props[key] = variant.parse(joined.strip())  # type: ignore[union-attr]
                except variant.VariantParseError as exc:
                    raise SceneParseError(f"{path}:{start}: {exc}") from exc
                pending = None
            continue
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        m = _HEADER.match(line)
        if m:
            current = Block(m.group("tag"), _parse_attrs(m.group("attrs"), lineno), {}, lineno)
            blocks.append(current)
            continue
        if current is None:
            raise SceneParseError(f"{path}:{lineno}: property before any header")
        m = _PROP.match(line)
        if not m:
            raise SceneParseError(f"{path}:{lineno}: unparseable line {line!r}")
        value = m.group("value")
        if variant.is_complete(value):
            try:
                current.props[m.group("key").strip()] = variant.parse(value.strip())
            except variant.VariantParseError as exc:
                raise SceneParseError(f"{path}:{lineno}: {exc}") from exc
        else:
            pending = (m.group("key").strip(), [value], lineno)
    if pending is not None:
        raise SceneParseError(f"{path}:{pending[2]}: unterminated value")
    if not blocks or blocks[0].tag not in ("gd_scene", "gd_resource"):
        raise SceneParseError(f"{path}: missing gd_scene/gd_resource header")
    return Scene(blocks[0], blocks[1:], path)


def load(path: str | Path) -> Scene:
    p = Path(path)
    return loads(p.read_text(encoding="utf-8"), str(p))
