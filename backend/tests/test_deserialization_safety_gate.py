from __future__ import annotations

from pathlib import Path

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


def test_rejects_joblib_load(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import joblib\nvalue = joblib.load(path)\n")
    assert any("joblib.load() is forbidden" in finding for finding in findings)


def test_rejects_aliased_pandas_read_pickle(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import pandas as pd\nvalue = pd.read_pickle(path)\n")
    assert any("pandas.read_pickle() is forbidden" in finding for finding in findings)


def test_rejects_yaml_load_without_safe_loader(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import yaml\nvalue = yaml.load(text, Loader=yaml.FullLoader)\n")
    assert any("requires literal SafeLoader" in finding for finding in findings)


def test_allows_yaml_safe_load(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import yaml\nvalue = yaml.safe_load(text)\n")
    assert findings == []


def test_allows_yaml_load_with_safe_loader(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import yaml\nvalue = yaml.load(text, Loader=yaml.SafeLoader)\n")
    assert findings == []


def test_rejects_numpy_pickle_enabled_load(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import numpy as np\nvalue = np.load(path, allow_pickle=True)\n")
    assert any("allow_pickle override must be literal False" in finding for finding in findings)


def test_rejects_numpy_dynamic_pickle_setting(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import numpy as np\nvalue = np.load(path, allow_pickle=setting)\n")
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


def test_allows_torch_weights_only_load(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "import torch\nvalue = torch.load(path, weights_only=True)\n")
    assert findings == []


def test_rejects_deserializer_star_import(tmp_path: Path) -> None:
    findings = _scan(tmp_path, "from pickle import *\n")
    assert any("star import" in finding for finding in findings)
