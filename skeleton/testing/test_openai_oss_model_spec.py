from __future__ import annotations

from skeleton.ai.integrations.openai_oss import ModelSpecIndex


def test_model_spec_snapshot_is_indexable_but_never_authoritative() -> None:
    index = ModelSpecIndex()
    assert index.authoritative is False
    assert len(index.digest) == 64
    assert len(index.sections()) > 20

    matches = index.find("chain of command")
    assert matches
    assert any(
        "chain of command" in (item.title + "\n" + item.body).casefold()
        for item in matches
    )
