from dataclasses import dataclass


@dataclass(frozen=True)
class ModelConsumer:
    consumer_id: str
    migrated: bool
    exception: str | None = None

    def __post_init__(self) -> None:
        if not self.consumer_id or not isinstance(self.migrated, bool):
            raise ValueError("valid model consumer required")
        if self.exception is not None and not self.exception:
            raise ValueError("exception cannot be empty")


@dataclass(frozen=True)
class ModelDeprecation:
    model_id: str
    replacement: str
    deadline: int
    consumers: tuple[ModelConsumer, ...]

    def __post_init__(self) -> None:
        if (
            not self.model_id
            or not self.replacement
            or self.model_id == self.replacement
            or isinstance(self.deadline, bool)
            or not isinstance(self.deadline, int)
            or self.deadline < 0
        ):
            raise ValueError("invalid deprecation record")
        if any(not isinstance(consumer, ModelConsumer) for consumer in self.consumers):
            raise ValueError("consumer inventory required")
        ids = [consumer.consumer_id for consumer in self.consumers]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate consumer inventory")


@dataclass(frozen=True)
class ModelRetirement:
    model_id: str
    retired: bool
    reason: str


def retire(deprecation: ModelDeprecation, now: int) -> ModelRetirement:
    if (
        not isinstance(deprecation, ModelDeprecation)
        or isinstance(now, bool)
        or not isinstance(now, int)
        or now < 0
    ):
        return ModelRetirement(
            getattr(deprecation, "model_id", ""),
            False,
            "invalid deprecation record",
        )

    pending = [
        consumer
        for consumer in deprecation.consumers
        if not consumer.migrated and consumer.exception is None
    ]
    if pending:
        return ModelRetirement(
            deprecation.model_id,
            False,
            "supported consumers remain",
        )
    if now < deprecation.deadline:
        return ModelRetirement(
            deprecation.model_id,
            False,
            "deadline not reached",
        )
    return ModelRetirement(deprecation.model_id, True, "migration complete")
