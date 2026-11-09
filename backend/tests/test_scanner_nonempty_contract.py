from __future__ import annotations

from scripts import check_deserialization_safety as deserialization_gate
from scripts import check_dynamic_import_safety as dynamic_import_gate
from scripts import check_process_safety as process_gate


def _assert_empty_surface_fails_closed(module, monkeypatch, capsys) -> None:
    monkeypatch.setattr(module, "python_files", lambda: iter(()))

    assert module.main() == 1
    captured = capsys.readouterr()
    assert "no backend Python files were scanned" in captured.err


def test_process_scanner_fails_closed_when_python_surface_is_empty(
    monkeypatch, capsys
) -> None:
    _assert_empty_surface_fails_closed(process_gate, monkeypatch, capsys)


def test_dynamic_import_scanner_fails_closed_when_python_surface_is_empty(
    monkeypatch, capsys
) -> None:
    _assert_empty_surface_fails_closed(dynamic_import_gate, monkeypatch, capsys)


def test_deserialization_scanner_fails_closed_when_python_surface_is_empty(
    monkeypatch, capsys
) -> None:
    _assert_empty_surface_fails_closed(deserialization_gate, monkeypatch, capsys)
