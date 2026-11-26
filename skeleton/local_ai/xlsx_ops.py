"""Create and read workbooks from inline strings. No model is bound."""

from __future__ import annotations

from skeleton.local_ai.office_pack import OfficeRejected, build_xlsx, read_xlsx

__all__ = ["OfficeRejected", "create_workbook", "read_rows"]


def create_workbook(rows: list[list[str]]) -> bytes:
    return build_xlsx(rows)


def read_rows(data: bytes) -> list[list[str]]:
    return read_xlsx(data)
