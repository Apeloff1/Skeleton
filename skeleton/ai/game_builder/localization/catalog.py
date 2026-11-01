"""Per-locale string tables for builder games: extraction, resolution, audits.

Fallback chains and locale normalization come from
``skeleton.contracts.localization`` (LocaleId, LocaleFallbackPolicy).
Each translation records the source hash it was made from, so a changed
source string makes the translation *stale* rather than silently wrong.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Iterable, Mapping, Protocol, runtime_checkable

from skeleton.contracts.localization import LocaleFallbackPolicy, LocaleId

from .messages import MessageError, check_placeholders, format_message, parse_message
from .plurals import text_direction

SCHEMA = "skeleton.game_builder.localization.v1"
TEXT_FIELDS = frozenset({"name", "title", "description", "text", "dialogue", "label", "prompt",
                         "summary", "line", "lines", "message", "tooltip", "hint", "objective",
                         "caption", "subtitle", "flavor", "quest_text", "choices"})
_ID_FIELDS = ("id", "key", "slug")
_SEG = re.compile(r"[^a-z0-9]+")
MAX_EXTRACT_NODES = 10_000
MAX_EXTRACT_DEPTH = 32
MAX_EXTRACT_STRINGS = 4_096


def source_hash(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class SourceString:
    key: str
    text: str
    context: str = ""

    @property
    def hash(self) -> str:
        return source_hash(self.text)


def _seg(v: Any) -> str:
    s = _SEG.sub("_", str(v).lower()).strip("_")
    return s or "x"


def extract_strings(data: Any, prefix: str = "game", *,
                    fields: Iterable[str] = TEXT_FIELDS) -> list[SourceString]:
    """Pull player-facing strings out of a plan/forge structure.

    Keys follow the structure; list items use their ``id``/``key``/``slug`` when
    present so keys stay stable when items are reordered.
    """
    wanted = frozenset(fields)
    out: dict[str, SourceString] = {}

    def item_seg(i: int, item: Any) -> str:
        if isinstance(item, Mapping):
            for f in _ID_FIELDS:
                if isinstance(item.get(f), str | int) and not isinstance(item.get(f), bool):
                    return _seg(item[f])
        return str(i)

    def add(key: str, text: str, ctx: str) -> None:
        if text.strip():
            if len(text) > 4096:
                raise ValueError("source localization text exceeds message bound")
            if key in out and out[key].text != text:
                raise ValueError(f"key collision at {key}")
            if key not in out and len(out) >= MAX_EXTRACT_STRINGS:
                raise ValueError("source localization string capacity exceeded")
            out[key] = SourceString(key, text, ctx)

    nodes_seen = 0
    active_containers: set[int] = set()

    def walk(node: Any, path: str, take: bool, ctx: str, depth: int = 0) -> None:
        nonlocal nodes_seen
        nodes_seen += 1
        if nodes_seen > MAX_EXTRACT_NODES or depth > MAX_EXTRACT_DEPTH:
            raise ValueError("source localization traversal budget exceeded")
        is_container = isinstance(node, (Mapping, list, tuple))
        if is_container:
            identity = id(node)
            if identity in active_containers:
                raise ValueError("cyclic source localization structure")
            active_containers.add(identity)
        try:
            if isinstance(node, Mapping):
                for k in sorted(node, key=str):
                    v = node[k]
                    sub = f"{path}.{_seg(k)}"
                    walk(v, sub, str(k) in wanted, str(k), depth + 1)
            elif isinstance(node, list | tuple):
                for i, item in enumerate(node):
                    walk(item, f"{path}.{item_seg(i, item)}", take, ctx, depth + 1)
            elif isinstance(node, str) and take:
                add(path, node, ctx)
        finally:
            if is_container:
                active_containers.remove(identity)

    walk(data, _seg(prefix), False, "")
    return [out[k] for k in sorted(out)]


@dataclass
class Translation:
    text: str
    source_hash: str
    reviewed: bool = False
    provider: str = ""


@dataclass
class LocaleTable:
    locale: str
    entries: dict[str, Translation] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.locale = LocaleId(self.locale).value

    @property
    def direction(self) -> str:
        return text_direction(self.locale)

    def set(self, src: SourceString, text: str, *, reviewed: bool = False, provider: str = "") -> None:
        problems = check_placeholders(src.text, text, self.locale)
        if problems:
            raise MessageError(f"{self.locale}:{src.key}: " + "; ".join(problems))
        self.entries[src.key] = Translation(text, src.hash, reviewed, provider)


@dataclass(frozen=True)
class AuditIssue:
    locale: str
    key: str
    code: str  # missing | stale | placeholder | orphan | unreviewed
    detail: str = ""


@runtime_checkable
class TranslationProvider(Protocol):
    """Offline-pluggable translator. Implementations must not be required by core code."""

    name: str

    def translate(self, source: SourceString, source_locale: str, target_locale: str) -> str | None: ...


@dataclass
class ResolvedText:
    key: str
    text: str
    locale: str
    direction: str
    fallback: bool
    stale: bool


class LocalizedGame:
    def __init__(self, strings: Iterable[SourceString], source_locale: str = "en") -> None:
        self.source_locale = LocaleId(source_locale).value
        self.sources: dict[str, SourceString] = {}
        for s in strings:
            parse_message(s.text)  # source must be well-formed
            self.sources[s.key] = s
        self.tables: dict[str, LocaleTable] = {}

    def table(self, locale: str) -> LocaleTable:
        loc = LocaleId(locale).value
        return self.tables.setdefault(loc, LocaleTable(loc))

    def update_sources(self, strings: Iterable[SourceString]) -> None:
        """Replace sources (e.g. re-extracted plan); translations keep their old hash → stale."""
        new = list(strings)
        for s in new:
            parse_message(s.text)
        self.sources = {s.key: s for s in new}

    def audit(self, locales: Iterable[str] | None = None) -> list[AuditIssue]:
        issues: list[AuditIssue] = []
        targets = [LocaleId(x).value for x in locales] if locales else sorted(self.tables)
        for loc in targets:
            if loc == self.source_locale:
                continue
            tbl = self.tables.get(loc, LocaleTable(loc))
            for key, src in sorted(self.sources.items()):
                tr = tbl.entries.get(key)
                if tr is None:
                    issues.append(AuditIssue(loc, key, "missing"))
                    continue
                if tr.source_hash != src.hash:
                    issues.append(AuditIssue(loc, key, "stale", f"{tr.source_hash}->{src.hash}"))
                probs = check_placeholders(src.text, tr.text, loc)
                if probs:
                    issues.append(AuditIssue(loc, key, "placeholder", "; ".join(probs)))
                if not tr.reviewed:
                    issues.append(AuditIssue(loc, key, "unreviewed", tr.provider))
            for key in sorted(set(tbl.entries) - set(self.sources)):
                issues.append(AuditIssue(loc, key, "orphan"))
        return issues

    def fill_missing(self, provider: TranslationProvider, locale: str) -> list[str]:
        """Ask ``provider`` for missing/stale keys. Results are stored unreviewed."""
        if not isinstance(provider, TranslationProvider):
            raise TypeError("provider must implement TranslationProvider")
        tbl = self.table(locale)
        filled: list[str] = []
        for key, src in sorted(self.sources.items()):
            tr = tbl.entries.get(key)
            if tr is not None and tr.source_hash == src.hash:
                continue
            text = provider.translate(src, self.source_locale, tbl.locale)
            if text is None:
                continue
            try:
                tbl.set(src, text, reviewed=False, provider=provider.name)
            except MessageError:
                continue  # provider output that breaks placeholders is rejected
            filled.append(key)
        return filled

    def resolve(self, key: str, locale: str, policy: LocaleFallbackPolicy | None = None, *,
                allow_stale: bool = False) -> ResolvedText:
        if key not in self.sources:
            raise KeyError(key)
        src = self.sources[key]
        req = LocaleId(locale)
        pol = policy or LocaleFallbackPolicy("game-default", LocaleId(self.source_locale))
        for cand in pol.chain(req):
            if cand.value == self.source_locale:
                return ResolvedText(key, src.text, cand.value, text_direction(cand.value),
                                    cand != req, False)
            tr = self.tables.get(cand.value, LocaleTable(cand.value)).entries.get(key)
            if tr is None:
                continue
            stale = tr.source_hash != src.hash
            if stale and not allow_stale:
                continue
            return ResolvedText(key, tr.text, cand.value, text_direction(cand.value), cand != req, stale)
        raise LookupError(f"no translation for {key} in {req.value} chain")

    def format(self, key: str, locale: str, args: Mapping[str, Any] | None = None,
               policy: LocaleFallbackPolicy | None = None) -> str:
        r = self.resolve(key, locale, policy)
        return format_message(r.text, args or {}, r.locale)

    def to_json(self) -> str:
        return json.dumps({
            "schema": SCHEMA, "source_locale": self.source_locale,
            "sources": [{"key": s.key, "text": s.text, "context": s.context}
                        for s in sorted(self.sources.values(), key=lambda s: s.key)],
            "tables": {loc: {k: vars(t) for k, t in sorted(tbl.entries.items())}
                       for loc, tbl in sorted(self.tables.items())},
        }, sort_keys=True, ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> LocalizedGame:
        doc = json.loads(raw)
        if doc.get("schema") != SCHEMA:
            raise ValueError("unsupported localization schema")
        g = cls([SourceString(**s) for s in doc["sources"]], doc["source_locale"])
        for loc, entries in doc["tables"].items():
            g.table(loc).entries = {k: Translation(**v) for k, v in entries.items()}
        return g
