"""B085: asset/content safety gate: malware signatures, disallowed content, secrets, rights."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from . import b083_secret_boundary as secrets
from ._core import verdict

MAGIC_DENY = {b"MZ": "pe_executable", b"\x7fELF": "elf_executable", b"#!": "script"}
ALLOWED_LICENSES = frozenset({"CC0-1.0", "CC-BY-4.0", "MIT", "proprietary-owned"})


@dataclass(frozen=True)
class Asset:
    path: str
    data: bytes
    rights: Mapping[str, str]


def scan_asset(a: Asset, blocked_terms: frozenset[str] = frozenset()) -> list[str]:
    out = []
    for magic, label in MAGIC_DENY.items():
        if a.data.startswith(magic):
            out.append(f"{a.path}:{label}")
    text = a.data.decode("utf-8", "ignore")
    out += [f"{a.path}:secret:{h}" for h in secrets.scan(text)]
    lowered = text.lower()
    out += [f"{a.path}:content:{t}" for t in sorted(blocked_terms) if t in lowered]
    lic = a.rights.get("license")
    if lic not in ALLOWED_LICENSES:
        out.append(f"{a.path}:license:{lic}")
    if not a.rights.get("author"):
        out.append(f"{a.path}:no_author")
    return out


def evaluate(assets: list[Asset], blocked_terms: frozenset[str] = frozenset()):
    findings = [f for a in sorted(assets, key=lambda a: a.path) for f in scan_asset(a, blocked_terms)]
    return verdict("B085", findings, assets=len(assets))
