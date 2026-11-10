"""Source-only, process-bounded PDF acquisition for Dragon CrawlRun.

Network acquisition, robots admission, consent, request reservations and source
custody remain inside CrawlRun. PDF parser runs in a finite-memory/CPU child,
never opening user-selected filenames or fetching links and annotations.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys


PDF_MEDIA_TYPE = "application/pdf"


class PDFDocumentError(ValueError):
    """PDF cannot be safely represented under declared resource limits."""


@dataclass(frozen=True)
class ExtractedPDF:
    text: str
    title: str
    links: tuple[str, ...] = ()
    truncated: bool = False
    body_executed: bool = False
    reference_trusted: bool = False
    network_used: bool = False


def extract_pdf_document(
    body: bytes, *, max_chars: int = 524288,
    deadline_seconds: float = 8.0,
) -> ExtractedPDF:
    if (
        type(body) is not bytes or not body.startswith(b"%PDF-")
        or len(body) > 2_097_152
        or type(max_chars) is not int or not 512 <= max_chars <= 2_097_152
        or isinstance(deadline_seconds, bool)
        or not isinstance(deadline_seconds, (float, int))
        or not 1 <= deadline_seconds <= 8
    ):
        raise PDFDocumentError("PDF input or limits are invalid")
    if os.name != "posix":
        raise PDFDocumentError("PDF requires hard process memory and CPU limits")
    path = Path(__file__).with_name("pdf_worker.py")
    try:
        program = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise PDFDocumentError("PDF worker source missing") from exc
    if len(program) > 32768:
        raise PDFDocumentError("unbounded PDF worker source")
    try:
        result = subprocess.run(
            [sys.executable, "-I", "-c", program, str(max_chars)],
            input=body, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=float(deadline_seconds), check=False,
            env={"PYTHONDONTWRITEBYTECODE": "1", "LANG": "C.UTF-8"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PDFDocumentError("PDF parser did not meet resource deadline") from exc
    if result.returncode != 0 or len(result.stdout) > max_chars * 4 + 8192:
        raise PDFDocumentError("isolated PDF parser rejected document")
    try:
        item = json.loads(result.stdout.decode("utf-8", errors="strict"))
    except (ValueError, UnicodeError) as exc:
        raise PDFDocumentError("PDF worker returned malformed output") from exc
    if (
        not isinstance(item, dict)
        or set(item) != {"text", "title", "truncated"}
        or not isinstance(item["text"], str)
        or not item["text"].strip() or len(item["text"]) > max_chars
        or "\x00" in item["text"]
        or not isinstance(item["title"], str) or len(item["title"]) > 512
        or type(item["truncated"]) is not bool
    ):
        raise PDFDocumentError("PDF output violates finite evidence contract")
    return ExtractedPDF(
        text=item["text"], title=item["title"],
        truncated=item["truncated"],
    )
