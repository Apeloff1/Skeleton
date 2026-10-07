from skeleton.ai.integrations.native_model import NativeRuntimeBackend

def test_native_backend_export_exists():
    assert NativeRuntimeBackend.__name__ == "NativeRuntimeBackend"
