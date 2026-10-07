"""Historical game-save policy adapter for Jeeves engine eras.

The repository already owns disk persistence through
skeleton.persistence.SnapshotStore. This module does not replace it.
Instead it defines historically appropriate game-save semantics and stores
bounded, hash-chained save envelopes through that existing store.

Early eras model score persistence rather than arbitrary resume state. Full
machine-state saves begin where cartridge/storage technology reasonably allows
it and grow through memory-card, local-disk, journaled and content-addressed
policies.

No save operation happens unless the caller explicitly supplies/creates a
manager. Runtime snapshots remain the authority for state restoration.
"""

from __future__ import annotations

import hashlib
import json
import zlib
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from skeleton.persistence import SnapshotStore

from .game_engine_lab import EngineEra, GameEngineLabError

SAVE_SCHEMA_VERSION = 1
MAX_SCORE = 2_147_483_647
MAX_SCORE_ENTRIES = 100
MAX_SAVE_SEQUENCE = 1_000_000


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _digest(value: object) -> str:
    return hashlib.sha256(
        _canonical(value).encode("utf-8")
    ).hexdigest()


def _slot_token(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 32
        or not all(
            char.isalnum() or char in "_.-"
            for char in value
        )
    ):
        raise GameEngineLabError(
            "save slot must be a bounded safe token"
        )
    return value


def _storage_token(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 192
        or not all(
            char.isalnum() or char in "_.-"
            for char in value
        )
    ):
        raise GameEngineLabError(
            "save storage key must be a bounded safe token"
        )
    return value


class SaveMedium(str, Enum):
    VOLATILE = "volatile"
    NVRAM_SCORE = "nvram_score"
    BATTERY_SRAM = "battery_sram"
    MEMORY_CARD = "memory_card"
    LOCAL_DISK = "local_disk"
    JOURNALED_DISK = "journaled_disk"
    CONTENT_ADDRESSED = "content_addressed"


class SaveIntegrity(str, Enum):
    NONE = "none"
    XOR8 = "xor8"
    CRC16 = "crc16"
    CRC32 = "crc32"
    SHA256 = "sha256"


class SaveKind(str, Enum):
    SCORE_TABLE = "score_table"
    MACHINE_STATE = "machine_state"


@dataclass(frozen=True, slots=True)
class EraSavePolicy:
    era: EngineEra
    medium: SaveMedium
    integrity: SaveIntegrity
    player_state: bool
    max_slots: int
    max_record_bytes: int
    max_versions_per_slot: int
    journaling: bool
    record_first_head: bool

    def __post_init__(self) -> None:
        if (
            self.max_slots < 1
            or self.max_record_bytes < 128
            or self.max_versions_per_slot < 1
        ):
            raise GameEngineLabError(
                "save policy bounds must be positive"
            )


SAVE_POLICIES = {
    EngineEra.PONG: EraSavePolicy(
        EngineEra.PONG,
        SaveMedium.VOLATILE,
        SaveIntegrity.NONE,
        False,
        1,
        1024,
        8,
        False,
        False,
    ),
    EngineEra.ARCADE: EraSavePolicy(
        EngineEra.ARCADE,
        SaveMedium.NVRAM_SCORE,
        SaveIntegrity.XOR8,
        False,
        1,
        2048,
        16,
        False,
        False,
    ),
    EngineEra.EIGHT_BIT: EraSavePolicy(
        EngineEra.EIGHT_BIT,
        SaveMedium.BATTERY_SRAM,
        SaveIntegrity.CRC16,
        True,
        3,
        64 * 1024,
        32,
        False,
        False,
    ),
    EngineEra.SIXTEEN_BIT: EraSavePolicy(
        EngineEra.SIXTEEN_BIT,
        SaveMedium.BATTERY_SRAM,
        SaveIntegrity.CRC16,
        True,
        5,
        128 * 1024,
        64,
        False,
        False,
    ),
    EngineEra.EARLY_3D: EraSavePolicy(
        EngineEra.EARLY_3D,
        SaveMedium.MEMORY_CARD,
        SaveIntegrity.CRC32,
        True,
        8,
        256 * 1024,
        96,
        False,
        True,
    ),
    EngineEra.FIXED_3D: EraSavePolicy(
        EngineEra.FIXED_3D,
        SaveMedium.MEMORY_CARD,
        SaveIntegrity.CRC32,
        True,
        16,
        512 * 1024,
        128,
        False,
        True,
    ),
    EngineEra.SHADER: EraSavePolicy(
        EngineEra.SHADER,
        SaveMedium.LOCAL_DISK,
        SaveIntegrity.CRC32,
        True,
        24,
        1024 * 1024,
        192,
        False,
        True,
    ),
    EngineEra.HD: EraSavePolicy(
        EngineEra.HD,
        SaveMedium.LOCAL_DISK,
        SaveIntegrity.SHA256,
        True,
        32,
        2 * 1024 * 1024,
        256,
        False,
        True,
    ),
    EngineEra.OPEN_WORLD: EraSavePolicy(
        EngineEra.OPEN_WORLD,
        SaveMedium.JOURNALED_DISK,
        SaveIntegrity.SHA256,
        True,
        64,
        4 * 1024 * 1024,
        512,
        True,
        True,
    ),
    EngineEra.MODERN: EraSavePolicy(
        EngineEra.MODERN,
        SaveMedium.JOURNALED_DISK,
        SaveIntegrity.SHA256,
        True,
        96,
        8 * 1024 * 1024,
        1024,
        True,
        True,
    ),
    EngineEra.NEXT: EraSavePolicy(
        EngineEra.NEXT,
        SaveMedium.CONTENT_ADDRESSED,
        SaveIntegrity.SHA256,
        True,
        128,
        16 * 1024 * 1024,
        2048,
        True,
        True,
    ),
}


def save_policy(era: EngineEra | str) -> EraSavePolicy:
    try:
        key = (
            era
            if isinstance(era, EngineEra)
            else EngineEra(str(era))
        )
    except ValueError as exc:
        raise GameEngineLabError(
            f"unknown engine era: {era!r}"
        ) from exc
    return SAVE_POLICIES[key]


def _integrity_code(
    policy: EraSavePolicy,
    payload_text: str,
) -> str:
    raw = payload_text.encode("utf-8")
    if policy.integrity is SaveIntegrity.NONE:
        return "none"
    if policy.integrity is SaveIntegrity.XOR8:
        value = 0
        for byte in raw:
            value ^= byte
        return f"{value:02x}"
    if policy.integrity is SaveIntegrity.CRC16:
        crc = 0xFFFF
        for byte in raw:
            crc ^= byte << 8
            for _ in range(8):
                crc = (
                    (crc << 1) ^ 0x1021
                    if crc & 0x8000
                    else crc << 1
                ) & 0xFFFF
        return f"{crc:04x}"
    if policy.integrity is SaveIntegrity.CRC32:
        return f"{zlib.crc32(raw) & 0xFFFFFFFF:08x}"
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True, slots=True)
class SaveEnvelope:
    schema_version: int
    era: EngineEra
    medium: SaveMedium
    kind: SaveKind
    slot: str
    sequence: int
    parent_digest: str | None
    payload: tuple[tuple[str, Any], ...]
    payload_digest: str
    integrity_code: str
    record_digest: str

    def payload_document(self) -> dict[str, Any]:
        return dict(self.payload)

    def identity_document(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "engine_era": self.era.value,
            "medium": self.medium.value,
            "kind": self.kind.value,
            "slot": self.slot,
            "sequence": self.sequence,
            "parent_digest": self.parent_digest,
            "payload": self.payload_document(),
            "payload_digest": self.payload_digest,
            "integrity_code": self.integrity_code,
        }

    def document(self) -> dict[str, object]:
        value = self.identity_document()
        value["record_digest"] = self.record_digest
        return value


@dataclass(frozen=True, slots=True)
class SaveSlotVerification:
    era: EngineEra
    slot: str
    passed: bool
    records: int
    head_digest: str | None
    failures: tuple[str, ...]


def _envelope(
    policy: EraSavePolicy,
    kind: SaveKind,
    slot: str,
    sequence: int,
    parent_digest: str | None,
    payload: dict[str, Any],
) -> SaveEnvelope:
    if (
        type(sequence) is not int
        or not 0 <= sequence <= MAX_SAVE_SEQUENCE
    ):
        raise GameEngineLabError(
            "save sequence outside bounds"
        )
    payload_text = _canonical(payload)
    if (
        len(payload_text.encode("utf-8"))
        > policy.max_record_bytes
    ):
        raise GameEngineLabError(
            "save payload exceeds era storage budget"
        )
    payload_digest = _digest(payload)
    integrity = _integrity_code(
        policy,
        payload_text,
    )
    payload_tuple = tuple(
        sorted(
            payload.items(),
            key=lambda row: row[0],
        )
    )
    identity = {
        "schema_version": SAVE_SCHEMA_VERSION,
        "engine_era": policy.era.value,
        "medium": policy.medium.value,
        "kind": kind.value,
        "slot": slot,
        "sequence": sequence,
        "parent_digest": parent_digest,
        "payload": dict(payload_tuple),
        "payload_digest": payload_digest,
        "integrity_code": integrity,
    }
    return SaveEnvelope(
        SAVE_SCHEMA_VERSION,
        policy.era,
        policy.medium,
        kind,
        slot,
        sequence,
        parent_digest,
        payload_tuple,
        payload_digest,
        integrity,
        _digest(identity),
    )


def _parse_envelope(
    policy: EraSavePolicy,
    value: dict[str, Any],
) -> SaveEnvelope:
    try:
        raw_schema = value[
            "schema_version"
        ]
        raw_sequence = value[
            "sequence"
        ]
        if (
            type(raw_schema) is not int
            or type(raw_sequence) is not int
        ):
            raise TypeError(
                "save schema and sequence must be strict integers"
            )
        schema_version = raw_schema
        era = EngineEra(
            value["engine_era"]
        )
        medium = SaveMedium(
            value["medium"]
        )
        kind = SaveKind(
            value["kind"]
        )
        slot = _slot_token(
            value["slot"]
        )
        sequence = raw_sequence
        parent = value.get(
            "parent_digest"
        )
        payload = value["payload"]
        payload_digest = str(
            value["payload_digest"]
        )
        integrity = str(
            value["integrity_code"]
        )
        record_digest = str(
            value["record_digest"]
        )
    except (
        KeyError,
        TypeError,
        ValueError,
    ) as exc:
        raise GameEngineLabError(
            "save envelope malformed"
        ) from exc
    if (
        schema_version != SAVE_SCHEMA_VERSION
        or era is not policy.era
        or medium is not policy.medium
        or not isinstance(payload, dict)
        or (
            parent is not None
            and (
                not isinstance(parent, str)
                or len(parent) != 64
            )
        )
        or len(payload_digest) != 64
        or len(record_digest) != 64
    ):
        raise GameEngineLabError(
            "save envelope contract mismatch"
        )
    parsed = _envelope(
        policy,
        kind,
        slot,
        sequence,
        parent,
        payload,
    )
    if (
        parsed.payload_digest != payload_digest
        or parsed.integrity_code != integrity
        or parsed.record_digest != record_digest
    ):
        raise GameEngineLabError(
            "save envelope integrity mismatch"
        )
    return parsed


class EraSaveManager:
    """Historical save semantics over the existing SnapshotStore."""

    def __init__(
        self,
        era: EngineEra | str,
        store: SnapshotStore | None = None,
        *,
        namespace: str = "jeeves-game",
    ) -> None:
        self.policy = save_policy(era)
        self.store = (
            store
            or SnapshotStore()
        )
        self.namespace = _slot_token(
            namespace
        )

    @property
    def era(self) -> EngineEra:
        return self.policy.era

    def _prefix(self, slot: str) -> str:
        slot = _slot_token(slot)
        return (
            self.namespace
            + "-"
            + self.era.value
            + "-"
            + slot
        )

    def _record_name(
        self,
        slot: str,
        sequence: int,
    ) -> str:
        return (
            self._prefix(slot)
            + "-record-"
            + f"{sequence:07d}"
        )

    def _head_name(self, slot: str) -> str:
        return self._prefix(slot) + "-head"

    def _record_names(
        self,
        slot: str,
    ) -> tuple[str, ...]:
        prefix = (
            self._prefix(slot)
            + "-record-"
        )
        names: list[str] = []
        for item in self.store.list():
            name = (
                item.get("name")
                if isinstance(
                    item,
                    dict,
                )
                else None
            )
            if not isinstance(
                name,
                str,
            ):
                continue
            try:
                _storage_token(
                    name
                )
            except GameEngineLabError:
                continue
            if not name.startswith(
                prefix
            ):
                continue
            suffix = name[
                len(prefix):
            ]
            if (
                len(suffix) == 7
                and suffix.isdigit()
                and name
                == prefix + suffix
            ):
                names.append(
                    name
                )
        return tuple(sorted(names))

    def slots(self) -> tuple[str, ...]:
        marker = (
            self.namespace
            + "-"
            + self.era.value
            + "-"
        )
        suffix = "-head"
        result = []
        for item in self.store.list():
            name = item.get("name")
            if (
                isinstance(name, str)
                and name.startswith(marker)
                and name.endswith(suffix)
            ):
                slot = name[
                    len(marker):
                    -len(suffix)
                ]
                try:
                    _slot_token(slot)
                except GameEngineLabError:
                    continue
                result.append(slot)
        return tuple(
            sorted(set(result))
        )

    def _ensure_slot_capacity(
        self,
        slot: str,
    ) -> None:
        slot = _slot_token(slot)
        known = set(self.slots())
        if (
            slot not in known
            and len(known)
            >= self.policy.max_slots
        ):
            raise GameEngineLabError(
                "save slot budget exceeded for engine era"
            )

    def _load_record_name(
        self,
        name: str,
    ) -> SaveEnvelope:
        name = _storage_token(
            name
        )
        raw = self.store.load(name)
        if not isinstance(raw, dict):
            raise GameEngineLabError(
                "save record missing"
            )
        return _parse_envelope(
            self.policy,
            raw,
        )

    def records(
        self,
        slot: str,
    ) -> tuple[SaveEnvelope, ...]:
        slot = _slot_token(
            slot
        )
        prefix = (
            self._prefix(
                slot
            )
            + "-record-"
        )
        values: list[
            SaveEnvelope
        ] = []
        for name in self._record_names(
            slot
        ):
            expected_sequence = int(
                name[
                    len(prefix):
                ]
            )
            record = (
                self._load_record_name(
                    name
                )
            )
            if (
                record.slot
                != slot
                or record.sequence
                != expected_sequence
            ):
                raise GameEngineLabError(
                    "save record identity does not match storage key"
                )
            values.append(
                record
            )
        return tuple(values)

    def head(
        self,
        slot: str,
    ) -> SaveEnvelope | None:
        slot = _slot_token(slot)
        pointer = self.store.load(
            self._head_name(slot)
        )
        if pointer is None:
            return None
        if (
            not isinstance(pointer, dict)
            or not isinstance(
                pointer.get(
                    "record_name"
                ),
                str,
            )
            or not isinstance(
                pointer.get(
                    "record_digest"
                ),
                str,
            )
            or type(
                pointer.get(
                    "sequence"
                )
            )
            is not int
        ):
            raise GameEngineLabError(
                "save head pointer malformed"
            )
        sequence = pointer[
            "sequence"
        ]
        if (
            not 0
            <= sequence
            < self.policy.max_versions_per_slot
            or sequence
            > MAX_SAVE_SEQUENCE
        ):
            raise GameEngineLabError(
                "save head pointer sequence invalid"
            )
        record_name = _storage_token(
            pointer[
                "record_name"
            ]
        )
        expected_name = (
            self._record_name(
                slot,
                sequence,
            )
        )
        if (
            record_name
            != expected_name
        ):
            raise GameEngineLabError(
                "save head pointer target mismatch"
            )
        record = self._load_record_name(
            record_name
        )
        if (
            record.slot
            != slot
            or record.sequence
            != sequence
        ):
            raise GameEngineLabError(
                "save head pointer record identity mismatch"
            )
        if (
            record.record_digest
            != pointer["record_digest"]
        ):
            raise GameEngineLabError(
                "save head pointer digest mismatch"
            )
        return record

    def _commit(
        self,
        kind: SaveKind,
        slot: str,
        payload: dict[str, Any],
    ) -> SaveEnvelope:
        slot = _slot_token(slot)
        self._ensure_slot_capacity(slot)
        previous = self.head(slot)
        sequence = (
            0
            if previous is None
            else previous.sequence + 1
        )
        if (
            sequence
            >= self.policy.max_versions_per_slot
        ):
            raise GameEngineLabError(
                "save version budget exceeded for slot"
            )
        envelope = _envelope(
            self.policy,
            kind,
            slot,
            sequence,
            (
                None
                if previous is None
                else previous.record_digest
            ),
            payload,
        )
        record_name = self._record_name(
            slot,
            sequence,
        )
        self.store.save(
            record_name,
            envelope.document(),
        )
        self.store.save(
            self._head_name(slot),
            {
                "record_name": record_name,
                "record_digest":
                    envelope.record_digest,
                "sequence": sequence,
            },
        )
        return envelope

    def save_scores(
        self,
        scores: Iterable[int],
        *,
        slot: str = "scores",
    ) -> SaveEnvelope:
        if (
            self.policy.medium
            is SaveMedium.VOLATILE
        ):
            raise GameEngineLabError(
                "persistent score storage unavailable for this engine era"
            )
        raw_values = tuple(scores)
        if (
            not raw_values
            or len(raw_values)
            > MAX_SCORE_ENTRIES
            or any(
                (
                    isinstance(value, bool)
                    or not isinstance(
                        value,
                        int,
                    )
                    or not 0
                    <= value
                    <= MAX_SCORE
                )
                for value
                in raw_values
            )
        ):
            raise GameEngineLabError(
                "score table outside bounds"
            )
        values = tuple(
            sorted(
                raw_values,
                reverse=True,
            )
        )
        return self._commit(
            SaveKind.SCORE_TABLE,
            slot,
            {
                "scores":
                    list(values),
            },
        )

    def load_scores(
        self,
        *,
        slot: str = "scores",
    ) -> tuple[int, ...] | None:
        record = self.head(slot)
        if record is None:
            return None
        if (
            record.kind
            is not SaveKind.SCORE_TABLE
        ):
            raise GameEngineLabError(
                "save slot does not contain score data"
            )
        values = (
            record.payload_document()
            .get("scores")
        )
        if not isinstance(values, list):
            raise GameEngineLabError(
                "score save payload malformed"
            )
        return tuple(
            int(value)
            for value
            in values
        )

    def save_machine(
        self,
        machine: Any,
        *,
        slot: str = "save0",
    ) -> SaveEnvelope:
        if not self.policy.player_state:
            raise GameEngineLabError(
                (
                    "full-state player saves unavailable "
                    f"for {self.era.value}"
                )
            )
        snapshot = machine.snapshot()
        if (
            getattr(
                snapshot,
                "era",
                None,
            )
            is not self.era
        ):
            raise GameEngineLabError(
                "machine era does not match save manager"
            )
        state = getattr(
            snapshot,
            "state",
            None,
        )
        digest = getattr(
            snapshot,
            "digest",
            None,
        )
        tick = getattr(
            snapshot,
            "tick",
            None,
        )
        if (
            not isinstance(tick, int)
            or not isinstance(digest, str)
            or len(digest) != 64
            or not isinstance(state, tuple)
        ):
            raise GameEngineLabError(
                "machine snapshot contract unsupported"
            )
        return self._commit(
            SaveKind.MACHINE_STATE,
            slot,
            {
                "tick": tick,
                "state": list(state),
                "snapshot_digest": digest,
            },
        )

    def restore_machine(
        self,
        machine: Any,
        *,
        slot: str = "save0",
        sequence: int | None = None,
    ) -> SaveEnvelope:
        if not self.policy.player_state:
            raise GameEngineLabError(
                (
                    "full-state player saves unavailable "
                    f"for {self.era.value}"
                )
            )
        if (
            sequence is not None
            and (
                type(sequence) is not int
                or sequence < 0
                or sequence
                > MAX_SAVE_SEQUENCE
            )
        ):
            raise GameEngineLabError(
                "save restore sequence invalid"
            )
        record = (
            self.head(slot)
            if sequence is None
            else self._load_record_name(
                self._record_name(
                    slot,
                    sequence,
                )
            )
        )
        if record is None:
            raise GameEngineLabError(
                "save slot is empty"
            )
        if (
            record.kind
            is not SaveKind.MACHINE_STATE
        ):
            raise GameEngineLabError(
                "save slot does not contain machine state"
            )
        payload = record.payload_document()
        try:
            tick = int(payload["tick"])
            raw_state = payload["state"]
            snapshot_digest = str(
                payload[
                    "snapshot_digest"
                ]
            )
        except (
            KeyError,
            TypeError,
            ValueError,
        ) as exc:
            raise GameEngineLabError(
                "machine save payload malformed"
            ) from exc
        if (
            not isinstance(raw_state, list)
            or len(snapshot_digest) != 64
        ):
            raise GameEngineLabError(
                "machine save payload malformed"
            )
        try:
            state = tuple(
                (
                    str(row[0]),
                    row[1],
                )
                for row
                in raw_state
            )
        except (
            TypeError,
            IndexError,
        ) as exc:
            raise GameEngineLabError(
                "machine save state malformed"
            ) from exc
        current = machine.snapshot()
        snapshot_type = type(current)
        try:
            restored = snapshot_type(
                self.era,
                tick,
                state,
                snapshot_digest,
            )
        except TypeError as exc:
            raise GameEngineLabError(
                "machine snapshot constructor unsupported"
            ) from exc
        machine.restore(restored)
        clear_history = getattr(
            machine,
            "clear_rollback_history",
            None,
        )
        if callable(
            clear_history
        ):
            clear_history()
        return record

    def verify_slot(
        self,
        slot: str,
    ) -> SaveSlotVerification:
        slot = _slot_token(slot)
        failures: list[str] = []
        try:
            records = self.records(slot)
        except GameEngineLabError:
            records = ()
            failures.append(
                "record_integrity"
            )

        previous = None
        for index, record in enumerate(
            records
        ):
            if record.sequence != index:
                failures.append(
                    "sequence"
                )
            if (
                record.parent_digest
                != previous
            ):
                failures.append(
                    "parent_chain"
                )
            previous = (
                record.record_digest
            )

        try:
            head = self.head(slot)
        except GameEngineLabError:
            head = None
            failures.append("head")
        if records:
            if (
                head is None
                or head.record_digest
                != records[-1].record_digest
            ):
                failures.append(
                    "head_chain"
                )
        elif head is not None:
            failures.append(
                "orphan_head"
            )

        return SaveSlotVerification(
            self.era,
            slot,
            not failures,
            len(records),
            (
                None
                if head is None
                else head.record_digest
            ),
            tuple(
                sorted(
                    set(failures)
                )
            ),
        )


def build_game_save_manager(
    era: EngineEra | str,
    store: SnapshotStore | None = None,
    *,
    namespace: str = "jeeves-game",
) -> EraSaveManager:
    return EraSaveManager(
        era,
        store,
        namespace=namespace,
    )
