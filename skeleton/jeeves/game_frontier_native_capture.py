"""Ingest *observed* Godot physics samples into GDD verified frame journal.

The Godot 4 exporter writes opt-in fixed-tick JSONL samples after the native
rigid-body solver advances. This importer verifies schema, source scene,
actor/asset allow-list, monotonic capture clocks and physically plausible
motion, then delegates to the canonical FrameReceiptJournal for atomic
frame/evidence/native-source commit. A file is evidence of reported runtime
observations, NOT remote hardware attestation or a rendered-pixel proof.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Mapping, Iterable

from .game_frontier_frame_coherence import FrameObject
from .game_frontier_production import Vec3
from .game_frontier_receipt_journal import FrameReceiptJournal, FrameJournalError


class NativeObservationError(ValueError):
    pass


def _triplet(data: object, name: str) -> Vec3:
    if (not isinstance(data,list) or len(data)!=3 or
        any(type(v) not in (int,float) or not math.isfinite(v)
            or abs(v)>1e8 for v in data)):
        raise NativeObservationError(f"{name}: finite native XYZ required")
    return Vec3(*[float(v) for v in data])


class GodotPhysicsCaptureIngestor:
    """Validated sample bridge to durable engine-neutral chunk receipts.

    Allowed asset IDs come from the authorized GDD/scene owner, never from
    the untrusted observation file.
    """

    def __init__(
        self, journal: FrameReceiptJournal, *,
        candidate_digest: str,
        allowed_assets: Mapping[str,str],
        max_samples: int = 1_000_000,
    ) -> None:
        if not isinstance(journal,FrameReceiptJournal):
            raise NativeObservationError("durable canonical frame journal required")
        if (type(candidate_digest) is not str or len(candidate_digest)!=64 or
            any(c not in "0123456789abcdef" for c in candidate_digest)):
            raise NativeObservationError("qualified scene candidate digest required")
        if (not isinstance(allowed_assets,Mapping) or
            not 1<=len(allowed_assets)<=256 or
            any(type(k) is not str or not k or len(k)>128 or
                type(v) is not str or len(v)!=64 or
                any(c not in "0123456789abcdef" for c in v)
                for k,v in allowed_assets.items())):
            raise NativeObservationError("signed source actor asset digest catalog required")
        if type(max_samples) is not int or not 1<=max_samples<=10_000_000:
            raise NativeObservationError("bounded native ingestion budget required")
        self.journal=journal
        self.candidate_digest=candidate_digest
        self.assets=dict(allowed_assets)
        self.max_samples=max_samples

    def ingest(self, native: Mapping) -> dict:
        if not isinstance(native,Mapping):
            raise NativeObservationError("typed Godot runtime sample required")
        head=self.journal.stats()["head"]
        if head+1>=self.max_samples:
            raise NativeObservationError("native capture ingestion budget exhausted")
        if (native.get("schema")!="skeleton.game.native_physics_observation.v1" or
            native.get("native_engine")!="godot4_physics" or
            native.get("authority")!="untrusted_native_candidate_observation_not_attested" or
            native.get("scene_candidate_digest")!=self.candidate_digest or
            native.get("signed_gdd_digest")!=self.journal.gdd.source_digest or
            type(native.get("native_tick")) is not int or
            native["native_tick"]!=head+1 or
            type(native.get("ticks_usec")) is not int or
            native["ticks_usec"]<0 or
            native.get("fps") not in (30,50,60,120)):
            raise NativeObservationError("native source/schema/FPS/tick does not match journal")
        prior=self.journal.native_sample(head) if head>=0 else None
        if prior is not None:
            if (native["ticks_usec"]<=prior["ticks_usec"] or
                native["scene_candidate_digest"]!=prior["scene_candidate_digest"]):
                raise NativeObservationError("native fixed-tick clock or scene regressed")
        submitted=native.get("actors")
        if not isinstance(submitted,list) or len(submitted)!=len(self.assets):
            raise NativeObservationError("all authorized source actors must be observed")
        actual={}
        for item in submitted:
            if not isinstance(item,Mapping):
                raise NativeObservationError("native actor object required")
            key=item.get("id")
            if key not in self.assets or key in actual or (
                item.get("source_digest")!=self.assets[key]):
                raise NativeObservationError("unknown, duplicate, or remapped native actor")
            xyz=_triplet(item.get("world_xyz_m"),"native world position")
            velocity=_triplet(item.get("velocity_xyz_mps"),"native velocity")
            actual[key]=FrameObject(key,xyz,velocity,self.assets[key])
        if len(actual)!=len(self.assets):
            raise NativeObservationError("native capture actor set incomplete")
        try:
            return self.journal.advance(
                tuple(actual[k] for k in sorted(actual)),
                fps=native["fps"],native_capture=dict(native))
        except (FrameJournalError,ValueError) as exc:
            raise NativeObservationError("Godot fixed-step source failed dual frame/chunk checks") from exc

    def ingest_jsonl(self, lines: Iterable[str], *,
                     max_bytes_per_line: int = 128*1024) -> tuple[dict,...]:
        results=[]
        for line in lines:
            if (type(line) is not str or
                len(line.encode("utf-8"))>max_bytes_per_line):
                raise NativeObservationError("bounded UTF-8 native JSONL required")
            try:
                record=json.loads(line)
            except (TypeError,ValueError) as exc:
                raise NativeObservationError("malformed Godot sample line") from exc
            results.append(self.ingest(record))
        return tuple(results)

    def ingest_file(self, path: str | Path) -> tuple[dict,...]:
        """Stream from an explicitly selected file; never invoke device GPS."""
        selected=Path(path)
        if not selected.is_file() or selected.is_symlink():
            raise NativeObservationError("regular Godot capture file required")
        with selected.open("r",encoding="utf-8") as source:
            return self.ingest_jsonl(source)
