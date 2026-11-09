"""Admit path for the volume census. Corrected sum only."""

from __future__ import annotations

from skeleton.ai.volume_census import admit, claimed_lines


def run() -> dict[str, object]:
    return admit(claimed_lines())


if __name__ == "__main__":
    print(run())
