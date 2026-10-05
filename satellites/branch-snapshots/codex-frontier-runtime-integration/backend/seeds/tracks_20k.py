"""
20K Hours Expansion — New high-hour tracks and academies to push past 20,000 total curriculum hours.
"""
def get_20k_tracks():
    # Deferred import: academy_data is heavy; keep it out of module top-level
    # so importing this module at boot stays cheap (cold-start win).
    from seeds.academy_data import _lesson, _module, _project, _assessment, _question
    return [
        {"id":"fullstack_web","name":"Full-Stack Web Engineering","icon":"globe","color":"#3B82F6","total_hours":1900,"category":"subject",
         "description":"Complete full-stack web development from HTML to production deployment at scale.",
         "certificate":"Full-Stack Web Engineer","modules":[
             _module("fsw_fe","Frontend Engineering","HTML, CSS, JS, React, Next.js, performance",120,[
                 _lesson("fsw_f1","Modern HTML & CSS","Semantic HTML5, Flexbox, Grid, animations, responsive",120,"beginner",["html","css"],"Semantic: header,nav,main,article,aside,footer\nFlexbox: display:flex, justify-content, align-items, gap\nGrid: grid-template-columns, grid-template-areas, auto-fit\nAnimations: @keyframes, transition, transform\nResponsive: media queries, clamp(), container queries"),
                 _lesson("fsw_f2","JavaScript Deep Dive","ES6+, async, DOM, events, modules, tooling",120,"intermediate",["javascript","es6","dom"],"Closures, promises, async/await, generators\nDOM: querySelector, addEventListener, MutationObserver\nModules: import/export, dynamic import, tree shaking\nTooling: Vite, esbuild, webpack, ESLint, Prettier"),
                 _lesson("fsw_f3","React Production","Hooks, state, routing, testing, SSR, performance",120,"advanced",["react","nextjs","ssr"],"useState, useEffect, useRef, useMemo, useCallback\nState: Zustand, Redux Toolkit, React Query\nRouting: Next.js App Router, Remix\nTesting: Vitest, Testing Library, Playwright\nSSR/SSG: Next.js, Remix, Astro"),
             ],_project("fsw_proj1","SaaS Dashboard","Build a production SaaS dashboard","advanced",50,["Next.js 14+ App Router","Auth (JWT + OAuth)","Dashboard with charts","CRUD with optimistic updates","Stripe payments","Vercel deployment"],tags=["fullstack","react","nextjs"])),
             _module("fsw_be","Backend Engineering","Node.js, Python, databases, APIs, auth",120,[
                 _lesson("fsw_b1","API Design & Development","REST, GraphQL, gRPC, validation, error handling",120,"intermediate",["api","rest","graphql"],"REST: resources, methods, status codes, pagination\nGraphQL: schema, queries, mutations, subscriptions\ngRPC: protobuf, streaming, service mesh\nValidation: Zod, Pydantic, class-validator"),
                 _lesson("fsw_b2","Database Mastery","SQL, NoSQL, caching, migrations, optimization",120,"intermediate",["database","sql","nosql"],"PostgreSQL: JSONB, full-text, partitioning, CTEs\nMongoDB: aggregation, indexing, sharding\nRedis: caching, pub/sub, streams, leaderboards\nORM: Prisma, SQLAlchemy, Drizzle"),
             ],_project("fsw_proj2","API Platform","Build a multi-tenant API platform","advanced",60,["Multi-tenant architecture","Rate limiting & API keys","PostgreSQL + Redis","WebSocket real-time","Docker + K8s deployment","Monitoring stack"],tags=["backend","api","database"])),
         ]},
        {"id":"cloud_native","name":"Cloud Native Engineering","icon":"cloud","color":"#0EA5E9","total_hours":1700,"category":"subject",
         "description":"Master cloud architecture, serverless, containers, and infrastructure at scale.",
         "certificate":"Cloud Native Architect","modules":[
             _module("cn_aws","AWS Solutions Architecture","EC2, Lambda, S3, RDS, DynamoDB, ECS, CDK",100,[
                 _lesson("cn_a1","AWS Compute & Networking","EC2, Lambda, ECS, VPC, ALB, CloudFront, Route53",120,"intermediate",["aws","compute","networking"],"EC2: instance types, ASG, launch templates\nLambda: handlers, layers, destinations, step functions\nECS/Fargate: task definitions, services, load balancing\nVPC: subnets, security groups, NAT, VPC peering"),
                 _lesson("cn_a2","AWS Data & Storage","S3, RDS, DynamoDB, ElastiCache, Kinesis, SQS",120,"intermediate",["aws","database","storage"],"S3: lifecycle, versioning, cross-region replication\nRDS: Aurora, read replicas, Multi-AZ\nDynamoDB: single-table design, GSI, streams\nKinesis: real-time streaming, analytics"),
             ],_project("cn_proj1","Serverless Platform","Build a serverless event-driven system","advanced",50,["Lambda + API Gateway","DynamoDB + S3","SQS + EventBridge","Step Functions orchestration","CDK infrastructure","CloudWatch monitoring"],tags=["aws","serverless","cloud"])),
             _module("cn_k8s","Kubernetes & Service Mesh","Production K8s, Helm, Istio, GitOps",100,[
                 _lesson("cn_k1","Production Kubernetes","Deployments, StatefulSets, DaemonSets, CRDs, operators",120,"advanced",["kubernetes","production"],"StatefulSets: ordered, stable network IDs\nDaemonSets: one pod per node (logging, monitoring)\nCRDs: custom resource definitions\nOperators: automate complex stateful applications\nHPA/VPA: auto-scaling"),
             ],_project("cn_proj2","K8s Platform","Deploy a multi-service app on K8s","advanced",60,["Helm charts for all services","Istio service mesh","ArgoCD GitOps","Prometheus + Grafana","EFK logging stack","Chaos engineering"],tags=["kubernetes","devops","cloud"])),
         ]},
        {"id":"ai_engineering","name":"AI/ML Engineering","icon":"hardware-chip","color":"#7C3AED","total_hours":2100,"category":"subject",
         "description":"Complete AI engineering from classical ML to LLMs, RAG, fine-tuning, and production deployment.",
         "certificate":"AI/ML Engineer Professional","modules":[
             _module("aie_ml","Classical ML & Deep Learning","Regression, classification, CNNs, RNNs, transformers",120,[
                 _lesson("aie_m1","Supervised & Unsupervised ML","Linear/logistic regression, trees, SVM, KNN, clustering, PCA",120,"intermediate",["ml","supervised","unsupervised"],"Supervised: labeled data → predict\nUnsupervised: find structure (clustering, dimensionality)\nPipeline: preprocess → train → evaluate → tune\nMetrics: accuracy, precision, recall, F1, AUC-ROC"),
                 _lesson("aie_m2","Deep Learning & Neural Networks","CNNs, RNNs, attention, transformers, GANs",120,"advanced",["dl","cnn","rnn","transformer"],"CNN: convolution → pooling → flatten → dense\nRNN/LSTM: sequential data, text, time series\nTransformer: self-attention, multi-head, positional encoding\nGAN: generator vs discriminator adversarial training"),
             ],_project("aie_proj1","Image Classifier","Build and deploy an image classification model","advanced",40,["PyTorch CNN from scratch","Transfer learning (ResNet/EfficientNet)","Data augmentation pipeline","MLflow experiment tracking","FastAPI model serving","Docker deployment"],tags=["ml","pytorch","computer-vision"])),
             _module("aie_llm","LLMs, RAG & Fine-Tuning","GPT, embeddings, vector search, LoRA, deployment",120,[
                 _lesson("aie_l1","LLM Applications","Prompt engineering, RAG, agents, function calling",120,"advanced",["llm","rag","agents"],"Prompt engineering: system/user/assistant, few-shot, CoT\nRAG: chunk → embed → vector DB → retrieve → generate\nAgents: ReAct, tool use, multi-step reasoning\nFunction calling: structured output, tool integration"),
                 _lesson("aie_l2","Fine-Tuning & Deployment","LoRA, QLoRA, RLHF, quantization, serving",120,"expert",["fine-tuning","lora","deployment"],"LoRA: low-rank adaptation, trainable adapters\nQLoRA: 4-bit quantized base + LoRA\nRLHF: reinforcement learning from human feedback\nServing: vLLM, TGI, Triton, ONNX Runtime"),
             ],_project("aie_proj2","RAG Chatbot","Build a production RAG chatbot","expert",50,["Document ingestion pipeline","ChromaDB/Pinecone vector store","LangChain/LlamaIndex orchestration","Streaming responses","Evaluation framework","Production deployment"],tags=["llm","rag","chatbot"])),
         ]},
        {"id":"mobile_engineering","name":"Mobile Engineering","icon":"phone-portrait","color":"#EC4899","total_hours":1700,"category":"subject",
         "description":"Master cross-platform and native mobile development for iOS and Android.",
         "certificate":"Mobile Engineer Professional","modules":[
             _module("mob_rn","React Native & Expo","Components, navigation, state, animations, native modules",100,[
                 _lesson("mob_r1","React Native Production","FlatList, navigation, gestures, Reanimated, native modules",120,"intermediate",["react-native","expo"],"FlatList: virtualization, keyExtractor, getItemLayout\nNavigation: Stack, Tabs, Drawer, deep linking\nAnimations: Reanimated, shared element transitions\nNative: camera, location, push notifications, biometrics"),
             ],_project("mob_proj1","Social Media App","Build a full social media mobile app","advanced",60,["Feed with infinite scroll","Stories & real-time chat","Camera with filters","Push notifications","Offline-first with sync","App Store submission"],tags=["react-native","mobile","social"])),
             _module("mob_native","Native iOS & Android","SwiftUI, Jetpack Compose, platform APIs",100,[
                 _lesson("mob_n1","SwiftUI & Compose","Declarative UI, state, navigation, platform features",120,"advanced",["swiftui","compose","native"],"SwiftUI: @State, @Observable, NavigationStack, async/await\nCompose: remember, LazyColumn, Scaffold, ViewModel\nPlatform: HealthKit, ARKit, ML Kit, App Clips/Instant Apps"),
             ],_project("mob_proj2","Fitness Tracker","Build a native fitness app","advanced",50,["HealthKit/Health Connect","GPS tracking & maps","Charts & statistics","Watch companion app","Widget extensions","In-app purchases"],tags=["mobile","native","health"])),
         ]},
        {"id":"game_engineering","name":"Game Engineering","icon":"game-controller","color":"#F59E0B","total_hours":1900,"category":"subject",
         "description":"Advanced game development: engine architecture, graphics, networking, and AI.",
         "certificate":"Game Engineer Professional","modules":[
             _module("ge_engine","Game Engine Architecture","Render pipeline, ECS, physics, asset management",120,[
                 _lesson("ge_e1","Engine Architecture","Game loop, ECS, scene graph, asset pipeline, scripting",120,"advanced",["game-engine","ecs","architecture"],"Game loop: fixed timestep physics, variable render\nECS: entities, components, systems, archetypes\nScene graph: spatial hierarchy, transforms, culling\nAsset pipeline: import, compress, stream, hot-reload"),
                 _lesson("ge_e2","Graphics Programming","Shaders, lighting, shadows, post-processing, PBR",120,"advanced",["graphics","shaders","opengl","vulkan"],"Rendering pipeline: vertex → fragment → framebuffer\nPBR: metallic-roughness, Cook-Torrance BRDF\nShadows: shadow maps, PCF, cascaded\nPost-processing: bloom, SSAO, tone mapping, FXAA"),
             ],_project("ge_proj1","Custom Game Engine","Build a 2D game engine from scratch","expert",80,["OpenGL/Vulkan renderer","ECS implementation","Physics engine (AABB, SAT)","Audio system","Scene editor","Scripting (Lua/C#)"],tags=["game-engine","graphics","ecs"])),
             _module("ge_multi","Multiplayer & Networking","Client-server, prediction, lag compensation, matchmaking",80,[
                 _lesson("ge_m1","Game Networking","Client prediction, server reconciliation, lag compensation",120,"advanced",["networking","multiplayer","prediction"],"Client-side prediction: simulate locally, reconcile with server\nServer authority: validate all actions server-side\nLag compensation: rewind server state for hit detection\nNetcode: UDP, reliable ordered channels, delta compression"),
             ],_project("ge_proj2","Online Multiplayer Game","Build an online multiplayer game","expert",60,["Authoritative server","Client prediction + reconciliation","Matchmaking system","Anti-cheat foundation","Replay system","Dedicated server deployment"],tags=["multiplayer","networking","game"])),
         ]},
        {"id":"data_engineering_full","name":"Data Engineering","icon":"server","color":"#06B6D4","total_hours":1700,"category":"subject",
         "description":"Master data pipelines, warehousing, streaming, and analytics at scale.",
         "certificate":"Data Engineer Professional","modules":[
             _module("de_pipelines","Data Pipelines","ETL, ELT, Airflow, dbt, data quality",100,[
                 _lesson("de_p1","Pipeline Design","Batch vs streaming, ETL vs ELT, orchestration, idempotency",120,"intermediate",["data-pipeline","etl","batch","streaming"],"Batch: scheduled, large volumes, high throughput\nStreaming: real-time, event-driven, low latency\nETL: extract→transform→load (traditional)\nELT: extract→load→transform (modern cloud)\nIdempotency: re-running produces same result"),
                 _lesson("de_p2","Orchestration & Quality","Airflow, Prefect, dbt, Great Expectations",120,"advanced",["airflow","dbt","data-quality"],"Airflow: DAGs, operators, sensors, XCom\ndbt: SQL transforms, refs, tests, docs\nData quality: schema validation, anomaly detection\nMonitoring: SLAs, freshness, completeness"),
             ],_project("de_proj1","Analytics Platform","Build a complete analytics data platform","advanced",60,["Ingestion: Kafka + Debezium CDC","Processing: Spark/dbt","Warehouse: BigQuery/Snowflake","Orchestration: Airflow","Quality: Great Expectations","Dashboard: Metabase/Superset"],tags=["data-engineering","pipeline","analytics"])),
             _module("de_streaming","Real-Time Streaming","Kafka, Flink, Spark Streaming, event processing",80,[
                 _lesson("de_s1","Stream Processing","Kafka Streams, Flink, windowing, exactly-once",120,"advanced",["kafka","flink","streaming","windowing"],"Windows: tumbling, sliding, session, global\nWatermarks: handle late-arriving data\nState management: RocksDB, checkpointing\nExactly-once: idempotent writes + transactional processing"),
             ],_project("de_proj2","Real-Time Dashboard","Build a real-time analytics dashboard","advanced",50,["Kafka event ingestion","Flink stream processing","ClickHouse for analytics","WebSocket real-time push","Grafana dashboards","Alerting system"],tags=["streaming","real-time","analytics"])),
         ]},
        {"id":"blockchain_full","name":"Blockchain & Web3 Engineering","icon":"link","color":"#F97316","total_hours":1000,"category":"subject",
         "description":"Master smart contracts, DeFi, NFTs, and decentralized application development.",
         "certificate":"Web3 Engineer","modules":[
             _module("bc_smart","Smart Contract Development","Solidity, testing, security, deployment",80,[
                 _lesson("bc_s1","Solidity Deep Dive","ERC standards, storage, gas optimization, upgradeable contracts",120,"intermediate",["solidity","erc","gas","upgradeable"],"ERC-20: fungible tokens\nERC-721: NFTs\nERC-1155: multi-token\nProxy patterns: UUPS, Transparent, Beacon\nGas optimization: storage packing, calldata, immutable"),
             ],_project("bc_proj1","DeFi Protocol","Build a lending/borrowing DeFi protocol","advanced",60,["ERC-20 token","Lending pool with interest","Liquidation mechanism","Oracle integration (Chainlink)","Hardhat tests + deployment","Frontend with wagmi/viem"],tags=["defi","solidity","web3"])),
         ]},
        {"id":"systems_programming","name":"Systems Programming","icon":"hardware-chip","color":"#64748B","total_hours":1500,"category":"subject",
         "description":"Low-level systems: OS concepts, networking, compilers, databases from scratch.",
         "certificate":"Systems Programmer","modules":[
             _module("sp_os","Operating Systems","Processes, threads, memory, file systems, scheduling",100,[
                 _lesson("sp_o1","OS Fundamentals","Processes, threads, scheduling, synchronization, memory",120,"advanced",["os","processes","threads","memory"],"Process: running program with own address space\nThread: lightweight, shared memory\nScheduling: round-robin, priority, CFS\nSync: mutex, semaphore, condition variable\nMemory: virtual memory, paging, TLB, page faults"),
                 _lesson("sp_o2","Advanced OS","File systems, I/O, networking stack, containers",120,"expert",["os","filesystem","networking","containers"],"File systems: ext4, btrfs, ZFS — inodes, journaling\nI/O: blocking, non-blocking, epoll/kqueue, io_uring\nNetwork stack: socket, TCP state machine, zero-copy\nContainers: namespaces, cgroups, overlay FS"),
             ],_project("sp_proj1","Build a Shell","Implement a Unix shell","advanced",40,["Command parsing & execution","Pipes and redirection","Job control (bg/fg)","Signal handling","Built-in commands (cd, export)","History & tab completion"],tags=["systems","shell","os","c"])),
             _module("sp_compiler","Compilers & Interpreters","Lexing, parsing, AST, code generation",80,[
                 _lesson("sp_c1","Compiler Design","Lexer, parser, AST, type checking, code generation",120,"expert",["compiler","lexer","parser","ast"],"Phases: source → lexer → tokens → parser → AST → semantic analysis → IR → optimization → code gen\nLexer: regex → tokens (DFA)\nParser: recursive descent, Pratt parsing\nAST: abstract syntax tree representation\nCode gen: bytecode, LLVM IR, or direct machine code"),
             ],_project("sp_proj2","Programming Language","Build an interpreter for a programming language","expert",60,["Lexer + parser","AST representation","Type system","Standard library","REPL interface","Error messages with source locations"],tags=["compiler","interpreter","language"])),
         ]},
    ]
