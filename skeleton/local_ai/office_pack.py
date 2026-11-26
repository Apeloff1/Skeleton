"""Stdlib PDF, DOCX, XLSX, and PPTX text round-trips. No model is bound."""

from __future__ import annotations

import io
import re
import xml.etree.ElementTree as ET
import zipfile

MAX_TEXT_CHARS = 4000
MAX_PAGES = 32
MAX_PARAGRAPHS = 32
MAX_SLIDES = 32
MAX_ROWS = 200
MAX_CELLS = 26

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_X_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
_P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_PKG_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"

_SLIDE_NAME = re.compile(r"ppt/slides/slide(\d+)\.xml$")


class OfficeRejected(ValueError):
    """An office document was refused or could not be read."""


def build_pdf(pages: list[str]) -> bytes:
    texts = _text_list(pages, limit=MAX_PAGES, what="pages")
    return _pdf_bytes(texts)


def read_pdf(data: bytes) -> list[str]:
    raw = _as_bytes(data)
    if not raw.startswith(b"%PDF"):
        raise OfficeRejected("pdf is missing a header")
    return _pdf_strings(raw)


def build_docx(paragraphs: list[str]) -> bytes:
    texts = _text_list(paragraphs, limit=MAX_PARAGRAPHS, what="paragraphs")
    body = "".join(
        "<w:p><w:r><w:t xml:space=\"preserve\">"
        + _xml_text(text)
        + "</w:t></w:r></w:p>"
        for text in texts
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{_W_NS}"><w:body>{body}</w:body></w:document>'
    )
    content_types = _content_types(
        [
            (
                "/word/document.xml",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
            )
        ]
    )
    rels = _package_rels("word/document.xml")
    return _zip(
        {
            "[Content_Types].xml": content_types,
            "_rels/.rels": rels,
            "word/document.xml": document,
        }
    )


def read_docx(data: bytes) -> list[str]:
    root = _xml_root(_zip_part(data, "word/document.xml"), what="docx")
    paragraphs: list[str] = []
    for paragraph in root.iter(f"{{{_W_NS}}}p"):
        parts = [node.text or "" for node in paragraph.iter(f"{{{_W_NS}}}t")]
        paragraphs.append("".join(parts))
    return paragraphs


def build_xlsx(rows: list[list[str]]) -> bytes:
    table = _rows(rows)
    row_xml: list[str] = []
    for row_index, cells in enumerate(table, start=1):
        cell_xml: list[str] = []
        for column, text in enumerate(cells):
            ref = f"{_column_name(column)}{row_index}"
            cell_xml.append(
                f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">'
                + _xml_text(text)
                + "</t></is></c>"
            )
        row_xml.append(f'<row r="{row_index}">{"".join(cell_xml)}</row>')
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<worksheet xmlns="{_X_NS}"><sheetData>{"".join(row_xml)}</sheetData></worksheet>'
    )
    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<workbook xmlns="{_X_NS}" xmlns:r="{_R_NS}">'
        '<sheets><sheet name="Notes" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{_PKG_NS}">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/></Relationships>'
    )
    content_types = _content_types(
        [
            (
                "/xl/workbook.xml",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
            ),
            (
                "/xl/worksheets/sheet1.xml",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml",
            ),
        ]
    )
    return _zip(
        {
            "[Content_Types].xml": content_types,
            "_rels/.rels": _package_rels("xl/workbook.xml"),
            "xl/workbook.xml": workbook,
            "xl/_rels/workbook.xml.rels": workbook_rels,
            "xl/worksheets/sheet1.xml": sheet,
        }
    )


def read_xlsx(data: bytes) -> list[list[str]]:
    root = _xml_root(_zip_part(data, "xl/worksheets/sheet1.xml"), what="xlsx")
    rows: list[list[str]] = []
    for row in root.iter(f"{{{_X_NS}}}row"):
        cells: list[str] = []
        for cell in list(row):
            if cell.tag != f"{{{_X_NS}}}c":
                continue
            parts = [node.text or "" for node in cell.iter(f"{{{_X_NS}}}t")]
            cells.append("".join(parts))
        rows.append(cells)
    return rows


def build_pptx(slides: list[str]) -> bytes:
    texts = _text_list(slides, limit=MAX_SLIDES, what="slides")
    slide_ids: list[str] = []
    rel_lines: list[str] = []
    parts: dict[str, str] = {}
    overrides: list[tuple[str, str]] = [
        (
            "/ppt/presentation.xml",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml",
        )
    ]
    for index, text in enumerate(texts, start=1):
        slide_ids.append(f'<p:sldId id="{255 + index}" r:id="rId{index}"/>')
        rel_lines.append(
            f'<Relationship Id="rId{index}" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide" '
            f'Target="slides/slide{index}.xml"/>'
        )
        overrides.append(
            (
                f"/ppt/slides/slide{index}.xml",
                "application/vnd.openxmlformats-officedocument.presentationml.slide+xml",
            )
        )
        parts[f"ppt/slides/slide{index}.xml"] = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<p:sld xmlns:a="{_A_NS}" xmlns:r="{_R_NS}" xmlns:p="{_P_NS}">'
            "<p:cSld><p:spTree><p:sp><p:txBody><a:p><a:r>"
            '<a:t xml:space="preserve">'
            + _xml_text(text)
            + "</a:t></a:r></a:p></p:txBody></p:sp></p:spTree></p:cSld></p:sld>"
        )
    presentation = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<p:presentation xmlns:p="{_P_NS}" xmlns:r="{_R_NS}">'
        f'<p:sldIdLst>{"".join(slide_ids)}</p:sldIdLst>'
        '<p:sldSz cx="9144000" cy="6858000"/></p:presentation>'
    )
    presentation_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{_PKG_NS}">{"".join(rel_lines)}</Relationships>'
    )
    parts["[Content_Types].xml"] = _content_types(overrides)
    parts["_rels/.rels"] = _package_rels("ppt/presentation.xml")
    parts["ppt/presentation.xml"] = presentation
    parts["ppt/_rels/presentation.xml.rels"] = presentation_rels
    return _zip(parts)


def read_pptx(data: bytes) -> list[str]:
    raw = _as_bytes(data)
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile as exc:
        raise OfficeRejected("pptx is not a zip package") from exc
    with archive:
        names = []
        for name in archive.namelist():
            match = _SLIDE_NAME.fullmatch(name)
            if match:
                names.append((int(match.group(1)), name))
        names.sort()
        slides: list[str] = []
        for _, name in names:
            root = _xml_root(archive.read(name), what="pptx")
            parts = [node.text or "" for node in root.iter(f"{{{_A_NS}}}t")]
            slides.append("".join(parts))
    return slides


def _text_list(values: object, *, limit: int, what: str) -> list[str]:
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
        raise OfficeRejected(f"{what} must be a list of strings")
    if len(values) > limit:
        raise OfficeRejected(f"{what} exceeds {limit}")
    texts: list[str] = []
    for value in values:
        texts.append(_text(value, what=what.removesuffix("s")))
    return texts


def _rows(values: object) -> list[list[str]]:
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)):
        raise OfficeRejected("rows must be a list")
    if len(values) > MAX_ROWS:
        raise OfficeRejected(f"rows exceeds {MAX_ROWS}")
    table: list[list[str]] = []
    for row in values:
        if isinstance(row, (str, bytes)) or not isinstance(row, (list, tuple)):
            raise OfficeRejected("row must be a list of strings")
        if len(row) > MAX_CELLS:
            raise OfficeRejected(f"row exceeds {MAX_CELLS} cells")
        table.append([_text(cell, what="cell") for cell in row])
    return table


def _text(value: object, *, what: str) -> str:
    if isinstance(value, bool) or not isinstance(value, str):
        raise OfficeRejected(f"{what} must be a string")
    if len(value) > MAX_TEXT_CHARS:
        raise OfficeRejected(f"{what} exceeds {MAX_TEXT_CHARS} characters")
    for char in value:
        if char in "\t\n\r":
            continue
        if ord(char) < 32:
            raise OfficeRejected(f"{what} contains an unsupported control character")
    return value


def _column_name(index: int) -> str:
    return chr(ord("A") + index)


def _xml_text(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _content_types(overrides: list[tuple[str, str]]) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        f'<Types xmlns="{_CT_NS}">',
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
    ]
    for part_name, content_type in overrides:
        lines.append(f'<Override PartName="{part_name}" ContentType="{content_type}"/>')
    lines.append("</Types>")
    return "".join(lines)


def _package_rels(target: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<Relationships xmlns="{_PKG_NS}">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        f'Target="{target}"/></Relationships>'
    )


def _zip(parts: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, text in parts.items():
            archive.writestr(name, text.encode("utf-8"))
    return buffer.getvalue()


def _as_bytes(data: object) -> bytes:
    if isinstance(data, bytes):
        return data
    if isinstance(data, (bytearray, memoryview)):
        return bytes(data)
    raise OfficeRejected("document must be bytes")


def _zip_part(data: object, name: str) -> bytes:
    raw = _as_bytes(data)
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            return archive.read(name)
    except KeyError as exc:
        raise OfficeRejected(f"package is missing {name}") from exc
    except zipfile.BadZipFile as exc:
        raise OfficeRejected("document is not a zip package") from exc


def _xml_root(payload: bytes, *, what: str) -> ET.Element:
    try:
        return ET.fromstring(payload)
    except ET.ParseError as exc:
        raise OfficeRejected(f"{what} xml could not be read") from exc


def _pdf_bytes(pages: list[str]) -> bytes:
    next_id = 4
    page_ids: list[int] = []
    content_ids: list[int] = []
    for _page in pages:
        page_ids.append(next_id)
        content_ids.append(next_id + 1)
        next_id += 2
    kids = " ".join(f"{page_id} 0 R" for page_id in page_ids)
    objects = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode("ascii"),
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    }
    for text, page_id, content_id in zip(pages, page_ids, content_ids):
        stream = b"BT /F1 12 Tf 72 720 Td (" + _pdf_literal(text) + b") Tj ET"
        objects[content_id] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream"
        )
        objects[page_id] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Contents {content_id} 0 R /Resources << /Font << /F1 3 0 R >> >> >>"
        ).encode("ascii")
    header = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
    chunks = [header]
    offsets: dict[int, int] = {}
    for object_id in range(1, next_id):
        offsets[object_id] = sum(len(chunk) for chunk in chunks)
        chunks.append(f"{object_id} 0 obj\n".encode("ascii") + objects[object_id] + b"\nendobj\n")
    xref_at = sum(len(chunk) for chunk in chunks)
    xref = [f"xref\n0 {next_id}\n".encode("ascii"), b"0000000000 65535 f \n"]
    for object_id in range(1, next_id):
        xref.append(f"{offsets[object_id]:010d} 00000 n \n".encode("ascii"))
    trailer = (
        f"trailer\n<< /Size {next_id} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n".encode("ascii")
    )
    return b"".join(chunks) + b"".join(xref) + trailer


def _pdf_literal(text: str) -> bytes:
    out = bytearray()
    for char in text:
        if char == "\\":
            out.extend(b"\\\\")
        elif char == "(":
            out.extend(b"\\(")
        elif char == ")":
            out.extend(b"\\)")
        elif char == "\n":
            out.extend(b"\\n")
        elif char == "\r":
            out.extend(b"\\r")
        elif char == "\t":
            out.extend(b"\\t")
        else:
            out.extend(char.encode("utf-8"))
    return bytes(out)


def _pdf_strings(data: bytes) -> list[str]:
    found: list[str] = []
    index = 0
    length = len(data)
    while index < length:
        if data[index] != 0x28:
            index += 1
            continue
        index += 1
        raw = bytearray()
        depth = 1
        while index < length and depth:
            byte = data[index]
            if byte == 0x5C:
                if index + 1 >= length:
                    break
                raw.append(byte)
                raw.append(data[index + 1])
                index += 2
                continue
            if byte == 0x28:
                depth += 1
                raw.append(byte)
            elif byte == 0x29:
                depth -= 1
                if depth:
                    raw.append(byte)
            else:
                raw.append(byte)
            index += 1
        cursor = index
        while cursor < length and data[cursor] in b" \t\r\n":
            cursor += 1
        if depth == 0 and data[cursor : cursor + 2] == b"Tj":
            found.append(_pdf_unescape(bytes(raw)))
    return found


def _pdf_unescape(raw: bytes) -> str:
    out = bytearray()
    index = 0
    escapes = {ord("n"): 10, ord("r"): 13, ord("t"): 9, ord("b"): 8, ord("f"): 12}
    while index < len(raw):
        if raw[index] != 0x5C or index + 1 >= len(raw):
            out.append(raw[index])
            index += 1
            continue
        nxt = raw[index + 1]
        if nxt in escapes:
            out.append(escapes[nxt])
            index += 2
            continue
        if nxt in b"()\\":
            out.append(nxt)
            index += 2
            continue
        if 48 <= nxt <= 55:
            end = index + 1
            digits = bytearray()
            while end < len(raw) and len(digits) < 3 and 48 <= raw[end] <= 55:
                digits.append(raw[end])
                end += 1
            out.append(int(digits, 8))
            index = end
            continue
        out.append(nxt)
        index += 2
    try:
        return out.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OfficeRejected("pdf text is not utf-8") from exc
