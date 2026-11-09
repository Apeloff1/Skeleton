from pathlib import Path


def test_security_doc_names_runtime_secret_boundary():
    text = Path("core/shift_supervisor/SECURITY.md").read_text(encoding="utf-8")
    assert "API credentials are read from environment at request time" in text
    assert "Model output is untrusted input" in text
