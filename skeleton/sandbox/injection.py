"""Injection detection for untrusted input (B086).

:func:`detect` scans text for several injection families and returns a
scored :class:`InjectionReport`.  Detection runs on a *normalised view* of
the input — NFKC, invisible/bidi characters removed, Unicode-tag smuggling
decoded, common leetspeak folded, and base64/percent/HTML-entity layers
peeled (bounded) — so trivial obfuscation does not hide a payload.

Families:

``prompt``     instruction override / role hijack / system-prompt exfiltration
``shell``      command chaining, substitution, redirection to sensitive paths
``sql``        tautologies, stacked queries, UNION SELECT, comment truncation
``path``       traversal and sensitive absolute paths
``template``   server-side template / expression-language injection
``markup``     script tags, event handlers, javascript: URLs
``exfil``      markdown-image / link beacons carrying data to remote hosts
``hidden``     invisible, bidi or tag characters present in the raw input

Contexts tune which families matter (``"prompt"``, ``"shell"``, ``"sql"``,
``"path"``, ``"html"``, ``"any"``); :func:`guard` raises
:class:`~.errors.InjectionDetectedError` at or above a threshold.
"""
from __future__ import annotations

import base64
import binascii
import html
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote

from .errors import InjectionDetectedError, SanitizerError
from .sanitizers import BIDI_CONTROLS, INVISIBLES, decode_tag_smuggling, hidden_characters

MAX_SCAN_CHARS = 200_000
MAX_DECODE_LAYERS = 3


@dataclass(frozen=True)
class Rule:
    family: str
    rule_id: str
    pattern: re.Pattern[str]
    weight: float
    description: str


def _r(family: str, rule_id: str, pattern: str, weight: float, description: str, flags: int = re.I) -> Rule:
    return Rule(family, rule_id, re.compile(pattern, flags), weight, description)


RULES: tuple[Rule, ...] = (
    # -- prompt injection --------------------------------------------------
    _r("prompt", "override", r"\b(ignore|disregard|forget|override|bypass)\b[^.\n]{0,40}\b(previous|prior|above|earlier|all|any|your|the)\b[^.\n]{0,20}\b(instructions?|prompts?|rules?|directives?|guidelines?|context)\b", 0.9, "instruction override"),
    _r("prompt", "new_instructions", r"\b(new|updated|real|actual)\s+(instructions?|system\s+prompt|rules)\s*[:\-]", 0.6, "replacement instructions"),
    _r("prompt", "role_hijack", r"\b(you\s+are\s+now|from\s+now\s+on\s+you|act\s+as|pretend\s+(to\s+be|you\s+are)|roleplay\s+as)\b[^.\n]{0,60}\b(unrestricted|jailbroken|dan|developer\s+mode|without\s+(any\s+)?(rules|restrictions|limits|filters))", 0.85, "role hijack"),
    _r("prompt", "jailbreak", r"\b(jailbreak|do\s+anything\s+now|developer\s+mode\s+enabled|god\s+mode)\b", 0.7, "jailbreak phrase"),
    _r("prompt", "fake_role_tag", r"(<\|?\s*(system|im_start|im_end|assistant)\s*\|?>|^\s*#{2,}\s*(system|instruction)s?\b|\[/?(system|inst)\]|^\s*system\s*:)", 0.7, "forged role delimiter", re.I | re.M),
    _r("prompt", "exfil_prompt", r"\b(reveal|print|show|repeat|output|leak|dump)\b[^.\n]{0,30}\b(system\s+prompt|hidden\s+(instructions|prompt)|initial\s+instructions|your\s+(instructions|prompt|rules))", 0.8, "system prompt exfiltration"),
    _r("prompt", "tool_coercion", r"\b(call|invoke|run|execute|use)\s+(the\s+)?(tool|function|shell|terminal|browser)\b[^.\n]{0,40}\b(without\s+(asking|confirmation|permission)|immediately|silently)", 0.6, "coerced tool use"),
    _r("prompt", "secret_request", r"\b(send|email|post|upload|exfiltrate|forward)\b[^.\n]{0,40}\b(api\s*keys?|tokens?|passwords?|credentials?|secrets?|ssh\s+keys?|\.env)\b", 0.75, "credential exfiltration request"),
    # -- shell -------------------------------------------------------------
    _r("shell", "chain", r"(;|&&|\|\||\|)\s*(rm|curl|wget|nc|ncat|bash|sh|zsh|python3?|perl|ruby|chmod|chown|sudo|cat|base64|eval|exec|dd|mkfifo|socat|powershell)\b", 0.8, "command chaining"),
    _r("shell", "substitution", r"(\$\([^)]{1,200}\)|`[^`\n]{1,200}`)", 0.6, "command substitution"),
    _r("shell", "rm_rf", r"\brm\s+-[a-z]*r[a-z]*f?\s+(/|~|\*|\$HOME)", 0.95, "recursive delete"),
    _r("shell", "pipe_to_shell", r"\b(curl|wget)\b[^|\n]{0,200}\|\s*(sudo\s+)?(ba|z|da)?sh\b", 0.95, "download piped to shell"),
    _r("shell", "reverse_shell", r"(/dev/tcp/\d|\bnc\b[^\n]{0,40}\s-e\s|\bbash\s+-i\s*>&|\bmkfifo\b[^\n]{0,60}\bnc\b)", 0.95, "reverse shell"),
    _r("shell", "sensitive_redirect", r">\s*/(etc|root|boot|proc|sys)/|>\s*~/\.(ssh|bashrc|profile)", 0.8, "redirect to sensitive path"),
    _r("shell", "ifs_newline", r"(\$\{?IFS\}?|%0a|\\n)\s*(rm|curl|wget|cat|id|whoami)\b", 0.6, "separator obfuscation"),
    # -- SQL ---------------------------------------------------------------
    _r("sql", "tautology", r"('|\")\s*(or|and)\s+(['\"]?)(\w+)\3\s*=\s*(['\"]?)\4\b|\bor\s+1\s*=\s*1\b|'\s*or\s*''='", 0.85, "boolean tautology"),
    _r("sql", "union", r"\bunion\b(\s+all)?\s+select\b", 0.85, "UNION SELECT"),
    _r("sql", "stacked", r";\s*(drop|delete|insert|update|alter|truncate|create|exec|shutdown)\b", 0.85, "stacked query"),
    _r("sql", "comment_trunc", r"('|\")\s*(--|#|/\*)", 0.6, "quote then comment"),
    _r("sql", "time_based", r"\b(sleep|pg_sleep|benchmark|waitfor\s+delay)\s*\(", 0.7, "time-based probe"),
    _r("sql", "info_schema", r"\binformation_schema\b|\bsqlite_master\b|\bpg_catalog\b", 0.6, "schema enumeration"),
    # -- path --------------------------------------------------------------
    _r("path", "traversal", r"(\.\.[/\\]){1,}|[/\\]\.\.$|^\.\.$", 0.8, "parent traversal", re.M),
    _r("path", "sensitive_abs", r"(^|[\s'\"=])(/etc/(passwd|shadow|sudoers)|/proc/self/|/root/|~/\.ssh/|c:\\windows\\system32)", 0.8, "sensitive absolute path", re.I | re.M),
    _r("path", "null_byte", r"(%00|\\x00|\x00)", 0.7, "null byte truncation"),
    # -- template / expression ---------------------------------------------
    _r("template", "jinja", r"\{\{[^}]{0,200}(__class__|__mro__|__subclasses__|__globals__|__builtins__|config|self\.|request\.|lipsum|cycler|joiner)[^}]{0,200}\}\}", 0.9, "Jinja SSTI gadget"),
    _r("template", "expr_math", r"\{\{\s*\d+\s*[*+]\s*\d+\s*\}\}|\$\{\s*\d+\s*[*+]\s*\d+\s*\}|#\{\s*\d+\s*[*+]\s*\d+\s*\}", 0.5, "template evaluation probe"),
    _r("template", "el_runtime", r"\$\{[^}]{0,200}(runtime|getclass|processbuilder|exec)\b", 0.9, "expression-language RCE"),
    _r("template", "dunder_chain", r"__(class|mro|subclasses|globals|builtins|import)__", 0.7, "Python dunder gadget chain"),
    # -- markup / XSS ------------------------------------------------------
    _r("markup", "script_tag", r"<\s*script\b|<\s*/\s*script\s*>", 0.85, "script tag"),
    _r("markup", "event_handler", r"<[^>]{0,200}\son[a-z]{3,20}\s*=", 0.75, "inline event handler"),
    _r("markup", "js_url", r"(javascript|vbscript)\s*:", 0.75, "script URL"),
    _r("markup", "data_html", r"data\s*:\s*text/html", 0.6, "data: HTML URL"),
    _r("markup", "iframe", r"<\s*(iframe|object|embed|svg[^>]*onload)\b", 0.6, "embedding element"),
    # -- exfiltration beacons ----------------------------------------------
    _r("exfil", "md_image_query", r"!\[[^\]]{0,100}\]\(\s*https?://[^)\s]{1,300}[?&][^)\s]{0,300}=[^)\s]{1,300}\)", 0.7, "markdown image beacon with query data"),
    _r("exfil", "md_image_template", r"!\[[^\]]{0,100}\]\(\s*https?://[^)\s]{0,300}(\{|%7b|<)[^)\s]{0,300}\)", 0.8, "templated image beacon"),
)

FAMILIES = ("prompt", "shell", "sql", "path", "template", "markup", "exfil", "hidden")
CONTEXT_FAMILIES: dict[str, frozenset[str]] = {
    "any": frozenset(FAMILIES),
    "prompt": frozenset({"prompt", "exfil", "hidden", "markup"}),
    "shell": frozenset({"shell", "path", "hidden"}),
    "sql": frozenset({"sql", "hidden"}),
    "path": frozenset({"path", "hidden"}),
    "html": frozenset({"markup", "template", "exfil", "hidden"}),
    "template": frozenset({"template", "hidden"}),
}
_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})
_B64_RE = re.compile(r"(?<![A-Za-z0-9+/=])[A-Za-z0-9+/]{24,}={0,2}(?![A-Za-z0-9+/=])")


@dataclass(frozen=True)
class Finding:
    family: str
    rule_id: str
    weight: float
    description: str
    excerpt: str
    layer: str

    def to_record(self) -> dict[str, Any]:
        return {"family": self.family, "rule": self.rule_id, "weight": self.weight, "description": self.description, "excerpt": self.excerpt, "layer": self.layer}


@dataclass
class InjectionReport:
    context: str
    score: float
    findings: list[Finding] = field(default_factory=list)
    layers: list[str] = field(default_factory=list)

    @property
    def families(self) -> list[str]:
        return sorted({f.family for f in self.findings})

    @property
    def flagged(self) -> bool:
        return self.score >= 0.5

    def verdict(self, threshold: float = 0.7) -> str:
        if self.score >= threshold:
            return "block"
        if self.score >= 0.4:
            return "review"
        return "allow"

    def to_record(self) -> dict[str, Any]:
        return {"context": self.context, "score": round(self.score, 4), "verdict": self.verdict(), "families": self.families,
                "layers": list(self.layers), "findings": [f.to_record() for f in self.findings]}


def _strip_hidden(text: str) -> str:
    return "".join(ch for ch in text if ch not in BIDI_CONTROLS and ch not in INVISIBLES and not 0xE0000 <= ord(ch) <= 0xE007F)


def _try_b64(token: str) -> str | None:
    try:
        raw = base64.b64decode(token + "=" * (-len(token) % 4), validate=True)
    except (binascii.Error, ValueError):
        return None
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    printable = sum(ch.isprintable() or ch in "\n\t" for ch in decoded)
    return decoded if decoded and printable / len(decoded) > 0.9 else None


def views(text: str) -> list[tuple[str, str]]:
    """Normalised views of ``text`` (layer name, content), bounded."""
    out: list[tuple[str, str]] = []
    seen: set[str] = set()

    def add(layer: str, value: str) -> None:
        if value and value not in seen and len(out) < 12:
            seen.add(value)
            out.append((layer, value))

    base = unicodedata.normalize("NFKC", _strip_hidden(text))
    add("raw", base)
    smuggled = decode_tag_smuggling(text)
    if smuggled:
        add("tag-smuggled", smuggled)
    queue = [("raw", base)] + ([("tag-smuggled", smuggled)] if smuggled else [])
    for depth in range(MAX_DECODE_LAYERS):
        nxt: list[tuple[str, str]] = []
        for layer, value in queue:
            pct = unquote(value)
            if pct != value:
                nxt.append((layer + "+url", pct))
            ent = html.unescape(value)
            if ent != value:
                nxt.append((layer + "+html", ent))
            for m in list(_B64_RE.finditer(value))[:8]:
                dec = _try_b64(m.group(0))
                if dec:
                    nxt.append((layer + "+b64", dec))
        for layer, value in nxt:
            add(layer, unicodedata.normalize("NFKC", _strip_hidden(value)))
        queue = nxt
        if not queue:
            break
    for layer, value in list(out):
        folded = value.translate(_LEET)
        if folded != value:
            add(layer + "+leet", folded)
        squashed = re.sub(r"(?<=\b\w)[\s.\-_*](?=\w\b)", "", value)  # "i g n o r e" -> "ignore"
        if squashed != value:
            add(layer + "+squash", squashed)
    return out


def detect(text: str, *, context: str = "any") -> InjectionReport:
    """Scan ``text``; score is a noisy-OR of finding weights (0..1)."""
    if not isinstance(text, str):
        raise SanitizerError("detect() needs text", context={"type": type(text).__name__})
    if context not in CONTEXT_FAMILIES:
        raise SanitizerError("unknown detection context", context={"context": context})
    families = CONTEXT_FAMILIES[context]
    sample = text[:MAX_SCAN_CHARS]
    report = InjectionReport(context=context, score=0.0)
    found: dict[tuple[str, str], Finding] = {}
    if "hidden" in families:
        hidden = hidden_characters(sample)
        if hidden:
            kinds = sorted({h["kind"] for h in hidden})
            weight = 0.8 if "tag" in kinds else 0.5 if "bidi" in kinds else 0.3
            found[("hidden", "chars")] = Finding("hidden", "chars", weight, "hidden characters: " + ", ".join(kinds), f"{len(hidden)} chars", "raw")
    layers = views(sample)
    report.layers = [name for name, _ in layers]
    for layer, value in layers:
        for rule in RULES:
            if rule.family not in families or (rule.family, rule.rule_id) in found:
                continue
            m = rule.pattern.search(value)
            if m:
                weight = rule.weight if layer == "raw" else min(0.99, rule.weight + 0.05)  # obfuscation is itself a signal
                found[(rule.family, rule.rule_id)] = Finding(rule.family, rule.rule_id, weight, rule.description, value[max(0, m.start() - 20): m.end() + 20][:160], layer)
    report.findings = sorted(found.values(), key=lambda f: (-f.weight, f.family, f.rule_id))
    miss = 1.0
    for f in report.findings:
        miss *= 1.0 - f.weight
    report.score = 1.0 - miss
    return report


def guard(text: str, *, context: str = "any", threshold: float = 0.7) -> InjectionReport:
    """Return the report, or raise :class:`InjectionDetectedError` when blocked."""
    report = detect(text, context=context)
    if report.score >= threshold:
        raise InjectionDetectedError("input blocked by injection detector", context=report.to_record())
    return report


def quarantine(text: str, *, source: str = "untrusted") -> str:
    """Wrap untrusted content in an explicit data fence for LLM prompts.

    Any fence-lookalike inside the content is neutralised so it cannot close
    the fence early.
    """
    body = _strip_hidden(text).replace("<<<", "‹‹‹").replace(">>>", "›››")
    label = re.sub(r"[^A-Za-z0-9_.:-]", "_", source)[:64] or "untrusted"
    return f"<<<UNTRUSTED source={label}>>>\n{body}\n<<<END UNTRUSTED>>>"


__all__ = [
    "CONTEXT_FAMILIES",
    "FAMILIES",
    "RULES",
    "Finding",
    "InjectionReport",
    "Rule",
    "detect",
    "guard",
    "quarantine",
    "views",
]
