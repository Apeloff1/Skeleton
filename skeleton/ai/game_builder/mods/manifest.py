"""Versioned mod manifest: SemVer 2.0 versions and npm-style dependency specs."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from skeleton.gameforge.batch_b09x._helpers import ContractError
from skeleton.gameforge.batch_b09x.b095_plugin_sdk import SDK_API
from skeleton.gameforge.batch_b09x.b099_ugc_sandbox import MOD_PERMISSIONS

MANIFEST_SCHEMA = "skeleton.game_builder.mod.v1"
_ID = re.compile(r"^[a-z][a-z0-9_-]{1,63}$")
_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$")
_CMP = re.compile(r"^(\^|~|>=|<=|>|<|=)?\s*(\S+)$")
MAX_DEPS = 32
MAX_TARGETS = 32
MAX_SEMVER_CHARS = 128


class ModError(ContractError):
    """Invalid mod manifest or spec."""


@dataclass(frozen=True, order=False)
class SemVer:
    major: int
    minor: int
    patch: int
    pre: tuple[Any, ...] = ()

    @classmethod
    def parse(cls, text: str) -> SemVer:
        # Bound untrusted version text before regex matching or integer parsing.
        if type(text) is not str or len(text) > MAX_SEMVER_CHARS:
            raise ModError("invalid semver length or type")
        m = _SEMVER.fullmatch(text.strip())
        if not m:
            raise ModError(f"invalid semver {text!r}")
        parts = m.group(4).split(".") if m.group(4) else []
        if any(not part or (part.isdigit() and len(part) > 1 and part[0] == "0")
               for part in parts):
            raise ModError("invalid semver prerelease identifiers")
        pre = tuple(int(p) if p.isdigit() else p for p in parts)
        return cls(int(m.group(1)), int(m.group(2)), int(m.group(3)), pre)

    def _key(self) -> tuple:
        # Release > prerelease; numeric identifiers sort before alphanumeric ones.
        pre = tuple((0, p, "") if isinstance(p, int) else (1, 0, p) for p in self.pre)
        return (self.major, self.minor, self.patch, 0 if self.pre else 1, pre)

    def __lt__(self, o: SemVer) -> bool: return self._key() < o._key()
    def __le__(self, o: SemVer) -> bool: return self._key() <= o._key()
    def __gt__(self, o: SemVer) -> bool: return self._key() > o._key()
    def __ge__(self, o: SemVer) -> bool: return self._key() >= o._key()

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        return base + ("-" + ".".join(map(str, self.pre)) if self.pre else "")


def _bounds(op: str, v: SemVer) -> list[tuple[str, SemVer]]:
    if op == "^":
        up = (SemVer(v.major + 1, 0, 0) if v.major else
              SemVer(0, v.minor + 1, 0) if v.minor else SemVer(0, 0, v.patch + 1))
        return [(">=", v), ("<", up)]
    if op == "~":
        return [(">=", v), ("<", SemVer(v.major, v.minor + 1, 0))]
    return [(op or "=", v)]


@dataclass(frozen=True)
class VersionSpec:
    """``^1.2.0``, ``~1.2.3``, ``>=1.0.0 <2.0.0``, ``1.4.2``, ``*``, and ``a || b``."""

    text: str
    alternatives: tuple[tuple[tuple[str, SemVer], ...], ...] = field(default=(), compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text.strip() or len(self.text) > 128:
            raise ModError("version spec must be a short string")
        alts = []
        for alt in self.text.split("||"):
            alt = alt.strip()
            # An empty OR branch otherwise becomes a match-all alternative,
            # silently bypassing mandatory dependency version constraints.
            if not alt:
                raise ModError("empty version spec alternative")
            terms: list[tuple[str, SemVer]] = []
            if alt != "*":
                for tok in re.sub(r"(>=|<=|>|<|=)\s+", r"\1", alt).split():
                    m = _CMP.fullmatch(tok)
                    if not m:
                        raise ModError(f"invalid version spec {self.text!r}")
                    terms += _bounds(m.group(1) or "", SemVer.parse(m.group(2)))
            alts.append(tuple(terms))
        object.__setattr__(self, "alternatives", tuple(alts))

    def matches(self, v: SemVer) -> bool:
        ops = {"=": v.__eq__, ">=": v.__ge__, "<=": v.__le__, ">": v.__gt__, "<": v.__lt__}
        for terms in self.alternatives:
            # Prereleases only match a term set that names the same major.minor.patch prerelease.
            if v.pre and not any(t.pre and (t.major, t.minor, t.patch) == (v.major, v.minor, v.patch)
                                 for _, t in terms):
                continue
            if all(ops[op](t) for op, t in terms):
                return True
        return False

    def __str__(self) -> str:
        return self.text


def _ids(value: Any, name: str) -> tuple[str, ...]:
    if not isinstance(value, list | tuple) or len(value) > MAX_DEPS:
        raise ModError(f"{name} must be a list")
    for v in value:
        if not isinstance(v, str) or not _ID.fullmatch(v):
            raise ModError(f"{name}: invalid mod id {v!r}")
    return tuple(sorted(set(value)))


@dataclass(frozen=True)
class ModManifest:
    mod_id: str
    version: SemVer
    sdk_api: tuple[int, int] = SDK_API
    permissions: tuple[str, ...] = ()
    depends: Mapping[str, VersionSpec] = field(default_factory=dict)
    optional: Mapping[str, VersionSpec] = field(default_factory=dict)
    conflicts: tuple[str, ...] = ()
    load_after: tuple[str, ...] = ()
    load_before: tuple[str, ...] = ()
    targets: tuple[str, ...] = ()  # path prefixes the mod may touch; () = whole plan
    title: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.mod_id, str) or not _ID.fullmatch(self.mod_id):
            raise ModError(f"invalid mod id {self.mod_id!r}")
        if (type(self.targets) is not tuple or len(self.targets) > MAX_TARGETS
                or any(type(t) is not str or not 1 <= len(t) <= 256
                       or any(ord(ch) < 32 or ord(ch) == 127 for ch in t)
                       for t in self.targets)):
            raise ModError("targets must be bounded, control-free path prefixes")
        bad = set(self.permissions) - MOD_PERMISSIONS
        if bad:
            raise ModError(f"unknown permissions {sorted(bad)}")
        if self.sdk_api[0] != SDK_API[0] or self.sdk_api[1] > SDK_API[1]:
            raise ModError(f"incompatible sdk_api {self.sdk_api}")
        rel = set(self.depends) | set(self.optional) | set(self.conflicts) | set(self.load_after) | set(self.load_before)
        if self.mod_id in rel:
            raise ModError("mod cannot reference itself")
        if set(self.depends) & set(self.conflicts):
            raise ModError("mod both depends on and conflicts with the same mod")

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ModManifest:
        if data.get("schema") != MANIFEST_SCHEMA:
            raise ModError("unsupported mod manifest schema")

        def specs(name: str) -> dict[str, VersionSpec]:
            raw = data.get(name, {})
            if not isinstance(raw, Mapping) or len(raw) > MAX_DEPS:
                raise ModError(f"{name} must be a mapping")
            _ids(list(raw), name)
            return {k: VersionSpec(v) for k, v in sorted(raw.items())}

        api = data.get("sdk_api", list(SDK_API))
        if not (isinstance(api, list | tuple) and len(api) == 2 and all(isinstance(x, int) for x in api)):
            raise ModError("sdk_api must be [major, minor]")
        targets = data.get("targets", [])
        if not isinstance(targets, list) or len(targets) > MAX_TARGETS:
            raise ModError("targets must be a bounded list of path prefixes")
        return cls(
            mod_id=data.get("mod_id", ""), version=SemVer.parse(data.get("version", "")),
            sdk_api=(api[0], api[1]), permissions=tuple(sorted(set(data.get("permissions", [])))),
            depends=specs("depends"), optional=specs("optional"),
            conflicts=_ids(data.get("conflicts", []), "conflicts"),
            load_after=_ids(data.get("load_after", []), "load_after"),
            load_before=_ids(data.get("load_before", []), "load_before"),
            targets=tuple(targets), title=str(data.get("title", ""))[:120],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": MANIFEST_SCHEMA, "mod_id": self.mod_id, "version": str(self.version),
            "sdk_api": list(self.sdk_api), "permissions": sorted(self.permissions),
            "depends": {k: str(v) for k, v in sorted(self.depends.items())},
            "optional": {k: str(v) for k, v in sorted(self.optional.items())},
            "conflicts": list(self.conflicts), "load_after": list(self.load_after),
            "load_before": list(self.load_before), "targets": list(self.targets), "title": self.title,
        }
