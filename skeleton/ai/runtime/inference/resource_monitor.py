"""Offline, payload-free resource monitoring using the canonical local sampler."""
from __future__ import annotations

import argparse
from collections.abc import Callable, Iterator, Sequence
from hashlib import sha256
import json
import math
import time
from typing import Any

from .adaptive_serving import AdaptiveServingController, ServingResources
from .local import sample_serving_resources


class ResourceMonitorError(ValueError):
    """Monitor configuration or measured resource contract is invalid."""


def _validate(count: int, interval_seconds: float, operator_max: int) -> None:
    if type(count) is not int or not 1 <= count <= 1000:
        raise ResourceMonitorError("sample count must be 1..1000")
    if (isinstance(interval_seconds, bool) or not isinstance(interval_seconds, (int, float))
            or not math.isfinite(interval_seconds) or not 0 <= interval_seconds <= 60):
        raise ResourceMonitorError("interval must be finite within 0..60 seconds")
    if type(operator_max) is not int or not 1 <= operator_max <= 64:
        raise ResourceMonitorError("operator concurrency must be 1..64")


def monitor_resources(
    *,
    count: int,
    interval_seconds: float,
    operator_max: int,
    sample: Callable[[], ServingResources] = sample_serving_resources,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> Iterator[dict[str, Any]]:
    """Produce bounded deterministic receipts, never prompts or model payloads."""
    _validate(count, interval_seconds, operator_max)
    if not callable(sample) or not callable(clock) or not callable(sleep):
        raise ResourceMonitorError("monitor requires callable sampler/clock/sleep")
    controller = AdaptiveServingController(operator_max)
    for index in range(count):
        measured = sample()
        if not isinstance(measured, ServingResources):
            raise ResourceMonitorError("sampler returned noncanonical resource data")
        now = clock()
        if isinstance(now, bool) or not isinstance(now, (int, float)) or not math.isfinite(now) or now < 0:
            raise ResourceMonitorError("invalid monotonic sample time")
        controller.update(measured, now=now, queued=1)
        body: dict[str, Any] = {
            "schema": "skeleton.ai.local-resource-monitor.v1",
            "sequence": index,
            "resource": measured.as_dict(),
            "pressure": controller.pressure_snapshot(),
            "effective_concurrency": controller.effective_concurrency,
            "background_limit": controller.background_limit,
            "operator_max": operator_max,
            "hardware_qualification": "not_assessed",
        }
        body["digest"] = sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        ).hexdigest()
        yield body
        if index + 1 < count:
            sleep(interval_seconds)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect native offline AI resource pressure")
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--operator-max", type=int, default=4)
    args = parser.parse_args(argv)
    try:
        for receipt in monitor_resources(
            count=args.count, interval_seconds=args.interval, operator_max=args.operator_max
        ):
            print(json.dumps(receipt, sort_keys=True, separators=(",", ":"), allow_nan=False))
    except (ResourceMonitorError, KeyboardInterrupt) as exc:
        if isinstance(exc, KeyboardInterrupt):
            return 130
        parser.exit(2, "resource monitor unavailable: " + str(exc) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
