from skeleton.cortex.live import reset_live
from skeleton.cortex.neocortex import JeevesCortex
from skeleton.genesis import Genesis


def test_genesis_reuses_live_cortex_when_own_is_configured(monkeypatch, tmp_path):
    own = tmp_path / "own.json"
    monkeypatch.setenv("SKELETON_OWN", str(own))
    reset_live(wipe_disk=True)

    try:
        first = Genesis()
        first._phase_cortex()
        second = Genesis()
        second._phase_cortex()

        assert first.get("cortex") is second.get("cortex")
        assert first.get("jeeves").cortex is first.get("cortex")
        assert second.get("jeeves").cortex is second.get("cortex")
    finally:
        reset_live(wipe_disk=True)


def test_genesis_restores_persisted_live_cortex(monkeypatch, tmp_path):
    own = tmp_path / "own.json"
    monkeypatch.setenv("SKELETON_OWN", str(own))
    reset_live(wipe_disk=True)

    seed = JeevesCortex()
    seed._winner_mouth = "right"
    seed.save(own)
    reset_live()

    try:
        genesis = Genesis()
        genesis._phase_cortex()
        assert genesis.get("cortex")._winner_mouth == "right"
        assert genesis.get("jeeves").cortex is genesis.get("cortex")
    finally:
        reset_live(wipe_disk=True)


def test_genesis_keeps_fresh_cortex_without_own_configuration(monkeypatch):
    monkeypatch.delenv("SKELETON_OWN", raising=False)
    reset_live()

    first = Genesis()
    first._phase_cortex()
    second = Genesis()
    second._phase_cortex()

    assert first.get("cortex") is not second.get("cortex")
    assert first.get("jeeves").cortex is first.get("cortex")
    assert second.get("jeeves").cortex is second.get("cortex")
