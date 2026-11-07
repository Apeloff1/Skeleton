"""Bounded ZIP entry inventory without extraction, decompression or execution.

No entry names are returned; only extension classes and declared sizes. ZIP
central-directory metadata is attacker controlled and not proof of contents.
Encrypted, symlinked, traversing and structurally excessive archives fail.
"""
from __future__ import annotations

from collections import Counter
import io
import re
import stat
import zipfile

from .research_projection import (
    ResearchFormatError, ResearchProjection, project_lines,
)

ZIP_INVENTORY_TYPES = frozenset({"application/zip", "application/x-zip-compressed"})
_SUFFIX = re.compile(r"^\.[a-z0-9]{1,12}$")
_MAX_SIZE = 2_097_152
_MAX_ENTRIES = 512
_MAX_TOTAL_DECLARED = 134_217_728


def extract_zip_inventory(
    body: bytes, *, max_chars: int = 524288,
) -> ResearchProjection:
    if (type(body) is not bytes or not body or len(body) > _MAX_SIZE
            or type(max_chars) is not int or not 1 <= max_chars <= _MAX_SIZE):
        raise ResearchFormatError("unbounded ZIP source metadata")
    try:
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            rows = archive.infolist()
            if not 1 <= len(rows) <= _MAX_ENTRIES:
                raise ResearchFormatError("ZIP entry capacity exceeded")
            seen = set()
            sizes = 0
            types = Counter()
            for row in rows:
                name = row.filename
                if (not isinstance(name, str) or len(name) > 1024
                        or name.startswith(("/", "\\"))
                        or "\\" in name or "\x00" in name
                        or ".." in name.split("/")):
                    raise ResearchFormatError("unsafe ZIP entry name")
                canonical = name.casefold()
                if canonical in seen:
                    raise ResearchFormatError("ZIP path alias collision")
                seen.add(canonical)
                mode = (row.external_attr >> 16) & 0xffff
                if stat.S_ISLNK(mode):
                    raise ResearchFormatError("ZIP symbolic links not admitted")
                if row.flag_bits & 1:
                    raise ResearchFormatError("ZIP encryption not admitted")
                if row.file_size < 0 or row.compress_size < 0:
                    raise ResearchFormatError("ZIP declared size invalid")
                sizes += row.file_size
                if sizes > _MAX_TOTAL_DECLARED:
                    raise ResearchFormatError("ZIP claimed expansion exceeds safe inventory")
                if name.endswith("/"):
                    continue
                base = name.rsplit("/", 1)[-1]
                suffix = "." + base.rsplit(".", 1)[-1].lower() if "." in base else "[none]"
                if not _SUFFIX.fullmatch(suffix):
                    suffix = "[other]"
                types[suffix] += 1
    except (zipfile.BadZipFile, EOFError, OSError, ValueError) as exc:
        raise ResearchFormatError("invalid ZIP central directory") from exc
    labels = [
        "Archive: ZIP inventory only",
        f"Central-directory entries: {len(rows)}",
        f"Advertised uncompressed bytes: {sizes}",
    ]
    for suffix, count in sorted(types.items()):
        labels.append(f"Extension class {suffix}: {count}")
    labels.append("Archive members: not extracted, decoded, executed or retained")
    return project_lines(labels, title="ZIP archive inventory", max_chars=max_chars)
