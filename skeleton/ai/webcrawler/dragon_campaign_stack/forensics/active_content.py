"""Source-text active-content, encoded directives and transport escape holds.

Review-only heuristic checks for web text that could be unsafe if accidentally
rendered as HTML, a command, URL or tool input. No URLs are opened, scripts
run or embedded data decoded. Strong signals never promote source authority.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
import re

from ..contracts import digest
from .frames import FrameSet


_PATTERNS = (
    ("html_script", re.compile(r"<\s*script\b", re.I)),
    ("html_iframe", re.compile(r"<\s*(?:iframe|object|embed)\b", re.I)),
    ("inline_event_handler", re.compile(r"\bon(?:load|error|click|mouseover)\s*=", re.I)),
    ("javascript_scheme", re.compile(r"\bjavascript\s*:", re.I)),
    ("data_html_scheme", re.compile(r"\bdata\s*:\s*text/html", re.I)),
    ("shell_substitution", re.compile(r"\$\([^\n]{1,120}\)")),
    ("terminal_escape", re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*\x07)")),
    ("html_meta_refresh", re.compile(r"<\s*meta\s+[^>]{0,256}http-equiv\s*=\s*['\"]?refresh", re.I)),
    ("html_form_password", re.compile(r"<\s*input\s+[^>]{0,256}type\s*=\s*['\"]?password", re.I)),
    ("possible_encoded_payload", re.compile(r"\b(?:[A-Za-z0-9+/]{80,}={0,2}|[0-9a-fA-F]{160,})\b")),
)


@dataclass(frozen=True)
class ActiveContentFinding:
    source_id: str
    passage_hash: str
    rule_codes: tuple[str, ...]
    total_rule_hits: int
    active_payload_executed: bool = False
    render_safe_certified: bool = False


@dataclass(frozen=True)
class ActiveContentReport:
    frame_set_digest: str
    findings: tuple[ActiveContentFinding, ...]
    rule_counts: tuple[tuple[str, int], ...]
    held_source_ids: tuple[str, ...]
    report_digest: str
    external_urls_opened: bool = False
    browser_rendering_performed: bool = False
    source_body_exported: bool = False


def inspect_active_content(frames: FrameSet) -> ActiveContentReport:
    if not isinstance(frames, FrameSet):
        raise TypeError("bound forensic frames required")
    counts = defaultdict(int)
    findings = []
    holds = set()
    for frame in frames.frames:
        rules = []
        occurrences = 0
        for code, pattern in _PATTERNS:
            count = len(pattern.findall(frame.text))
            if count:
                rules.append(code)
                counts[code] += count
                occurrences += count
        if rules:
            holds.add(frame.anchor.source_id)
        findings.append(ActiveContentFinding(
            frame.anchor.source_id, frame.anchor.passage_hash,
            tuple(sorted(rules)), occurrences,
        ))
    payload = {
        "frames": frames.frame_set_digest,
        "findings": [asdict(x) for x in findings],
        "rules": sorted(counts.items()),
    }
    return ActiveContentReport(
        frames.frame_set_digest, tuple(findings), tuple(sorted(counts.items())),
        tuple(sorted(holds)), digest(payload),
    )
