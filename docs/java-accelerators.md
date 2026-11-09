# Optional Java accelerators

Skeleton stays Python-first. The Java code in `java-accelerators/` is a set
of optional batch kernels for workloads where moving a bounded block of numeric
data to a warm JVM can be useful.

The design rule is simple:

> Java may accelerate computation. It does not become the owner of application
> state, policy, identity, metadata, model behavior, or orchestration.

That rule keeps the normal Python runtime understandable and keeps every Java
path removable: if Java is missing, slow, rejected by policy, or returns a
protocol error, the existing Python implementation remains the fallback.

## Current accelerators

### Observability batches

Source:

- `java-accelerators/observability/AcceleratorMain.java`
- `skeleton/observability/jvm_accelerator.py`

Python integration:

- `MetricsCollector` can offload large histogram snapshot batches.
- the canonical `skeleton.observability.anomaly.AnomalyDetector` can offload
  large batches for its statistical strategy.
- the older detector in `skeleton.observability.metrics` has a compatible
  batch fast path as well.

Java does not own:

- counters or gauges;
- histogram retention;
- anomaly detector configuration;
- event bus emission;
- adaptive threshold state;
- seasonal decomposition state.

Adaptive and seasonal detection stay in Python because moving those evolving
state machines into a helper would duplicate domain behavior rather than merely
accelerate arithmetic.

### Dense vector top-K

Source:

- `java-accelerators/vector/VectorSearchMain.java`
- `skeleton/memory/jvm_vector_accelerator.py`

Python integration:

- `skeleton.memory.vector.VectorStore` can offload a sufficiently large
  candidate batch after Python has already applied metadata filters.
- `VectorStore.query_many()` can send one candidate matrix once and score
  multiple query vectors against it in one bounded JVM request.

Java receives:

- one query vector, or a bounded batch of query vectors;
- query norms;
- candidate vectors and their cached norms;
- the requested top-K count.

Java returns only:

- candidate indices;
- raw cosine similarities.

Python still constructs `ScoredChunk` objects and maps cosine similarity from
`[-1, 1]` to the store's existing `[0, 1]` score contract.

Equal cosine scores use candidate index as the secondary ordering key. Candidate
indices follow Python insertion order, preserving the stable tie behavior of the
existing Python sort.

### Physics finite broad phase

Source:

- `java-accelerators/physics/BroadPhaseMain.java`
- `skeleton/simulation/physics/jvm_broadphase_accelerator.py`

Python integration:

- `SweepAndPruneBroadPhase` can offload finite-AABB candidate generation.
- `PhysicsWorld(..., use_jvm_broadphase=True)` enables the same fast path for
  normal world stepping.
- `PhysicsWorld.query_aabb_many()` can reuse one finite-body AABB batch for
  many spatial overlap queries in a single bounded JVM request.

Java receives only:

- finite AABB minima/maxima;
- one boolean saying whether each body is dynamic for pair generation;
- the requested pair bound and Python sweep epsilon;
- for spatial batches, bounded query AABBs and a total-hit cap.

Java returns only stable integer index pairs.

Python still owns body IDs, infinite planes, body/shape objects, narrow-phase
collision detection, contact manifolds, caches, islands, constraints, and the
solver. Infinite planes intentionally stay in Python because their candidate
rule is domain-specific rather than finite spatial overlap.

The broad-phase optimization is especially threshold-sensitive: unlike a bulk
offline vector query, physics can pay the pipe cost every simulation step. Use
it only once measured body counts make the JVM sweep cheaper end-to-end.

## Why these workloads qualify

A cross-language fast path has fixed costs:

1. locate/start the JVM;
2. compile source-launcher code on first start;
3. encode a request;
4. copy data through the pipe;
5. decode a response.

It is therefore usually a bad idea for tiny work.

The implemented workloads can become large enough for the arithmetic to
dominate those fixed costs:

- histogram sorting and statistical reduction over many observations;
- repeated rolling-window statistics over a large input batch;
- cosine scoring over many dense vectors;
- bulk retrieval where many queries reuse one candidate matrix;
- finite-AABB sweep-and-prune over large physics worlds;
- many spatial AABB queries that reuse one decoded body-bound array.

By contrast, Java is intentionally not used here for:

- a single counter increment;
- one anomaly observation;
- a four-plane retrieval fan-out already coordinated by Python;
- metadata filtering;
- hashing that is already implemented efficiently by Python's native-backed
  cryptographic libraries;
- application policy or supervisor logic;
- model calls;
- stateful adaptive/seasonal algorithms.

## CPU threads vs virtual threads

The numeric work in these accelerators is CPU-bound.

Virtual threads are designed primarily to make large numbers of blocking tasks
cheap to represent. They do not create more CPU cores and are not a general
speed button for arithmetic.

The observability many-series path therefore uses a bounded CPU worker pool, and
large individual sorts use Java's parallel sort threshold. This is a deliberate
choice: concurrency type should match the workload rather than the language
fashion of the moment.

## Enabling acceleration

Acceleration is opt-in at the owning Python object.

Example:

```python
from skeleton.observability import MetricsCollector

metrics = MetricsCollector(use_jvm_acceleration=True)
```

Canonical anomaly detector:

```python
from skeleton.observability import AnomalyDetector

detector = AnomalyDetector(
    strategy="statistical",
    use_jvm_acceleration=True,
)
reports = detector.observe_many(batch, metric_name="latency_ms")
```

Dense vector store:

```python
from skeleton.memory import VectorStore

store = VectorStore(use_jvm_acceleration=True)
results = store.query_many(["query one", "query two"], top_k=10)
```

Physics world:

```python
from skeleton.simulation.physics import PhysicsWorld

world = PhysicsWorld(use_jvm_broadphase=True)
hits = world.query_aabb_many((first_bounds, second_bounds))
```

Existing constructors without the new keyword continue to use only Python.

## Batch thresholds

Default thresholds exist to avoid paying IPC/startup costs for small work.

Observability:

- `SKELETON_JVM_OBSERVABILITY_MIN_BATCH`
- default: 2048 values

Dense vectors:

- `SKELETON_JVM_VECTOR_MIN_CANDIDATES`
- default: 512 candidates

Physics broad phase:

- `SKELETON_JVM_BROADPHASE_MIN_BODIES`
- default: 2048 finite bodies

These values are conservative defaults, not universal truths. Hardware,
container limits, Java distribution, vector dimensions, and workload shape all
change the crossover point.

Measure before lowering them.

## Benchmarking

Run:

```bash
PYTHONPATH=. python scripts/benchmark_java_accelerators.py
```

A larger example:

```bash
PYTHONPATH=. python scripts/benchmark_java_accelerators.py \
  --hist-values 250000 \
  --vectors 10000 \
  --dims 256 \
  --top-k 20 \
  --batch-queries 16 \
  --physics-bodies 10000 \
  --physics-queries 64 \
  --repeats 7
```

The benchmark:

1. creates deterministic fixtures;
2. starts and warms all three JVM helpers;
3. measures the Python baseline;
4. measures the Java path;
5. verifies output parity;
6. reports median/min/max timings and speedup.

It does not fail CI based on elapsed time. Performance assertions on shared CI
runners are usually noisy and encourage tuning to the runner rather than the
deployment.

A reported speedup below `1.0x` means Python was faster for that fixture.
Raise the threshold or leave acceleration disabled for that workload.

## Failure semantics

Java is an optimization, not an availability dependency.

Owning Python classes catch accelerator failures and execute their normal Python
path. This includes:

- Java missing;
- source file missing;
- source compilation failure;
- process exit;
- broken pipe;
- response timeout;
- malformed response;
- rejected bounds;
- dimension mismatch after acceleration is attempted.

The normal methods do not expose a Java-specific exception merely because
acceleration was enabled.

Separate `acceleration_stats()` methods expose attempts, successes,
fallbacks, and small-batch bypasses without changing existing `stats()` or
snapshot contracts.

## Process model

Each accelerator is a lazy singleton by default.

The JVM does not start when the package is imported. It starts on the first
accelerated operation large enough to use it.

Communication uses stdin/stdout, not a listening network socket. This has several
advantages:

- no port allocation;
- no service discovery;
- no accidental external exposure;
- process lifetime is tied to the Python parent;
- the protocol surface stays small.

The Python side also accepts an injected accelerator object. Tests use that seam
to verify fallback and parity without requiring Java.

## Protocol design

Both protocols are binary and length/bounds checked.

Every request carries:

- a fixed magic number;
- a protocol version;
- an operation code;
- a positive request ID.

Every response carries:

- the same magic/version;
- the operation code;
- a status;
- the request ID.

The Python client checks response correlation before consuming a result.

This avoids relying on line-delimited text for large arrays and prevents stdout
logging from being confused with protocol data. Java diagnostics go to stderr.

## Bounds

Observability bounds include:

- maximum values per request;
- maximum number of series;
- finite-number checks;
- bounded error messages.

Vector bounds include:

- maximum dimensions;
- maximum candidates;
- maximum batch query count;
- maximum total vector elements across queries plus candidates;
- positive finite norms;
- finite vector components;
- bounded error messages.

Physics broad-phase bounds include:

- maximum finite body count;
- maximum candidate pair count;
- maximum batch spatial-query count;
- maximum total spatial-query hits;
- finite AABB coordinates;
- valid AABB minimum/maximum ordering;
- bounded sweep epsilon;
- stable unique index-pair validation;
- bounded error messages.

Bounds matter even for a local child process. They prevent one malformed
in-process caller from turning the optimization into an accidental memory
amplifier.

## Numerical behavior

### Histograms

The Java summary contract returns:

- count;
- min/max;
- mean;
- sample variance and standard deviation;
- p50/p90/p95/p99;
- sum.

The fields used by `MetricsCollector.snapshot()` intentionally preserve the
existing Python snapshot schema.

### Anomaly windows

There are two existing detector semantics in the repository:

- one computes the reference window before inserting the current value;
- the canonical detector inserts the current value before computing statistics.

The Java anomaly operation explicitly supports both modes. This avoids a common
cross-language acceleration bug where the optimization quietly changes the
algorithm by one sample.

### Vector search

Cosine similarity is returned directly. Python performs the existing final score
mapping.

Top-K ordering is:

1. similarity descending;
2. original candidate index ascending.

For batch top-K, Java parallelizes across queries on a bounded CPU worker pool.
The candidate matrix is decoded once for the batch rather than once per query.

The second key preserves stable Python ordering on ties.

## Java version

CI provisions Java 21 for these helpers.

The runtime uses the Java source-file launcher, so no Maven or Gradle project is
required. That is intentional: adding a dependency graph and another package
manager would be a poor trade for a few small optional kernels.

The dedicated CI lane runs:

1. all Java source self-tests;
2. Python compilation for the affected packages;
3. fake-accelerator parity/fallback tests;
4. real Java protocol tests.

## Operations registry and health

`skeleton.jvm_accelerators.JvmAcceleratorRegistry` provides a single optional
operations surface for the three helpers. Importing or constructing the
registry does not start Java.

```python
from skeleton.jvm_accelerators import JvmAcceleratorRegistry

registry = JvmAcceleratorRegistry()

# Filesystem/runtime preflight only. No JVM process is started.
preflight = registry.preflight()

# Status is also non-starting for helpers that have not been initialized.
status = registry.status()

# Explicitly start and ping one helper.
registry.warm("vector")

# Restart and close are explicit lifecycle operations.
registry.restart("vector")
registry.close("vector")
```

The registry is intentionally separate from the root `skeleton` exports. This
keeps ordinary package imports cheap and prevents an operations convenience
layer from becoming a hidden runtime dependency.

### Preflight versus runtime health

`preflight()` checks only whether:

- the configured Java binary resolves to a real executable file; and
- the configured accelerator source exists.

It does not compile source, launch a JVM, or send a protocol frame.

`status()` reports initialized/running state plus client-side lifecycle
telemetry. For an uninitialized helper it combines non-starting preflight
information with `initialized=False`.

Each runtime status includes:

- process PID when running;
- Java/source configuration;
- detected server processor count after a successful ping;
- JVM process start count;
- failed JVM process-start attempts;
- explicit restart count;
- total protocol requests;
- successful request count;
- failed request count;
- timeout count;
- the last client-side error.

The counters belong to the Python bridge. They do not require another JVM
request and therefore cannot create a monitoring feedback loop.

### HealthRegistry integration

The registry can create a probe compatible with Skeleton's existing
`HealthRegistry`:

```python
from skeleton.jvm_accelerators import JvmAcceleratorRegistry
from skeleton.observability import HealthRegistry

jvm = JvmAcceleratorRegistry()
health = HealthRegistry()

# Readiness means Java + source are provisioned, or an initialized helper is
# healthy. This call itself does not start Java.
health.add_readiness(jvm.health_probe("vector"))

# For a deployment where the vector helper must already be running:
health.add_readiness(
    jvm.health_probe("vector", require_running=True)
)
```

`require_running=False` is appropriate when Java acceleration is optional but
the deployment wants to verify that the fast path is provisioned. Setting it
to `True` is an explicit choice to make an already-running JVM helper part of
readiness.

### Warm behavior

`warm()` calls `ping()` explicitly. With `strict=True` (the default), any
failed helper causes one aggregated registry exception. With `strict=False`,
healthy helpers remain available and the returned status snapshot records the
individual failure instead.

```python
statuses = registry.warm(strict=False)
for name, item in statuses.items():
    print(name, item.running, item.last_error)
```

Use non-strict warm when acceleration is an optimization and Python fallback
must preserve service availability. Use strict warm only when a deployment
has deliberately promoted one or more JVM helpers into a readiness
requirement.

## Operational configuration

Shared Java binary:

- `SKELETON_JAVA_BIN`

Observability source override:

- `SKELETON_JVM_OBSERVABILITY_SOURCE`

Observability response timeout:

- `SKELETON_JVM_OBSERVABILITY_TIMEOUT`

Observability batch threshold:

- `SKELETON_JVM_OBSERVABILITY_MIN_BATCH`

Vector source override:

- `SKELETON_JVM_VECTOR_SOURCE`

Vector response timeout:

- `SKELETON_JVM_VECTOR_TIMEOUT`

Vector candidate threshold:

- `SKELETON_JVM_VECTOR_MIN_CANDIDATES`

Physics broad-phase source override:

- `SKELETON_JVM_BROADPHASE_SOURCE`

Physics broad-phase response timeout:

- `SKELETON_JVM_BROADPHASE_TIMEOUT`

Physics broad-phase body threshold:

- `SKELETON_JVM_BROADPHASE_MIN_BODIES`

## What to measure in production

If acceleration is enabled, track:

- accelerated attempts;
- successful accelerated calls;
- fallback count;
- bypass count;
- caller latency distributions;
- Java process restarts;
- RSS / container memory;
- CPU saturation.

A fast kernel can still hurt end-to-end latency if serialization, memory
pressure, or CPU contention dominates.

## Adding another Java accelerator

A proposed accelerator should answer yes to most of these:

1. Is the workload already present and useful in Skeleton?
2. Is it batchable?
3. Is it expensive enough to amortize IPC?
4. Can inputs and outputs be bounded?
5. Can Python remain the owner of domain state?
6. Can fallback reproduce the existing behavior?
7. Can deterministic ordering be specified?
8. Can parity be regression-tested?
9. Is the Java version measurably faster on representative hardware?
10. Does the Java implementation avoid duplicating policy/business logic?

If those answers are weak, keep the code in Python.

That standard is more valuable than a target Java line count.
