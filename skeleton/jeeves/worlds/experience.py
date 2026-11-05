"""Single playable handoff joining canonical world, reviewed NPC cast and route.

A world route witness and authored NPC dialogue share the same actual player
choice state. The source digests are verified together under one world lock;
cross-source drift cannot silently publish an apparently playable artifact.
"""
from __future__ import annotations

import base64
from hashlib import sha256
import html
import os
from typing import Any

from .bundle import _artifact_read
from .cast import CastStore, _PLAYER_JS as _CAST_JS, compile_cast
from .route import RouteStore, compile_route
from .world_canon import (
    CanonError, WorldStore, _id, canonical, digest, prove, strict_json,
)

SCHEMA = "jeeves.world.experience.v1"
RECEIPT_SCHEMA = "jeeves.world.experience_receipt.v1"

_ROUTE_SEAM = '  root.append(node("p", "Choices: " + trace.join(", ")));'
_ROUTE_HINT = """
  root.append(node("p", "Choices: " + trace.join(", ")));
  const onRoute = trace.every((id, index) => routeTrace[index] === id);
  if (onRoute && routeTrace[trace.length]) {
    root.append(node("p", "Reviewed route next choice: " + routeTrace[trace.length]));
  } else if (!onRoute) {
    root.append(node("p", "You have left the reviewed route. Other authored paths remain playable."));
  }
""".rstrip()
if _CAST_JS.count(_ROUTE_SEAM) != 1 or _CAST_JS.count("const cast = model.cast;") != 1:
    raise RuntimeError("canonical_cast_runtime_seam_changed")
_EXPERIENCE_JS = _CAST_JS.replace(
    "const cast = model.cast;",
    "const cast = model.cast;\nconst routeTrace = model.route.choice_trace;",
).replace(_ROUTE_SEAM, _ROUTE_HINT)


def compile_experience(world: Any, cast: Any, route: Any) -> dict[str, Any]:
    proof = prove(world)
    cast_manifest = compile_cast(cast, world)
    route_manifest = compile_route(route, world)
    if (cast_manifest["world_digest"] != proof.source_digest or
        route_manifest["world_digest"] != proof.source_digest):
        raise CanonError("experience_source_lease_mismatch")
    return {
        "schema": SCHEMA,
        "world_id": world["id"],
        "world_digest": proof.source_digest,
        "cast_digest": digest(cast),
        "route_digest": digest(route),
        "world": world, "cast": cast, "route": route_manifest,
        "world_proof": proof.as_dict(),
        "qualification": "operator_approved_not_release_certified",
    }


def render_experience_html(manifest: Any) -> bytes:
    if manifest.get("schema") != SCHEMA:
        raise CanonError("invalid_experience_manifest")
    embedded = canonical(manifest).decode("utf-8").replace("<", "\\u003c")
    policy_hash = base64.b64encode(
        sha256(_EXPERIENCE_JS.encode("utf-8")).digest()).decode()
    title = html.escape(manifest["world_id"], quote=True)
    markup = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; "
        f"script-src 'sha256-{policy_hash}'; style-src 'none'; "
        "connect-src 'none'; img-src 'none'; base-uri 'none'; form-action 'none'\">"
        f"<title>{title} — reviewed world experience</title></head><body>"
        "<main id='play' aria-live='polite'></main>"
        f"<script id='cast-data' type='application/json'>{embedded}</script>"
        f"<script>{_EXPERIENCE_JS}</script></body></html>\n"
    )
    return markup.encode("utf-8")


class ExperienceStore:
    """Atomic-source-read, receipt-bound compile and independent byte verification."""
    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)
        self.cast = CastStore(root)
        self.route = RouteStore(root)

    @staticmethod
    def _names(world_id: str) -> tuple[str, str, str]:
        _id(world_id, "world_id")
        return (world_id + ".experience.playable.html",
                world_id + ".experience.manifest.json",
                world_id + ".experience.receipt.json")

    def _sources(self, fd: int, world_id: str):
        world = self.cast._world(fd, world_id)
        cast = self.cast._cast(fd, world_id, world)
        route = self.route._read_spec(fd, world_id, world)
        return world, cast, route

    def _lock(self, fd: int, world_id: str) -> int:
        _id(world_id, "world_id")
        try:
            return os.open(world_id + ".lock", os.O_WRONLY | os.O_CREAT |
                           os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        except FileExistsError:
            raise CanonError("lease_busy") from None

    def _outputs(self, world: Any, cast: Any, route: Any):
        manifest = compile_experience(world, cast, route)
        artifacts = [render_experience_html(manifest), canonical(manifest)]
        names = self._names(world["id"])
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": world["id"],
            "world_digest": digest(world), "cast_digest": digest(cast),
            "route_digest": digest(route),
            "artifacts": {
                name: sha256(content).hexdigest()
                for name, content in zip(names[:2], artifacts)
            },
            "qualification": "reviewed_source_only_not_release_certified",
        }
        return receipt, artifacts

    def compile(self, world_id: str, *, world_digest: str,
                cast_digest: str, route_digest: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            lock_fd = self._lock(fd, world_id)
            try:
                os.close(lock_fd)
                world, cast, route = self._sources(fd, world_id)
                if (digest(world) != world_digest or
                    digest(cast) != cast_digest or
                    digest(route) != route_digest):
                    raise CanonError("stale_experience_source")
                receipt, artifacts = self._outputs(world, cast, route)
                names = self._names(world_id)
                for name, content in zip(names[:2], artifacts):
                    self.worlds._write(fd, name, content)
                self.worlds._write(fd, names[2], canonical(receipt))
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def verify(self, world_id: str) -> dict[str, Any]:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            lock_fd = self._lock(fd, world_id)
            try:
                os.close(lock_fd)
                world, cast, route = self._sources(fd, world_id)
                expected, artifacts = self._outputs(world, cast, route)
                names = self._names(world_id)
                actual = strict_json(self.worlds._read(fd, names[2]))
                if actual != expected:
                    raise CanonError("experience_receipt_mismatch")
                for name, content in zip(names[:2], artifacts):
                    if _artifact_read(fd, name) != content:
                        raise CanonError("experience_artifact_mismatch", name)
                return expected
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
