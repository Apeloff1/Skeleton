"""Live original-game save transition handoff and adversarial inspection."""
from __future__ import annotations

from dataclasses import asdict
import json
import os

import pytest

from skeleton.app.cli import run_app_cli
from skeleton.app.offline_mixed_game_library_continuity_handoff import (
    OfflineMixedLibraryContinuityHandoffError,
    publish_mixed_library_continuity_handoff,
    inspect_mixed_library_continuity_handoff,
)
from skeleton.testing.test_app_offline_mixed_game_library_continuity import (
    catalog, _advance,
)
from skeleton.testing.test_app_offline_policy_chain_delivery import chain_delivery

pytestmark = pytest.mark.skipif(os.name != "posix", reason="POSIX private custody")


@pytest.fixture
def transition(catalog, tmp_path):
    unsigned, signed = catalog
    newer = _advance(unsigned, tmp_path / "advanced-handoff.json")
    receipt = tmp_path / "mixed-continuity-handoff.json"
    return unsigned, newer, signed, receipt


def _args(unsigned, newer, signed):
    result = ["mixed-library-continuity-handoff"]
    for name, entry in (
        ("before-unsigned-entry", unsigned),
        ("after-unsigned-entry", newer),
        ("before-signed-entry", signed),
        ("after-signed-entry", signed),
    ):
        result.extend(("--" + name, json.dumps(asdict(entry))))
    return result + ["--trusted-local-operator"]


def _publish(transition):
    old, new, signed, receipt = transition
    return publish_mixed_library_continuity_handoff(
        [old], [new], [signed], [signed], receipt, authorized=True,
    )


def _inspect(transition, digest):
    old, new, signed, receipt = transition
    return inspect_mixed_library_continuity_handoff(
        [old], [new], [signed], [signed], receipt,
        expected_receipt_sha256=digest, authorized=True,
    )


def test_end_to_end_publish_and_reinspect_signed_unsigned_replays(
    transition, capsys,
):
    old, new, signed, receipt = transition
    before = (
        open(old.private_save, "rb").read(),
        open(new.private_save, "rb").read(),
        open(signed.private_save, "rb").read(),
    )
    assert run_app_cli(_args(old, new, signed) + ["--output", str(receipt)]) == 0
    published = json.loads(capsys.readouterr().out)
    assert published["receipt_published"] is True
    assert published["advanced_games"] == 1
    assert published["release_certified"] is False
    assert receipt.stat().st_mode & 0o077 == 0
    assert run_app_cli(_args(old, new, signed) + [
        "--inspect-receipt", str(receipt),
        "--expected-receipt-sha256", published["receipt_sha256"],
    ]) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["receipt_integrity_verified"] is True
    assert inspected["both_library_states_reexecuted"] is True
    assert inspected["signed_policy_history_reverified"] is True
    assert inspected["release_certified"] is False
    assert before == (
        open(old.private_save, "rb").read(),
        open(new.private_save, "rb").read(),
        open(signed.private_save, "rb").read(),
    )


def test_no_clobber_preserves_preexisting_destination(transition):
    *_, receipt = transition
    receipt.write_text("existing", encoding="utf-8")
    with pytest.raises((OSError, ValueError)):
        _publish(transition)
    assert receipt.read_text(encoding="utf-8") == "existing"


def test_wrong_pin_and_missing_pin_fail_closed(transition, capsys):
    published = _publish(transition)
    with pytest.raises((OSError, ValueError)):
        _inspect(transition, "0" * 64)
    old, new, signed, receipt = transition
    assert run_app_cli(_args(old, new, signed) + [
        "--inspect-receipt", str(receipt),
    ]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "blocked"
    assert published["receipt_published"] is True


def test_receipt_cannot_alias_save_or_installed_source(transition):
    old, new, signed, _ = transition
    for target in (
        old.private_save,
        os.path.join(new.installed_source, "unsafe-receipt.json"),
    ):
        with pytest.raises((OSError, ValueError)):
            publish_mixed_library_continuity_handoff(
                [old], [new], [signed], [signed], target, authorized=True,
            )


def test_same_byte_receipt_inode_replacement_is_rejected(
    transition, tmp_path, monkeypatch,
):
    published = _publish(transition)
    *_, receipt = transition
    import skeleton.app.offline_mixed_game_library_continuity_handoff as module
    original = module._audit
    calls = 0

    def replace_receipt(*args, **kwargs):
        nonlocal calls
        result = original(*args, **kwargs)
        calls += 1
        if calls == 1:
            other = tmp_path / "replacement-continuity.json"
            other.write_bytes(receipt.read_bytes())
            other.chmod(0o600)
            os.replace(other, receipt)
        return result

    monkeypatch.setattr(module, "_audit", replace_receipt)
    with pytest.raises((OSError, ValueError)):
        _inspect(transition, published["receipt_sha256"])


def test_source_mutation_after_initial_continuity_blocks_publication(
    transition, monkeypatch,
):
    old, new, signed, receipt = transition
    import skeleton.app.offline_mixed_game_library_continuity_handoff as module
    original = module._audit
    calls = 0

    def mutate(*args, **kwargs):
        nonlocal calls
        result = original(*args, **kwargs)
        calls += 1
        if calls == 1:
            with open(old.archive, "ab") as stream:
                stream.write(b"tampered")
        return result

    monkeypatch.setattr(module, "_audit", mutate)
    with pytest.raises((OSError, ValueError)):
        _publish(transition)
    assert not receipt.exists()


def test_authority_rejected_before_any_game_read(transition, monkeypatch):
    old, new, signed, receipt = transition
    import skeleton.app.offline_mixed_game_library_continuity_handoff as module
    monkeypatch.setattr(
        module, "_protected_all",
        lambda *_: pytest.fail("unauthorized original game read"),
    )
    with pytest.raises(PermissionError):
        module.publish_mixed_library_continuity_handoff(
            [old], [new], [signed], [signed], receipt, authorized=False,
        )


def test_same_byte_receipt_swap_after_publication_is_not_success(
    transition, tmp_path, monkeypatch,
):
    old, new, signed, receipt = transition
    import skeleton.app.offline_mixed_game_library_continuity_handoff as module
    original = module._read_envelope

    def replace_after_read(*args, **kwargs):
        value = original(*args, **kwargs)
        other = tmp_path / "post-publish-replacement.json"
        other.write_bytes(receipt.read_bytes())
        other.chmod(0o600)
        os.replace(other, receipt)
        return value

    monkeypatch.setattr(module, "_read_envelope", replace_after_read)
    with pytest.raises((OSError, ValueError)):
        _publish(transition)
    # An uncertain published receipt remains for operator quarantine.
    assert receipt.exists()
