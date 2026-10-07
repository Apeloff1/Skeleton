from __future__ import annotations

from pathlib import Path

import pytest

from skeleton.jeeves.core import Jeeves
from skeleton.jeeves.game_engine_lab import (
    EngineEra,
    GameEngineLabError,
)
from skeleton.jeeves.game_engine_legacy import (
    InputButton,
    InputFrame,
)
from skeleton.jeeves.game_engine_runtime import (
    ExecutableGameEngineLab,
)
from skeleton.jeeves.game_engine_saves import (
    SAVE_POLICIES,
    EraSaveManager,
    SaveIntegrity,
    SaveKind,
    SaveMedium,
    build_game_save_manager,
    save_policy,
)
from skeleton.persistence import (
    SnapshotStore,
)


@pytest.mark.parametrize(
    "era",
    list(EngineEra),
)
def test_every_engine_era_has_historical_save_policy(
    era: EngineEra,
) -> None:
    policy = save_policy(
        era
    )

    assert policy.era is era
    assert era in SAVE_POLICIES
    assert policy.max_slots >= 1
    assert policy.max_record_bytes >= 128
    assert (
        policy.max_versions_per_slot
        >= 1
    )


def test_save_media_progress_historically() -> None:
    assert (
        save_policy(
            EngineEra.PONG
        ).medium
        is SaveMedium.VOLATILE
    )
    assert (
        save_policy(
            EngineEra.ARCADE
        ).medium
        is SaveMedium.NVRAM_SCORE
    )
    assert (
        save_policy(
            EngineEra.EIGHT_BIT
        ).medium
        is SaveMedium.BATTERY_SRAM
    )
    assert (
        save_policy(
            EngineEra.EARLY_3D
        ).medium
        is SaveMedium.MEMORY_CARD
    )
    assert (
        save_policy(
            EngineEra.SHADER
        ).medium
        is SaveMedium.LOCAL_DISK
    )
    assert (
        save_policy(
            EngineEra.OPEN_WORLD
        ).medium
        is SaveMedium.JOURNALED_DISK
    )
    assert (
        save_policy(
            EngineEra.NEXT
        ).medium
        is SaveMedium.CONTENT_ADDRESSED
    )


def test_full_state_player_save_begins_at_eight_bit() -> None:
    assert not save_policy(
        EngineEra.PONG
    ).player_state
    assert not save_policy(
        EngineEra.ARCADE
    ).player_state
    assert save_policy(
        EngineEra.EIGHT_BIT
    ).player_state
    assert save_policy(
        EngineEra.NEXT
    ).player_state


def test_integrity_strength_progresses_to_sha256() -> None:
    assert (
        save_policy(
            EngineEra.PONG
        ).integrity
        is SaveIntegrity.NONE
    )
    assert (
        save_policy(
            EngineEra.ARCADE
        ).integrity
        is SaveIntegrity.XOR8
    )
    assert (
        save_policy(
            EngineEra.EIGHT_BIT
        ).integrity
        is SaveIntegrity.CRC16
    )
    assert (
        save_policy(
            EngineEra.FIXED_3D
        ).integrity
        is SaveIntegrity.CRC32
    )
    assert (
        save_policy(
            EngineEra.HD
        ).integrity
        is SaveIntegrity.SHA256
    )


def test_pong_refuses_persistent_player_and_score_saves(
    tmp_path: Path,
) -> None:
    manager = EraSaveManager(
        EngineEra.PONG,
        SnapshotStore(
            tmp_path
        ),
    )
    machine = (
        ExecutableGameEngineLab()
        .create(
            EngineEra.PONG
        )
        .machine()
    )

    with pytest.raises(
        GameEngineLabError,
        match="score storage unavailable",
    ):
        manager.save_scores(
            (100,)
        )

    with pytest.raises(
        GameEngineLabError,
        match="full-state player saves unavailable",
    ):
        manager.save_machine(
            machine
        )


def test_arcade_nvram_score_table_is_sorted_and_round_trips(
    tmp_path: Path,
) -> None:
    manager = EraSaveManager(
        EngineEra.ARCADE,
        SnapshotStore(
            tmp_path
        ),
    )

    record = manager.save_scores(
        (
            1200,
            9000,
            4500,
        )
    )

    assert (
        record.kind
        is SaveKind.SCORE_TABLE
    )
    assert (
        record.medium
        is SaveMedium.NVRAM_SCORE
    )
    assert len(
        record.integrity_code
    ) == 2
    assert (
        manager.load_scores()
        == (
            9000,
            4500,
            1200,
        )
    )
    verification = manager.verify_slot(
        "scores"
    )
    assert verification.passed
    assert verification.records == 1


@pytest.mark.parametrize(
    "era",
    [
        EngineEra.EIGHT_BIT,
        EngineEra.SIXTEEN_BIT,
        EngineEra.EARLY_3D,
        EngineEra.FIXED_3D,
        EngineEra.SHADER,
        EngineEra.HD,
        EngineEra.OPEN_WORLD,
        EngineEra.MODERN,
        EngineEra.NEXT,
    ],
)
def test_full_state_save_restores_exact_machine_fingerprint(
    era: EngineEra,
    tmp_path: Path,
) -> None:
    sandbox = (
        ExecutableGameEngineLab()
        .create(
            era
        )
    )
    machine = sandbox.machine()
    for tick in range(8):
        machine.step(
            InputFrame(
                tick,
                (
                    InputButton.UP
                    | (
                        InputButton.RIGHT
                        if tick % 2 == 0
                        else InputButton.NONE
                    )
                ),
            )
        )
    expected = machine.fingerprint()
    manager = EraSaveManager(
        era,
        SnapshotStore(
            tmp_path
        ),
    )

    record = manager.save_machine(
        machine,
        slot="campaign",
    )
    for tick in range(
        8,
        14,
    ):
        machine.step(
            InputFrame(
                tick,
                InputButton.LEFT,
            )
        )
    assert (
        machine.fingerprint()
        != expected
    )

    restored = manager.restore_machine(
        machine,
        slot="campaign",
    )

    assert (
        restored.record_digest
        == record.record_digest
    )
    assert machine.fingerprint() == expected
    assert manager.verify_slot(
        "campaign"
    ).passed


def test_save_versions_form_parent_hash_chain(
    tmp_path: Path,
) -> None:
    manager = EraSaveManager(
        EngineEra.MODERN,
        SnapshotStore(
            tmp_path
        ),
    )
    machine = (
        ExecutableGameEngineLab()
        .create(
            EngineEra.MODERN
        )
        .machine()
    )

    first = manager.save_machine(
        machine,
        slot="campaign",
    )
    machine.step(
        InputFrame(
            0,
            InputButton.UP,
        )
    )
    second = manager.save_machine(
        machine,
        slot="campaign",
    )
    machine.step(
        InputFrame(
            1,
            InputButton.RIGHT,
        )
    )
    third = manager.save_machine(
        machine,
        slot="campaign",
    )

    assert first.sequence == 0
    assert second.sequence == 1
    assert third.sequence == 2
    assert first.parent_digest is None
    assert (
        second.parent_digest
        == first.record_digest
    )
    assert (
        third.parent_digest
        == second.record_digest
    )
    verification = manager.verify_slot(
        "campaign"
    )
    assert verification.passed
    assert verification.records == 3
    assert (
        verification.head_digest
        == third.record_digest
    )


def test_restore_prior_save_sequence_recovers_historical_state(
    tmp_path: Path,
) -> None:
    manager = EraSaveManager(
        EngineEra.MODERN,
        SnapshotStore(
            tmp_path
        ),
    )
    machine = (
        ExecutableGameEngineLab()
        .create(
            EngineEra.MODERN
        )
        .machine()
    )
    for tick in range(5):
        machine.step(
            InputFrame(
                tick,
                InputButton.UP,
            )
        )
    first_fingerprint = (
        machine.fingerprint()
    )
    first = manager.save_machine(
        machine,
        slot="campaign",
    )

    for tick in range(
        5,
        10,
    ):
        machine.step(
            InputFrame(
                tick,
                InputButton.RIGHT,
            )
        )
    second = manager.save_machine(
        machine,
        slot="campaign",
    )
    assert (
        second.record_digest
        != first.record_digest
    )

    for tick in range(
        10,
        13,
    ):
        machine.step(
            InputFrame(
                tick,
                InputButton.LEFT,
            )
        )

    restored = manager.restore_machine(
        machine,
        slot="campaign",
        sequence=0,
    )

    assert restored.sequence == 0
    assert (
        machine.fingerprint()
        == first_fingerprint
    )


def test_save_state_survives_manager_restart(
    tmp_path: Path,
) -> None:
    store = SnapshotStore(
        tmp_path
    )
    first_manager = EraSaveManager(
        EngineEra.EIGHT_BIT,
        store,
    )
    machine = (
        ExecutableGameEngineLab()
        .create(
            EngineEra.EIGHT_BIT
        )
        .machine()
    )
    machine.step(
        InputFrame(
            0,
            InputButton.RIGHT,
        )
    )
    expected = machine.fingerprint()
    saved = first_manager.save_machine(
        machine,
        slot="slot1",
    )

    second_manager = EraSaveManager(
        EngineEra.EIGHT_BIT,
        SnapshotStore(
            tmp_path
        ),
    )
    head = second_manager.head(
        "slot1"
    )

    assert head is not None
    assert (
        head.record_digest
        == saved.record_digest
    )
    machine.step(
        InputFrame(
            1,
            InputButton.LEFT,
        )
    )
    second_manager.restore_machine(
        machine,
        slot="slot1",
    )
    assert machine.fingerprint() == expected


def test_tampered_save_record_fails_integrity_and_slot_verification(
    tmp_path: Path,
) -> None:
    store = SnapshotStore(
        tmp_path
    )
    manager = EraSaveManager(
        EngineEra.ARCADE,
        store,
    )
    manager.save_scores(
        (
            100,
            50,
        )
    )
    record_name = next(
        item["name"]
        for item
        in store.list()
        if "-record-" in item[
            "name"
        ]
    )
    raw = store.load(
        record_name
    )
    assert raw is not None
    raw[
        "payload"
    ][
        "scores"
    ][0] = 999999
    store.save(
        record_name,
        raw,
    )

    with pytest.raises(
        GameEngineLabError,
        match="integrity mismatch",
    ):
        manager.records(
            "scores"
        )

    verification = manager.verify_slot(
        "scores"
    )
    assert not verification.passed
    assert (
        "record_integrity"
        in verification.failures
    )


def test_tampered_head_pointer_is_rejected(
    tmp_path: Path,
) -> None:
    store = SnapshotStore(
        tmp_path
    )
    manager = EraSaveManager(
        EngineEra.ARCADE,
        store,
    )
    manager.save_scores(
        (100,)
    )
    head_name = next(
        item["name"]
        for item
        in store.list()
        if item["name"].endswith(
            "-head"
        )
    )
    raw = store.load(
        head_name
    )
    assert raw is not None
    raw[
        "record_digest"
    ] = "0" * 64
    store.save(
        head_name,
        raw,
    )

    with pytest.raises(
        GameEngineLabError,
        match="head pointer digest mismatch",
    ):
        manager.head(
            "scores"
        )


def test_arcade_slot_budget_is_enforced(
    tmp_path: Path,
) -> None:
    manager = EraSaveManager(
        EngineEra.ARCADE,
        SnapshotStore(
            tmp_path
        ),
    )
    manager.save_scores(
        (100,),
        slot="cabinet",
    )

    with pytest.raises(
        GameEngineLabError,
        match="slot budget exceeded",
    ):
        manager.save_scores(
            (200,),
            slot="second",
        )


@pytest.mark.parametrize(
    "slot",
    [
        "../escape",
        "/absolute",
        "nested/path",
        "",
    ],
)
def test_save_slot_rejects_unsafe_paths(
    slot: str,
    tmp_path: Path,
) -> None:
    manager = EraSaveManager(
        EngineEra.ARCADE,
        SnapshotStore(
            tmp_path
        ),
    )

    with pytest.raises(
        GameEngineLabError,
        match="safe token",
    ):
        manager.save_scores(
            (100,),
            slot=slot,
        )


def test_save_manager_rejects_machine_from_wrong_era(
    tmp_path: Path,
) -> None:
    manager = EraSaveManager(
        EngineEra.EIGHT_BIT,
        SnapshotStore(
            tmp_path
        ),
    )
    machine = (
        ExecutableGameEngineLab()
        .create(
            EngineEra.SIXTEEN_BIT
        )
        .machine()
    )

    with pytest.raises(
        GameEngineLabError,
        match="machine era",
    ):
        manager.save_machine(
            machine
        )


def test_next_save_is_content_addressed_sha256_journal(
    tmp_path: Path,
) -> None:
    manager = EraSaveManager(
        EngineEra.NEXT,
        SnapshotStore(
            tmp_path
        ),
    )
    machine = (
        ExecutableGameEngineLab()
        .create(
            EngineEra.NEXT
        )
        .machine()
    )

    record = manager.save_machine(
        machine,
        slot="world",
    )

    assert (
        manager.policy.medium
        is SaveMedium.CONTENT_ADDRESSED
    )
    assert (
        manager.policy.integrity
        is SaveIntegrity.SHA256
    )
    assert manager.policy.journaling
    assert manager.policy.record_first_head
    assert len(
        record.integrity_code
    ) == 64
    assert len(
        record.payload_digest
    ) == 64
    assert len(
        record.record_digest
    ) == 64


def test_builder_reuses_supplied_snapshot_store(
    tmp_path: Path,
) -> None:
    store = SnapshotStore(
        tmp_path
    )

    manager = build_game_save_manager(
        EngineEra.ARCADE,
        store,
        namespace="game-test",
    )

    assert manager.store is store
    assert manager.namespace == "game-test"


def test_jeeves_creates_historical_save_manager_over_existing_store(
    tmp_path: Path,
) -> None:
    jeeves = Jeeves()
    store = SnapshotStore(
        tmp_path
    )

    manager = jeeves.game_save_manager(
        EngineEra.MODERN,
        store,
        namespace="jeeves-test",
    )

    assert isinstance(
        manager,
        EraSaveManager,
    )
    assert manager.store is store
    assert (
        manager.era
        is EngineEra.MODERN
    )
    assert (
        manager.policy.medium
        is SaveMedium.JOURNALED_DISK
    )


def test_boolean_scores_are_rejected_even_though_bool_is_int(
    tmp_path: Path,
) -> None:
    manager = EraSaveManager(
        EngineEra.ARCADE,
        SnapshotStore(
            tmp_path
        ),
    )

    with pytest.raises(
        GameEngineLabError,
        match="score table",
    ):
        manager.save_scores(
            (
                True,
                100,
            )
        )


@pytest.mark.parametrize(
    "sequence",
    [
        -1,
        True,
        1_000_001,
    ],
)
def test_restore_sequence_is_strictly_bounded(
    sequence,
    tmp_path: Path,
) -> None:
    manager = EraSaveManager(
        EngineEra.EIGHT_BIT,
        SnapshotStore(
            tmp_path
        ),
    )
    machine = (
        ExecutableGameEngineLab()
        .create(
            EngineEra.EIGHT_BIT
        )
        .machine()
    )
    manager.save_machine(
        machine
    )

    with pytest.raises(
        GameEngineLabError,
        match="restore sequence",
    ):
        manager.restore_machine(
            machine,
            sequence=sequence,
        )



def test_forged_head_cannot_redirect_snapshot_store_outside_namespace(
    tmp_path: Path,
) -> None:
    store = SnapshotStore(
        tmp_path
    )
    manager = EraSaveManager(
        EngineEra.ARCADE,
        store,
    )
    manager.save_scores(
        (100,)
    )
    head_name = next(
        item["name"]
        for item
        in store.list()
        if item["name"].endswith(
            "-head"
        )
    )
    raw = store.load(
        head_name
    )
    assert raw is not None
    raw[
        "record_name"
    ] = "../outside"
    store.save(
        head_name,
        raw,
    )

    with pytest.raises(
        GameEngineLabError,
        match="storage key",
    ):
        manager.head(
            "scores"
        )


def test_forged_head_cannot_retarget_another_valid_record(
    tmp_path: Path,
) -> None:
    store = SnapshotStore(
        tmp_path
    )
    manager = EraSaveManager(
        EngineEra.MODERN,
        store,
    )
    machine = (
        ExecutableGameEngineLab()
        .create(
            EngineEra.MODERN
        )
        .machine()
    )
    manager.save_machine(
        machine,
        slot="a",
    )
    manager.save_machine(
        machine,
        slot="b",
    )
    head_a = next(
        item["name"]
        for item
        in store.list()
        if (
            "-a-head"
            in item["name"]
        )
    )
    record_b = next(
        item["name"]
        for item
        in store.list()
        if (
            "-b-record-"
            in item["name"]
        )
    )
    raw = store.load(
        head_a
    )
    assert raw is not None
    raw[
        "record_name"
    ] = record_b
    store.save(
        head_a,
        raw,
    )

    with pytest.raises(
        GameEngineLabError,
        match="target mismatch",
    ):
        manager.head(
            "a"
        )



def test_modern_save_restore_discards_future_rollback_history(
    tmp_path: Path,
) -> None:
    manager = EraSaveManager(
        EngineEra.MODERN,
        SnapshotStore(
            tmp_path
        ),
    )
    machine = (
        ExecutableGameEngineLab()
        .create(
            EngineEra.MODERN
        )
        .machine()
    )
    for tick in range(8):
        machine.step(
            InputFrame(
                tick,
                InputButton.UP,
            )
        )
    assert machine.rollback_depth > 0
    manager.save_machine(
        machine,
        slot="campaign",
    )

    for tick in range(
        8,
        16,
    ):
        machine.step(
            InputFrame(
                tick,
                InputButton.RIGHT,
            )
        )
    assert machine.rollback_depth > 0

    manager.restore_machine(
        machine,
        slot="campaign",
    )

    assert machine.rollback_depth == 0
    with pytest.raises(
        GameEngineLabError,
        match="rollback distance unavailable",
    ):
        machine.rollback(
            1
        )


def test_valid_record_transplant_between_slots_is_rejected(
    tmp_path: Path,
) -> None:
    store = SnapshotStore(
        tmp_path
    )
    manager = EraSaveManager(
        EngineEra.MODERN,
        store,
    )
    machine = (
        ExecutableGameEngineLab()
        .create(
            EngineEra.MODERN
        )
        .machine()
    )
    manager.save_machine(
        machine,
        slot="a",
    )
    machine.step(
        InputFrame(
            0,
            InputButton.RIGHT,
        )
    )
    manager.save_machine(
        machine,
        slot="b",
    )

    record_a = next(
        item["name"]
        for item
        in store.list()
        if "-a-record-" in item[
            "name"
        ]
    )
    record_b = next(
        item["name"]
        for item
        in store.list()
        if "-b-record-" in item[
            "name"
        ]
    )
    valid_b = store.load(
        record_b
    )
    assert valid_b is not None
    store.save(
        record_a,
        valid_b,
    )

    with pytest.raises(
        GameEngineLabError,
        match="identity does not match storage key",
    ):
        manager.records(
            "a"
        )


def test_save_envelope_rejects_coerced_string_sequence(
    tmp_path: Path,
) -> None:
    store = SnapshotStore(
        tmp_path
    )
    manager = EraSaveManager(
        EngineEra.ARCADE,
        store,
    )
    manager.save_scores(
        (100,)
    )
    record_name = next(
        item["name"]
        for item
        in store.list()
        if "-record-" in item[
            "name"
        ]
    )
    raw = store.load(
        record_name
    )
    assert raw is not None
    raw["sequence"] = "0"
    store.save(
        record_name,
        raw,
    )

    with pytest.raises(
        GameEngineLabError,
        match="envelope malformed",
    ):
        manager.records(
            "scores"
        )
