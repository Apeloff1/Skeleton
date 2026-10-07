"""PyInstaller entrypoint for the Windows Skeleton launcher."""

from skeleton.app.windows_launcher import main

if __name__ == "__main__":
    raise SystemExit(main())
