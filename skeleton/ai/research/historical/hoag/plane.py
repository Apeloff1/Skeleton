"""12 region cards. Warp extract-once. Bind mouth/body."""

from __future__ import annotations

from skeleton.hoag.cards import hoag_card
from skeleton.hoag.law import REGION_N, REGIONS


def region_cards() -> list[dict]:
    return [
        hoag_card(kind="region", hit=1, law="12 regions", extra={"region": name, "i": i})
        for i, name in enumerate(REGIONS)
    ]


class Warp:
    def __init__(self) -> None:
        self.extracted = 0

    def extract(self, payload: str) -> dict:
        if self.extracted:
            return hoag_card(
                kind="warp",
                hit=1,
                law="extract-once",
                extra={"once": 1, "skipped": 1, "payload": ""},
            )
        self.extracted = 1
        return hoag_card(
            kind="warp",
            hit=1,
            law="extract-once",
            extra={"once": 1, "skipped": 0, "payload": payload},
        )


def bind_mouth_body(mouth: str, body: str) -> dict:
    return hoag_card(
        kind="bind",
        hit=1,
        law="bind mouth/body",
        extra={"mouth": mouth, "body": body, "bound": 1},
    )


def plane_ok() -> bool:
    cards = region_cards()
    return len(cards) == REGION_N and cards[0]["region"] == "mouth" and cards[1]["region"] == "body"
