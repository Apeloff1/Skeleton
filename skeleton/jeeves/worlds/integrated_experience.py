"""One verified playable world joining cast, route, promises and private context.

This is a new opt-in integration plane; existing experience and source formats
remain unchanged. No private context note text enters the HTML or manifest.
"""
from __future__ import annotations

import base64
from hashlib import sha256
import html
import os
from typing import Any

from .bundle import _artifact_read
from .context_journal import ContextStore, compile_context, context_status
from .experience import ExperienceStore, _EXPERIENCE_JS, compile_experience
from .promises import PromiseStore, compile_promises, replay_promises
from .session import SessionStore
from .world_canon import (
    CanonError, WorldStore, _id, canonical, digest, strict_json,
)

SCHEMA = "jeeves.world.integrated_experience.v1"
RECEIPT_SCHEMA = "jeeves.world.integrated_experience_receipt.v1"

_SOURCE_SEAM = "const routeTrace = model.route.choice_trace;"
_ROOT_SEAM = 'const root = document.getElementById("play");'
_ENDING_SEAM = "  if (endings.has(scene)) {"
_ROUTE_SEAM = "  const onRoute = trace.every((id, index) => routeTrace[index] === id);"
for _seam in (_SOURCE_SEAM, _ROOT_SEAM, _ENDING_SEAM, _ROUTE_SEAM):
    if _EXPERIENCE_JS.count(_seam) != 1:
        raise RuntimeError("integrated_world_runtime_seam_changed")

_PROMISE_JS = r"""
function promiseState() {
  const opened = new Set();
  const resolved = new Set();
  for (const choiceId of trace) {
    for (const promise of model.promises.promises) {
      if (promise.trigger_choice === choiceId) {
        opened.add(promise.id);
        resolved.delete(promise.id);
      }
      if (promise.resolve_choice === choiceId && opened.has(promise.id)) {
        opened.delete(promise.id);
        resolved.add(promise.id);
      }
    }
  }
  return {opened, resolved};
}
""".strip()

_INTEGRATED_JS = _EXPERIENCE_JS.replace(
    _SOURCE_SEAM, _SOURCE_SEAM + "\nconst promiseItems = model.promises.promises;",
).replace(
    _ROOT_SEAM, _ROOT_SEAM + "\n" + _PROMISE_JS,
).replace(
    _ROUTE_SEAM,
    '  const promiseProgress = promiseState();\n'
    '  const openTitles = promiseItems.filter(p => promiseProgress.opened.has(p.id))'
    '.map(p => p.title);\n'
    '  root.append(node("p", "Open narrative promises: " + '
    '(openTitles.length ? openTitles.join(", ") : "none")));\n'
    + _ROUTE_SEAM,
).replace(
    _ENDING_SEAM,
    _ENDING_SEAM + "\n"
    '    if (promiseItems.some(p => p.required && promiseProgress.opened.has(p.id))) {\n'
    '      root.append(node("h2", "Continuity violation: unresolved required promise"));\n'
    '      return;\n'
    '    }',
)


def compile_integrated_experience(
    world: Any, cast: Any, route: Any, promises: Any, context: Any,
) -> dict[str, Any]:
    base = compile_experience(world, cast, route)
    promise_manifest = compile_promises(promises, world)
    context_manifest = compile_context(context, world)
    if (promise_manifest["world_digest"] != base["world_digest"] or
        context_manifest["world_digest"] != base["world_digest"]):
        raise CanonError("integrated_world_lease_mismatch")
    return {
        **base, "schema": SCHEMA,
        "promises_digest": digest(promises), "context_head": context["head"],
        "context_digest": digest(context),
        "promises": promise_manifest, "context": context_manifest,
        "qualification": "source_verified_not_device_or_release_certified",
    }


def render_integrated_html(manifest: Any) -> bytes:
    if type(manifest) is not dict or manifest.get("schema") != SCHEMA:
        raise CanonError("invalid_integrated_manifest")
    embedded = canonical(manifest).decode("utf-8").replace("<", "\\u003c")
    policy = base64.b64encode(sha256(_INTEGRATED_JS.encode()).digest()).decode()
    title = html.escape(manifest["world_id"], quote=True)
    page = (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; "
        f"script-src 'sha256-{policy}'; style-src 'none'; "
        "connect-src 'none'; img-src 'none'; object-src 'none'; "
        "base-uri 'none'; form-action 'none'\">"
        f"<title>{title} — integrated original world</title></head><body>"
        "<main id='play' aria-live='polite'></main>"
        f"<script id='cast-data' type='application/json'>{embedded}</script>"
        f"<script>{_INTEGRATED_JS}</script></body></html>\n"
    ).encode("utf-8")
    if len(page) > 1572864:
        raise CanonError("integrated_html_too_large")
    return page


class IntegratedExperienceStore:
    """Read all five canonical planes under one lease, publish receipt last."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.worlds = WorldStore(root)
        self.experience = ExperienceStore(root)
        self.promises = PromiseStore(root)
        self.context = ContextStore(root)

    @staticmethod
    def _names(world_id: str) -> tuple[str, str, str]:
        _id(world_id, "world_id")
        return (
            world_id + ".integrated.playable.html",
            world_id + ".integrated.manifest.json",
            world_id + ".integrated.receipt.json",
        )

    @staticmethod
    def _lock(fd: int, world_id: str) -> int:
        try:
            return os.open(world_id + ".lock",
                           os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                           0o600, dir_fd=fd)
        except FileExistsError:
            raise CanonError("lease_busy") from None

    def _sources(self, fd: int, world_id: str):
        world, cast, route = self.experience._sources(fd, world_id)
        promises = self.promises._data(fd, world_id, world)
        context = self.context._data(fd, world_id, world)
        return world, cast, route, promises, context

    def _outputs(self, world: Any, cast: Any, route: Any,
                 promises: Any, context: Any):
        manifest = compile_integrated_experience(
            world, cast, route, promises, context)
        contents = (render_integrated_html(manifest), canonical(manifest))
        if max(map(len, contents)) > 1572864:
            raise CanonError("integrated_artifact_too_large")
        names = self._names(world["id"])
        receipt = {
            "schema": RECEIPT_SCHEMA, "world_id": world["id"],
            "world_digest": digest(world), "cast_digest": digest(cast),
            "route_digest": digest(route), "promises_digest": digest(promises),
            "context_digest": digest(context), "context_head": context["head"],
            "artifacts": {
                name: sha256(content).hexdigest()
                for name, content in zip(names[:2], contents)
            },
            "qualification": "source_verified_not_release_certified",
        }
        return receipt, contents

    def compile(
        self, world_id: str, *, world_digest: str, cast_digest: str,
        route_digest: str, promises_digest: str, context_head: str,
    ) -> dict[str, Any]:
        _id(world_id, "world_id")
        fd = self.worlds._directory()
        try:
            lock_fd = self._lock(fd, world_id)
            try:
                os.close(lock_fd)
                sources = self._sources(fd, world_id)
                world, cast, route, promises, context = sources
                if (digest(world) != world_digest or
                    digest(cast) != cast_digest or
                    digest(route) != route_digest or
                    digest(promises) != promises_digest or
                    context["head"] != context_head):
                    raise CanonError("stale_integrated_source")
                receipt, contents = self._outputs(*sources)
                names = self._names(world_id)
                for name, content in zip(names[:2], contents):
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
                receipt, contents = self._outputs(*self._sources(fd, world_id))
                names = self._names(world_id)
                if strict_json(self.worlds._read(fd, names[2])) != receipt:
                    raise CanonError("integrated_receipt_mismatch")
                for name, content in zip(names[:2], contents):
                    if _artifact_read(fd, name) != content:
                        raise CanonError("integrated_artifact_mismatch", name)
                return receipt
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)

    def player(self, world_id: str, slot: str) -> dict[str, Any]:
        _id(slot, "slot")
        fd = self.worlds._directory()
        try:
            lock_fd = self._lock(fd, world_id)
            try:
                os.close(lock_fd)
                world, cast, route, promises, context = self._sources(fd, world_id)
                # Approval and all-ending closure must be re-proven on each read.
                compile_integrated_experience(world, cast, route, promises, context)
                session = SessionStore(self.worlds.root).read(world_id, slot)
                progress = replay_promises(promises, world, session["choices"])
                return {
                    "schema": "jeeves.world.integrated_player.v1",
                    "world_id": world_id, "world_digest": digest(world),
                    "session_digest": digest(session), "scene": progress["scene"],
                    "ending": progress["ending"], "promises": progress,
                    "context": context_status(context, world),
                    "qualification": "source_replay_not_device_certified",
                }
            finally:
                os.unlink(world_id + ".lock", dir_fd=fd)
        finally:
            os.close(fd)
