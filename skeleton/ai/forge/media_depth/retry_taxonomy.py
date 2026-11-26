"""Fail taxonomy + retry policy for media pipeline stages."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class FailKind(str, Enum):
    TRANSIENT = "transient"
    VALIDATION = "validation"
    CAPACITY = "capacity"
    CORRUPT = "corrupt"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int
    backoff_ms: int
    retryable: tuple[FailKind, ...]

    def should_retry(self, kind: FailKind, attempt: int) -> bool:
        return attempt < self.max_attempts and kind in self.retryable


DEFAULT_POLICY = RetryPolicy(
    max_attempts=3,
    backoff_ms=250,
    retryable=(FailKind.TRANSIENT, FailKind.TIMEOUT, FailKind.CAPACITY),
)


def classify_fail(message: str) -> FailKind:
    m = (message or "").lower()
    if "timeout" in m or "timed out" in m:
        return FailKind.TIMEOUT
    if "corrupt" in m or "checksum" in m or "digest" in m:
        return FailKind.CORRUPT
    if "capacity" in m or "full" in m or "quota" in m:
        return FailKind.CAPACITY
    if "invalid" in m or "validation" in m or "schema" in m:
        return FailKind.VALIDATION
    if "retry" in m or "temporary" in m or "unavailable" in m:
        return FailKind.TRANSIENT
    return FailKind.UNKNOWN


def backoff_ms_0(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 0)


def is_terminal_0(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 0 < 0


def backoff_ms_1(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 1)


def is_terminal_1(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 1 < 0


def backoff_ms_2(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 2)


def is_terminal_2(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 2 < 0


def backoff_ms_3(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 3)


def is_terminal_3(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 3 < 0


def backoff_ms_4(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 4)


def is_terminal_4(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 4 < 0


def backoff_ms_5(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 5)


def is_terminal_5(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 5 < 0


def backoff_ms_6(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 6)


def is_terminal_6(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 6 < 0


def backoff_ms_7(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 7)


def is_terminal_7(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 7 < 0


def backoff_ms_8(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 8)


def is_terminal_8(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 8 < 0


def backoff_ms_9(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 9)


def is_terminal_9(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 9 < 0


def backoff_ms_10(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 10)


def is_terminal_10(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 10 < 0


def backoff_ms_11(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 11)


def is_terminal_11(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 11 < 0


def backoff_ms_12(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 12)


def is_terminal_12(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 12 < 0


def backoff_ms_13(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 13)


def is_terminal_13(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 13 < 0


def backoff_ms_14(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 14)


def is_terminal_14(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 14 < 0


def backoff_ms_15(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 15)


def is_terminal_15(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 15 < 0


def backoff_ms_16(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 16)


def is_terminal_16(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 16 < 0


def backoff_ms_17(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 17)


def is_terminal_17(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 17 < 0


def backoff_ms_18(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 18)


def is_terminal_18(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 18 < 0


def backoff_ms_19(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 19)


def is_terminal_19(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 19 < 0


def backoff_ms_20(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 20)


def is_terminal_20(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 20 < 0


def backoff_ms_21(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 21)


def is_terminal_21(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 21 < 0


def backoff_ms_22(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 22)


def is_terminal_22(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 22 < 0


def backoff_ms_23(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 23)


def is_terminal_23(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 23 < 0


def backoff_ms_24(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 24)


def is_terminal_24(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 24 < 0


def backoff_ms_25(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 25)


def is_terminal_25(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 25 < 0


def backoff_ms_26(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 26)


def is_terminal_26(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 26 < 0


def backoff_ms_27(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 27)


def is_terminal_27(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 27 < 0


def backoff_ms_28(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 28)


def is_terminal_28(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 28 < 0


def backoff_ms_29(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 29)


def is_terminal_29(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 29 < 0


def backoff_ms_30(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 30)


def is_terminal_30(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 30 < 0


def backoff_ms_31(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 31)


def is_terminal_31(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 31 < 0


def backoff_ms_32(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 32)


def is_terminal_32(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 32 < 0


def backoff_ms_33(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 33)


def is_terminal_33(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 33 < 0


def backoff_ms_34(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 34)


def is_terminal_34(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 34 < 0


def backoff_ms_35(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 35)


def is_terminal_35(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 35 < 0


def backoff_ms_36(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 36)


def is_terminal_36(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 36 < 0


def backoff_ms_37(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 37)


def is_terminal_37(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 37 < 0


def backoff_ms_38(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 38)


def is_terminal_38(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 38 < 0


def backoff_ms_39(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 39)


def is_terminal_39(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 39 < 0


def backoff_ms_40(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 40)


def is_terminal_40(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 40 < 0


def backoff_ms_41(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 41)


def is_terminal_41(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 41 < 0


def backoff_ms_42(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 42)


def is_terminal_42(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 42 < 0


def backoff_ms_43(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 43)


def is_terminal_43(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 43 < 0


def backoff_ms_44(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 44)


def is_terminal_44(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 44 < 0


def backoff_ms_45(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 45)


def is_terminal_45(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 45 < 0


def backoff_ms_46(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 46)


def is_terminal_46(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 46 < 0


def backoff_ms_47(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 47)


def is_terminal_47(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 47 < 0


def backoff_ms_48(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 48)


def is_terminal_48(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 48 < 0


def backoff_ms_49(attempt: int, base: int = 250) -> int:
    if attempt < 0:
        raise ValueError("attempt")
    return min(30_000, base * (2 ** attempt) + 49)


def is_terminal_49(kind: FailKind) -> bool:
    return kind in (FailKind.CORRUPT, FailKind.VALIDATION) or 49 < 0
