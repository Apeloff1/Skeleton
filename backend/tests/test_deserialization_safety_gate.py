from __future__ import annotations

from pathlib import Path

import pytest

from scripts import check_deserialization_safety as scanner
from scripts.check_deserialization_safety import violations


def _scan(tmp_path: Path, source: str) -> list[str]:
    path = tmp_path / "sample.py"
    path.write_text(source, encoding="utf-8")
    return violations(path)


def test_rejects_pickle_loads(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import pickle\nvalue = pickle.loads(payload)\n")
    assert any("pickle.loads() is forbidden" in finding for finding in findings)


def test_rejects_aliased_pickle_load(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "from pickle import load as restore\nvalue = restore(stream)\n")
    assert any("pickle.load() is forbidden" in finding for finding in findings)


def test_rejects_stable_callable_alias_to_pickle_loads(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import pickle\ndecoder = pickle.loads\nvalue = decoder(payload)\n",
    )
    assert any("pickle.loads() is forbidden" in finding for finding in findings)


def test_rejects_stable_callable_alias_chain(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import pickle\ndecoder = pickle.loads\nrestore = decoder\nvalue = restore(payload)\n",
    )
    assert any("pickle.loads() is forbidden" in finding for finding in findings)


def test_rejects_function_local_callable_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import pickle\ndef decode(payload):\n    loader = pickle.loads\n    return loader(payload)\n",
    )
    assert any("pickle.loads() is forbidden" in finding for finding in findings)


def test_rejects_walrus_alias_to_pickle_loads(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import pickle\nif (restore := pickle.loads):\n    value = restore(payload)\n",
    )
    assert any("pickle.loads() is forbidden" in finding for finding in findings)


def test_rejects_walrus_alias_to_torch_load_without_weights_only(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import torch\nif (restore := torch.load):\n    value = restore(path)\n",
    )
    assert any("weights_only=True" in finding for finding in findings)


def test_rebound_callable_alias_is_not_assumed_to_keep_provenance(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import json\nimport pickle\ndecoder = pickle.loads\ndecoder = json.loads\nvalue = decoder(payload)\n",
    )
    assert findings == []


def test_rejects_stable_pickle_module_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import pickle\ncodec = pickle\nvalue = codec.loads(payload)\n",
    )
    assert any("pickle.loads() is forbidden" in finding for finding in findings)


def test_rejects_stable_deserializer_module_alias_chain(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import torch\nfirst = torch\nsecond = first\nvalue = second.load(path)\n",
    )
    assert any("weights_only=True" in finding for finding in findings)


def test_reassigned_deserializer_module_alias_is_not_inferred(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import pickle\ncodec = pickle\ncodec = safe_codec\nvalue = codec.loads(payload)\n",
    )
    assert findings == []


def test_rejects_joblib_load(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import joblib\nvalue = joblib.load(path)\n")
    assert any("joblib.load() is forbidden" in finding for finding in findings)


def test_rejects_aliased_pandas_read_pickle(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import pandas as pd\nvalue = pd.read_pickle(path)\n")
    assert any("pandas.read_pickle() is forbidden" in finding for finding in findings)


def test_rejects_yaml_load_without_safe_loader(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import yaml\nvalue = yaml.load(text, Loader=yaml.FullLoader)\n")
    assert any("requires literal SafeLoader" in finding for finding in findings)


def test_rejects_yaml_load_through_callable_alias_without_safe_loader(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import yaml\nloader = yaml.load\nvalue = loader(text, Loader=yaml.FullLoader)\n",
    )
    assert any("requires literal SafeLoader" in finding for finding in findings)


def test_allows_yaml_safe_load(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import yaml\nvalue = yaml.safe_load(text)\n")
    assert findings == []


def test_allows_yaml_load_with_safe_loader(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import yaml\nvalue = yaml.load(text, Loader=yaml.SafeLoader)\n")
    assert findings == []


def test_allows_yaml_load_alias_with_safe_loader(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import yaml\nloader = yaml.load\nvalue = loader(text, Loader=yaml.SafeLoader)\n",
    )
    assert findings == []


def test_rejects_numpy_pickle_enabled_load(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import numpy as np\nvalue = np.load(path, allow_pickle=True)\n")
    assert any("allow_pickle override must be literal False" in finding for finding in findings)


def test_rejects_numpy_dynamic_pickle_setting(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import numpy as np\nvalue = np.load(path, allow_pickle=setting)\n")
    assert any("allow_pickle override must be literal False" in finding for finding in findings)


def test_rejects_numpy_pickle_enabled_load_through_callable_alias(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import numpy as np\nloader = np.load\nvalue = loader(path, allow_pickle=True)\n",
    )
    assert any("allow_pickle override must be literal False" in finding for finding in findings)


def test_allows_numpy_default_non_pickle_load(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import numpy as np\nvalue = np.load(path)\n")
    assert findings == []


def test_allows_numpy_non_pickle_load(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import numpy as np\nvalue = np.load(path, allow_pickle=False)\n")
    assert findings == []


def test_rejects_torch_load_without_weights_only(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import torch\nvalue = torch.load(path)\n")
    assert any("weights_only=True" in finding for finding in findings)


def test_rejects_torch_load_with_dynamic_weights_only(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import torch\nvalue = torch.load(path, weights_only=setting)\n")
    assert any("weights_only=True" in finding for finding in findings)


def test_rejects_torch_load_alias_without_weights_only(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import torch\nloader = torch.load\nvalue = loader(path)\n",
    )
    assert any("weights_only=True" in finding for finding in findings)


def test_allows_torch_weights_only_load(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import torch\nvalue = torch.load(path, weights_only=True)\n")
    assert findings == []


def test_allows_torch_alias_with_weights_only(tmp_path: Path) -> None:
    findings = _scan(
        tmp_path,
        "import torch\nloader = torch.load\nvalue = loader(path, weights_only=True)\n",
    )
    assert findings == []


def test_rejects_deserializer_star_import(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "from pickle import *\n")
    assert any("star import" in finding for finding in findings)


def test_nested_enumeration_failure_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "backend"
    blocked = root / "blocked"
    blocked.mkdir(parents=True)
    (root / "safe.py").write_text("value = 1\n", encoding="utf-8")
    real_scandir = scanner.os.scandir

    def guarded_scandir(path):
        if Path(path) == blocked:
            raise PermissionError("SECRET_DESERIALIZATION_PATH")
        return real_scandir(path)

    monkeypatch.setattr(scanner, "ROOT", root)
    monkeypatch.setattr(scanner.os, "scandir", guarded_scandir)

    assert scanner.main() == 1
    captured = capsys.readouterr()
    assert "scanner coverage failure: source traversal failed" in captured.err
    assert "SECRET_DESERIALIZATION_PATH" not in captured.err


def test_missing_root_is_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(scanner, "ROOT", tmp_path / "missing-backend")

    assert scanner.main() == 1
    assert "scanner coverage failure: source traversal failed" in capsys.readouterr().err


def test_zero_file_scan_cannot_report_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(scanner, "ROOT", tmp_path)

    assert scanner.main() == 1
    assert "no backend Python files were scanned" in capsys.readouterr().err


def test_parse_failure_reports_exception_class_without_payload(tmp_path: Path) -> None:
    bad = tmp_path / "broken.py"
    bad.write_text("def broken(:  # SECRET_DESERIALIZATION_PARSE\n    pass\n", encoding="utf-8")

    findings = scanner.violations(bad)

    assert findings == [f"{bad}: parse failure: SyntaxError"]
    assert "SECRET_DESERIALIZATION_PARSE" not in findings[0]
    assert "invalid syntax" not in findings[0]


def test_discovery_does_not_follow_symlink_directories(tmp_path: Path) -> None:
    root = tmp_path / "backend"
    external = tmp_path / "external"
    root.mkdir()
    external.mkdir()
    (root / "safe.py").write_text("value = 1\n", encoding="utf-8")
    (external / "hidden.py").write_text("import pickle\npickle.loads(payload)\n", encoding="utf-8")
    link = root / "linked"
    try:
        link.symlink_to(external, target_is_directory=True)
    except OSError:
        pytest.skip("directory symlinks are unavailable on this platform")

    assert list(scanner.python_files(root)) == [root / "safe.py"]
