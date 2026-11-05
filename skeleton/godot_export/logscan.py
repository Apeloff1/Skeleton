"""Classify Godot engine output (GFD-02 / GFD-05)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

FATAL = re.compile(r"^\s*(ERROR:|SCRIPT ERROR:|Parse Error|USER ERROR:)", re.M)
MISSING = re.compile(r"(Failed loading resource|Cannot open file|Resource file not found|No loader found for resource)")
WARNING = re.compile(r"^\s*(WARNING:|USER WARNING:)", re.M)
# Known-benign engine noise in headless CI (no display / audio device).
BENIGN = (
    re.compile(r"No audio driver|Audio driver failed|ALSA lib", re.I),
    re.compile(r"Couldn't load the Vulkan|Your video card drivers seem not to support", re.I),
)


@dataclass
class LogScan:
    fatal: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not self.fatal and not self.missing


def _benign(line: str) -> bool:
    return any(p.search(line) for p in BENIGN)


def scan(output: str, limit: int = 50) -> LogScan:
    res = LogScan()
    for line in output.splitlines():
        if _benign(line):
            continue
        if MISSING.search(line):
            if len(res.missing) < limit:
                res.missing.append(line.strip())
        elif FATAL.match(line):
            if len(res.fatal) < limit:
                res.fatal.append(line.strip())
        elif WARNING.match(line):
            if len(res.warnings) < limit:
                res.warnings.append(line.strip())
    return res
