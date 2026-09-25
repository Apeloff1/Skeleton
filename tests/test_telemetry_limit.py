"""A telemetry limit of zero must not mean every row."""

import pytest

from skeleton.intelligence.repair_telemetry import load_telemetry
from skeleton.organism.paths import organism_dir


def test_non_positive_limit_does_not_return_the_whole_file(tmp_path) -> None:
    path = organism_dir(tmp_path) / "repair_telemetry.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text('{"surface": "forge"}\n{"surface": "other"}\n', encoding="utf-8")
    assert load_telemetry(root=tmp_path, limit=0) == []
    assert len(load_telemetry(root=tmp_path, limit=1)) == 1
    with pytest.raises(ValueError):
        load_telemetry(root=tmp_path, limit=-1)
