"""Inert spreadsheet and slide-deck extraction from finite Office ZIP packages.

This is a read-only extension of BoundedArchive. It never evaluates workbook
formulas, VBA, spreadsheet macros, external links, embedded object packages,
PowerPoint actions, source URLs or remote relationships.
"""
from __future__ import annotations

import re

from .archive_documents import (
    BoundedArchive, ArchiveDocumentError, ArchivedText,
    _xml, _text_bound, _container_path,
)

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
ODS = "application/vnd.oasis.opendocument.spreadsheet"
ODP = "application/vnd.oasis.opendocument.presentation"
OFFICE_SUITE_TYPES = frozenset({XLSX, PPTX, ODS, ODP})

SS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
DOC_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
ODT_TABLE = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
ODT_TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
ODT_OFFICE = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
ODT_DRAW = "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
DRAW_TEXT = "http://schemas.openxmlformats.org/drawingml/2006/main"
SLIDE = "http://schemas.openxmlformats.org/presentationml/2006/main"
_COL = re.compile(r"^[A-Z]{1,3}$")
_SLIDE = re.compile(r"^ppt/slides/slide([1-9][0-9]{0,2})[.]xml$")


def _safecell(value: str, limit=2048) -> str:
    if not isinstance(value, str) or len(value) > limit:
        raise ArchiveDocumentError("office text cell exceeds finite bound")
    return " ".join(value.split())


def _shared_strings(archive: BoundedArchive) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.files:
        return []
    root = _xml(archive.read("xl/sharedStrings.xml"))
    if root.tag != f"{{{SS}}}sst":
        raise ArchiveDocumentError("invalid XLSX shared strings")
    result = []
    for node in root:
        if node.tag != f"{{{SS}}}si":
            continue
        result.append(_safecell("".join(
            element.text or ""
            for element in node.iter()
            if element.tag == f"{{{SS}}}t"
        )))
        if len(result) > 8192:
            raise ArchiveDocumentError("XLSX shared string capacity exceeded")
    return result


def _xlsx(archive: BoundedArchive, max_chars: int) -> ArchivedText:
    workbook = _xml(archive.read("xl/workbook.xml"))
    if workbook.tag != f"{{{SS}}}workbook":
        raise ArchiveDocumentError("unexpected XLSX workbook")
    relationships = _xml(archive.read("xl/_rels/workbook.xml.rels"))
    mapping = {}
    for node in relationships.iter(f"{{{PKG_REL}}}Relationship"):
        kind = node.get("Type", "")
        if kind.endswith("/worksheet"):
            rid, target = node.get("Id"), node.get("Target")
            if not rid or rid in mapping:
                raise ArchiveDocumentError("duplicate workbook relationship")
            mapping[rid] = _container_path("xl/workbook.xml", target)
    sheets = []
    for sheet in workbook.iter(f"{{{SS}}}sheet"):
        name = _safecell(sheet.get("name", ""), limit=128) or "Sheet"
        rid = sheet.get(f"{{{DOC_REL}}}id")
        if not rid or rid not in mapping:
            raise ArchiveDocumentError("workbook sheet lacks bounded relationship")
        sheets.append((name, mapping[rid]))
        if len(sheets) > 16:
            raise ArchiveDocumentError("XLSX sheet count exceeds budget")
    if not sheets:
        raise ArchiveDocumentError("XLSX workbook contains no worksheets")
    strings = _shared_strings(archive)
    lines = []
    total_rows = 0
    for name, path in sheets:
        root = _xml(archive.read(path))
        if root.tag != f"{{{SS}}}worksheet":
            raise ArchiveDocumentError("unexpected XLSX worksheet part")
        for row in root.iter(f"{{{SS}}}row"):
            total_rows += 1
            if total_rows > 2048:
                raise ArchiveDocumentError("XLSX row budget exceeded")
            values = []
            for cell in row:
                if cell.tag != f"{{{SS}}}c":
                    continue
                if len(values) >= 48:
                    raise ArchiveDocumentError("XLSX column budget exceeded")
                ref = cell.get("r", "")
                raw_column = re.sub(r"[0-9]+", "", ref).upper()
                if not _COL.fullmatch(raw_column):
                    raise ArchiveDocumentError("invalid spreadsheet cell reference")
                typecode = cell.get("t", "")
                if typecode not in ("", "n", "s", "inlineStr", "str", "b", "e"):
                    raise ArchiveDocumentError("unsupported spreadsheet scalar")
                value = next((n.text for n in cell
                              if n.tag == f"{{{SS}}}v"), None)
                if typecode == "inlineStr":
                    value = "".join((n.text or "") for n in cell.iter(
                        f"{{{SS}}}t"))
                elif typecode == "s" and value is not None:
                    try:
                        idx = int(value)
                        value = strings[idx] if 0 <= idx < len(strings) else None
                    except (ValueError, TypeError):
                        value = None
                if value is not None:
                    values.append(f"{ref}: {_safecell(value)}")
            if values:
                lines.append(f"Workbook {name} row {total_rows}: " + "; ".join(values))
                if sum(map(len, lines)) > max_chars * 2 + 16384:
                    raise ArchiveDocumentError("XLSX text projection exceeds budget")
    return _text_bound(lines, max_chars, sheets[0][0])


def _pptx(archive: BoundedArchive, max_chars: int) -> ArchivedText:
    slides = []
    for path in archive.files:
        match = _SLIDE.fullmatch(path)
        if match:
            slides.append((int(match.group(1)), path))
    slides.sort()
    if not 1 <= len(slides) <= 96:
        raise ArchiveDocumentError("slide count exceeds archive budget")
    rows = []
    for number, path in slides:
        root = _xml(archive.read(path))
        if root.tag != f"{{{SLIDE}}}sld":
            raise ArchiveDocumentError("invalid PowerPoint slide root")
        words = [
            _safecell(node.text or "")
            for node in root.iter(f"{{{DRAW_TEXT}}}t")
            if node.text
        ]
        if words:
            rows.append(f"Slide {number}: " + " ".join(words))
        if sum(map(len, rows)) > max_chars * 2 + 16384:
            raise ArchiveDocumentError("slide text exceeds source budget")
    return _text_bound(rows, max_chars, "Presentation")


def _ods(archive: BoundedArchive, max_chars: int) -> ArchivedText:
    root = _xml(archive.read("content.xml"))
    if root.tag != f"{{{ODT_OFFICE}}}document-content":
        raise ArchiveDocumentError("invalid ODS package")
    lines = []
    sheets = rows = 0
    for table in root.iter(f"{{{ODT_TABLE}}}table"):
        sheets += 1
        if sheets > 16:
            raise ArchiveDocumentError("ODS table count exceeded")
        name = _safecell(table.get(f"{{{ODT_TABLE}}}name", "Sheet"), 128)
        for row in table.iter(f"{{{ODT_TABLE}}}table-row"):
            rows += 1
            if rows > 2048:
                raise ArchiveDocumentError("ODS row count exceeded")
            repeat = int(row.get(f"{{{ODT_TABLE}}}number-rows-repeated", "1"))
            if not 1 <= repeat <= 16:
                raise ArchiveDocumentError("ODS repeated rows exceeded")
            values = []
            for i, cell in enumerate(row):
                if cell.tag != f"{{{ODT_TABLE}}}table-cell":
                    continue
                if i >= 48:
                    raise ArchiveDocumentError("ODS columns exceeded")
                col_repeat = int(cell.get(f"{{{ODT_TABLE}}}number-columns-repeated", "1"))
                if not 1 <= col_repeat <= 16:
                    raise ArchiveDocumentError("ODS repeated columns exceeded")
                text = " ".join("".join(p.itertext()) for p in cell.iter(f"{{{ODT_TEXT}}}p"))
                if text.strip():
                    values.append(f"column {i+1}: {_safecell(text)}")
            if values:
                for _ in range(repeat):
                    lines.append(f"Sheet {name} row {rows}: " + "; ".join(values))
            if sum(map(len, lines)) > max_chars * 2 + 16384:
                raise ArchiveDocumentError("ODS text projection over capacity")
    return _text_bound(lines, max_chars, "Spreadsheet")


def _odp(archive: BoundedArchive, max_chars: int) -> ArchivedText:
    root = _xml(archive.read("content.xml"))
    if root.tag != f"{{{ODT_OFFICE}}}document-content":
        raise ArchiveDocumentError("invalid OpenDocument presentation")
    lines = []
    pages = 0
    for page in root.iter(f"{{{ODT_DRAW}}}page"):
        pages += 1
        if pages > 96:
            raise ArchiveDocumentError("ODP slide count exceeded")
        words = [
            _safecell("".join(item.itertext()))
            for item in page.iter(f"{{{ODT_TEXT}}}p")
        ]
        if any(words):
            lines.append(f"Slide {pages}: " + " ".join(words))
        if sum(map(len, lines)) > max_chars * 2 + 16384:
            raise ArchiveDocumentError("ODP text exceeds capacity")
    return _text_bound(lines, max_chars, "Presentation")


def extract_office_suite(
    archive: BoundedArchive, media_type: str, *, max_chars: int,
) -> ArchivedText:
    if media_type not in OFFICE_SUITE_TYPES:
        raise ArchiveDocumentError("unsupported office suite type")
    if media_type == XLSX:
        return _xlsx(archive, max_chars)
    if media_type == PPTX:
        return _pptx(archive, max_chars)
    if media_type == ODS:
        return _ods(archive, max_chars)
    return _odp(archive, max_chars)
