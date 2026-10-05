"""
╔══════════════════════════════════════════════════════════════════════════╗
║  HYPERSCALE DOMAIN EXPANSION — EVERY CODING DOMAIN KNOWN TO HUMANITY   ║
║  Languages · DevOps · Data · ML/AI · Mobile · Testing · APIs · Web     ║
║  Database Internals · Security Deep · Blockchain · Game Dev Deep       ║
║  Target: 500+ knowledge entries across 20+ domains                     ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
import hashlib
import random

random.seed(2026)

def _eid(prefix, name):
    return f"{prefix}_{hashlib.md5(name.encode()).hexdigest()[:8]}"

# ═══════════════════════════════════════════════════════════════
# PROGRAMMING LANGUAGES — DEEP INTERNALS FOR EVERY MAJOR LANGUAGE
# ═══════════════════════════════════════════════════════════════

_LANGUAGES = [
    ("Python","python",800,["Type System (duck typing, type hints, mypy)","Memory Model (reference counting, GC, pymalloc)","GIL & Concurrency (threading, multiprocessing, asyncio)","Data Model (__dunder__ methods, descriptors, metaclasses)","Iterators & Generators (yield, async generators, itertools)","Decorators & Context Managers","Import System (packages, namespace, importlib)","C Extensions (ctypes, cffi, Cython, pybind11)","Standard Library Deep Dive (collections, functools, pathlib, dataclasses)","Packaging (pip, poetry, setuptools, wheels, conda)","Performance (profiling, cProfile, line_profiler, optimization)","Testing (pytest, unittest, hypothesis, coverage)","Web Frameworks (Django, Flask, FastAPI, Starlette)","Data Science Stack (NumPy, Pandas, Matplotlib, Jupyter)","Python Internals (bytecode, dis, AST, CPython source)"]),
    ("JavaScript","javascript",900,["Engine Internals (V8, SpiderMonkey, JIT compilation)","Event Loop (microtasks, macrotasks, queueMicrotask)","Prototypal Inheritance & Classes","Closures, Scopes & Hoisting","Promises, async/await, AbortController","Proxy & Reflect API","WeakRef & FinalizationRegistry","Modules (ESM, CJS, dynamic import, tree shaking)","TypedArrays & ArrayBuffer","Web APIs (DOM, Fetch, Web Workers, Service Workers)","Node.js Runtime (libuv, streams, child_process, cluster)","Deno & Bun Runtimes","Memory Management & Garbage Collection","Regex Engine & Unicode","ES2025+ Features (decorators, records, tuples, pattern matching)"]),
    ("TypeScript","typescript",600,["Type System (structural typing, type narrowing, discriminated unions)","Generics (constraints, conditional types, mapped types, template literals)","Utility Types (Partial, Required, Pick, Omit, Record, Exclude)","Declaration Files (.d.ts, DefinitelyTyped, module augmentation)","Compiler API & AST Manipulation","Project References & Composite Projects","Enums vs Const Assertions","Decorators (Stage 3, experimental, reflect-metadata)","Type Guards & Assertion Functions","Variance (covariance, contravariance, bivariance)","TSConfig Deep Dive (strict mode, paths, moduleResolution)","TypeScript with React (generic components, HOCs, hooks typing)","TypeScript with Node.js (express types, prisma, trpc)","Performance (isolatedModules, skipLibCheck, incremental)","Migration Strategies (JSDoc, allowJS, gradual adoption)"]),
    ("Rust","rust",700,["Ownership & Borrowing (move semantics, lifetimes, borrow checker)","Trait System (impl, dyn, associated types, supertraits)","Error Handling (Result, Option, ? operator, anyhow, thiserror)","Concurrency (Send, Sync, Arc, Mutex, channels, tokio, rayon)","Unsafe Rust (raw pointers, FFI, transmute, Pin)","Macros (declarative, procedural, derive, attribute)","Smart Pointers (Box, Rc, Arc, Cow, Cell, RefCell)","Iterators & Closures (map, filter, fold, collect)","Async/Await (Future, Pin, tokio, async-std)","Memory Layout (repr, alignment, zero-cost abstractions)","Cargo & Ecosystem (workspaces, features, build scripts)","WebAssembly (wasm-bindgen, wasm-pack, trunk)","Embedded Rust (no_std, embassy, RTIC)","Networking (hyper, axum, actix-web, tonic/gRPC)"]),
    ("Go","golang",550,["Goroutines & Channels (select, context, sync.WaitGroup)","Interface System (implicit implementation, type assertions, embedding)","Memory Model (stack vs heap, escape analysis, GC)","Generics (type parameters, constraints, type inference)","Error Handling Patterns (sentinel errors, wrapping, errors.Is/As)","Reflection (reflect package, struct tags, dynamic dispatch)","Testing (table-driven, benchmarks, fuzzing, testify)","Concurrency Patterns (fan-in, fan-out, pipeline, worker pool)","Standard Library (net/http, encoding/json, database/sql, context)","Module System (go.mod, workspaces, versioning, GOPROXY)","CGO & FFI (C interop, shared libraries)","Performance (pprof, trace, benchmarks, escape analysis)","Web Frameworks (Gin, Echo, Fiber, Chi)","Cloud Native Go (gRPC, protobuf, Kubernetes operators)"]),
    ("C++","cpp",900,["Modern C++ (C++20/23: concepts, ranges, coroutines, modules)","Templates (SFINAE, variadic, fold expressions, CTAD)","Memory Management (RAII, smart pointers, allocators, arenas)","Move Semantics (rvalue references, perfect forwarding, copy elision)","Concurrency (std::thread, atomic, mutex, futures, coroutines)","STL Deep Dive (containers, algorithms, iterators, ranges)","Compile-Time Programming (constexpr, consteval, template metaprogramming)","Exception Safety (RAII, noexcept, strong/basic guarantee)","ABI & Linking (name mangling, ODR, shared libraries, modules)","Undefined Behavior (strict aliasing, signed overflow, dangling references)","Build Systems (CMake, Bazel, Meson, vcpkg, Conan)","Game Engine C++ (ECS, memory pools, SIMD, cache optimization)","Embedded C++ (no-RTTI, no-exceptions, bare metal)","Performance (profiling, SIMD, cache lines, branch prediction)"]),
    ("Java","java",800,["JVM Internals (class loading, bytecode, JIT, GC algorithms)","Generics (type erasure, wildcards, bounded types, variance)","Concurrency (virtual threads, CompletableFuture, ForkJoinPool, structured concurrency)","Streams API (lazy evaluation, parallel streams, collectors)","Module System (JPMS, module-info.java, services)","Records, Sealed Classes, Pattern Matching","Reflection & Annotations (runtime, compile-time, annotation processors)","Memory Model (happens-before, volatile, atomic, VarHandle)","GC Tuning (G1, ZGC, Shenandoah, epsilon)","Spring Ecosystem (Boot, Security, Data, Cloud, WebFlux)","Build Tools (Maven, Gradle, multi-module projects)","Testing (JUnit 5, Mockito, Testcontainers, ArchUnit)","Reactive Programming (Project Reactor, RxJava, Spring WebFlux)","Microservices (Quarkus, Micronaut, Helidon, gRPC)"]),
    ("CSharp","csharp",750,["Type System (value types, reference types, nullable, spans)","LINQ (query syntax, method syntax, expression trees, IQueryable)","Async/Await (Task, ValueTask, channels, async streams)","Generics (constraints, covariance, contravariance)","Pattern Matching (switch expressions, property patterns, list patterns)","Records & Init-Only Properties","Source Generators & Analyzers","Memory Management (.NET GC, Span<T>, Memory<T>, ArrayPool)","Interop (P/Invoke, COM, C++/CLI, NativeAOT)","ASP.NET Core (minimal APIs, middleware, SignalR, Blazor)","Entity Framework Core (migrations, change tracking, raw SQL)","Unity C# (MonoBehaviour, ECS/DOTS, Burst compiler, Jobs)","Testing (xUnit, NUnit, Moq, FluentAssertions, BenchmarkDotNet)"]),
    ("Swift","swift",500,["Protocol-Oriented Programming (protocol extensions, associated types, PAT)","Value Types vs Reference Types (structs, classes, copy-on-write)","Generics (where clauses, opaque types, some/any keywords)","Concurrency (async/await, actors, structured concurrency, Sendable)","Memory Management (ARC, weak/unowned, capture lists)","Property Wrappers (@State, @Binding, @Published, custom)","Result Builders (@ViewBuilder, custom DSLs)","SwiftUI (declarative UI, state management, navigation, animations)","UIKit Interop (UIViewRepresentable, coordinators)","Swift Package Manager (dependencies, plugins, macros)","Testing (XCTest, Swift Testing, snapshot testing)","Server-Side Swift (Vapor, Hummingbird)"]),
    ("Kotlin","kotlin",500,["Null Safety (nullable types, safe calls, elvis, smart casts)","Coroutines (suspend, Flow, channels, structured concurrency, StateFlow)","Extension Functions & Properties","Delegation (by keyword, delegated properties, lazy, observable)","Sealed Classes & Inline Classes","DSL Building (type-safe builders, scope functions)","Multiplatform (KMP, expect/actual, Compose Multiplatform)","Jetpack Compose (state, recomposition, side effects, navigation)","Android Architecture (ViewModel, Room, Hilt, WorkManager)","Kotlin/JS & Kotlin/Native","Testing (JUnit, MockK, Turbine, Compose testing)"]),
    ("Ruby","ruby",400,["Object Model (everything is an object, eigenclasses, method lookup)","Metaprogramming (method_missing, define_method, class_eval, instance_eval)","Blocks, Procs & Lambdas (yield, closures, curry)","Concurrency (Ractor, Fiber, Thread, GVL)","Module System (mixins, prepend, refinements)","Ruby on Rails Deep Dive (ActiveRecord, Action Cable, Hotwire, Turbo)","Gems & Bundler (gem creation, Gemfile, version constraints)","Testing (RSpec, Minitest, FactoryBot, VCR)","Performance (profiling, JIT, YJIT compiler)","Ruby 3+ Features (pattern matching, Ractor, type signatures/RBS)"]),
    ("PHP","php",400,["Type System (strict types, union types, intersection, enums, fibers)","OOP (traits, interfaces, abstract, readonly, constructor promotion)","Composer & Autoloading (PSR-4, packages, scripts)","Laravel Deep Dive (Eloquent, Blade, Livewire, queues, broadcasting)","Symfony Components (HttpFoundation, Console, DependencyInjection)","Concurrency (Fibers, Swoole, ReactPHP, Amphp)","Testing (PHPUnit, Pest, Mockery, Dusk)","Performance (OPcache, preloading, JIT, profiling)","Modern PHP (PHP 8.3+: readonly classes, typed constants, #[Override])"]),
    ("Scala","scala",400,["Type System (higher-kinded types, path-dependent, match types)","Functional Programming (immutability, ADTs, pattern matching, for-comprehensions)","Implicits & Given/Using (context parameters, type classes, extension methods)","Effects Systems (Cats Effect, ZIO, monads, IO)","Concurrency (Akka actors, Cats Effect fibers, ZIO fibers)","Macros & Metaprogramming (Scala 3 inline, quotes, splices)","Spark with Scala (RDD, DataFrame, Dataset, Structured Streaming)","Build Tools (sbt, Mill, Bloop)","Interop with Java (seamless, collections conversion)"]),
    ("Elixir","elixir",350,["OTP (GenServer, Supervisor, Application, ETS, Agent)","Concurrency Model (lightweight processes, message passing, BEAM VM)","Pattern Matching & Guards","Protocols & Behaviours","Metaprogramming (macros, quote/unquote, AST)","Phoenix Framework (LiveView, Channels, PubSub, Ecto)","Distributed Computing (Node connections, :global, Horde, libcluster)","Testing (ExUnit, Mox, StreamData, Wallaby)","Nerves (embedded Elixir, firmware, hardware)"]),
    ("Haskell","haskell",400,["Type System (algebraic data types, type classes, kinds, GADTs)","Monads (IO, Maybe, Either, State, Reader, Writer, ST)","Lazy Evaluation (thunks, seq, deepseq, strictness annotations)","Concurrency (STM, MVar, async, par, sparks)","Template Haskell & GHC Extensions","Lens & Optics (van Laarhoven, profunctor optics)","Category Theory (functors, applicatives, monoids, arrows)","Build Tools (Cabal, Stack, Nix)","Web (Servant, Yesod, Scotty, IHP)"]),
    ("Zig","zig",300,["Comptime (compile-time execution, generic programming)","Error Handling (error unions, errdefer, try)","Memory Management (allocators, arena, GeneralPurposeAllocator)","C Interop (seamless, translate-c, libc)","SIMD & Vectors (built-in vector types)","Build System (build.zig, cross-compilation)","Async I/O (evented I/O, coroutines)"]),
    ("Clojure","clojure",350,["Immutable Data Structures (persistent, structural sharing)","Concurrency Primitives (atoms, refs, agents, STM)","Macros & Reader Macros","Transducers & Reducers","spec & Generative Testing","ClojureScript & Reagent/Re-frame","REPL-Driven Development","Java Interop (calling Java, implementing interfaces)"]),
]

def get_languages_database():
    """Every programming language with deep internals."""
    entries = []
    for name, lang_id, hours, topics in _LANGUAGES:
        entries.append({
            "id": f"lang_{lang_id}",
            "name": f"{name} Deep Dive",
            "level": "comprehensive",
            "hours": hours,
            "topics": topics,
            "category": "programming_language",
        })
    return entries

# ═══════════════════════════════════════════════════════════════
# DEVOPS & CLOUD — COMPLETE
# ═══════════════════════════════════════════════════════════════

_DEVOPS_ENTRIES = [
    ("Docker Mastery","docker",300,["Dockerfile (multi-stage, BuildKit, cache optimization)","Compose (services, networks, volumes, profiles)","Networking (bridge, overlay, host, macvlan)","Security (rootless, seccomp, AppArmor, image scanning)","Registry (Harbor, ECR, GCR, ACR, distribution)","Orchestration Basics (swarm mode)","Buildx & Multi-platform","Storage (volumes, bind mounts, tmpfs, drivers)"]),
    ("Kubernetes Production","kubernetes",600,["Architecture (control plane, kubelet, kube-proxy, etcd)","Workloads (Deployments, StatefulSets, DaemonSets, Jobs, CronJobs)","Networking (Services, Ingress, NetworkPolicy, DNS, CNI)","Storage (PV, PVC, StorageClasses, CSI drivers)","Security (RBAC, ServiceAccounts, PodSecurity, Secrets, OPA/Gatekeeper)","Operators & CRDs (operator-sdk, kubebuilder, controller-runtime)","Helm (charts, templates, hooks, library charts, OCI)","Service Mesh (Istio, Linkerd, Cilium)","Observability (Prometheus, Grafana, Loki, Tempo, OpenTelemetry)","GitOps (ArgoCD, Flux, progressive delivery)","Autoscaling (HPA, VPA, KEDA, Cluster Autoscaler)","Multi-cluster & Federation"]),
    ("Terraform & IaC","terraform",400,["HCL Language (blocks, expressions, functions, for_each, dynamic)","State Management (remote backends, locking, import, state surgery)","Modules (composition, versioning, registry, testing)","Providers (AWS, GCP, Azure, Kubernetes, custom)","Workspaces & Environments","Testing (Terratest, terraform test, plan validation)","Pulumi Alternative (TypeScript/Python/Go IaC)","Ansible (playbooks, roles, galaxy, vault, AWX)"]),
    ("CI/CD Pipelines","cicd",350,["GitHub Actions (workflows, composite actions, reusable, OIDC)","GitLab CI (pipeline architecture, includes, rules, DAG)","Jenkins (declarative pipelines, shared libraries, agents)","ArgoCD (app-of-apps, ApplicationSets, sync waves)","Deployment Strategies (blue/green, canary, rolling, A/B)","Feature Flags (LaunchDarkly, Unleash, Flagsmith)","Artifact Management (Artifactory, Nexus, GitHub Packages)","Security Scanning (SAST, DAST, SCA, container scanning)"]),
    ("AWS Complete","aws",800,["Compute (EC2, Lambda, ECS, EKS, Fargate, App Runner)","Storage (S3, EBS, EFS, FSx, Glacier)","Database (RDS, DynamoDB, ElastiCache, Neptune, Timestream, MemoryDB)","Networking (VPC, ALB/NLB, CloudFront, Route53, Transit Gateway, PrivateLink)","Security (IAM, KMS, Secrets Manager, WAF, Shield, GuardDuty, Security Hub)","Messaging (SQS, SNS, EventBridge, Kinesis, MSK)","ML (SageMaker, Bedrock, Comprehend, Rekognition)","Serverless (Lambda, API Gateway, Step Functions, SAM)","Observability (CloudWatch, X-Ray, CloudTrail)","Cost Optimization (Reserved, Spot, Savings Plans, Cost Explorer)","Well-Architected Framework (6 pillars)"]),
    ("GCP Complete","gcp",600,["Compute (GCE, Cloud Run, GKE, Cloud Functions, App Engine)","Storage (Cloud Storage, Persistent Disk, Filestore)","Database (Cloud SQL, Spanner, Firestore, Bigtable, AlloyDB)","Networking (VPC, Cloud CDN, Cloud Armor, Cloud DNS)","Data (BigQuery, Dataflow, Dataproc, Pub/Sub, Composer)","AI/ML (Vertex AI, AutoML, TPUs, Gemini API)","Security (IAM, VPC Service Controls, Binary Authorization)"]),
    ("Azure Complete","azure",600,["Compute (VMs, AKS, Functions, Container Apps, App Service)","Storage (Blob, Files, Disks, Data Lake)","Database (Azure SQL, Cosmos DB, Cache for Redis, PostgreSQL Flexible)","Networking (VNet, Front Door, Application Gateway, Private Link)","AI (Azure OpenAI, Cognitive Services, ML Studio)","DevOps (Azure DevOps, Repos, Pipelines, Boards, Artifacts)","Security (Entra ID, Key Vault, Defender, Sentinel)"]),
    ("Observability","observability",350,["Metrics (Prometheus, Grafana, InfluxDB, Datadog)","Logging (ELK/EFK, Loki, Fluentd, structured logging)","Tracing (Jaeger, Zipkin, Tempo, OpenTelemetry)","APM (New Relic, Dynatrace, Datadog APM)","SRE Practices (SLOs, SLIs, error budgets, incident management)","Alerting (PagerDuty, OpsGenie, Alertmanager)","Chaos Engineering (Chaos Monkey, Litmus, Gremlin)"]),
    ("Linux & Systems","linux_systems",400,["Kernel (syscalls, namespaces, cgroups, eBPF)","Filesystems (ext4, XFS, Btrfs, ZFS, overlayfs)","Networking (iptables, nftables, tc, socket programming)","Process Management (systemd, init, cgroups, namespaces)","Shell Scripting (bash, zsh, awk, sed, jq)","Performance (perf, strace, dtrace, flame graphs, BPF tools)","Security (SELinux, AppArmor, seccomp, capabilities)"]),
]

def get_devops_database():
    entries = []
    for name, did, hours, topics in _DEVOPS_ENTRIES:
        entries.append({"id": f"devops_{did}", "name": name, "level": "professional", "hours": hours, "topics": topics, "category": "devops_cloud"})
    return entries

# ═══════════════════════════════════════════════════════════════
# DATA ENGINEERING — COMPLETE
# ═══════════════════════════════════════════════════════════════

_DATA_ENTRIES = [
    ("Apache Spark","spark",500,["RDD API (transformations, actions, partitioning)","DataFrame & Dataset API (catalyst optimizer, tungsten)","Structured Streaming (micro-batch, continuous, watermarking)","Spark SQL (query plans, UDFs, adaptive query execution)","MLlib (classification, regression, clustering, pipelines)","GraphX & GraphFrames","Performance Tuning (partitioning, caching, broadcast, shuffle)","Deployment (standalone, YARN, Kubernetes, Databricks)"]),
    ("Apache Kafka","kafka",400,["Core (producers, consumers, brokers, ZooKeeper/KRaft)","Topics & Partitions (replication, ISR, min.insync.replicas)","Kafka Streams (KTable, KStream, joins, windowing, exactly-once)","Kafka Connect (source/sink connectors, transforms, schemas)","Schema Registry (Avro, Protobuf, JSON Schema, compatibility)","KSQL/ksqlDB (streaming SQL, materialized views)","Security (SASL, SSL, ACLs, encryption)","Performance (compression, batching, idempotent producers)"]),
    ("Data Warehousing","data_warehouse",350,["Dimensional Modeling (star, snowflake, slowly changing dimensions)","Snowflake (warehouses, stages, pipes, time travel, cloning)","BigQuery (partitioning, clustering, materialized views, BI Engine)","Redshift (distribution keys, sort keys, WLM, Spectrum)","dbt (models, tests, documentation, macros, packages)","Data Vault 2.0 (hubs, links, satellites)"]),
    ("Apache Airflow","airflow",300,["DAGs (operators, sensors, hooks, XComs)","Executors (Local, Celery, Kubernetes, CeleryKubernetes)","Connections & Variables","Dynamic DAGs & Task Groups","Testing (unit tests, DAG validation, CI/CD)","Alternatives (Dagster, Prefect, Mage, Luigi)"]),
    ("Elasticsearch","elasticsearch",300,["Indexing (mappings, analyzers, tokenizers, filters)","Query DSL (bool, match, term, range, nested, aggregations)","Cluster Management (shards, replicas, allocation, routing)","Performance (caching, doc values, field data, force merge)","Kibana (Lens, Discover, dashboards, alerting)","ELK Stack (Logstash, Beats, APM)"]),
    ("Stream Processing","stream_proc",300,["Apache Flink (DataStream, Table API, CEP, state backends)","Kinesis (Data Streams, Firehose, Analytics)","Pulsar (topics, subscriptions, functions, IO)","Event Sourcing & CQRS patterns","Change Data Capture (Debezium, Maxwell)"]),
    ("Data Lakes","data_lakes",250,["Delta Lake (ACID transactions, time travel, Z-ordering, liquid clustering)","Apache Iceberg (hidden partitioning, schema evolution, branching)","Apache Hudi (copy-on-write, merge-on-read, clustering)","Lakehouse Architecture (medallion pattern, bronze/silver/gold)","Object Storage (S3, GCS, MinIO, partitioning strategies)"]),
]

def get_data_engineering_database():
    entries = []
    for name, did, hours, topics in _DATA_ENTRIES:
        entries.append({"id": f"data_{did}", "name": name, "level": "professional", "hours": hours, "topics": topics, "category": "data_engineering"})
    return entries

# ═══════════════════════════════════════════════════════════════
# ML/AI DEEP DIVE — COMPLETE
# ═══════════════════════════════════════════════════════════════

_ML_ENTRIES = [
    ("Deep Learning Architectures","dl_arch",500,["Feedforward Networks (MLP, activation functions, initialization)","CNNs (convolution, pooling, ResNet, EfficientNet, ConvNeXt)","RNNs/LSTMs/GRUs (vanishing gradients, attention, seq2seq)","Transformers (self-attention, multi-head, positional encoding)","Vision Transformers (ViT, DeiT, Swin, BEiT)","Diffusion Models (DDPM, stable diffusion, ControlNet, SDXL)","GANs (DCGAN, StyleGAN, pix2pix, CycleGAN)","Graph Neural Networks (GCN, GAT, GraphSAGE)","State Space Models (Mamba, S4, structured SSMs)","Mixture of Experts (Switch Transformer, GShard)"]),
    ("NLP & LLMs","nlp_llm",600,["Tokenization (BPE, SentencePiece, WordPiece, tiktoken)","Embeddings (Word2Vec, GloVe, FastText, contextual)","Transformer Architecture (encoder, decoder, encoder-decoder)","Pre-training (masked LM, causal LM, denoising, contrastive)","Fine-tuning (full, LoRA, QLoRA, prefix tuning, adapters)","RLHF (reward models, PPO, DPO, RLAIF)","RAG (retrieval-augmented generation, vector databases, chunking)","Prompt Engineering (few-shot, chain-of-thought, tree-of-thought)","LLM Serving (vLLM, TGI, TensorRT-LLM, quantization)","Evaluation (perplexity, BLEU, ROUGE, human eval, benchmarks)","Agents & Tool Use (function calling, ReAct, plan-and-execute)"]),
    ("Computer Vision","cv_deep",500,["Object Detection (YOLO, SSD, Faster R-CNN, DETR, RT-DETR)","Segmentation (semantic, instance, panoptic, SAM)","Image Generation (diffusion, ControlNet, IP-Adapter, SDXL Turbo)","3D Vision (NeRF, 3D Gaussian Splatting, point clouds, depth estimation)","Video Understanding (action recognition, tracking, temporal models)","OCR (CRNN, TrOCR, PaddleOCR, document AI)","Medical Imaging (U-Net, segmentation, classification, DICOM)"]),
    ("Reinforcement Learning","rl_deep",400,["Value-Based (Q-Learning, DQN, Double DQN, Dueling DQN, Rainbow)","Policy Gradient (REINFORCE, A2C, A3C, PPO, SAC, TD3)","Model-Based RL (Dreamer, MuZero, world models)","Multi-Agent RL (MAPPO, QMIX, communication)","Offline RL (BCQ, CQL, Decision Transformer, IQL)","Environments (Gymnasium, PettingZoo, Unity ML-Agents)","Applications (game AI, robotics, recommendation, LLM alignment)"]),
    ("MLOps","mlops_deep",400,["Experiment Tracking (MLflow, Weights & Biases, Neptune, CometML)","Feature Stores (Feast, Tecton, Hopsworks)","Model Serving (TorchServe, TF Serving, Triton, BentoML, Ray Serve)","Pipeline Orchestration (Kubeflow, Vertex AI, SageMaker Pipelines)","Monitoring (data drift, model drift, concept drift, Evidently, Arize)","A/B Testing & Shadow Deployment","Model Registry & Versioning","GPU Optimization (mixed precision, quantization, pruning, distillation)"]),
    ("Gen AI Applications","genai_apps",350,["LLM Application Framework (LangChain, LlamaIndex, Semantic Kernel)","Vector Databases (Pinecone, Weaviate, Qdrant, Milvus, Chroma)","Embedding Models (OpenAI, Cohere, sentence-transformers, BGE)","Agent Frameworks (AutoGen, CrewAI, LangGraph, Phidata)","Image Generation APIs (DALL-E, Midjourney, Stable Diffusion, Flux)","Voice AI (Whisper, ElevenLabs, text-to-speech, speech-to-text)","Code Generation (Copilot, Cursor, Codex, CodeLlama, DeepSeek)"]),
]

def get_ml_ai_database():
    entries = []
    for name, did, hours, topics in _ML_ENTRIES:
        entries.append({"id": f"ml_{did}", "name": name, "level": "advanced", "hours": hours, "topics": topics, "category": "ml_ai"})
    return entries

# ═══════════════════════════════════════════════════════════════
# MOBILE DEVELOPMENT — COMPLETE
# ═══════════════════════════════════════════════════════════════

_MOBILE_ENTRIES = [
    ("iOS Development","ios",500,["SwiftUI (views, state, data flow, navigation, animations)","UIKit (view controller lifecycle, Auto Layout, collection views)","Combine (publishers, subscribers, operators, scheduling)","Core Data & SwiftData (models, relationships, migrations, CloudKit)","Networking (URLSession, async/await, Combine, Alamofire)","App Architecture (MVVM, TCA, Clean, coordinator pattern)","Performance (Instruments, memory, CPU, energy, Metal)","App Store (provisioning, certificates, review guidelines, ASO)","Widgets & Live Activities","Push Notifications (APNs, rich notifications, notification extensions)","Accessibility (VoiceOver, Dynamic Type, color contrast)"]),
    ("Android Development","android",500,["Jetpack Compose (state, side effects, navigation, theming, animation)","Android Architecture Components (ViewModel, LiveData, Room, WorkManager)","Kotlin Coroutines & Flow (StateFlow, SharedFlow, channelFlow)","Dependency Injection (Hilt, Koin, manual)","Networking (Retrofit, OkHttp, Ktor, serialization)","Data Persistence (Room, DataStore, SharedPreferences, SQLite)","Testing (Compose testing, Espresso, Robolectric, MockK)","Play Store (signing, bundles, Play Console, review policies)","Material Design 3 (Material You, dynamic color, components)","Background Processing (WorkManager, foreground services, AlarmManager)"]),
    ("React Native","react_native",400,["Architecture (new architecture, Fabric, TurboModules, JSI, Hermes)","Navigation (React Navigation, Expo Router, deep linking)","State Management (Zustand, Redux Toolkit, Jotai, React Query)","Native Modules (Turbo Native Modules, native views)","Animations (Reanimated, Gesture Handler, Skia)","Expo (SDK, EAS Build, EAS Submit, OTA updates, dev client)","Performance (Flashlight, Flipper, Hermes profiling, list optimization)","Testing (Jest, React Native Testing Library, Detox, Maestro)"]),
    ("Flutter","flutter_dev",400,["Widget System (StatelessWidget, StatefulWidget, InheritedWidget)","State Management (Bloc, Riverpod, Provider, GetX)","Navigation (GoRouter, Navigator 2.0, deep linking)","Platform Channels (MethodChannel, EventChannel, pigeon)","Rendering Engine (Skia, Impeller, custom painting)","Testing (widget testing, integration testing, golden tests)","Dart Fundamentals (null safety, isolates, FFI, extensions)","Flutter Web & Desktop (platform targeting, responsive layout)"]),
    ("Cross-Platform Patterns","cross_platform",250,["Shared Business Logic (KMP, Rust FFI, C++)","Design Systems (platform-adaptive UI, tokens)","Deep Linking (universal links, app links, deferred deep links)","Push Notifications (FCM, APNs, OneSignal, unified handling)","Analytics (Firebase, Amplitude, Mixpanel, privacy)","CI/CD (Fastlane, EAS, Codemagic, Bitrise)","App Performance (startup time, frame rate, memory, battery)"]),
]

def get_mobile_database():
    entries = []
    for name, did, hours, topics in _MOBILE_ENTRIES:
        entries.append({"id": f"mobile_{did}", "name": name, "level": "professional", "hours": hours, "topics": topics, "category": "mobile_development"})
    return entries

# ═══════════════════════════════════════════════════════════════
# TESTING & QA — COMPLETE
# ═══════════════════════════════════════════════════════════════

_TESTING_ENTRIES = [
    ("Unit Testing","unit_testing",250,["Test Anatomy (arrange, act, assert, GWT)","Mocking (stubs, spies, fakes, test doubles)","Coverage (line, branch, path, mutation testing)","Frameworks (Jest, pytest, JUnit, xUnit, RSpec, Go testing)","TDD (red-green-refactor, outside-in, classicist vs mockist)","Property-Based Testing (QuickCheck, Hypothesis, fast-check)"]),
    ("Integration Testing","integration_testing",200,["API Testing (Postman, REST Assured, httpx, supertest)","Database Testing (Testcontainers, in-memory DBs, fixtures)","Message Queue Testing (embedded Kafka, localstack)","Contract Testing (Pact, Spring Cloud Contract)","Test Environments (Docker Compose, Testcontainers, LocalStack)"]),
    ("E2E Testing","e2e_testing",250,["Browser Automation (Playwright, Cypress, Selenium, Puppeteer)","Mobile E2E (Detox, Maestro, Appium, XCUITest, Espresso)","Visual Regression (Percy, Chromatic, BackstopJS)","API E2E (Newman, k6, artillery)","Page Object Model & Test Architecture","CI Integration (parallel, sharding, flaky test management)"]),
    ("Performance Testing","perf_testing",200,["Load Testing (k6, Gatling, JMeter, Locust, artillery)","Stress Testing & Soak Testing","Profiling (CPU, memory, I/O, network)","Benchmarking (micro, macro, statistical significance)","Web Performance (Lighthouse, Core Web Vitals, SpeedIndex)","Database Performance (query plans, EXPLAIN, index analysis)"]),
    ("Security Testing","sec_testing",250,["SAST (SonarQube, Semgrep, CodeQL, Bandit)","DAST (OWASP ZAP, Burp Suite, Nuclei)","SCA (Snyk, Dependabot, Trivy, Grype)","Penetration Testing (methodology, reconnaissance, exploitation)","Fuzzing (AFL, libFuzzer, Go fuzzing, property-based)","Compliance (SOC2, PCI-DSS, HIPAA, GDPR automation)"]),
    ("Test Architecture","test_arch",200,["Test Pyramid (unit, integration, E2E ratios)","Testing Strategies (shift-left, continuous testing)","Test Data Management (factories, fixtures, seeding, anonymization)","Flaky Test Prevention (determinism, isolation, retry policies)","Quality Metrics (defect density, MTTR, test effectiveness)"]),
]

def get_testing_database():
    entries = []
    for name, did, hours, topics in _TESTING_ENTRIES:
        entries.append({"id": f"testing_{did}", "name": name, "level": "professional", "hours": hours, "topics": topics, "category": "testing_qa"})
    return entries

# ═══════════════════════════════════════════════════════════════
# API DESIGN & WEB TECHNOLOGIES — COMPLETE
# ═══════════════════════════════════════════════════════════════

_API_ENTRIES = [
    ("REST API Design","rest_api",250,["Resource Design (nouns, plurals, nesting, HATEOAS)","HTTP Methods & Status Codes (idempotency, safety)","Versioning (URL, header, query param, content negotiation)","Pagination (offset, cursor, keyset, relay-style)","Filtering, Sorting & Searching","Authentication (JWT, OAuth2, API keys, session)","Rate Limiting & Throttling","OpenAPI/Swagger (documentation, code generation, validation)"]),
    ("GraphQL","graphql",300,["Schema Design (types, queries, mutations, subscriptions)","Resolvers (N+1 problem, DataLoader, batching)","Authentication & Authorization (directives, middleware)","Federation (Apollo Federation, schema stitching)","Code Generation (codegen, typed-document-node)","Performance (persisted queries, query complexity, caching)","Alternatives (tRPC, Relay, urql)"]),
    ("gRPC & Protobuf","grpc",200,["Protocol Buffers (proto3, messages, services, enums, oneof)","Streaming (unary, server, client, bidirectional)","Interceptors & Middleware","Load Balancing & Service Discovery","gRPC-Web (browser support, Envoy proxy)","Code Generation (protoc, Buf, Connect)"]),
    ("WebSocket & Real-time","websocket",200,["WebSocket Protocol (handshake, frames, close codes)","Socket.IO (rooms, namespaces, acknowledgments)","Server-Sent Events (EventSource, reconnection)","WebRTC (peer connections, data channels, signaling)","Scaling (Redis pub/sub, NATS, sticky sessions)"]),
    ("Web Technologies Deep","web_tech",400,["HTML5 (semantic elements, Canvas, WebGL, Web Components, Shadow DOM)","CSS3 (Grid, Flexbox, Container Queries, Cascade Layers, Subgrid, Nesting)","WebAssembly (WAT, memory model, WASI, component model, Emscripten)","Web APIs (Intersection Observer, ResizeObserver, Web Crypto, File System Access)","PWA (Service Workers, Web App Manifest, Background Sync, Push API)","WebGPU (compute shaders, render pipelines, WGSL)","Performance APIs (Navigation Timing, Resource Timing, Layout Instability)"]),
    ("Frontend Frameworks Deep","frontend_fw",500,["React 19+ (Server Components, Actions, use(), compiler, Suspense)","Next.js 15+ (App Router, Server Actions, Partial Prerendering, middleware)","Vue 3 (Composition API, Pinia, Nuxt 3, Vapor mode)","Angular 18+ (Signals, standalone components, defer, SSR hydration)","Svelte 5 (runes, snippets, SvelteKit, universal reactivity)","Solid.js (fine-grained reactivity, signals, stores, SolidStart)","Qwik (resumability, progressive hydration, Qwik City)","Astro (content collections, view transitions, islands, middleware)","HTMX (hx-boost, hx-trigger, hyperscript, hypermedia)"]),
]

def get_api_web_database():
    entries = []
    for name, did, hours, topics in _API_ENTRIES:
        entries.append({"id": f"api_{did}", "name": name, "level": "professional", "hours": hours, "topics": topics, "category": "api_web"})
    return entries

# ═══════════════════════════════════════════════════════════════
# DATABASE INTERNALS — COMPLETE
# ═══════════════════════════════════════════════════════════════

_DB_ENTRIES = [
    ("PostgreSQL Internals","postgresql",500,["Storage (heap, TOAST, pages, tuples, MVCC)","Indexing (B-tree, Hash, GiST, SP-GiST, GIN, BRIN, bloom)","Query Planner (cost estimation, join strategies, parallel queries)","Transactions (isolation levels, SSI, advisory locks)","Replication (streaming, logical, pglogical, Patroni)","Extensions (PostGIS, pg_vector, TimescaleDB, Citus)","Performance (EXPLAIN ANALYZE, pg_stat, auto_vacuum, connection pooling)","Partitioning (range, list, hash, declarative)"]),
    ("MongoDB Internals","mongodb_int",350,["Storage Engine (WiredTiger, B-tree, LSM, compression)","Replication (replica sets, oplog, elections, read preferences)","Sharding (shard keys, chunks, balancer, zones)","Aggregation (pipeline stages, $lookup, $merge, $out, expressions)","Indexing (compound, multikey, text, 2dsphere, TTL, partial)","Transactions (multi-document, read/write concerns, causal consistency)","Atlas (serverless, search, vector search, data federation)"]),
    ("Redis Internals","redis_int",250,["Data Structures (strings, lists, sets, sorted sets, hashes, streams)","Persistence (RDB, AOF, hybrid, BGSAVE)","Cluster (hash slots, resharding, failover)","Pub/Sub & Streams (consumer groups, acknowledgment)","Lua Scripting & Functions","Modules (RedisJSON, RediSearch, RedisTimeSeries, RedisGraph)","Performance (pipelining, memory optimization, big keys)"]),
    ("SQL Mastery","sql_mastery",400,["Window Functions (ROW_NUMBER, RANK, LAG, LEAD, NTILE, frames)","CTEs & Recursive Queries (hierarchical data, graph traversal)","JSON/JSONB Operations (path queries, aggregation, indexing)","Full-Text Search (tsvector, tsquery, ranking, fuzzy)","Query Optimization (indexes, statistics, join elimination, subquery flattening)","Stored Procedures & Functions (PL/pgSQL, PL/Python, triggers)","Database Design (normalization, denormalization, partitioning strategies)","Migration Strategies (zero-downtime, blue-green, expand-contract)"]),
    ("NewSQL & Distributed DB","newsql",300,["CockroachDB (distributed SQL, serializable isolation, geo-partitioning)","TiDB (HTAP, TiKV, TiFlash, Raft)","YugabyteDB (YSQL, YCQL, tablet splitting)","Vitess (MySQL sharding, vtgate, vttablet)","Consensus (Raft, Paxos, Multi-Raft)","CAP Theorem in Practice"]),
    ("Graph Databases","graph_db",200,["Neo4j (Cypher, APOC, GDS, graph algorithms)","Property Graph Model vs RDF","Graph Algorithms (PageRank, community detection, shortest path)","Use Cases (social networks, knowledge graphs, fraud detection)"]),
]

def get_database_internals_database():
    entries = []
    for name, did, hours, topics in _DB_ENTRIES:
        entries.append({"id": f"db_{did}", "name": name, "level": "advanced", "hours": hours, "topics": topics, "category": "database_internals"})
    return entries

# ═══════════════════════════════════════════════════════════════
# SECURITY DEEP DIVE — COMPLETE
# ═══════════════════════════════════════════════════════════════

_SECURITY_ENTRIES = [
    ("Application Security","appsec",400,["OWASP Top 10 (each vulnerability deep dive with code examples)","Input Validation & Sanitization (SQL injection, XSS, SSRF)","Authentication (passwords, MFA, WebAuthn/Passkeys, OAuth2, OIDC)","Authorization (RBAC, ABAC, ReBAC, policy engines)","Session Management (tokens, cookies, SameSite, CSRF protection)","API Security (rate limiting, input validation, CORS, CSP)","Secrets Management (Vault, AWS Secrets Manager, SOPS, sealed secrets)","Dependency Security (SCA, lock files, vulnerability scanning)"]),
    ("Cryptography Engineering","crypto_eng",350,["Symmetric Encryption (AES-GCM, ChaCha20-Poly1305, modes of operation)","Asymmetric Encryption (RSA, ECDSA, Ed25519, X25519)","Hash Functions (SHA-256, SHA-3, BLAKE3, Argon2, bcrypt)","TLS/SSL (handshake, certificates, cipher suites, mTLS)","PKI (certificate authorities, ACME, Let's Encrypt)","Zero-Knowledge Proofs (zk-SNARKs, zk-STARKs, Groth16)","Post-Quantum Cryptography (CRYSTALS-Kyber, CRYSTALS-Dilithium)"]),
    ("Cloud Security","cloud_sec",300,["Identity (IAM best practices, least privilege, just-in-time access)","Network Security (VPC, security groups, WAF, DDoS protection)","Container Security (image scanning, runtime security, Falco)","Supply Chain (SBOM, SLSA, Sigstore, cosign)","Compliance Automation (OPA, Kyverno, cloud-native policies)","Incident Response (runbooks, forensics, post-mortem)"]),
    ("Blockchain & Web3 Security","web3_sec",250,["Smart Contract Security (reentrancy, overflow, access control)","Solidity Security Patterns (checks-effects-interactions, pull payments)","DeFi Exploits (flash loan attacks, oracle manipulation, MEV)","Audit Methodology (static analysis, Slither, Mythril, Foundry)","Wallet Security (key management, multisig, MPC)"]),
]

def get_security_database():
    entries = []
    for name, did, hours, topics in _SECURITY_ENTRIES:
        entries.append({"id": f"sec_{did}", "name": name, "level": "advanced", "hours": hours, "topics": topics, "category": "security_deep"})
    return entries

# ═══════════════════════════════════════════════════════════════
# GAME DEVELOPMENT DEEP — COMPLETE
# ═══════════════════════════════════════════════════════════════

_GAMEDEV_DEEP = [
    ("Unity Mastery","unity_deep",600,["C# for Unity (MonoBehaviour lifecycle, ScriptableObjects, coroutines)","DOTS/ECS (entities, components, systems, Burst compiler, Jobs)","Shader Graph & VFX Graph","Physics (Rigidbody, colliders, joints, custom physics)","UI Toolkit & UGUI (runtime UI, editor extensions)","Addressables & Asset Bundles","Netcode for GameObjects & Entities","Profiling (Profiler, Memory Profiler, Frame Debugger)","Platforms (mobile, console, VR/AR, WebGL)"]),
    ("Unreal Engine Mastery","unreal_deep",700,["Blueprints (visual scripting, macros, interfaces, data tables)","C++ Gameplay Framework (AActor, UObject, GC, UPROPERTY, UFUNCTION)","Rendering (Nanite, Lumen, Virtual Shadow Maps, substrate)","World Partition & Level Streaming","Gameplay Ability System (GAS)","Niagara VFX System","MetaSounds (procedural audio)","Replication & Networking","Build & Deployment (packaging, cooking, platforms)"]),
    ("Godot Mastery","godot_deep",400,["GDScript Deep Dive (typed, signals, await, annotations)","Node System (scenes, composition, autoloads)","2D Engine (TileMapLayer, physics, animation, shaders)","3D Engine (CSG, GridMap, navigation, PBR materials)","C# in Godot (Godot.NET, signals, exports)","GDExtension (C/C++ integration, Rust bindings)","Multiplayer (high-level, ENet, WebSocket)","Export & Publishing (templates, platforms, CI/CD)"]),
    ("Game Audio","game_audio",250,["Audio Engines (FMOD, Wwise, Unity Audio, Unreal MetaSounds)","Spatial Audio (3D positioning, HRTF, ambisonics, occlusion)","Dynamic Music (layers, transitions, stingers, adaptive)","Sound Design (foley, synthesis, processing, implementation)","Performance (streaming, compression, memory budgets)"]),
    ("Game Production","game_prod",300,["Pre-Production (GDD, prototyping, vertical slice, pitch)","Production (milestones, sprints, build management, playtesting)","QA (test plans, regression, automated testing, certification)","Launch (marketing, community, press, store optimization)","Live Operations (seasons, events, monetization, analytics)","Post-Mortem (what went right/wrong, lessons learned)"]),
]

def get_gamedev_deep_database():
    entries = []
    for name, did, hours, topics in _GAMEDEV_DEEP:
        entries.append({"id": f"gd_{did}", "name": name, "level": "professional", "hours": hours, "topics": topics, "category": "game_dev_deep"})
    return entries

# ═══════════════════════════════════════════════════════════════
# SOFTWARE ENGINEERING PRACTICES — COMPLETE
# ═══════════════════════════════════════════════════════════════

_SE_ENTRIES = [
    ("Design Patterns","design_patterns",300,["Creational (Singleton, Factory, Abstract Factory, Builder, Prototype)","Structural (Adapter, Bridge, Composite, Decorator, Facade, Flyweight, Proxy)","Behavioral (Chain of Responsibility, Command, Iterator, Mediator, Memento, Observer, State, Strategy, Template, Visitor)","Concurrency (Active Object, Monitor, Thread Pool, Producer-Consumer)","Game Patterns (Game Loop, Update Method, Component, Service Locator, Object Pool, Spatial Partition)"]),
    ("System Design","sys_design",400,["Scalability (horizontal, vertical, database sharding, caching)","Load Balancing (algorithms, health checks, session persistence)","Caching (CDN, application, database, invalidation strategies)","Message Queues (async processing, at-least-once, exactly-once)","Microservices (decomposition, communication, data management)","Distributed Systems (consistency, availability, partition tolerance)","Real-World Systems (URL shortener, chat, notification, rate limiter, search engine, social feed, video streaming)"]),
    ("Code Quality","code_quality",200,["Clean Code (naming, functions, classes, formatting, comments)","SOLID Principles (with real examples and violations)","Refactoring (catalog of refactorings, code smells, when to refactor)","Code Review (best practices, automated checks, constructive feedback)","Technical Debt (measurement, management, repayment strategies)","Static Analysis (linters, formatters, type checkers, custom rules)"]),
    ("Version Control","version_control",150,["Git Internals (objects, refs, packfiles, index)","Branching Strategies (GitFlow, trunk-based, GitHub Flow, ship/show/ask)","Advanced Git (rebase, cherry-pick, bisect, reflog, worktrees)","Monorepo (Nx, Turborepo, Lerna, Bazel, Rush)","Code Review Workflows (PR templates, CODEOWNERS, auto-merge)"]),
    ("Documentation","documentation",150,["API Documentation (OpenAPI, AsyncAPI, GraphQL SDL)","Architecture Decision Records (ADRs, lightweight RFCs)","Technical Writing (tutorials, how-tos, reference, explanation)","Diagramming (C4 model, Mermaid, PlantUML, architecture diagrams)","Knowledge Management (wikis, runbooks, playbooks)"]),
]

def get_software_engineering_database():
    entries = []
    for name, did, hours, topics in _SE_ENTRIES:
        entries.append({"id": f"se_{did}", "name": name, "level": "professional", "hours": hours, "topics": topics, "category": "software_engineering"})
    return entries


# ═══════════════════════════════════════════════════════════════
# AGGREGATED EXPORT FOR ALL EXPANDED DOMAINS
# ═══════════════════════════════════════════════════════════════

def get_all_expanded_databases():
    """Return ALL expanded knowledge databases for seeding."""
    return {
        "languages_deep": get_languages_database(),
        "devops_cloud": get_devops_database(),
        "data_engineering": get_data_engineering_database(),
        "ml_ai_deep": get_ml_ai_database(),
        "mobile_dev": get_mobile_database(),
        "testing_qa": get_testing_database(),
        "api_web": get_api_web_database(),
        "database_internals": get_database_internals_database(),
        "security_deep": get_security_database(),
        "game_dev_deep": get_gamedev_deep_database(),
        "software_engineering": get_software_engineering_database(),
    }


def get_expanded_quiz_domains():
    """Generate 5,000 MORE quizzes for the new domains."""
    random.seed(2026)
    quizzes = []
    counter = 10000  # Start after existing 10k

    new_domains = {
        "languages_deep": {
            "topics": ["python","javascript","typescript","rust","go","cpp","java","csharp","swift","kotlin","ruby","php","scala","elixir","haskell"],
            "questions": [
                ("In {lang}, what handles {concept}?", ["Garbage collector","Reference counting","Ownership system","Manual allocation","ARC","JVM GC","BEAM VM"]),
                ("Which {lang} feature enables {purpose}?", ["Generics","Traits/Interfaces","Macros","Decorators","Extensions","Protocols","Type classes"]),
                ("The {lang} concurrency model uses?", ["Goroutines","Coroutines","Virtual threads","Actors","Async/await","Green threads","Fibers"]),
            ],
            "lang": ["Python","JavaScript","TypeScript","Rust","Go","C++","Java","C#","Swift","Kotlin","Ruby","PHP","Scala","Elixir","Haskell"],
            "concept": ["memory management","concurrency","error handling","type safety","metaprogramming","dependency injection"],
            "purpose": ["code reuse","compile-time checks","runtime polymorphism","domain-specific languages","null safety","pattern matching"],
        },
        "devops_expanded": {
            "topics": ["docker","kubernetes","terraform","cicd","aws","gcp","azure","observability","linux"],
            "questions": [
                ("In Kubernetes, {resource} is used for?", ["Running stateless apps","Running stateful apps","Scheduled jobs","Node-level daemons","Batch processing","Configuration","Secrets"]),
                ("Which AWS service handles {usecase}?", ["Lambda","S3","DynamoDB","SQS","CloudFront","ECS","RDS","Kinesis","Bedrock"]),
                ("In Docker, {feature} provides?", ["Layer caching","Multi-stage builds","Network isolation","Volume persistence","Resource limits","Health checks"]),
            ],
            "resource": ["Deployment","StatefulSet","DaemonSet","Job","CronJob","ConfigMap","Secret","Ingress","Service","PersistentVolumeClaim"],
            "usecase": ["serverless compute","object storage","NoSQL database","message queuing","CDN","container orchestration","relational database","real-time streaming","AI/ML"],
            "feature": ["BuildKit","compose profiles","overlay networks","bind mounts","cgroup limits","HEALTHCHECK instruction"],
        },
        "data_eng": {
            "topics": ["spark","kafka","airflow","dbt","snowflake","flink","delta_lake"],
            "questions": [
                ("In Apache Spark, {component} handles?", ["Lazy transformations","Eager actions","Query optimization","Memory management","Shuffle operations","Broadcast variables"]),
                ("Kafka's {feature} ensures?", ["At-least-once delivery","Exactly-once semantics","Message ordering","Consumer rebalancing","Schema evolution","Data retention"]),
            ],
            "component": ["RDD transformations","DataFrame API","Catalyst optimizer","Tungsten engine","Shuffle Manager","Broadcast Manager"],
            "feature": ["idempotent producers","transactional API","partition ordering","consumer groups","Schema Registry","log compaction"],
        },
        "testing_expanded": {
            "topics": ["unit","integration","e2e","performance","security","architecture"],
            "questions": [
                ("Which testing technique catches {issue}?", ["Unit testing","Integration testing","E2E testing","Load testing","Fuzzing","Static analysis","Contract testing"]),
                ("In {framework}, how do you handle {scenario}?", ["Mocking","Stubbing","Fixtures","Factories","Snapshots","Golden tests","Property-based tests"]),
            ],
            "issue": ["logic errors","API contract breaks","UI regressions","performance degradation","security vulnerabilities","memory leaks","race conditions"],
            "framework": ["Jest","pytest","JUnit","Playwright","Cypress","k6","Detox","RSpec"],
            "scenario": ["external dependencies","async operations","database state","authentication","file uploads","websocket connections"],
        },
        "mobile_expanded": {
            "topics": ["ios","android","react_native","flutter","cross_platform"],
            "questions": [
                ("In {platform} development, {pattern} is used for?", ["State management","Navigation","Dependency injection","Data persistence","Background tasks","Push notifications"]),
                ("Which {platform} API handles {feature}?", ["Camera","Location","Notifications","Biometrics","In-App Purchases","Background Fetch","Widgets"]),
            ],
            "platform": ["iOS/SwiftUI","Android/Compose","React Native","Flutter","KMP"],
            "pattern": ["MVVM","TCA","BLoC","Redux","Coordinator","Repository"],
            "feature": ["camera access","GPS location","push notifications","fingerprint/face auth","subscriptions","background sync","home screen widgets"],
        },
    }

    difficulties = ["beginner","intermediate","advanced","expert","master"]
    diff_weights = [0.20, 0.30, 0.25, 0.15, 0.10]

    for domain_key, domain in new_domains.items():
        for i in range(1000):
            counter += 1
            topic = random.choice(domain["topics"])
            import re as _re
            template_q, template_answers = random.choice(domain["questions"])
            placeholders = _re.findall(r'\{(\w+)\}', template_q)
            subs = {}
            for ph in placeholders:
                if ph in domain:
                    subs[ph] = random.choice(domain[ph])
                else:
                    subs[ph] = ph.replace("_"," ").title()
            question_text = template_q.format(**subs)
            correct = random.choice(template_answers)
            wrong = [a for a in template_answers if a != correct]
            random.shuffle(wrong)
            options = [correct] + wrong[:3]
            random.shuffle(options)
            diff = random.choices(difficulties, weights=diff_weights, k=1)[0]
            quizzes.append({
                "id": f"quiz_exp_{domain_key}_{i:05d}",
                "domain": domain_key,
                "topic": topic,
                "question": question_text,
                "options": options,
                "correct_answer": correct,
                "difficulty": diff,
                "explanation": f"This tests {topic.replace('_',' ')} knowledge in {domain_key.replace('_',' ')}. Answer: {correct}.",
                "hints": [f"Think about {topic.replace('_',' ')} core concepts.", f"Consider how {subs.get(placeholders[0],'it') if placeholders else topic} works."],
                "tags": [domain_key, topic, diff],
                "points": {"beginner":10,"intermediate":20,"advanced":30,"expert":50,"master":100}.get(diff,20),
                "time_limit_seconds": {"beginner":30,"intermediate":45,"advanced":60,"expert":90,"master":120}.get(diff,45),
                "interactive": True,
                "quiz_number": counter,
            })
    random.shuffle(quizzes)
    return quizzes
