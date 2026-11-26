"""Regression coverage for offline installations without training extras."""
import subprocess
import sys
import textwrap

import pytest


@pytest.mark.parametrize("existing", [False, True])
def test_missing_torch_preserves_checkpoint(tmp_path, existing):
    root = tmp_path / "training"
    if existing:
        root.mkdir()
        (root / "checkpoint.pt").write_bytes(b"existing checkpoint")
    script = textwrap.dedent("""
        import importlib.abc
        import sys
        from pathlib import Path

        class NoTorch(importlib.abc.MetaPathFinder):
            def find_spec(self, fullname, path=None, target=None):
                if fullname == "torch" or fullname.startswith("torch."):
                    raise ModuleNotFoundError(fullname, name=fullname)

        sys.meta_path.insert(0, NoTorch())
        from skeleton.ai.runtime.inference.game_adaptive_ratchet import (
            AdaptiveRatchet, ByteRNN, train_budget,
        )
        assert AdaptiveRatchet().observe({"a": 2.0}, {"a": 1.0})
        for operation in (
            lambda: ByteRNN(4),
            lambda: train_budget(budget_bytes=1, checkpoint_dir=Path(sys.argv[1])),
        ):
            try:
                operation()
            except RuntimeError as exc:
                assert "PyTorch" in str(exc)
            else:
                raise AssertionError("training admitted without PyTorch")
    """)
    result = subprocess.run(
        [sys.executable, "-c", script, str(root)],
        capture_output=True, text=True, timeout=60, check=False,
    )
    assert result.returncode == 0, result.stderr
    if existing:
        assert sorted(p.name for p in root.iterdir()) == ["checkpoint.pt"]
        assert (root / "checkpoint.pt").read_bytes() == b"existing checkpoint"
    else:
        assert not root.exists()


def test_native_torch_scoring():
    torch = pytest.importorskip("torch")
    from skeleton.ai.runtime.inference.game_adaptive_ratchet import ByteRNN, _scores

    model = ByteRNN(4)
    scores = _scores(model, {"track": ("hello",)})
    assert torch.isfinite(torch.tensor(scores["track"]))
    assert model.training
    assert all(p.grad is None for p in model.parameters())
