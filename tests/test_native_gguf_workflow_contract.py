"""The backend gate must run the actual bounded GGUF adversarial fixture."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def test_backend_quality_calls_adversarial_gguf_source_suite():
    source=(ROOT/".github/workflows/backend-quality.yml").read_text(encoding="utf-8")
    assert "GGUF descriptor-bound source and parent-replacement regression" in source
    assert "python -m unittest discover -s tests -p 'test_native_gguf_preflight.py' -v" in source
    assert "python -m py_compile skeleton/native/gguf_preflight.py tests/test_native_gguf_preflight.py" in source
    assert "if: steps.scope.outputs.full == 'true'" in source
    assert "python scripts/check_malware_iocs.py" in source
