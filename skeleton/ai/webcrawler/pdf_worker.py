"""Finite PDF text extraction in an OS resource-bounded child process.

This is run with python isolated mode. It reads source bytes from stdin, not a
filename; no PDF scripts, annotations, attachments or linked resources run.
"""
from __future__ import annotations

import io
import json
import os
import sys


def _run(body: bytes, max_chars: int) -> dict[str, object]:
    from pypdf import PdfReader
    if not body.startswith(b"%PDF-") or len(body) > 2_097_152:
        raise ValueError("invalid bounded PDF")
    reader = PdfReader(io.BytesIO(body), strict=True)
    if reader.is_encrypted or len(reader.pages) > 64:
        raise ValueError("encrypted or too many PDF pages")
    lines: list[str] = []
    total = 0
    for index, page in enumerate(reader.pages):
        contents = page.get_contents()
        if contents is not None and len(contents.get_data()) > 524288:
            raise ValueError("PDF page stream exceeds resource limit")
        text = page.extract_text(extraction_mode="plain") or ""
        if len(text) > 131072:
            raise ValueError("PDF page text too large")
        value = " ".join(text.split()).strip()
        if value:
            line = f"Page {index + 1}: {value}"
            total += len(line) + 1
            if total > max_chars * 2 + 16384:
                raise ValueError("PDF text projection too large")
            lines.append(line)
    text = "\n".join(lines).strip()
    if not text or "\x00" in text:
        raise ValueError("PDF has no extractable safe text")
    title = ""
    try:
        meta = reader.metadata
        if meta and isinstance(meta.title, str):
            title = meta.title[:512]
    except (AttributeError, ValueError, TypeError):
        pass
    return {
        "text": text[:max_chars],
        "title": title or lines[0][8:136],
        "truncated": len(text) > max_chars,
    }


def main() -> int:
    try:
        if os.name != "posix":
            return 2
        import resource
        memory = 384 * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
        if len(sys.argv) != 2:
            return 2
        limit = int(sys.argv[1])
        if not 512 <= limit <= 2_097_152:
            return 2
        source = sys.stdin.buffer.read(2_097_153)
        output = _run(source, limit)
        encoded = json.dumps(output, ensure_ascii=False).encode("utf-8")
        if len(encoded) > limit * 4 + 8192:
            return 2
        sys.stdout.buffer.write(encoded)
        return 0
    except (Exception, KeyboardInterrupt):
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
