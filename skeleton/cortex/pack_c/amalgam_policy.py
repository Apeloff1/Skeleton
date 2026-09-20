"""Amalgam policy — unfitted → kind=own; fitted → own-lm with sigil survival."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple


@dataclass(frozen=True)
class AmalgamDecision:
    kind: str
    text: str
    tags: Tuple[str, ...]
    numbers: Tuple[float, ...] = ()
    confidence: float = 0.5
    decoded: bool = False
    policy: str = "pack_c.v1"

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "text": self.text,
            "tags": list(self.tags),
            "numbers": list(self.numbers),
            "confidence": self.confidence,
            "decoded": self.decoded,
            "policy": self.policy,
        }


@dataclass
class AmalgamPolicy:
    """Encode neo amalgam invariants without mutating neocortex in-place.

    Callers may mirror `_lm_amalgam` behavior via :meth:`decide`.
    """

    unfitted_kind: str = "own"
    fitted_kind: str = "own-lm"
    require_no_lm_tag_when_unfitted: bool = True
    sigil_separator: str = " || "

    def fitted_count(self, lm: Any) -> int:
        if lm is None:
            return 0
        return int(getattr(lm, "fitted", 0) or 0)

    def decide(
        self,
        *,
        lm: Any,
        composed_text: str = "",
        composed_tags: Sequence[str] = (),
        composed_numbers: Sequence[float] = (),
        jaccard: float = 0.0,
        decoded_text: str = "",
        mouth_name: str = "neo",
    ) -> AmalgamDecision:
        fitted = self.fitted_count(lm)
        if fitted <= 0:
            tags = tuple(dict.fromkeys(list(composed_tags) + ["own", "surpass", mouth_name]))
            if self.require_no_lm_tag_when_unfitted:
                tags = tuple(t for t in tags if t != "lm")
            return AmalgamDecision(
                kind=self.unfitted_kind,
                text=composed_text or "",
                tags=tags,
                numbers=tuple(float(x) for x in composed_numbers),
                confidence=min(1.0, 0.5 + 0.3 * float(jaccard or 0.0)),
                decoded=False,
            )
        gen = decoded_text or ""
        body = (
            f"{gen}{self.sigil_separator}{composed_text}"
            if (gen or composed_text)
            else (gen or composed_text or "")
        )
        tags = tuple(
            dict.fromkeys(list(composed_tags) + ["lm", "neo", "own", "surpass", mouth_name])
        )
        return AmalgamDecision(
            kind=self.fitted_kind,
            text=body,
            tags=tags,
            numbers=tuple(float(x) for x in composed_numbers),
            confidence=min(1.0, 0.58 + 0.35 * float(jaccard or 0.0)),
            decoded=True,
        )


_DEFAULT = AmalgamPolicy()


def decide_amalgam(**kwargs: Any) -> AmalgamDecision:
    return _DEFAULT.decide(**kwargs)


def assert_unfitted_invariants(decision: AmalgamDecision) -> None:
    assert decision.kind == "own", decision.kind
    assert decision.kind != "own-lm"
    assert "lm" not in decision.tags
    assert decision.decoded is False


def assert_fitted_invariants(decision: AmalgamDecision) -> None:
    assert decision.kind == "own-lm"
    assert "lm" in decision.tags
    assert decision.decoded is True


# Bulk policy matrix for deterministic audits (structured, not noise).
POLICY_MATRIX: Tuple[Mapping[str, Any], ...] = tuple(
    {
        "id": f"amalgam-case-{i:04d}",
        "fitted": i % 7,
        "jaccard": round((i % 10) / 10.0, 3),
        "expect_kind": "own" if (i % 7) == 0 else "own-lm",
        "mouth": ("neo", "left", "right", "pfc")[i % 4],
        "composed": f"tape-{i:04d}",
    }
    for i in range(1, 401)
)


def evaluate_matrix(policy: Optional[AmalgamPolicy] = None) -> list[dict[str, Any]]:
    pol = policy or _DEFAULT

    class _LM:
        def __init__(self, fitted: int) -> None:
            self.fitted = fitted

    out: list[dict[str, Any]] = []
    for row in POLICY_MATRIX:
        d = pol.decide(
            lm=_LM(int(row["fitted"])),
            composed_text=str(row["composed"]),
            jaccard=float(row["jaccard"]),
            decoded_text=f"gen-{row['id']}" if int(row["fitted"]) > 0 else "",
            mouth_name=str(row["mouth"]),
        )
        out.append(
            {
                "id": row["id"],
                "kind": d.kind,
                "expect": row["expect_kind"],
                "ok": d.kind == row["expect_kind"],
                "tags": d.tags,
            }
        )
    return out
