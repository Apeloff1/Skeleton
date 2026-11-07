"""Sign-out sequencing (port of ``sign-out-plan.mjs``), asyncio flavoured.

* Live preview: session rides a bearer token; dropping it IS signing out, so the
  server call is best effort and a wedged request must never strand the user.
* Deployed: session rides an HttpOnly cookie only the server can clear. A timed
  out or failed sign-out raises rather than pretending the user is signed out.
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Awaitable, Callable, Literal, Union

PREVIEW_SIGN_OUT_TIMEOUT_S = 1.5
DEPLOYED_SIGN_OUT_TIMEOUT_S = 10.0

Outcome = Literal["ok", "failed", "timeout"]
Starter = Callable[[], Union[Awaitable[Any], Any]]


class SignOutError(RuntimeError):
    def __init__(self, outcome: Outcome):
        self.outcome = outcome
        what = "timed out" if outcome == "timeout" else "failed"
        super().__init__(f"Sign-out {what}; you are still signed in. Please try again.")


def sign_out_timeout_s(live_preview: bool) -> float:
    return PREVIEW_SIGN_OUT_TIMEOUT_S if live_preview else DEPLOYED_SIGN_OUT_TIMEOUT_S


async def settle_within(start: Starter, timeout_s: float) -> Outcome:
    """Run ``start`` but give up after ``timeout_s``. Never raises."""
    try:
        result = start()
    except Exception:
        return "failed"
    if not inspect.isawaitable(result):
        return "ok"
    task = asyncio.ensure_future(result)
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout_s)
    except asyncio.TimeoutError:
        task.add_done_callback(lambda t: t.cancelled() or t.exception())
        return "timeout"
    except Exception:
        return "failed"
    return "ok"


async def run_sign_out(
    *,
    live_preview: bool,
    has_bearer: bool,
    request_sign_out: Starter,
    clear_token: Callable[[], None],
    redirect: Callable[[], None],
    timeout_s: float | None = None,
) -> Outcome | None:
    """End the session then clear + redirect. Returns the server outcome (or None
    when no request was needed). Raises :class:`SignOutError` when deployed and
    the server did not confirm."""
    t = sign_out_timeout_s(live_preview) if timeout_s is None else timeout_s
    if live_preview:
        outcome: Outcome | None = (
            await settle_within(request_sign_out, t) if has_bearer else None
        )
        clear_token()
        redirect()
        return outcome
    outcome = await settle_within(request_sign_out, t)
    if outcome != "ok":
        raise SignOutError(outcome)
    clear_token()
    redirect()
    return outcome


async def run_pre_sign_in_sign_out(
    *,
    live_preview: bool,
    has_bearer: bool,
    request_sign_out: Starter,
    clear_token: Callable[[], None],
    timeout_s: float | None = None,
) -> Outcome | None:
    """Best-effort drop of any prior session before a new sign-in. Never raises."""
    outcome: Outcome | None = None
    if has_bearer or not live_preview:
        t = sign_out_timeout_s(live_preview) if timeout_s is None else timeout_s
        outcome = await settle_within(request_sign_out, t)
    clear_token()
    return outcome
