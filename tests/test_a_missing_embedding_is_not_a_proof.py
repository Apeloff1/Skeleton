"""A fact without an embedding is not a random proof, and a rule needs premises."""

import pytest

from skeleton.intelligence.neurosymbolic import NeuralSymbolicEngine, SymbolicRule


def test_missing_embedding_does_not_prove_a_neighbor() -> None:
    engine = NeuralSymbolicEngine()
    engine.add_fact("cat")
    assert "cat" not in engine._embeddings
    proved, chain, confidence = engine.infer("dog")
    assert proved is False
    assert chain == []
    assert confidence == 0.0
    with pytest.raises(ValueError):
        engine.add_rule(SymbolicRule([], "dog"))
    with pytest.raises(ValueError):
        engine.infer("", max_depth=True)
    engine.add_fact("mammal")
    engine.add_rule(SymbolicRule(["mammal"], "animal", 0.7))
    proved, chain, confidence = engine.infer("animal")
    assert proved is True
    assert confidence == 0.7
    assert chain[0].conclusion == "animal"
