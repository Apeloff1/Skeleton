#!/usr/bin/env python3
"""Local/CI entry point for the canonical Skeleton cache contract."""

from skeleton.build.cache_contract import cli_main


if __name__ == "__main__":
    raise SystemExit(cli_main())
