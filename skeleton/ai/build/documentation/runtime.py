"""Deterministic human/generated documentation engine for VOL-089/VOL-090."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
import re
from typing import Iterable, Mapping
from urllib.parse import urlsplit

_SHA = re.compile(r"^[0-9a-f]{64}$")
_ID = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.:/-]{1,191}$")
_MARKER_PREFIX = "<!-- skeleton:generated:"
_BEGIN = "<!-- skeleton:generated:{id}:begin -->"
_END = "<!-- skeleton:generated:{id}:end -->"


class DocumentationError(ValueError):
    pass


class SourceKind(str, Enum):
    HUMAN = "human"
    MACHINE = "machine"


class CheckStatus(str, Enum):
    PASS = "pass"
    FAIL = "fail"


def canonical_digest(value: object) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _id(value: str, field: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise DocumentationError(f"{field} must be a stable identifier")
    return value


def _sha(value: str, field: str) -> str:
    if not isinstance(value, str) or not _SHA.fullmatch(value):
        raise DocumentationError(f"{field} must be lowercase sha256")
    return value


def _repo_path(value: str, field: str) -> str:
    value = _id(value, field)
    parts = value.split("/")
    if (
        value.startswith("/")
        or "\\" in value
        or any(part in ("", ".", "..") for part in parts)
    ):
        raise DocumentationError(f"{field} must be a safe repository-relative path")
    return value


@dataclass(frozen=True, slots=True)
class DocumentationSource:
    source_id: str
    kind: SourceKind
    path: str
    digest: str

    def __post_init__(self):
        object.__setattr__(self, "source_id", _id(self.source_id, "source_id"))
        if not isinstance(self.kind, SourceKind):
            raise DocumentationError("kind must be a SourceKind")
        object.__setattr__(self, "path", _repo_path(self.path, "path"))
        object.__setattr__(self, "digest", _sha(self.digest, "digest"))


@dataclass(frozen=True, slots=True)
class GeneratorIdentity:
    generator_id: str
    version: str
    implementation_digest: str

    def __post_init__(self):
        object.__setattr__(self, "generator_id", _id(self.generator_id, "generator_id"))
        object.__setattr__(self, "version", _id(self.version, "version"))
        object.__setattr__(self, "implementation_digest", _sha(self.implementation_digest, "implementation_digest"))

    @property
    def digest(self) -> str:
        return canonical_digest({
            "generator_id": self.generator_id,
            "version": self.version,
            "implementation_digest": self.implementation_digest,
        })


@dataclass(frozen=True, slots=True)
class SourceDigestSet:
    sources: tuple[DocumentationSource, ...]

    def __post_init__(self):
        if not isinstance(self.sources, tuple) or not self.sources:
            raise DocumentationError("source set must be a non-empty tuple")
        if len(self.sources) > 4096:
            raise DocumentationError("source set exceeds policy bound")
        if any(not isinstance(source, DocumentationSource) for source in self.sources):
            raise DocumentationError("source set contains invalid source")
        ordered = tuple(sorted(self.sources, key=lambda s: s.source_id))
        if len({s.source_id for s in ordered}) != len(ordered):
            raise DocumentationError("duplicate source identity")
        object.__setattr__(self, "sources", ordered)

    @property
    def digest(self) -> str:
        return canonical_digest([
            {"source_id": s.source_id, "kind": s.kind.value, "path": s.path, "digest": s.digest}
            for s in self.sources
        ])


@dataclass(frozen=True, slots=True)
class GeneratedSection:
    section_id: str
    source_digest_set: str
    generator_digest: str
    body: str

    def __post_init__(self):
        object.__setattr__(self, "section_id", _id(self.section_id, "section_id"))
        object.__setattr__(self, "source_digest_set", _sha(self.source_digest_set, "source_digest_set"))
        object.__setattr__(self, "generator_digest", _sha(self.generator_digest, "generator_digest"))
        if not isinstance(self.body, str) or "\x00" in self.body:
            raise DocumentationError("body must be safe text")
        if _MARKER_PREFIX in self.body:
            raise DocumentationError("generated body cannot contain ownership markers")

    @property
    def digest(self) -> str:
        return canonical_digest({
            "section_id": self.section_id,
            "source_digest_set": self.source_digest_set,
            "generator_digest": self.generator_digest,
            "body": self.body,
        })


@dataclass(frozen=True, slots=True)
class GeneratedDocument:
    path: str
    generator: GeneratorIdentity
    source_set: SourceDigestSet
    sections: tuple[GeneratedSection, ...]

    def __post_init__(self):
        object.__setattr__(self, "path", _repo_path(self.path, "path"))
        if not isinstance(self.generator, GeneratorIdentity) or not isinstance(self.source_set, SourceDigestSet):
            raise DocumentationError("generated document identities are invalid")
        if not isinstance(self.sections, tuple) or not self.sections:
            raise DocumentationError("generated document requires sections")
        if len(self.sections) > 4096 or any(not isinstance(section, GeneratedSection) for section in self.sections):
            raise DocumentationError("generated section set is invalid or exceeds policy bound")
        ordered = tuple(sorted(self.sections, key=lambda s: s.section_id))
        if len({s.section_id for s in ordered}) != len(ordered):
            raise DocumentationError("duplicate generated section identity")
        for section in ordered:
            if section.source_digest_set != self.source_set.digest:
                raise DocumentationError("section source digest is stale")
            if section.generator_digest != self.generator.digest:
                raise DocumentationError("section generator identity is stale")
        object.__setattr__(self, "sections", ordered)

    @property
    def manifest_digest(self) -> str:
        return canonical_digest({
            "path": self.path,
            "generator": self.generator.digest,
            "sources": self.source_set.digest,
            "sections": [s.digest for s in self.sections],
        })


@dataclass(frozen=True, slots=True)
class DocumentationCheck:
    check_id: str
    status: CheckStatus
    detail: str

    def __post_init__(self):
        object.__setattr__(self, "check_id", _id(self.check_id, "check_id"))
        if not isinstance(self.detail, str) or not self.detail.strip():
            raise DocumentationError("check detail is required")


def markers(section_id: str) -> tuple[str, str]:
    section_id = _id(section_id, "section_id")
    return _BEGIN.format(id=section_id), _END.format(id=section_id)


def render_section(section: GeneratedSection) -> str:
    begin, end = markers(section.section_id)
    body = section.body.rstrip()
    return f"{begin}\n{body}\n{end}"


def replace_generated_section(document: str, section: GeneratedSection) -> str:
    """Replace exactly one owned section while preserving all human text byte-for-byte."""
    if not isinstance(document, str):
        raise DocumentationError("document must be text")
    begin, end = markers(section.section_id)
    starts = [m.start() for m in re.finditer(re.escape(begin), document)]
    ends = [m.start() for m in re.finditer(re.escape(end), document)]
    if len(starts) != 1 or len(ends) != 1:
        raise DocumentationError("generated ownership markers must exist exactly once")
    start, end_start = starts[0], ends[0]
    if end_start <= start:
        raise DocumentationError("generated ownership markers are malformed")
    end_pos = end_start + len(end)
    return document[:start] + render_section(section) + document[end_pos:]


def render_generated_document(
    template: str,
    document: GeneratedDocument,
) -> str:
    """Materialize all owned sections into an existing human-authored template.

    Generated section order is canonical, each section must already have one
    unique ownership boundary in the template, and text outside those
    boundaries is preserved byte-for-byte.
    """
    if not isinstance(template, str):
        raise DocumentationError("template must be text")
    if not isinstance(document, GeneratedDocument):
        raise DocumentationError("document must be GeneratedDocument")
    rendered = template
    for section in document.sections:
        rendered = replace_generated_section(rendered, section)
    return rendered


def validate_owned_sections(document: str, section_ids: Iterable[str]) -> tuple[DocumentationCheck, ...]:
    checks: list[DocumentationCheck] = []
    for section_id in sorted(set(section_ids)):
        begin, end = markers(section_id)
        ok = document.count(begin) == 1 and document.count(end) == 1 and document.index(begin) < document.index(end) if begin in document and end in document else False
        checks.append(DocumentationCheck(
            check_id=f"ownership:{section_id}",
            status=CheckStatus.PASS if ok else CheckStatus.FAIL,
            detail="owned section is uniquely bounded" if ok else "owned section marker missing, duplicated, or malformed",
        ))
    return tuple(checks)


def validate_references(document: str, known_ids: Iterable[str]) -> tuple[DocumentationCheck, ...]:
    """Validate explicit [[ref:IDENTIFIER]] references without guessing prose links."""
    if not isinstance(document, str):
        raise DocumentationError("document must be text")
    known = {_id(item, "known_id") for item in known_ids}
    proper = re.findall(r"\[\[ref:([^\]]+)\]\]", document)
    raw_refs = sorted(set(proper))
    checks: list[DocumentationCheck] = []
    if document.count("[[ref:") != len(proper):
        checks.append(DocumentationCheck(
            check_id=f"reference-invalid-framing:{canonical_digest(document)[:16]}",
            status=CheckStatus.FAIL,
            detail="reference marker is unterminated or malformed",
        ))
    for raw in raw_refs:
        try:
            ref = _id(raw, "reference")
        except DocumentationError:
            checks.append(DocumentationCheck(
                check_id=f"reference-invalid:{canonical_digest(raw)[:16]}",
                status=CheckStatus.FAIL,
                detail="reference syntax is invalid",
            ))
            continue
        checks.append(DocumentationCheck(
            check_id=f"reference:{ref}",
            status=CheckStatus.PASS if ref in known else CheckStatus.FAIL,
            detail="reference resolves" if ref in known else "reference is unknown",
        ))
    return tuple(checks)


def validate_links(
    document: str,
    known_paths: Iterable[str],
    *,
    allowed_schemes: Iterable[str] = ("https",),
) -> tuple[DocumentationCheck, ...]:
    """Validate Markdown links without performing network access.

    Local links must resolve to an explicitly supplied repository path. External
    links must use an allowed absolute scheme and authority. Anchors are local
    presentation references and are accepted without pretending to validate a
    remote resource.
    """
    known = set(known_paths)
    schemes = {item.lower() for item in allowed_schemes}
    checks: list[DocumentationCheck] = []
    links = sorted(set(re.findall(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)", document)))
    for target in links:
        digest = canonical_digest(target)[:16]
        if target.startswith("#"):
            ok, detail = True, "local anchor is syntactically valid"
        else:
            parsed = urlsplit(target)
            if parsed.scheme:
                ok = parsed.scheme.lower() in schemes and bool(parsed.netloc)
                detail = "external link policy satisfied" if ok else "external link scheme or authority is invalid"
            else:
                path = parsed.path
                unsafe = (
                    not path
                    or path.startswith("/")
                    or "\\" in path
                    or any(part in ("", ".", "..") for part in path.split("/"))
                )
                ok = not unsafe and path in known
                detail = "repository link resolves" if ok else "repository link is unknown or unsafe"
        checks.append(DocumentationCheck(
            check_id=f"link:{digest}",
            status=CheckStatus.PASS if ok else CheckStatus.FAIL,
            detail=detail,
        ))
    return tuple(checks)


def validate_version_relationships(
    declared: Mapping[str, str],
    expected: Mapping[str, str],
) -> tuple[DocumentationCheck, ...]:
    """Require documented version relationships to match authoritative values."""
    keys = sorted(set(declared) | set(expected))
    checks: list[DocumentationCheck] = []
    for key in keys:
        stable = _id(key, "version relationship")
        actual = declared.get(key)
        wanted = expected.get(key)
        ok = actual is not None and wanted is not None and actual == wanted
        checks.append(DocumentationCheck(
            check_id=f"version:{stable}",
            status=CheckStatus.PASS if ok else CheckStatus.FAIL,
            detail="version relationship matches authority" if ok else "version relationship is missing or stale",
        ))
    return tuple(checks)


def assert_clean_regeneration(existing: str, generated: str) -> None:
    if existing != generated:
        raise DocumentationError("generated document drift: regenerate derived output")


def generated_manifest(document: GeneratedDocument) -> Mapping[str, object]:
    return {
        "schema_version": 1,
        "path": document.path,
        "generator": {
            "generator_id": document.generator.generator_id,
            "version": document.generator.version,
            "implementation_digest": document.generator.implementation_digest,
            "digest": document.generator.digest,
        },
        "source_digest_set": document.source_set.digest,
        "sources": [
            {"source_id": s.source_id, "kind": s.kind.value, "path": s.path, "digest": s.digest}
            for s in document.source_set.sources
        ],
        "sections": [
            {"section_id": s.section_id, "digest": s.digest}
            for s in document.sections
        ],
        "manifest_digest": document.manifest_digest,
        "editing_policy": "regenerate-derived-sections-do-not-hand-edit",
    }
