from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AI_READER = REPO_ROOT / "backend" / "routes" / "ai_reader.py"
AI_PIPELINE = REPO_ROOT / "backend" / "routes" / "ai_pipeline.py"
AI_DEBUGGER = REPO_ROOT / "backend" / "routes" / "ai_debugger.py"


def _is_exception_handler(handler: ast.ExceptHandler) -> bool:
    return isinstance(handler.type, ast.Name) and handler.type.id == "Exception"


def _http_exception_calls(node: ast.AST):
    for child in ast.walk(node):
        if (
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Name)
            and child.func.id == "HTTPException"
        ):
            yield child


def _references_name(node: ast.AST, name: str) -> bool:
    return any(
        isinstance(child, ast.Name)
        and isinstance(child.ctx, ast.Load)
        and child.id == name
        for child in ast.walk(node)
    )


def _broad_failure_http_leaks(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    leaks: list[int] = []
    for handler in (node for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler)):
        if not _is_exception_handler(handler) or not handler.name:
            continue
        for statement in handler.body:
            for call in _http_exception_calls(statement):
                if _references_name(call, handler.name):
                    leaks.append(call.lineno)
    return leaks


def test_ai_reader_broad_failures_cannot_reach_http_error_detail() -> None:
    leaks = _broad_failure_http_leaks(AI_READER)
    assert leaks == [], f"AI Reader exposes caught exception data in HTTP responses at lines {leaks}"


def test_ai_reader_provider_failures_use_stable_generic_details() -> None:
    source = AI_READER.read_text(encoding="utf-8")
    assert 'detail="Expressive TTS failed"' in source
    assert source.count('detail="TTS generation failed"') == 3
    assert "str(e)" not in source
    assert "str(exc)" not in source


def test_ai_pipeline_broad_failures_cannot_reach_http_error_detail() -> None:
    leaks = _broad_failure_http_leaks(AI_PIPELINE)
    assert leaks == [], f"AI Pipeline exposes caught exception data in HTTP responses at lines {leaks}"


def test_ai_pipeline_does_not_stringify_caught_failures() -> None:
    source = AI_PIPELINE.read_text(encoding="utf-8")
    assert "detail=str(" not in source
    assert "str(exc)" not in source
    assert "str(e)" not in source
    assert "repr(exc)" not in source
    assert "repr(e)" not in source


def test_ai_pipeline_uses_stable_generic_public_failures() -> None:
    source = AI_PIPELINE.read_text(encoding="utf-8")
    assert 'detail="AI pipeline request failed"' in source
    assert 'detail="AI text generation failed"' in source
    assert "raise _pipeline_http_error(" in source
    assert " from None" in source


def test_ai_pipeline_image_helpers_do_not_forward_provider_error_payloads() -> None:
    source = AI_PIPELINE.read_text(encoding="utf-8")
    assert 'result.get("error"' not in source
    assert "result.get('error'" not in source
    assert source.count('"error": "image generation failed"') >= 3


def test_ai_debugger_broad_failures_cannot_reach_http_error_detail() -> None:
    leaks = _broad_failure_http_leaks(AI_DEBUGGER)
    assert leaks == [], f"AI Debugger exposes caught exception data in HTTP responses at lines {leaks}"


def test_ai_debugger_does_not_stringify_caught_failures() -> None:
    source = AI_DEBUGGER.read_text(encoding="utf-8")
    assert "detail=str(" not in source
    assert "str(exc)" not in source
    assert "str(e)" not in source
    assert "repr(exc)" not in source
    assert "repr(e)" not in source


def test_ai_debugger_uses_stable_generic_public_failures() -> None:
    source = AI_DEBUGGER.read_text(encoding="utf-8")
    assert 'detail="AI debugger engine failed"' in source
    assert 'detail="AI debugger request failed"' in source
    assert source.count("except HTTPException:") == 7
    assert source.count("raise _debugger_http_error(") == 6
    assert source.count(" from None") >= 7
