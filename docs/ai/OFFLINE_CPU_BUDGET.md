# Offline CPU topology and worker budgeting — Studio C

Run the installed package without any provider or model download:

    python -m skeleton.app.offline_cpu_budget --max-workers 8 --memory-per-worker-mib 256 --memory-reserve-mib 512

The command reads actual OS evidence where available. Linux uses process
affinity, sysfs physical-core/L3 data, cgroup CPU quota, procfs MemAvailable
and cgroup-v2 memory ceilings. macOS uses bounded sysctl queries for physical
cores and L3; it reports memory availability as unknown rather than inventing
free RAM. Windows uses GlobalMemoryStatusEx for RAM and os.cpu_count as a
clearly labeled logical-count fallback. GPU/Metal/CUDA/WDDM memory is NOT
inferred from CPU topology.

The deterministic planner reserves interactive CPU capacity, enforces a
per-worker memory estimate and a physical available-memory reserve, and
reduces concurrency on unknown or elevated thermal input. Critical thermal
input denies background workers. The thermal CLI value is an OPERATOR HINT,
not a measured hardware sensor. Callers must enforce the returned worker
count; this utility does not start threads or alter OS resource controls.

If available RAM cannot be measured, parallel background work is limited
to one worker. If CPU or memory reserve is exhausted, the result may be
zero workers. Every plan includes explicit evidence source labels and a
stable SHA-256 decision receipt. No unsupported platform feature is
advertised as qualified.

Focused canonical tests:

    python -m pytest -q --noconftest skeleton/testing/test_offline_cpu_budget.py
