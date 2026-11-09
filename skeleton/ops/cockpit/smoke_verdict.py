"""Browser smoke verdicts (port of ``browser-smoke-verdict.mjs``).

A verdict is ``{"viewports": {name: {...}}}`` where each viewport records HTTP
status, title, canvas presence, overflow, console/page errors and a normalized
body-text hash/prefix/length. Two verdicts are compared to flag regressions
without pixel diffs.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

IDENTITY_PREFIX_LEN = 64
TRIVIAL_LEN_DELTA = 20
TRIVIAL_LEN_RATIO = 0.1
COLLAPSE_RATIO = 0.5
DEFAULT_URL = "http://127.0.0.1:8080/"
DEFAULT_OUT_PNG = "/workspace/screenshots/app-builder-preview.png"
_WS = re.compile(r"\s+")


def normalize_body_text(text: Any) -> str:
    return _WS.sub(" ", "" if text is None else str(text)).strip()


def normalized_body_text_hash(text: Any) -> str:
    return hashlib.sha256(normalize_body_text(text).encode("utf-8")).hexdigest()


def body_text_prefix(text: Any) -> str:
    return normalize_body_text(text)[:IDENTITY_PREFIX_LEN]


def viewport_record(
    *,
    status: int,
    title: str | None,
    body_text: str,
    has_canvas: bool = False,
    horizontal_overflow: bool = False,
    console_errors: Sequence[str] = (),
    page_errors: Sequence[str] = (),
) -> dict[str, Any]:
    """Build a viewport entry in the same shape the JS capture script writes."""
    norm = normalize_body_text(body_text)
    return {
        "status": status,
        "title": title,
        "hasCanvas": has_canvas,
        "horizontalOverflow": horizontal_overflow,
        "consoleErrors": list(console_errors),
        "pageErrors": list(page_errors),
        "bodyTextLen": len(norm),
        "bodyTextHash": normalized_body_text_hash(norm),
        "bodyTextPrefix": norm[:IDENTITY_PREFIX_LEN],
    }


@dataclass
class SmokeArgs:
    url: str = DEFAULT_URL
    out_png: str = DEFAULT_OUT_PNG
    baseline: str = ""
    error: str | None = None


def parse_smoke_args(
    argv: Sequence[str], env: Mapping[str, str] | None = None
) -> SmokeArgs:
    env = env or {}
    positional: list[str] = []
    baseline = env.get("BROWSER_SMOKE_BASELINE", "")
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--baseline":
            i += 1
            value = argv[i] if i < len(argv) else ""
            if not value:
                return SmokeArgs(
                    error="--baseline requires a path to a prior verdict JSON"
                )
            baseline = value
        elif arg.startswith("--baseline="):
            value = arg[len("--baseline=") :]
            if not value:
                return SmokeArgs(
                    error="--baseline requires a path to a prior verdict JSON"
                )
            baseline = value
        elif arg.startswith("--"):
            return SmokeArgs(error=f"unknown flag: {arg}")
        else:
            positional.append(arg)
        i += 1
    return SmokeArgs(
        url=positional[0] if positional else DEFAULT_URL,
        out_png=positional[1] if len(positional) > 1 else DEFAULT_OUT_PNG,
        baseline=baseline,
    )


def derived_paths(out_png: str) -> dict[str, str]:
    base = re.sub(r"\.png$", "", out_png, flags=re.IGNORECASE)
    return {"mobilePng": f"{base}-mobile.png", "verdictJson": f"{base}.json"}


@dataclass
class Comparison:
    diverges_from_baseline: bool
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "divergesFromBaseline": self.diverges_from_baseline,
            "reasons": list(self.reasons),
        }


def _errs(v: Mapping[str, Any]) -> int:
    return len(v.get("consoleErrors") or []) + len(v.get("pageErrors") or [])


def compare_to_baseline(
    current: Mapping[str, Any] | None, baseline: Mapping[str, Any] | None
) -> Comparison:
    entries = list(((current or {}).get("viewports") or {}).items())
    if not entries:
        return Comparison(True, ["current verdict has no viewport data"])
    reasons: list[str] = []
    base_vps = (baseline or {}).get("viewports") or {}
    for name, cur in entries:
        base = base_vps.get(name)
        if not base:
            reasons.append(f"{name}: no baseline data for this viewport")
            continue
        if cur.get("status") != base.get("status"):
            reasons.append(
                f"{name}: HTTP status changed {base.get('status')} -> {cur.get('status')}"
            )
        if (
            base.get("title") is not None
            and cur.get("title") is not None
            and cur["title"] != base["title"]
        ):
            reasons.append(
                f'{name}: title changed ("{base["title"]}" -> "{cur["title"]}")'
            )
        if base.get("hasCanvas") and not cur.get("hasCanvas"):
            reasons.append(f"{name}: canvas disappeared")
        if cur.get("horizontalOverflow") and not base.get("horizontalOverflow"):
            reasons.append(f"{name}: horizontal overflow appeared")
        cur_errs, base_errs = _errs(cur), _errs(base)
        if cur_errs > 0 and base_errs == 0:
            reasons.append(f"{name}: console/page errors appeared ({cur_errs})")
        base_len = base.get("bodyTextLen") or 0
        cur_len = cur.get("bodyTextLen") or 0
        if base_len > 0 and cur_len < base_len * COLLAPSE_RATIO:
            reasons.append(
                f"{name}: body text collapsed ({base_len} -> {cur_len} chars)"
            )
        elif cur.get("bodyTextHash") != base.get("bodyTextHash"):
            if abs(cur_len - base_len) > max(
                TRIVIAL_LEN_DELTA, base_len * TRIVIAL_LEN_RATIO
            ):
                reasons.append(
                    f"{name}: body text changed ({base_len} -> {cur_len} chars, hash mismatch)"
                )
            elif (
                base.get("bodyTextPrefix") is not None
                and cur.get("bodyTextPrefix") is not None
                and cur["bodyTextPrefix"] != base["bodyTextPrefix"]
            ):
                reasons.append(
                    f"{name}: body text replaced (similar length, page start changed)"
                )
    return Comparison(bool(reasons), reasons)


def baseline_comparison(current: Mapping[str, Any], raw_text: str) -> Comparison:
    try:
        baseline = json.loads(raw_text)
    except ValueError:
        return Comparison(True, ["baseline unreadable: invalid JSON"])
    if not isinstance(baseline, dict) or not isinstance(
        baseline.get("viewports"), dict
    ):
        return Comparison(True, ["baseline unreadable: not a verdict object"])
    return compare_to_baseline(current, baseline)


def exit_code_for(viewports: Mapping[str, Any] | None) -> int:
    """0 clean, 1 unreachable/HTTP error (or no data), 2 console/page errors."""
    items = list((viewports or {}).values())
    if not items:
        return 1
    if any((v.get("status") or 0) >= 400 or (v.get("status") or 0) == 0 for v in items):
        return 1
    if any(_errs(v) > 0 for v in items):
        return 2
    return 0
