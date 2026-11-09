"""Semantic version parsing, comparison and bumping for releases."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal

from skeleton.build.delivery._util import DeliveryError

_SEMVER = re.compile(
    r"^v?(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<pre>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
    r"(?:\+(?P<build>[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$"
)

BumpKind = Literal["major", "minor", "patch", "prerelease"]


@dataclass(frozen=True, order=False)
class Version:
    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] = ()
    build: tuple[str, ...] = ()

    @classmethod
    def parse(cls, text: str) -> "Version":
        if not isinstance(text, str):
            raise DeliveryError("version must be text")
        match = _SEMVER.fullmatch(text.strip())
        if not match:
            raise DeliveryError(f"invalid semantic version: {text!r}")
        pre = tuple(match["pre"].split(".")) if match["pre"] else ()
        for ident in pre:
            if ident.isdigit() and len(ident) > 1 and ident.startswith("0"):
                raise DeliveryError("numeric prerelease identifiers must not have leading zeros")
        build = tuple(match["build"].split(".")) if match["build"] else ()
        return cls(int(match["major"]), int(match["minor"]), int(match["patch"]), pre, build)

    def __str__(self) -> str:
        text = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            text += "-" + ".".join(self.prerelease)
        if self.build:
            text += "+" + ".".join(self.build)
        return text

    @property
    def is_prerelease(self) -> bool:
        return bool(self.prerelease)

    def _key(self) -> tuple:
        # Build metadata is ignored for precedence (SemVer 2.0.0 section 10).
        if not self.prerelease:
            pre_key: tuple = ((1,),)
        else:
            pre_key = tuple(
                (0, int(p), "") if p.isdigit() else (1, 0, p) for p in self.prerelease
            )
            pre_key = ((0,),) + pre_key
        return (self.major, self.minor, self.patch, pre_key)

    def __lt__(self, other: "Version") -> bool:
        return self._key() < other._key()

    def __le__(self, other: "Version") -> bool:
        return self._key() <= other._key()

    def __gt__(self, other: "Version") -> bool:
        return self._key() > other._key()

    def __ge__(self, other: "Version") -> bool:
        return self._key() >= other._key()

    def precedence_equal(self, other: "Version") -> bool:
        return self._key() == other._key()

    def bump(self, kind: BumpKind, *, pre_label: str = "rc") -> "Version":
        if kind == "major":
            return Version(self.major + 1, 0, 0)
        if kind == "minor":
            return Version(self.major, self.minor + 1, 0)
        if kind == "patch":
            if self.prerelease:
                return Version(self.major, self.minor, self.patch)
            return Version(self.major, self.minor, self.patch + 1)
        if kind == "prerelease":
            if not re.fullmatch(r"[A-Za-z][0-9A-Za-z-]*", pre_label):
                raise DeliveryError("prerelease label must be alphanumeric")
            if self.prerelease and self.prerelease[0] == pre_label and len(self.prerelease) == 2 and self.prerelease[1].isdigit():
                return Version(self.major, self.minor, self.patch, (pre_label, str(int(self.prerelease[1]) + 1)))
            base = self if self.prerelease else Version(self.major, self.minor, self.patch + 1)
            return Version(base.major, base.minor, base.patch, (pre_label, "1"))
        raise DeliveryError(f"unknown bump kind: {kind!r}")


def latest(versions: list[str] | tuple[str, ...], *, include_prerelease: bool = False) -> Version | None:
    parsed = [Version.parse(v) for v in versions]
    if not include_prerelease:
        parsed = [v for v in parsed if not v.is_prerelease]
    return max(parsed, key=lambda v: v._key()) if parsed else None
