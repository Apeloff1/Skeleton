"""Headless JSON-stdin operator interface for real GGUF/SQLite source campaigns.

Review is read-only. Run requires exact manifest plus three independent
operator flags; verify is cold, read-only and never reissues model work.
"""
from __future__ import annotations

import argparse
import sys
from typing import BinaryIO, TextIO, Callable

from .desktop_client import DesktopBridge
from .desktop_native_campaign import (
    MAX_REQUEST_BYTES, MAX_OUTPUT_BYTES, NativeCampaignHold,
    parse_campaign, execute_campaign_request,
)
from .desktop_workspace import _canonical


class _PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, _message):
        raise NativeCampaignHold("unsupported private campaign CLI options")


def main(
    argv: list[str] | None = None, *,
    stdin: BinaryIO | None = None, stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    bridge_factory: Callable[..., DesktopBridge] = DesktopBridge,
) -> int:
    parser = _PrivateArgumentParser(
        prog="jeeves-native-campaign",
        description="Bounded serial local GGUF + SQLite source work; private receipt only",
    )
    parser.add_argument("--approve-campaign", action="store_true")
    parser.add_argument("--approve-native", action="store_true")
    parser.add_argument("--approve-private-storage", action="store_true")
    inp = stdin if stdin is not None else sys.stdin.buffer
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr
    try:
        options = parser.parse_args(argv)
        raw = inp.read(MAX_REQUEST_BYTES + 1)
        _, req = parse_campaign(raw)
        result = execute_campaign_request(
            req,
            approve_campaign=options.approve_campaign,
            approve_native=options.approve_native,
            approve_private_storage=options.approve_private_storage,
            bridge_factory=bridge_factory,
        )
        encoded = _canonical(result)
        if len(encoded) > MAX_OUTPUT_BYTES:
            raise NativeCampaignHold("bounded public campaign receipt exceeded")
        out.write(encoded.decode("utf-8", "strict") + "\n")
        return 0 if "held" not in result.get("status", "") else 2
    except (Exception, KeyboardInterrupt):
        err.write("JEEVES_NATIVE_CAMPAIGN_HELD_NO_AUTOMATIC_RETRY\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["main"]
