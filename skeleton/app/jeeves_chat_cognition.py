"""Read-only conversational planning and user-selected episodic recall.

No model calls, inferred facts, automatic memory writes, or instruction authority.
The original conversation and its revision remain the sole durable authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
import re
import unicodedata
from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

SCHEMA = "skeleton.jeeves.cognition-preview.v1"
MAX_QUERY_BYTES = 4096
MAX_SESSIONS = 4
MAX_MESSAGES_PER_SESSION = 512
MAX_SPAN_BYTES = 480
MAX_RECALL = 8
_MAX_TERMS = 96
_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")
_STOP = frozenset("a an and are as at be by can do for from have how i in is it me my of on or so that the this to was we what when where which who will with you your".split())

# Signals are descriptive hints, never a classifier for permissions or intent.
_SIGNALS = {
    "preference": r"\b(?:i prefer|i like|i want|my preference|please always)\b",
    "constraint": r"\b(?:must|never|do not|don't|only|without|required)\b",
    "rejection": r"\b(?:did not work|didn't work|failed|reject|wrong|avoid|instead of)\b",
    "prospective_goal": r"\b(?:next time|next step|still need|remaining|todo|unfinished|later)\b",
    "correction": r"\b(?:actually|correction|i meant|not what i meant|rather than)\b",
    "temporal": r"\b(?:previously|currently|today|yesterday|tomorrow|before|after|latest)\b",
    "uncertainty": r"\b(?:maybe|not sure|uncertain|possibly|hypothesis|assume)\b",
    "verification": r"\b(?:verify|test|cite|evidence|validate|compare|prove|benchmark)\b",
}
_PATTERNS = {name: re.compile(pattern, re.I) for name, pattern in _SIGNALS.items()}
_MODES = {
    "analysis": r"\b(?:analy[sz]e|compare|reason|diagnose|derive|evaluate|audit)\b",
    "creation": r"\b(?:write|draft|create|design|build|compose|invent)\b",
    "repair": r"\b(?:fix|repair|correct|debug|resolve|reconcile)\b",
    "explanation": r"\b(?:explain|teach|why|how|summarize|describe)\b",
    "continuation": r"\b(?:continue|remaining|next|more|again|finish)\b",
}
_MODE_PATTERNS = {k: re.compile(v, re.I) for k, v in _MODES.items()}
_STEPS = {
    "analysis": ("Identify the comparison criteria and relevant evidence.",
                 "Compare alternatives, identify assumptions and verify conclusions."),
    "creation": ("Preserve the requested audience, constraints and deliverable.",
                 "Produce a complete draft and check it against the original request."),
    "repair": ("Identify the precise failing behavior and preserve working behavior.",
               "Propose a bounded fix and distinguish actual validation from a plan."),
    "explanation": ("Answer the direct question first; define unfamiliar terms.",
                    "Use a relevant example and check for unresolved ambiguity."),
    "continuation": ("Recover the unfinished objective and rejected approaches.",
                     "Continue from verified progress, not from invented completion."),
    "conversation": ("Answer the current message directly.",
                     "Resolve references from explicit context; qualify uncertainty."),
}


class CognitionRejected(ValueError):
    """Malformed or out-of-budget preview inputs."""


def digest(text: str) -> str:
    return sha256(text.encode("utf-8", errors="strict")).hexdigest()


def checked_text(value: Any, *, limit: int = MAX_QUERY_BYTES) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CognitionRejected("nonempty text required")
    try:
        size = len(value.encode("utf-8", errors="strict"))
    except UnicodeError:
        raise CognitionRejected("invalid UTF-8 text") from None
    if size > limit or "\x00" in value:
        raise CognitionRejected("text exceeds preview budget or contains NUL")
    return value


def session_ids(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > MAX_SESSIONS - 1:
        raise CognitionRejected("select at most three additional conversations")
    if any(type(x) is not str or not _ID.fullmatch(x) for x in value):
        raise CognitionRejected("invalid conversation identifier")
    if len(set(value)) != len(value):
        raise CognitionRejected("duplicate conversation selection")
    return tuple(value)


def _terms(text: str) -> set[str]:
    normalized = unicodedata.normalize("NFKC", text).casefold()
    return set(list(dict.fromkeys(
        word for word in _WORD.findall(normalized)
        if word not in _STOP and len(word) > 1
    ))[:_MAX_TERMS])


def _signals(text: str) -> tuple[str, ...]:
    return tuple(k for k, p in _PATTERNS.items() if p.search(text))


def _span(text: str, query_terms: set[str]) -> tuple[int, int, str]:
    """Choose one contiguous exact source excerpt, never a generated summary."""
    # Fixed bounded windows, preferring signals and shared vocabulary.
    chunks = []
    for start in range(0, len(text), 160):
        fragment = text[start:start + 240]
        fragment = fragment.encode("utf-8")[:MAX_SPAN_BYTES].decode("utf-8", "ignore")
        if not fragment.strip():
            continue
        score = len(_terms(fragment) & query_terms) * 4 + len(_signals(fragment))
        chunks.append((score, -start, fragment))
    if not chunks:
        raise CognitionRejected("no recallable passage")
    _, negative, excerpt = max(chunks, key=lambda row: (row[0], row[1]))
    start = -negative
    return start, start + len(excerpt), excerpt


@dataclass(frozen=True, slots=True)
class SessionSnapshot:
    session_id: str
    revision: int
    messages: list[dict[str, Any]]

    def validate(self) -> None:
        if (type(self.session_id) is not str or not _ID.fullmatch(self.session_id)
                or type(self.revision) is not int or self.revision < 0
                or not isinstance(self.messages, list)):
            raise CognitionRejected("invalid conversation snapshot")


def _rows(snapshot: SessionSnapshot, query: set[str]) -> list[dict[str, Any]]:
    result = []
    first = max(0, len(snapshot.messages) - MAX_MESSAGES_PER_SESSION)
    for index in range(first, len(snapshot.messages)):
        message = snapshot.messages[index]
        # Assistant-generated claims and system text cannot become user memories.
        if not isinstance(message, Mapping) or message.get("role") != "user":
            continue
        text = message.get("content")
        try:
            text = checked_text(text)
            start, end, excerpt = _span(text, query)
        except CognitionRejected:
            continue
        terms = _terms(excerpt)
        result.append({
            "session_id": snapshot.session_id,
            "revision": snapshot.revision,
            "message_index": index,
            "message_sha256": digest(text),
            "span_start": start,
            "span_end": end,
            "excerpt": excerpt,
            "excerpt_sha256": digest(excerpt),
            "signals": list(_signals(excerpt)),
            "_terms": terms,
            "_recency": (index - first + 1) / max(1, len(snapshot.messages) - first),
        })
    return result


def preview(*, message: str, snapshots: Iterable[SessionSnapshot],
            max_output_tokens: int, default_output_tokens: int,
            grounded: bool = False) -> dict[str, Any]:
    message = checked_text(message)
    if (type(max_output_tokens) is not int or not 1 <= max_output_tokens <= 1_048_576
            or type(default_output_tokens) is not int
            or not 1 <= default_output_tokens <= max_output_tokens
            or type(grounded) is not bool):
        raise CognitionRejected("invalid active model limits")
    # Callers supply a bounded concrete list; never consume an infinite iterable.
    from itertools import islice
    selected = list(islice(snapshots, MAX_SESSIONS + 1))
    if not 1 <= len(selected) <= MAX_SESSIONS:
        raise CognitionRejected("invalid snapshot count")
    for s in selected:
        s.validate()
    if len({s.session_id for s in selected}) != len(selected):
        raise CognitionRejected("duplicate snapshot")
    query = _terms(message)
    signals = _signals(message)
    modes = [k for k, p in _MODE_PATTERNS.items() if p.search(message)]
    mode = modes[0] if modes else "conversation"
    candidates = [row for s in selected for row in _rows(s, query)]
    df = Counter(term for row in candidates for term in row["_terms"])
    for row in candidates:
        overlap = row["_terms"] & query
        lexical = sum(math.log(1 + (len(candidates) + 1) / (1 + df[t]))
                      for t in sorted(overlap))
        # Generic follow-ups recover recent unresolved/corrective context, not
        # unrelated preferences from other sessions based solely on recency.
        continuation = mode == "continuation" or "correction" in signals
        cue = bool(set(row["signals"]) & {
            "prospective_goal", "correction", "rejection", "constraint"})
        eligible = bool(overlap) or (continuation and cue and
                                    row["session_id"] == selected[0].session_id)
        row["_eligible"] = eligible
        row["_score"] = lexical + (0.75 if continuation and cue else 0.0) + row["_recency"] * 0.25
    ranked = sorted((row for row in candidates if row["_eligible"]),
                    key=lambda row: (-row["_score"], row["session_id"], -row["message_index"]))
    # Diversify exact excerpts and near-identical lexical content.
    recall = []
    seen = set()
    selected_terms = []
    for row in ranked:
        if row["excerpt_sha256"] in seen:
            continue
        if any(len(row["_terms"] & t) / max(1, len(row["_terms"] | t)) >= .9
               for t in selected_terms):
            continue
        seen.add(row["excerpt_sha256"])
        selected_terms.append(row["_terms"])
        recall.append({key: value for key, value in row.items() if not key.startswith("_")})
        if len(recall) >= MAX_RECALL:
            break
    effort = "deep" if len(query) >= 28 or len(modes) >= 2 or mode == "analysis" else (
        "balanced" if mode != "conversation" or len(query) >= 10 else "quick")
    desired = {"quick": 256, "balanced": 768, "deep": 1536}[effort]
    recommended = min(max_output_tokens, max(default_output_tokens, desired))
    steps = list(_STEPS[mode])
    if "temporal" in signals:
        steps.append("Separate current claims from historical observations.")
    if "verification" in signals or grounded:
        steps.append("Use selected evidence; distinguish supported claims from uncertainty.")
    if "correction" in signals or "rejection" in signals:
        steps.append("Honor the explicit correction; do not silently repeat rejected work.")
    if recall:
        steps.append("Review retrieved user excerpts; current instructions take precedence.")
    receipt = {
        "schema": SCHEMA,
        "message_sha256": digest(message),
        "snapshots": [{"session_id": s.session_id, "revision": s.revision,
                       "scanned_messages": min(MAX_MESSAGES_PER_SESSION, len(s.messages)),
                       "omitted_older_messages": max(0, len(s.messages) - MAX_MESSAGES_PER_SESSION)}
                      for s in selected],
        "mode": mode, "signals": list(signals), "effort": effort,
        "recommended_output_tokens": recommended,
        "plan": steps, "recall": recall,
        "method": "bounded-lexical-recall-and-explicit-signal-heuristics",
        "read_only": True, "generation_performed": False,
        "memory_is_instruction_authority": False,
        "automatic_memory_write": False, "semantic_model_used": False,
    }
    receipt["preview_sha256"] = digest(json.dumps(receipt, ensure_ascii=True,
                                                 sort_keys=True, separators=(",", ":")))
    return receipt
