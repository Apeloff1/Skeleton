"""Bounded, inert inspection at the canonical Dragon acquisition boundary.

This is a conservative heuristic, not a malware classifier or authorization
engine. A source can never grant a new URL, credential, tool or execution
permission. Known instruction artifacts are data, not agent configuration.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import html
import re
import unicodedata
from urllib.parse import unquote, urlsplit

MAX_INPUT_BYTES = 2_097_152
MAX_NORMALIZED_CHARS = 4_194_304
MAX_MATCHES = 16
MAX_INCIDENTS = 128

# Every pattern is bounded or has a fixed literal prefix. Do not introduce
# attacker-controlled regexes, nested repetition or open-ended wildcards.
_PATTERNS = {
    "authority_override": re.compile(
        r"(?:\b(?:ignore|disregard|override|forget|bypass)\s{1,16}(?:all\s{1,16})?"
        r"(?:previous|prior|earlier|system|developer|user|safety|security|original)"
        r"\s{1,16}(?:instructions?|rules?|polic(?:y|ies)|prompts?|restrictions?)\b"
        r"|\b(?:ignorer?|se bort fra|overstyr)\s{1,16}(?:alle\s{1,16})?"
        r"(?:tidligere|forrige|systemets)\s{1,16}(?:instruksjoner|regler)\b"
        r"|\bignoriere\s{1,16}(?:alle\s{1,16})?(?:vorherigen|bisherigen)\s{1,16}anweisungen\b"
        r"|\bignore[rz]?\s{1,16}(?:toutes\s{1,16})?(?:les\s{1,16})?instructions\s{1,16}(?:précédentes|antérieures)\b"
        r"|\bignora\s{1,16}(?:todas\s{1,16})?(?:las\s{1,16})?instrucciones\s{1,16}(?:anteriores|previas)\b"
        r"|\bignore\s{1,16}(?:todas\s{1,16})?(?:as\s{1,16})?instruções\s{1,16}anteriores\b"
        r"|(?:忽略|无视)(?:所有)?(?:之前|先前|以上|系统)(?:的)?(?:指令|指示)"
        r"|(?:以前|これまで|前)の(?:指示|命令)を(?:無視|上書き))"
    ),
    "role_impersonation": re.compile(
        r"(?:<\|(?:im_start|system|assistant|developer|endoftext)\|>|\[inst\]|"
        r"<<sys>>|(?:^|\n)\s{0,16}(?:system|developer|assistant)\s{0,8}:)"
    ),
    "secret_request": re.compile(
        r"\b(?:send|upload|post|exfiltrate|reveal|disclose|print|forward|dump)\b"
        r"[\s\S]{0,96}\b(?:passwords?|api[\s_-]{0,4}keys?|secrets?|credentials?|"
        r"access[\s_-]{0,4}tokens?|system[\s_-]{0,4}prompts?)\b"
    ),
    "tool_execution": re.compile(
        r"\b(?:execute|invoke|call|run|launch)\s{1,16}(?:the\s{1,16})?"
        r"(?:shell|terminal|python|command|tool|powershell|bash|javascript|script)\b"
    ),
    "agent_directive": re.compile(
        r"\b(?:ai\s{1,8})?(?:agent|assistant|crawler|bot|spider)s?"
        r"\s{0,8}(?::|,|\b(?:must|should|shall|always|now)\b)"
    ),
    "policy_evasion": re.compile(
        r"\b(?:disable|bypass|ignore|evade|skip)\s{1,16}(?:the\s{1,16})?"
        r"(?:robots(?:\.txt)?|authentication|authorization|rate[\s_-]{0,4}limits?|"
        r"access[\s_-]{0,4}controls?|safety[\s_-]{0,4}checks?)\b"
    ),
    "instruction_artifact": re.compile(
        r"\b(?:agents\.md|llms(?:-full)?\.txt|crawler[-_]instructions\.(?:txt|md|json))\b"
        r"[\s\S]{0,64}\b(?:follow|obey|execute|override|mandatory)\b"
    ),
}
_CODES = frozenset((*_PATTERNS, "instruction_file", "inspection_limit"))
_INSTRUCTION_NAMES = frozenset({
    "agents.md", "agent.md", "llms.txt", "llms-full.txt",
    "crawler-instructions.txt", "crawler-instructions.md", "crawler-instructions.json",
    "agent-instructions.txt", "agent-instructions.md", "agent-instructions.json",
})
# Only remove ordinary markup in a SECOND inspection view. Preserve the
# original decoded view for role tokens. Bounded tag size avoids quadratic work.
_TAG = re.compile(r"<[a-z/!][^<>]{0,512}>", re.I)
_SPACE = re.compile(r"\s{1,256}")
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_JSON_ESCAPE = re.compile(r"\\u([0-9a-fA-F]{4})")
_REP_FIELDS = frozenset({"user-agent", "allow", "disallow", "crawl-delay", "request-rate", "sitemap"})


def _decode_escape(match: re.Match[str]) -> str:
    value = int(match.group(1), 16)
    # Never produce unpaired surrogate characters in a detection view.
    return match.group() if 0xD800 <= value <= 0xDFFF else chr(value)
_TEXT_TYPES = frozenset({
    "application/json", "application/xml", "application/xhtml+xml",
    "application/javascript", "application/ld+json", "application/rss+xml",
    "application/atom+xml", "image/svg+xml",
})


@dataclass(frozen=True)
class InstructionObservation:
    stage: str
    categories: tuple[str, ...]
    match_count_lower_bound: int
    inspection_limited: bool
    input_digest: str
    inspected_bytes: int
    match_fingerprints: tuple[tuple[str, str], ...]

    @property
    def held(self) -> bool:
        return bool(self.categories)


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _normalize(text: str) -> str:
    # Drop zero-width/bidi formatting in the detection view only. Original
    # text and provenance are never rewritten or reinterpreted as authority.
    # Two finite layers catch escaped strings without evaluating JSON, scripts,
    # or arbitrary encoded payloads. Source bytes remain untouched.
    for _ in range(2):
        text = html.unescape(_JSON_ESCAPE.sub(_decode_escape, text))
        if len(text) > MAX_NORMALIZED_CHARS:
            raise ValueError("inspection normalization limit")
    text = unicodedata.normalize("NFKC", text).casefold()
    if len(text) > MAX_NORMALIZED_CHARS:
        raise ValueError("inspection normalization limit")
    return "".join(
        ch for ch in text if unicodedata.category(ch) != "Cf"
    )


def _inspect(raw: bytes, *, stage: str, instruction_file: bool = False,
             markup: bool = False) -> InstructionObservation:
    if type(raw) is not bytes or stage not in {"response", "extracted", "robots_comment"}:
        raise ValueError("invalid inspection inputs")
    digest = _digest(raw)
    categories = {"instruction_file"} if instruction_file else set()
    count = 0
    fingerprints = []
    limited = len(raw) > MAX_INPUT_BYTES
    if not limited:
        try:
            decoded = _normalize(raw.decode("utf-8", errors="replace"))
        except ValueError:
            limited = True
        else:
            # Preserve original raw-normalized view, then inspect visible
            # split-token markup. Never parse scripts or execute embedded code.
            flattened = _SPACE.sub(" ", _TAG.sub("", decoded)) if markup else _SPACE.sub(" ", decoded)
            views = (decoded,) if flattened == decoded else (decoded, flattened)
            for name, pattern in _PATTERNS.items():
                local_count = 0
                first = None
                for view in views:
                    view_count = 0
                    for match in pattern.finditer(view):
                        if first is None:
                            first = _digest(match.group().encode("utf-8"))
                        view_count += 1
                        if view_count >= MAX_MATCHES:
                            break
                    local_count = max(local_count, view_count)
                if local_count:
                    categories.add(name)
                    # Count pattern detections, not unique physical spans.
                    # Two normalized views of the same match do not double count.
                    count = min(MAX_MATCHES, count + local_count)
                    fingerprints.append((name, first))
    if limited:
        categories.add("inspection_limit")
    return InstructionObservation(
        stage, tuple(sorted(categories)), count, limited, digest,
        min(len(raw), MAX_INPUT_BYTES), tuple(sorted(fingerprints)),
    )


def inspect_response(url: str, media_type: str, body: bytes) -> InstructionObservation | None:
    if not isinstance(url, str) or not isinstance(media_type, str) or type(body) is not bytes:
        raise ValueError("invalid response inspection")
    name = unquote(urlsplit(url).path.rsplit("/", 1)[-1]).casefold()
    artifact = name in _INSTRUCTION_NAMES
    text_type = (media_type.startswith("text/") or media_type in _TEXT_TYPES
                 or media_type.endswith(("+xml", "+json")))
    if not artifact and not text_type:
        return None
    return _inspect(body, stage="response", instruction_file=artifact,
                    markup=media_type in {"text/html", "application/xhtml+xml", "image/svg+xml"})


def inspect_extracted(title: str, text: str) -> InstructionObservation:
    if not isinstance(title, str) or not isinstance(text, str):
        raise ValueError("non-text extraction cannot be inspected")
    # The delimiter prevents a title from being interpreted as a role
    # continuation of the body. Inspection covers both, including title-only attacks.
    return _inspect((title + "\n" + text).encode("utf-8"), stage="extracted")


def inspect_robots_comments(body: bytes) -> InstructionObservation:
    if type(body) is not bytes:
        raise ValueError("invalid robots input")
    # Comments and non-REP fields carry no access or tool authority. Known
    # access/retention metadata is interpreted separately by its typed parser.
    inert = []
    for line in body.splitlines():
        policy, separator, comment = line.partition(b"#")
        if separator and comment:
            inert.append(comment)
        key, colon, _ = policy.partition(b":")
        if policy.strip() and (not colon or key.strip().decode("ascii", "ignore").casefold() not in _REP_FIELDS):
            inert.append(policy)
    return _inspect(b"\n".join(inert), stage="robots_comment")


def retained_robots_policy(text: str) -> str:
    """Store only known policy fields; comments and arbitrary prose are inert."""
    lines = []
    for line in text.splitlines():
        policy = line.partition("#")[0]
        key, colon, _ = policy.partition(":")
        if colon and key.strip().casefold() in _REP_FIELDS:
            lines.append(policy)
        else:
            lines.append("")
    return "\n".join(lines)


def incident_receipt(
    observation: InstructionObservation, *, url: str, sequence: int,
    retain_fingerprint: bool,
) -> dict:
    if not observation.held or type(sequence) is not int or sequence < 1:
        raise ValueError("unheld incident cannot be recorded")
    return {
        "sequence": sequence,
        "url_digest": _digest(url.encode("utf-8")),
        "stage": observation.stage,
        "categories": list(observation.categories),
        "match_count_lower_bound": observation.match_count_lower_bound,
        "inspection_limited": observation.inspection_limited,
        "inspected_bytes": observation.inspected_bytes,
        "input_digest": observation.input_digest if retain_fingerprint else None,
        "match_fingerprints": dict(observation.match_fingerprints) if retain_fingerprint else {},
        "payload_retained": False,
        "execution_authorized": False,
    }


def validate_incidents(rows: object, *, sequence: int, requests: int) -> None:
    if not isinstance(rows, list) or len(rows) > min(MAX_INCIDENTS, requests):
        raise ValueError("instruction incident capacity exceeded")
    previous = 0
    keys = {"sequence", "url_digest", "stage", "categories",
            "match_count_lower_bound", "inspection_limited", "inspected_bytes",
            "input_digest", "match_fingerprints", "payload_retained", "execution_authorized"}
    for row in rows:
        if not isinstance(row, dict) or set(row) != keys:
            raise ValueError("invalid incident receipt")
        n = row["sequence"]
        categories = row["categories"]
        if (type(n) is not int or not previous < n <= sequence
                or not isinstance(row["url_digest"], str) or not _HEX.fullmatch(row["url_digest"])
                or row["stage"] not in {"response", "extracted", "robots_comment"}
                or not isinstance(categories, list) or not 1 <= len(categories) <= len(_CODES)
                or any(not isinstance(code, str) or code not in _CODES for code in categories)
                or categories != sorted(set(categories))
                or type(row["match_count_lower_bound"]) is not int
                or not 0 <= row["match_count_lower_bound"] <= MAX_MATCHES
                or type(row["inspection_limited"]) is not bool
                or row["inspection_limited"] != ("inspection_limit" in categories)
                or type(row["inspected_bytes"]) is not int
                or not 0 <= row["inspected_bytes"] <= MAX_INPUT_BYTES
                or (row["input_digest"] is not None and
                    (not isinstance(row["input_digest"], str) or not _HEX.fullmatch(row["input_digest"])))
                or not isinstance(row["match_fingerprints"], dict)
                or any(code not in categories or code not in _PATTERNS
                       or not isinstance(value, str) or not _HEX.fullmatch(value)
                       for code, value in row["match_fingerprints"].items())
                or (row["input_digest"] is None and row["match_fingerprints"])
                or (row["input_digest"] is not None and set(row["match_fingerprints"]) !=
                    set(categories).intersection(_PATTERNS))
                or row["payload_retained"] is not False or row["execution_authorized"] is not False):
            raise ValueError("invalid incident custody")
        previous = n


def incident_summary(rows: list[dict]) -> dict:
    categories = Counter(code for row in rows for code in row["categories"])
    return {"count": len(rows), "categories": dict(sorted(categories.items())),
            "records": [dict(row, categories=list(row["categories"]),
                             match_fingerprints=dict(row["match_fingerprints"])) for row in rows],
            "payload_retained": False, "execution_authorized": False}
