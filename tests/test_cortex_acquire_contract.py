"""Acquire/surpass contract tests for trained and untrained tract mouths.

These tests pin the safety boundary introduced by the live CI repair: storing an
untrained tract snapshot is allowed, but Neo must not absorb its random mouth or
be promoted to a trained LM. Once the source mouth is explicitly trained,
acquisition may absorb it and surpass must keep speaking from Neo even if the
source slot is rebound afterward.
"""
from __future__ import annotations


class TestAcquireAbsorbContract:
    def test_unfitted_source_is_stored_without_promoting_neo(self) -> None:
        from skeleton.cortex import JeevesCortex
        from skeleton.cortex.hive import merkle_card

        neo = JeevesCortex()
        stimulus = "compile ttk hp dps recipe sim"
        source = neo.slots["left"].transformer
        assert source is not None
        assert max(int(getattr(source, "fitted", 0) or 0), int(getattr(source, "steps", 0) or 0)) == 0

        neo.think(stimulus)
        before = merkle_card(neo)
        got = neo.acquire("left")

        assert got["model"] == 1
        assert "left" in got["models"]
        assert got["absorb"]["absorbed"] == 0
        assert got["absorb"]["reason"] == "source-unfitted"
        assert neo.own.models["left"]
        assert merkle_card(neo)["e_fp"] == before["e_fp"]
        assert int(getattr(neo.transformer, "fitted", 0) or 0) == 0
        assert int(getattr(neo.transformer, "steps", 0) or 0) == 0

        neo.surpass("left")
        trace = neo.think(stimulus)
        assert trace.used_own
        assert trace.amalgam.kind != "own-lm"
        assert "lm" not in trace.amalgam.tags

    def test_trained_source_absorbs_and_surpass_decodes_from_neo(self) -> None:
        from skeleton.cortex import JeevesCortex
        from skeleton.cortex.hive import merkle_card

        neo = JeevesCortex()
        stimulus = "compile ttk hp dps recipe sim"
        source = neo.slots["left"]
        assert source.fit(stimulus) >= 1
        assert int(getattr(source.transformer, "steps", 0) or 0) > 0

        neo.think(stimulus)
        before = merkle_card(neo)
        embedding_before = [row[:] for row in neo.transformer.E[:2]]
        got = neo.acquire("left")

        assert got["model"] == 1
        assert "left" in got["models"]
        assert got["absorb"]["absorbed"] == 1
        assert neo.own.models["left"]
        after = merkle_card(neo)
        assert after["e_fp"] != before["e_fp"]
        assert any(
            abs(a - b) > 1e-12
            for row_before, row_after in zip(embedding_before, neo.transformer.E[:2])
            for a, b in zip(row_before, row_after)
        )
        assert int(getattr(neo.transformer, "fitted", 0) or 0) >= 1

        neo.surpass("left")
        first = neo.think(stimulus)
        assert first.used_own
        assert first.amalgam.slot == "neo"
        assert first.amalgam.kind == "own-lm"
        assert "surpass" in first.amalgam.tags
        assert "ECHO" not in first.amalgam.text

        neo.bind_echo("left")
        rebound = neo.think(stimulus)
        assert rebound.used_own
        assert rebound.amalgam.kind == "own-lm"
        assert "ECHO" not in rebound.amalgam.text
        assert rebound.left is not None and rebound.left.text.startswith("ECHO")
