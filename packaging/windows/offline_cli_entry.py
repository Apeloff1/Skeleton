"""Console entrypoint for the frozen Skeleton runtime.

The internal readiness worker is dispatched before loading the offline
inference interface; the normal public console remains offline-only.
"""
import sys


if __name__ == "__main__":
    if sys.argv[1:2] == ["--internal-install-probe-v1"]:
        from skeleton.app.install_probe_worker import main
        raise SystemExit(main(sys.argv[1:]))
    from skeleton.app.offline_cli import main
    raise SystemExit(main())
