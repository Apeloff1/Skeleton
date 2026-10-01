#!/usr/bin/env python3
"""Live-but-non-activating PyMongo Async qualification for the P2 spine."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

from skeleton.deploy.spine_pymongo_async import SpinePyMongoAsyncAdapter
from skeleton.persistence.spine_motor_bootstrap import SpineMotorBootstrap
from skeleton.persistence.spine_motor_bootstrap_replay import SpineMotorBootstrapReplay
from skeleton.persistence.spine_motor_bootstrap_verify import SpineMotorBootstrapVerify
from skeleton.persistence.spine_motor_plan import SpineMotorPlan
from skeleton.persistence.spine_motor_preflight import SpineMotorPreflight
from skeleton.persistence.spine_motor_preflight_verify import SpineMotorPreflightVerify


class SpinePyMongoAsyncQualificationError(RuntimeError):
    """Live async-driver qualification failed closed."""


def _digest(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


async def qualify(*, uri: str, database_name: str) -> dict[str, Any]:
    adapter = SpinePyMongoAsyncAdapter()
    session = adapter.open(uri=uri, database_name=database_name)
    try:
        plan = SpineMotorPlan().card()
        preflight = await SpineMotorPreflight().probe(session.database)
        preflight_verified = SpineMotorPreflightVerify().verify(preflight)
        collections = {
            row["collection"]: session.database.get_collection(row["collection"])
            for row in plan["indexes"]
        }
        bootstrapper = SpineMotorBootstrap()
        first = await bootstrapper.apply(collections)
        first_verified = SpineMotorBootstrapVerify().verify(first)
        second = await bootstrapper.apply(collections)
        replay = SpineMotorBootstrapReplay().card(first=first, second=second)

        if not preflight_verified["verified"]:
            raise SpinePyMongoAsyncQualificationError("preflight verification failed")
        if not first_verified["verified"]:
            raise SpinePyMongoAsyncQualificationError("bootstrap verification failed")
        if not replay["equivalent"]:
            raise SpinePyMongoAsyncQualificationError("bootstrap replay changed")

        evidence = {
            "driver_receipt_digest": session.receipt["digest"],
            "driver_distribution": session.receipt["driver_distribution"],
            "driver_version": session.receipt["driver_version"],
            "driver_class": session.receipt["driver_class"],
            "plan_digest": plan["digest"],
            "preflight_digest": preflight["digest"],
            "wire_version_min": preflight["min_wire_version"],
            "wire_version_max": preflight["max_wire_version"],
            "indexes_planned": first["planned"],
            "indexes_applied": first["applied"],
            "bootstrap_replay_equivalent": replay["equivalent"],
            "supported_async_driver": True,
            "deployment_driver_imported": True,
            "deployment_driver_connected": True,
            "core_driver_imported": False,
            "runtime_driver_selected": False,
            "runtime_activated": False,
            "live_motor": False,
        }
        return {
            "schema_version": 1,
            "kind": "spine_pymongo_async_live_qualification",
            "law": "live-driver-qualification-is-not-runtime-activation",
            **evidence,
            "digest": _digest(evidence),
            "qualified": True,
            "completion_checkbox": False,
            "implementation_signature": False,
            "verification_signature": False,
        }
    finally:
        try:
            await session.client.drop_database(database_name)
        finally:
            await session.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--uri", required=True)
    parser.add_argument("--database", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = asyncio.run(qualify(uri=args.uri, database_name=args.database))
    except Exception as exc:
        print(json.dumps({"qualified": False, "error": str(exc)}, sort_keys=True))
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
