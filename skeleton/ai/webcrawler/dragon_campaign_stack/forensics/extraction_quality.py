"""Selected-text extraction fidelity and parse-artifact quality diagnostics.

Detects finite, rule-coded extraction artifacts in exact retained spans.
Scores indicate *review needs*, not unsafe content, remote page errors,
plagiarism, factual confidence, or permission for publishing/training.
Literal external strings never enter public receipts.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import re
import unicodedata

from ..contracts import digest, integer
from .frames import FrameSet


_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_HTML = re.compile(r"</?[a-z][a-z0-9-]{0,30}(?:\s[^>]{0,256})?>", re.I)
_MARKDOWN_LINK = re.compile(r"\[[^\]\n]{1,160}\]\(\S{1,512}\)")
_ENTITY = re.compile(r"&(?:[a-z]{2,12}|#\d{1,7}|#x[0-9a-f]{1,6});", re.I)
_LONG_RUN = re.compile(r"(.)\1{40,}", re.DOTALL)
_WHITESPACE = re.compile(r"\s{6,}")
_SENTENCE_BREAK = re.compile(r"[.!?\n]")
_NOISY_TITLE = ("cookie policy", "privacy policy", "accept cookies",
                "all rights reserved", "enable javascript", "sign in to continue")


@dataclass(frozen=True)
class ExtractionFinding:
    source_id: str
    anchor_digest: str
    passage_hash: str
    characters: int
    utf8_bytes: int
    token_count: int
    control_characters: int
    html_tag_signals: int
    html_entity_signals: int
    markdown_link_signals: int
    repeated_character_runs: int
    collapsed_whitespace_runs: int
    boilerplate_phrase_signals: int
    sparse_word_density: bool
    review_codes: tuple[str, ...]
    extraction_verified: bool = False


@dataclass(frozen=True)
class ExtractionQualityReport:
    frame_set_digest: str
    findings: tuple[ExtractionFinding, ...]
    held_source_ids: tuple[str, ...]
    suspect_passages: int
    compared_characters: int
    compared_bytes: int
    report_digest: str
    remote_page_rechecked: bool = False
    extraction_fidelity_certified: bool = False
    external_text_exported: bool = False


def inspect_extraction_quality(
    frames: FrameSet, *,
    max_passage_bytes: int = 24_000,
    max_total_bytes: int = 131_072,
    sparse_min_chars: int = 160,
    sparse_word_ratio: float = .11,
) -> ExtractionQualityReport:
    if not isinstance(frames, FrameSet):
        raise TypeError("bound selected source frames required")
    integer(max_passage_bytes, "extraction passage bytes", 128, 24_000)
    integer(max_total_bytes, "extraction total bytes", 1024, 131_072)
    integer(sparse_min_chars, "extraction sparse threshold", 16, 4096)
    if (type(sparse_word_ratio) not in (float, int)
            or not .01 <= sparse_word_ratio <= 1.0):
        raise ValueError("invalid sparse word ratio")
    findings = []
    held = set()
    total_bytes = total_chars = 0
    for frame in frames.frames:
        body = frame.text
        size = len(body.encode("utf-8"))
        if size > max_passage_bytes:
            raise ValueError("extraction source span exceeds local limit")
        total_bytes += size
        total_chars += len(body)
        if total_bytes > max_total_bytes:
            raise ValueError("total inspected text exceeds local limit")
        tokens = _WORD.findall(body)
        controls = sum(unicodedata.category(ch) in ("Cc", "Cf")
                       and ch not in "\n\r\t" for ch in body)
        tags = len(_HTML.findall(body))
        entities = len(_ENTITY.findall(body))
        markdown = len(_MARKDOWN_LINK.findall(body))
        repeated = len(_LONG_RUN.findall(body))
        whitespace = len(_WHITESPACE.findall(body))
        lowered = body.casefold()
        policy_phrases = sum(phrase in lowered for phrase in _NOISY_TITLE)
        density = sum(len(word) for word in tokens) / max(1, len(body))
        sparse = len(body) >= sparse_min_chars and density < sparse_word_ratio
        flags = []
        if controls:
            flags.append("nonprintable_extraction_characters")
        if tags >= 3:
            flags.append("html_markup_residue")
        if entities >= 3:
            flags.append("unresolved_html_entities")
        if markdown >= 4:
            flags.append("excess_markdown_links")
        if repeated:
            flags.append("repeated_character_payload")
        if whitespace >= 3:
            flags.append("excess_whitespace_artifacts")
        if policy_phrases >= 2:
            flags.append("navigation_or_consent_boilerplate")
        if sparse:
            flags.append("sparse_text_extraction")
        if flags:
            held.add(frame.anchor.source_id)
        findings.append(ExtractionFinding(
            frame.anchor.source_id, frame.anchor.anchor_digest,
            frame.anchor.passage_hash, len(body), size, len(tokens),
            controls, tags, entities, markdown, repeated, whitespace,
            policy_phrases, sparse, tuple(sorted(flags)),
        ))
    payload = {"frame_set": frames.frame_set_digest,
               "findings": [asdict(x) for x in findings],
               "limits": (max_passage_bytes, max_total_bytes,
                          sparse_min_chars, sparse_word_ratio)}
    return ExtractionQualityReport(
        frames.frame_set_digest, tuple(findings), tuple(sorted(held)),
        sum(bool(row.review_codes) for row in findings),
        total_chars, total_bytes, digest(payload),
    )
