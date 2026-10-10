"""External, signed, append-only checkpoint heads for Dragon source/Wiki custody.

Anchor files live OUTSIDE the knowledge SQLite database on a separately
secured storage volume. HMAC keys must be held by a trusted deployment secret
manager. This detects database rollback relative to a retained signed anchor;
neither local files nor HMACs alone defend against a compromised signing key
or an attacker who can delete the independent anchor root.
"""
from __future__ import annotations

from hashlib import sha256
import hmac
import json
import os
from pathlib import Path

from .contracts import canonical_digest, canonical_json
from .dragon_wisdom_pyramid import DragonWisdomPyramid, _id, _time


class DragonCustodyAnchor:
    def __init__(self, directory: Path | str, *, signing_key: bytes):
        if type(signing_key) is not bytes or len(signing_key) < 32:
            raise ValueError("independent 256-bit anchor signing key required")
        self.key = signing_key
        self.root = Path(directory)
        if not self.root.is_absolute() or not self.root.is_dir() or self.root.is_symlink():
            raise ValueError("existing separate absolute anchor directory required")

    def _path(self, owner: str) -> Path:
        return self.root / sha256(owner.encode("utf-8")).hexdigest()

    def _sig(self, body: dict) -> str:
        return hmac.new(self.key, canonical_json(body).encode("utf-8"), sha256).hexdigest()

    def _anchors(self, owner: str) -> list[dict]:
        directory = self._path(owner)
        if not directory.exists():
            return []
        if not directory.is_dir() or directory.is_symlink():
            raise ValueError("custody owner directory invalid")
        children = sorted(directory.iterdir())
        if len(children) > 10000:
            raise ValueError("anchor count exceeded")
        records = []
        previous = None
        last_sequence = -1
        for p in children:
            if (p.is_symlink() or not p.is_file() or not p.name.endswith(".json")
                    or len(p.name) != 15 or not p.name[:10].isdigit()):
                raise ValueError("unexpected or unsafe custody anchor file")
            try:
                with p.open("rb") as f:
                    raw = f.read(4097)
                if len(raw) > 4096:
                    raise ValueError("anchor size exceeded")
                data = json.loads(raw)
            except (OSError, ValueError, TypeError) as exc:
                raise ValueError("invalid custody anchor") from exc
            if not isinstance(data, dict) or set(data) != {"body", "signature"}:
                raise ValueError("malformed signed custody envelope")
            body, signature = data["body"], data["signature"]
            if not isinstance(body, dict) or not isinstance(signature, str):
                raise ValueError("invalid custody anchor shape")
            if (body.get("schema") != "skeleton.dragon.external_anchor.v1"
                    or body.get("owner_hash") != sha256(owner.encode()).hexdigest()
                    or body.get("previous_signature") != previous
                    or body.get("sequence") != int(p.name[:10])
                    or body["sequence"] <= last_sequence
                    or not hmac.compare_digest(signature, self._sig(body))
                    or canonical_json(data).encode("utf-8") != raw):
                raise ValueError("signed custody anchor lineage invalid")
            previous = signature
            last_sequence = body["sequence"]
            records.append(data)
        return records

    def verify(self, pyramid: DragonWisdomPyramid, owner: str, *, authorized: bool,
               require_current: bool = True) -> dict:
        if authorized is not True:
            raise PermissionError("authenticated anchor verification required")
        if not isinstance(pyramid, DragonWisdomPyramid):
            raise TypeError("canonical Wiki journal required")
        _id(owner)
        rows = pyramid._history(owner)
        anchors = self._anchors(owner)
        if not anchors:
            if rows:
                raise ValueError("nonempty journal has no independent signed anchor")
            return {"anchored": False, "sequence": None, "current": False}
        for envelope in anchors:
            body = envelope["body"]
            sequence = body["sequence"]
            if sequence >= len(rows) or rows[sequence]["digest"] != body["head_digest"]:
                raise ValueError("database rollback or journal rewrite detected")
        final = anchors[-1]["body"]
        current = bool(rows and final["sequence"] == len(rows) - 1
                       and final["knowledge_root"] ==
                           pyramid.library.snapshot_root(owner, authorized=True))
        if require_current and not current:
            raise ValueError("latest journal/source root not externally anchored")
        return {
            "anchored": True, "sequence": final["sequence"],
            "current": current, "head_digest": final["head_digest"],
            "anchor_signature": anchors[-1]["signature"],
        }

    def checkpoint(self, pyramid: DragonWisdomPyramid, owner: str, *,
                   now: int, authorized: bool, trusted_worker: bool,
                   allow_initial_bootstrap: bool = False) -> dict:
        if authorized is not True or trusted_worker is not True:
            raise PermissionError("independent custody signer required")
        _id(owner); _time(now)
        if allow_initial_bootstrap is not True and allow_initial_bootstrap is not False:
            raise ValueError("explicit bootstrap policy required")
        # Caller serializes owner checkpoint writes with the Wiki worker. The
        # write is create-only, so concurrent competing heads fail closed.
        rows = pyramid._history(owner)
        if not rows:
            raise ValueError("cannot anchor empty Wiki journal")
        prior = self._anchors(owner)
        if not prior and not allow_initial_bootstrap:
            raise PermissionError("first anchor requires separate migration approval")
        for envelope in prior:
            body = envelope["body"]
            if body["sequence"] >= len(rows) or rows[body["sequence"]]["digest"] != body["head_digest"]:
                raise ValueError("existing external anchor contradicts live journal")
        last = prior[-1] if prior else None
        root = pyramid.library.snapshot_root(owner, authorized=True)
        if last and last["body"]["sequence"] == len(rows)-1:
            if last["body"]["knowledge_root"] != root:
                raise ValueError("root changed without new journal event")
            return last
        if last and now < last["body"]["at"]:
            raise ValueError("anchor clock reversal")
        body = {
            "schema": "skeleton.dragon.external_anchor.v1",
            "owner_hash": sha256(owner.encode()).hexdigest(),
            "sequence": len(rows)-1, "head_digest": rows[-1]["digest"],
            "knowledge_root": root, "at": now,
            "previous_signature": last["signature"] if last else None,
        }
        output = {"body": body, "signature": self._sig(body)}
        raw = canonical_json(output).encode("utf-8")
        target_dir = self._path(owner)
        if target_dir.exists() and target_dir.is_symlink():
            raise ValueError("unsafe custody directory")
        target_dir.mkdir(mode=0o700, exist_ok=True)
        dest = target_dir / f"{body['sequence']:010}.json"
        fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
        except Exception:
            raise
        # fsync the owning directory to durably commit filename creation.
        directory_fd = os.open(target_dir, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return output
