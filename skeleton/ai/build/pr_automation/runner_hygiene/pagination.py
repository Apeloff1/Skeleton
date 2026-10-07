"""Fail-closed pagination helpers for privileged inventory collection.

Incomplete, truncated, errored, or unknown pagination NEVER authorizes a
positive admission decision. Saturation remains incomplete when caps hit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Generic, Iterable, Iterator, Sequence, TypeVar

from .types import (
    Finding,
    HygienePolicy,
    HygieneVerdict,
    PaginationCursor,
    PaginationStatus,
)

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class Page(Generic[T]):
    items: tuple[T, ...]
    page_number: int
    has_next: bool


@dataclass
class PageAccumulator(Generic[T]):
    max_pages: int
    per_page: int
    items: list[T] = field(default_factory=list)
    pages_fetched: int = 0
    truncated: bool = False
    error: str | None = None
    status: PaginationStatus = PaginationStatus.UNKNOWN

    def __post_init__(self) -> None:
        if self.max_pages <= 0 or self.per_page <= 0:
            raise ValueError("pagination bounds must be positive")

    def add_page(self, page: Page[T]) -> None:
        if self.error is not None:
            return
        if self.pages_fetched >= self.max_pages:
            self.truncated = True
            self.status = PaginationStatus.TRUNCATED
            return
        if page.page_number != self.pages_fetched + 1:
            self.error = (
                f"unexpected page number {page.page_number}; "
                f"expected {self.pages_fetched + 1}"
            )
            self.status = PaginationStatus.ERROR
            return
        if len(page.items) > self.per_page:
            self.error = (
                f"page {page.page_number} returned {len(page.items)} items; "
                f"per_page={self.per_page}"
            )
            self.status = PaginationStatus.ERROR
            return
        self.items.extend(page.items)
        self.pages_fetched += 1
        if page.has_next:
            if self.pages_fetched >= self.max_pages:
                self.truncated = True
                self.status = PaginationStatus.TRUNCATED
            else:
                self.status = PaginationStatus.UNKNOWN
        else:
            if self.truncated:
                self.status = PaginationStatus.TRUNCATED
            else:
                self.status = PaginationStatus.COMPLETE

    def mark_error(self, message: str) -> None:
        self.error = message
        self.status = PaginationStatus.ERROR

    def cursor(self) -> PaginationCursor:
        return PaginationCursor(
            status=self.status,
            pages_fetched=self.pages_fetched,
            per_page=self.per_page,
            max_pages=self.max_pages,
            items_seen=len(self.items),
            truncated=self.truncated,
            error=self.error,
        )

    def result(self) -> "PagedResult[T]":
        return PagedResult(items=tuple(self.items), cursor=self.cursor())


@dataclass(frozen=True, slots=True)
class PagedResult(Generic[T]):
    items: tuple[T, ...]
    cursor: PaginationCursor

    @property
    def complete(self) -> bool:
        return self.cursor.is_complete

    def deny_reason(self) -> str | None:
        return self.cursor.deny_reason()


def accumulate_pages(
    pages: Iterable[Page[T]],
    *,
    max_pages: int,
    per_page: int,
) -> PagedResult[T]:
    acc = PageAccumulator[T](max_pages=max_pages, per_page=per_page)
    for page in pages:
        acc.add_page(page)
        if acc.status in {PaginationStatus.ERROR, PaginationStatus.TRUNCATED} and (
            acc.error or acc.truncated
        ):
            # Keep consuming only until we know we are done or capped.
            if not page.has_next or acc.truncated or acc.error:
                if acc.truncated and page.has_next:
                    break
                if acc.error:
                    break
    # If iterator ended without explicit completion and no error/truncation:
    if acc.status is PaginationStatus.UNKNOWN and acc.error is None and not acc.truncated:
        # Iterator exhausted without has_next=False on last page => incomplete
        if acc.pages_fetched == 0:
            acc.status = PaginationStatus.UNKNOWN
        else:
            # Last page must have declared has_next=False to be complete.
            # If we exit the loop naturally after a has_next=False, status is COMPLETE.
            # If the iterable simply ended mid-stream, remain UNKNOWN (fail closed).
            pass
    return acc.result()


def collect_until_complete(
    fetch_page: Callable[[int], Page[T]],
    *,
    max_pages: int,
    per_page: int,
) -> PagedResult[T]:
    """Pull pages 1..N until complete, truncated, or error. Fail closed."""
    acc = PageAccumulator[T](max_pages=max_pages, per_page=per_page)
    for page_number in range(1, max_pages + 1):
        try:
            page = fetch_page(page_number)
        except Exception as exc:  # noqa: BLE001 — boundary; convert to fail-closed
            acc.mark_error(f"page_fetch_failed:{type(exc).__name__}")
            break
        if not isinstance(page, Page):
            acc.mark_error("page_fetch_returned_non_page")
            break
        acc.add_page(page)
        if acc.error:
            break
        if acc.truncated:
            break
        if not page.has_next:
            break
    else:
        # Exhausted max_pages without has_next=False
        if acc.status is not PaginationStatus.COMPLETE:
            acc.truncated = True
            acc.status = PaginationStatus.TRUNCATED
    return acc.result()


def pagination_from_policy(policy: HygienePolicy) -> tuple[int, int]:
    return policy.max_pages, policy.per_page


def assess_pagination(
    cursor: PaginationCursor,
    *,
    fail_closed: bool = True,
) -> tuple[HygieneVerdict, tuple[Finding, ...]]:
    reason = cursor.deny_reason()
    if reason is None:
        return HygieneVerdict.ALLOW, ()
    if not fail_closed:
        # Even when callers opt into non-strict mode, UNKNOWN/ERROR still deny.
        if cursor.status in {PaginationStatus.UNKNOWN, PaginationStatus.ERROR}:
            pass
        else:
            return HygieneVerdict.HOLD, (
                Finding(
                    code=f"pagination.{reason}",
                    severity="medium",
                    message=f"pagination not complete: {reason}",
                ),
            )
    severity = "critical" if cursor.status in {PaginationStatus.UNKNOWN, PaginationStatus.ERROR} else "high"
    return HygieneVerdict.DENY, (
        Finding(
            code=f"pagination.{reason}",
            severity=severity,
            message=f"fail-closed pagination denied admission: {reason}",
        ),
    )


def merge_cursors(cursors: Sequence[PaginationCursor]) -> PaginationCursor:
    """Combine multiple inventory cursors; any incomplete dominates."""
    if not cursors:
        return PaginationCursor(
            status=PaginationStatus.UNKNOWN,
            pages_fetched=0,
            per_page=1,
            max_pages=1,
            items_seen=0,
            truncated=False,
            error="no_cursors",
        )
    pages = sum(c.pages_fetched for c in cursors)
    items = sum(c.items_seen for c in cursors)
    per_page = max(c.per_page for c in cursors)
    max_pages = max(c.max_pages for c in cursors)
    truncated = any(c.truncated or c.status is PaginationStatus.TRUNCATED for c in cursors)
    errors = [c.error for c in cursors if c.error]
    if any(c.status is PaginationStatus.ERROR for c in cursors) or errors:
        status = PaginationStatus.ERROR
        error = errors[0] if errors else "merged_error"
    elif truncated:
        status = PaginationStatus.TRUNCATED
        error = None
    elif any(c.status is PaginationStatus.UNKNOWN for c in cursors):
        status = PaginationStatus.UNKNOWN
        error = None
    elif all(c.status is PaginationStatus.COMPLETE for c in cursors):
        status = PaginationStatus.COMPLETE
        error = None
    else:
        status = PaginationStatus.UNKNOWN
        error = None
    return PaginationCursor(
        status=status,
        pages_fetched=pages,
        per_page=per_page,
        max_pages=max_pages,
        items_seen=items,
        truncated=truncated,
        error=error,
    )


def iter_complete_or_raise(result: PagedResult[T]) -> Iterator[T]:
    if not result.complete:
        raise RuntimeError(f"refusing to iterate incomplete page set: {result.deny_reason()}")
    yield from result.items


__all__ = [
    "Page",
    "PageAccumulator",
    "PagedResult",
    "accumulate_pages",
    "assess_pagination",
    "collect_until_complete",
    "iter_complete_or_raise",
    "merge_cursors",
    "pagination_from_policy",
]
