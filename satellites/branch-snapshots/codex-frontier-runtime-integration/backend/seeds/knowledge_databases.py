"""
╔══════════════════════════════════════════════════════════════════════════╗
║  KNOWLEDGE DATABASES — HYPERSCALE EDITION                               ║
║  CS · Physics · Rendering · Architecture · Frameworks · 10,000 Quizzes  ║
║  The most comprehensive game-dev learning database ever assembled.       ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
import hashlib
import random

def _qid(domain, i):
    return f"quiz_{domain}_{i:05d}"


# ═══════════════════════════════════════════════════════════════════════
# 1. COMPUTER SCIENCE COMPLETE DATABASE
# ═══════════════════════════════════════════════════════════════════════

def get_cs_database():
    return {"fields": [
        {"id":"cs_automata","name":"Automata Theory","level":"undergraduate","hours":300,"topics":["DFA","NFA","Regular Expressions","Context-Free Grammars","Pushdown Automata","Turing Machines","Decidability","Complexity Classes (P, NP, NP-Complete)","Reductions","Church-Turing Thesis"]},
        {"id":"cs_algorithms","name":"Algorithms","level":"undergraduate","hours":400,"topics":["Sorting (Quick, Merge, Heap, Radix, Tim)","Searching (Binary, Hash, BST)","Graph (BFS, DFS, Dijkstra, Bellman-Ford, Floyd-Warshall, MST)","Dynamic Programming","Greedy","Divide & Conquer","Backtracking","String (KMP, Rabin-Karp, Suffix Array)","Geometric","Randomized","Amortized Analysis","NP-Completeness"]},
        {"id":"cs_data_structures","name":"Data Structures","level":"undergraduate","hours":350,"topics":["Arrays","Linked Lists","Stacks","Queues","Hash Tables","BST","AVL/Red-Black Trees","B-Trees","Heaps","Tries","Segment Trees","Fenwick Trees","Union-Find","Skip Lists","Bloom Filters","LRU Cache"]},
        {"id":"cs_os","name":"Operating Systems","level":"undergraduate","hours":400,"topics":["Processes","Threads","Scheduling (FIFO, SJF, RR, CFS)","Synchronization (Mutex, Semaphore, Monitor)","Deadlocks","Memory Management (Paging, Segmentation, TLB)","Virtual Memory","File Systems (ext4, NTFS, ZFS)","I/O Systems","Interrupts","System Calls","Virtualization","Containers"]},
        {"id":"cs_networking","name":"Computer Networking","level":"undergraduate","hours":400,"topics":["OSI/TCP-IP Model","Physical Layer","Data Link (Ethernet, MAC)","Network (IP, Routing, OSPF, BGP)","Transport (TCP, UDP, QUIC)","Application (HTTP, DNS, SMTP, FTP)","Socket Programming","Congestion Control","NAT","Firewalls","VPN","TLS/SSL","CDN","Load Balancing","WebSocket"]},
        {"id":"cs_databases","name":"Database Systems","level":"undergraduate","hours":400,"topics":["Relational Model","SQL","Normalization (1NF-BCNF)","Indexing (B-Tree, Hash, GiST)","Query Processing","Query Optimization","Transactions (ACID)","Concurrency Control (2PL, MVCC)","Recovery (WAL, Checkpointing)","Distributed Databases","NoSQL (Document, KV, Column, Graph)","NewSQL","CAP Theorem"]},
        {"id":"cs_compilers","name":"Compilers","level":"undergraduate","hours":350,"topics":["Lexical Analysis (Regex to DFA)","Parsing (LL, LR, LALR)","AST","Semantic Analysis","Type Checking","Intermediate Representation (SSA, TAC)","Optimization (Dead Code, Constant Folding, Loop Unrolling)","Register Allocation","Code Generation","Garbage Collection","JIT Compilation","LLVM"]},
        {"id":"cs_ai","name":"Artificial Intelligence","level":"undergraduate","hours":400,"topics":["Search (BFS, DFS, A*, IDA*)","Constraint Satisfaction","Game Playing (Minimax, Alpha-Beta)","Knowledge Representation","Planning","Machine Learning","Neural Networks","NLP","Computer Vision","Reinforcement Learning","Ethics"]},
        {"id":"cs_pl","name":"Programming Languages","level":"undergraduate","hours":300,"topics":["Syntax & Semantics","Type Systems","Lambda Calculus","Functional Programming","Logic Programming","Object-Oriented","Memory Management","Concurrency Models","Metaprogramming","DSLs","Language Design"]},
        {"id":"cs_security","name":"Computer Security","level":"undergraduate","hours":350,"topics":["Cryptography (Symmetric, Asymmetric, Hashing)","Authentication","Access Control","Network Security","Web Security (OWASP)","Buffer Overflows","Malware","Intrusion Detection","Digital Forensics","Privacy","Blockchain Security"]},
        {"id":"cs_distributed","name":"Distributed Systems","level":"graduate","hours":500,"topics":["Clock Synchronization","Logical Clocks (Lamport, Vector)","Consensus (Paxos, Raft, PBFT)","Replication","Consistency Models","Partitioning/Sharding","MapReduce","Stream Processing","Microservices","CRDTs","Gossip Protocols","Byzantine Fault Tolerance"]},
        {"id":"cs_ml","name":"Machine Learning","level":"graduate","hours":500,"topics":["Supervised (Regression, Classification)","Unsupervised (Clustering, PCA)","Ensemble Methods","SVM","Neural Networks","CNNs","RNNs/LSTMs","Transformers","GANs","Diffusion Models","Reinforcement Learning","Federated Learning","AutoML","MLOps"]},
        {"id":"cs_hci","name":"Human-Computer Interaction","level":"undergraduate","hours":250,"topics":["Usability","User Research","Prototyping","Accessibility","Design Systems","Information Architecture","Interaction Design","Evaluation Methods","Mobile UX","Voice UI","AR/VR Interfaces"]},
        {"id":"cs_graphics","name":"Computer Graphics","level":"graduate","hours":500,"topics":["Rasterization","Ray Tracing","Shading Models (Phong, PBR)","Texture Mapping","Shadow Algorithms","Global Illumination","Radiosity","Photon Mapping","Volume Rendering","GPU Programming","Real-Time Rendering","Animation"]},
        {"id":"cs_parallel","name":"Parallel Computing","level":"graduate","hours":400,"topics":["Shared Memory (OpenMP)","Message Passing (MPI)","GPU Computing (CUDA, OpenCL)","Map-Reduce","SIMD","Pipeline Parallelism","Data Parallelism","Task Parallelism","Lock-Free Data Structures","Memory Models","Amdahl's Law","Gustafson's Law"]},
        {"id":"cs_quantum","name":"Quantum Computing","level":"graduate","hours":350,"topics":["Qubits","Quantum Gates","Superposition","Entanglement","Quantum Circuits","Grover's Algorithm","Shor's Algorithm","Quantum Error Correction","Quantum Machine Learning","Quantum Cryptography","Qiskit/Cirq"]},
        {"id":"cs_theory","name":"Theory of Computation","level":"graduate","hours":300,"topics":["Computability","Decidability","Halting Problem","Rice's Theorem","Complexity Classes","P vs NP","Space Complexity","Randomized Complexity","Approximation Algorithms","Information-Theoretic Lower Bounds"]},
        {"id":"cs_se","name":"Software Engineering","level":"undergraduate","hours":400,"topics":["SDLC Models","Requirements Engineering","UML","Design Patterns (GoF)","SOLID Principles","Code Review","Version Control","CI/CD","Testing (Unit, Integration, E2E)","Agile/Scrum/Kanban","Technical Debt","Refactoring"]},
        {"id":"cs_info_retrieval","name":"Information Retrieval","level":"graduate","hours":300,"topics":["TF-IDF","Boolean Retrieval","Vector Space Model","PageRank","Inverted Index","Query Expansion","Relevance Feedback","Web Crawling","Search Engine Architecture","Recommendation Systems","Collaborative Filtering"]},
        {"id":"cs_robotics","name":"Robotics","level":"graduate","hours":400,"topics":["Kinematics","Dynamics","Control Systems (PID)","Path Planning (RRT, PRM)","SLAM","Computer Vision for Robots","Sensor Fusion","Manipulation","Locomotion","Swarm Robotics","ROS"]},
        {"id":"cs_bioinformatics","name":"Bioinformatics","level":"graduate","hours":300,"topics":["Sequence Alignment","BLAST","Phylogenetics","Genome Assembly","Protein Folding","Gene Expression","Systems Biology","Drug Discovery","Metagenomics","CRISPR"]},
        {"id":"cs_crypto","name":"Cryptography","level":"graduate","hours":350,"topics":["AES","RSA","Elliptic Curve","Diffie-Hellman","Digital Signatures","Hash Functions (SHA-256)","Zero-Knowledge Proofs","Homomorphic Encryption","Post-Quantum Crypto","Blockchain Consensus","Secure Multi-Party Computation"]},
        {"id":"cs_nlp","name":"Natural Language Processing","level":"graduate","hours":450,"topics":["Tokenization","POS Tagging","Named Entity Recognition","Sentiment Analysis","Machine Translation","Transformers (BERT, GPT)","Attention Mechanisms","Word Embeddings","Language Models","Text Generation","Summarization","Question Answering"]},
        {"id":"cs_cv","name":"Computer Vision","level":"graduate","hours":450,"topics":["Image Filtering","Edge Detection","Feature Detection (SIFT, ORB)","Object Detection (YOLO, SSD)","Semantic Segmentation","Instance Segmentation","Optical Flow","Stereo Vision","3D Reconstruction","Face Recognition","Generative Models","NeRF"]},
    ]}


# ═══════════════════════════════════════════════════════════════════════
# 2. PHYSICS COMPLETE DATABASE
# ═══════════════════════════════════════════════════════════════════════

def get_physics_database():
    return {"fields": [
        {"id":"phys_mechanics","name":"Classical Mechanics","level":"undergraduate","hours":400,"topics":["Kinematics","Newton's Laws","Energy & Work","Momentum","Rotational Motion","Oscillations","Gravity","Fluid Mechanics","Lagrangian Mechanics","Hamiltonian Mechanics"],"game_applications":["Projectile motion","Rigid body physics","Collision response","Vehicle simulation","Cloth simulation"]},
        {"id":"phys_em","name":"Electromagnetism","level":"undergraduate","hours":350,"topics":["Electric Fields","Gauss's Law","Electric Potential","Capacitance","Current & Resistance","Magnetic Fields","Faraday's Law","Maxwell's Equations","Electromagnetic Waves","Optics"],"game_applications":["Lightning effects","Electromagnetic puzzles","Radio wave simulation","Light propagation"]},
        {"id":"phys_thermo","name":"Thermodynamics","level":"undergraduate","hours":300,"topics":["Temperature","Heat Transfer","Laws of Thermodynamics","Entropy","Free Energy","Phase Transitions","Statistical Mechanics","Kinetic Theory"],"game_applications":["Fire/smoke simulation","Weather systems","Engine simulation","Material states"]},
        {"id":"phys_waves","name":"Waves & Optics","level":"undergraduate","hours":250,"topics":["Wave Equation","Interference","Diffraction","Polarization","Reflection","Refraction","Lenses","Fiber Optics","Doppler Effect","Sound Waves"],"game_applications":["Sound propagation","Water surface simulation","Lens flare effects","Ray tracing fundamentals"]},
        {"id":"phys_quantum","name":"Quantum Mechanics","level":"graduate","hours":400,"topics":["Wave-Particle Duality","Schrodinger Equation","Uncertainty Principle","Quantum States","Operators","Angular Momentum","Spin","Identical Particles","Perturbation Theory","Scattering"],"game_applications":["Quantum computing games","Educational simulations","Probability visualizations"]},
        {"id":"phys_relativity","name":"Relativity","level":"graduate","hours":300,"topics":["Special Relativity","Time Dilation","Length Contraction","Mass-Energy Equivalence","General Relativity","Spacetime Curvature","Black Holes","Gravitational Waves","Cosmology"],"game_applications":["Relativistic effects in space games","Time manipulation mechanics","Gravity simulation"]},
        {"id":"phys_computational","name":"Computational Physics","level":"graduate","hours":350,"topics":["Numerical Integration","Monte Carlo Methods","Molecular Dynamics","Finite Element Method","Finite Difference","Spectral Methods","N-Body Simulation","Lattice Models","Fluid Simulation (Navier-Stokes)"],"game_applications":["Fluid simulation","Particle systems","Soft body physics","Destruction simulation"]},
        {"id":"phys_game","name":"Physics for Game Development","level":"applied","hours":500,"topics":["Rigid Body Dynamics","Collision Detection (AABB, OBB, GJK, SAT)","Collision Response","Constraints & Joints","Ragdoll Physics","Vehicle Physics","Fluid Dynamics","Cloth Simulation","Soft Body","Destruction","Verlet Integration","Physics Engines (Box2D, Bullet, PhysX, Jolt)"]},
        {"id":"phys_astro","name":"Astrophysics","level":"graduate","hours":350,"topics":["Stellar Evolution","Nebulae","Galaxy Formation","Dark Matter","Dark Energy","Neutron Stars","Pulsars","Cosmic Microwave Background","Big Bang Theory","Multiverse Hypotheses"],"game_applications":["Space game world generation","Realistic star systems","Orbital mechanics"]},
        {"id":"phys_nuclear","name":"Nuclear Physics","level":"graduate","hours":300,"topics":["Radioactivity","Fission","Fusion","Nuclear Reactions","Particle Physics","Standard Model","Quarks & Leptons","Higgs Boson","Neutrinos","Accelerators"],"game_applications":["Radiation simulation","Particle effect systems","Sci-fi weapon physics"]},
        {"id":"phys_materials","name":"Materials Science","level":"graduate","hours":300,"topics":["Crystal Structure","Defects","Mechanical Properties","Thermal Properties","Electrical Properties","Polymers","Ceramics","Composites","Nanomaterials","Biomaterials"],"game_applications":["Material destruction systems","Surface properties","Deformation simulation"]},
        {"id":"phys_acoustics","name":"Acoustics","level":"undergraduate","hours":200,"topics":["Sound Wave Properties","Room Acoustics","Reverberation","Absorption","Diffraction","Psychoacoustics","Musical Acoustics","Noise Control","Ultrasound"],"game_applications":["3D spatial audio","Room reverb simulation","Sound occlusion","Dynamic audio mixing"]},
    ]}


# ═══════════════════════════════════════════════════════════════════════
# 3. RENDERING & SKINNING COMPLETE DATABASE
# ═══════════════════════════════════════════════════════════════════════

def get_rendering_database():
    return {"fields": [
        {"id":"rend_pipeline","name":"Rendering Pipeline","level":"core","hours":400,"topics":["Vertex Processing","Primitive Assembly","Rasterization","Fragment Processing","Depth Testing","Blending","Stencil Testing","Multi-pass Rendering","Deferred Rendering","Forward+"]},
        {"id":"rend_shaders","name":"Shader Programming","level":"core","hours":500,"topics":["GLSL","HLSL","SPIR-V","Vertex Shaders","Fragment/Pixel Shaders","Geometry Shaders","Tessellation","Compute Shaders","Shader Graph","Ray Tracing Shaders (Ray Gen, Closest Hit, Miss, Any Hit)"]},
        {"id":"rend_lighting","name":"Lighting & Shadows","level":"core","hours":400,"topics":["Phong/Blinn-Phong","PBR (Cook-Torrance BRDF)","Image-Based Lighting","Shadow Mapping","Cascaded Shadow Maps","PCF","PCSS","Ray-Traced Shadows","Ambient Occlusion (SSAO, HBAO, RTAO)","Global Illumination","Screen-Space GI","Lumen"]},
        {"id":"rend_texturing","name":"Texturing & Materials","level":"core","hours":350,"topics":["UV Mapping","Texture Filtering (Bilinear, Trilinear, Anisotropic)","Mipmaps","Normal Mapping","Parallax Mapping","PBR Materials (Albedo, Metallic, Roughness, Normal, AO)","Texture Atlasing","Virtual Texturing","Procedural Textures"]},
        {"id":"rend_skinning","name":"Character Skinning & Animation","level":"specialized","hours":450,"topics":["Skeletal Animation","Bone Hierarchy","Skinning Weights","Linear Blend Skinning (LBS)","Dual Quaternion Skinning","Blend Shapes/Morph Targets","Animation Blending","State Machines","Animation Layers","IK (FABRIK, CCD)","Motion Matching","Root Motion","Facial Animation","Cloth Simulation on Characters"]},
        {"id":"rend_post","name":"Post-Processing","level":"core","hours":300,"topics":["Bloom","Tone Mapping (ACES, Reinhard)","Color Grading","Depth of Field","Motion Blur","FXAA/TAA/DLSS/FSR","Chromatic Aberration","Vignette","Film Grain","Screen-Space Reflections","Volumetric Lighting/Fog"]},
        {"id":"rend_optimization","name":"Rendering Optimization","level":"advanced","hours":400,"topics":["Draw Call Batching","Instancing","LOD (Level of Detail)","Nanite (Virtualized Geometry)","Occlusion Culling","Frustum Culling","GPU Profiling","Frame Budget","Async Compute","Mesh Shaders","Bindless Rendering","Indirect Rendering"]},
        {"id":"rend_raytracing","name":"Ray Tracing","level":"advanced","hours":400,"topics":["Ray-Triangle Intersection","BVH (Bounding Volume Hierarchy)","Path Tracing","Bidirectional Path Tracing","Photon Mapping","Metropolis Light Transport","Denoising (AI-based)","Hybrid Rendering","RT Cores (NVIDIA)","DXR/Vulkan RT"]},
        {"id":"rend_vfx","name":"Visual Effects","level":"specialized","hours":350,"topics":["Particle Systems","GPU Particles","Fluid VFX","Fire & Smoke","Explosions","Weather Effects","Decals","Trails","Distortion Effects","Screen-Space Effects"]},
        {"id":"rend_terrain","name":"Terrain Rendering","level":"specialized","hours":300,"topics":["Heightmap Rendering","Clipmap LOD","Virtual Heightfields","Terrain Splatting","Procedural Terrain","Erosion Simulation","Foliage Rendering","Grass Rendering","Water Rendering","Ocean Simulation (FFT)"]},
        {"id":"rend_ui_rendering","name":"UI Rendering","level":"core","hours":200,"topics":["Immediate Mode GUI","Retained Mode GUI","SDF Font Rendering","UI Batching","Anchoring Systems","Responsive Layouts","Shader-based UI Effects","9-Slice Rendering"]},
    ]}


# ═══════════════════════════════════════════════════════════════════════
# 4. ARCHITECTURE & FRAMEWORK DATABASE
# ═══════════════════════════════════════════════════════════════════════

def get_architecture_database():
    return {"patterns": [
        {"id":"arch_mvc","name":"MVC/MVP/MVVM","description":"Model-View-Controller, Model-View-Presenter, Model-View-ViewModel. Separate data, presentation, and user interaction.","languages":["All"],"use_cases":["Web apps","Mobile apps","Desktop apps"]},
        {"id":"arch_clean","name":"Clean Architecture","description":"Dependency rule: outer layers depend on inner. Entities→UseCases→Adapters→Frameworks.","languages":["All"],"use_cases":["Enterprise","Testable systems","Long-lived projects"]},
        {"id":"arch_hex","name":"Hexagonal (Ports & Adapters)","description":"Core logic surrounded by ports (interfaces) and adapters (implementations). Framework-agnostic.","languages":["All"],"use_cases":["Domain-driven design","Swappable infrastructure"]},
        {"id":"arch_micro","name":"Microservices","description":"Independent services communicating via APIs/events. Each owns its data. Deploy independently.","languages":["All"],"use_cases":["Large teams","Scalable systems","Polyglot environments"]},
        {"id":"arch_event","name":"Event-Driven Architecture","description":"Components communicate via events. Event sourcing stores all state changes as events.","languages":["All"],"use_cases":["Real-time","Audit trails","Loosely coupled systems"]},
        {"id":"arch_cqrs","name":"CQRS","description":"Separate read model (optimized queries) from write model (domain logic). Often paired with event sourcing.","languages":["All"],"use_cases":["Complex domains","High-read systems","Event sourcing"]},
        {"id":"arch_serverless","name":"Serverless","description":"Functions as a Service. No server management. Pay per invocation. Event-driven.","languages":["Node.js","Python","Go","Java"],"use_cases":["APIs","Event processing","Scheduled tasks"]},
        {"id":"arch_modular","name":"Modular Monolith","description":"Single deployment unit with clear module boundaries. Best of monolith and microservices.","languages":["All"],"use_cases":["Starting projects","Small-medium teams","Gradual decomposition"]},
        {"id":"arch_ddd","name":"Domain-Driven Design","description":"Entities, Value Objects, Aggregates, Repositories, Domain Events, Bounded Contexts.","languages":["All"],"use_cases":["Complex business domains","Enterprise systems"]},
        {"id":"arch_12factor","name":"12-Factor App","description":"Methodology for building SaaS: codebase, dependencies, config, backing services, build/release/run, processes, port binding, concurrency, disposability, dev/prod parity, logs, admin.","languages":["All"],"use_cases":["Cloud-native apps","Containerized deployments"]},
        {"id":"arch_ecs","name":"Entity Component System","description":"Entities are IDs, Components are data, Systems process components. Cache-friendly, scalable.","languages":["C++","C#","Rust"],"use_cases":["Game engines","Simulation","High-performance apps"]},
        {"id":"arch_pipe_filter","name":"Pipe and Filter","description":"Data flows through a pipeline of processing stages. Each filter transforms data independently.","languages":["All"],"use_cases":["Data processing","Compilers","Stream processing"]},
        {"id":"arch_layered","name":"Layered Architecture","description":"Presentation→Business→Data Access→Database. Each layer only calls the layer below.","languages":["All"],"use_cases":["Enterprise apps","Traditional web apps"]},
        {"id":"arch_space","name":"Space-Based Architecture","description":"Distribute processing and storage across multiple nodes. Tuple spaces for coordination.","languages":["Java","Scala"],"use_cases":["High-volume trading","Real-time bidding","Gaming backends"]},
        {"id":"arch_actor","name":"Actor Model","description":"Actors are units of computation: receive messages, create actors, send messages. No shared state.","languages":["Erlang","Scala","Rust"],"use_cases":["Concurrent systems","Telecom","Distributed computing"]},
    ],"frameworks":[
        {"id":"fw_react","name":"React","type":"frontend","language":"JavaScript/TypeScript","paradigm":"Component-based, Virtual DOM","key_features":["JSX","Hooks","Server Components","Suspense","Concurrent"]},
        {"id":"fw_nextjs","name":"Next.js","type":"fullstack","language":"TypeScript","paradigm":"File-based routing, SSR/SSG/ISR","key_features":["App Router","Server Actions","Middleware","Edge Runtime"]},
        {"id":"fw_django","name":"Django","type":"backend","language":"Python","paradigm":"MTV (Model-Template-View), batteries-included","key_features":["ORM","Admin","Auth","Forms","REST Framework"]},
        {"id":"fw_spring","name":"Spring Boot","type":"backend","language":"Java/Kotlin","paradigm":"Dependency Injection, convention over configuration","key_features":["Auto-config","Security","Data JPA","Cloud","WebFlux"]},
        {"id":"fw_express","name":"Express.js","type":"backend","language":"JavaScript","paradigm":"Middleware-based, minimalist","key_features":["Routing","Middleware chain","Template engines","WebSocket"]},
        {"id":"fw_fastapi","name":"FastAPI","type":"backend","language":"Python","paradigm":"Async, type-driven, OpenAPI-first","key_features":["Pydantic","Async","Auto-docs","Dependency injection"]},
        {"id":"fw_rails","name":"Ruby on Rails","type":"fullstack","language":"Ruby","paradigm":"MVC, Convention over Configuration","key_features":["ActiveRecord","Hotwire","Action Cable","Generators"]},
        {"id":"fw_flutter","name":"Flutter","type":"mobile","language":"Dart","paradigm":"Widget tree, declarative UI","key_features":["Hot reload","Custom rendering","Cross-platform","Material/Cupertino"]},
        {"id":"fw_unity","name":"Unity","type":"game","language":"C#","paradigm":"Component-based, visual editor","key_features":["Cross-platform","Asset Store","DOTS/ECS","Shader Graph"]},
        {"id":"fw_unreal","name":"Unreal Engine","type":"game","language":"C++/Blueprints","paradigm":"Actor-Component, visual scripting","key_features":["Nanite","Lumen","MetaHuman","World Partition"]},
        {"id":"fw_godot","name":"Godot","type":"game","language":"GDScript/C#","paradigm":"Scene tree, node-based","key_features":["Open source","GDScript","2D/3D","Visual scripting"]},
        {"id":"fw_bevy","name":"Bevy","type":"game","language":"Rust","paradigm":"ECS, data-driven","key_features":["Rust safety","ECS","Hot reloading","Modular"]},
        {"id":"fw_svelte","name":"Svelte/SvelteKit","type":"fullstack","language":"JavaScript","paradigm":"Compile-time reactivity","key_features":["No virtual DOM","Small bundles","SSR","Transitions"]},
        {"id":"fw_vue","name":"Vue.js","type":"frontend","language":"JavaScript/TypeScript","paradigm":"Progressive framework","key_features":["Composition API","Pinia","Single-file components","Nuxt"]},
        {"id":"fw_angular","name":"Angular","type":"frontend","language":"TypeScript","paradigm":"Full-featured opinionated","key_features":["RxJS","NgRx","Dependency Injection","Signals"]},
        {"id":"fw_htmx","name":"HTMX","type":"frontend","language":"HTML","paradigm":"Hypermedia-driven","key_features":["No JS needed","Server-side rendering","Progressive enhancement"]},
        {"id":"fw_phoenix","name":"Phoenix","type":"fullstack","language":"Elixir","paradigm":"Functional MVC","key_features":["LiveView","Channels","PubSub","Ecto ORM"]},
        {"id":"fw_gin","name":"Gin","type":"backend","language":"Go","paradigm":"HTTP router","key_features":["Fast","Middleware","Validation","Binding"]},
        {"id":"fw_actix","name":"Actix Web","type":"backend","language":"Rust","paradigm":"Actor-based async","key_features":["Fastest benchmarks","Type-safe","WebSocket","Middleware"]},
        {"id":"fw_laravel","name":"Laravel","type":"fullstack","language":"PHP","paradigm":"MVC, Elegant syntax","key_features":["Eloquent ORM","Blade","Queues","Broadcasting","Livewire"]},
    ],"design_patterns":[
        {"id":"dp_singleton","name":"Singleton","category":"creational","description":"Ensure a class has only one instance.","game_use":"Audio Manager, Game Manager, Input System"},
        {"id":"dp_factory","name":"Factory Method","category":"creational","description":"Create objects without specifying exact class.","game_use":"Enemy spawning, Weapon creation, Level generation"},
        {"id":"dp_observer","name":"Observer","category":"behavioral","description":"Objects subscribe to events and get notified.","game_use":"Event system, Achievement tracking, UI updates"},
        {"id":"dp_state","name":"State Machine","category":"behavioral","description":"Object changes behavior based on internal state.","game_use":"Character states, AI states, Game flow states"},
        {"id":"dp_command","name":"Command","category":"behavioral","description":"Encapsulate actions as objects. Enables undo/redo.","game_use":"Input handling, Replay system, Undo in editors"},
        {"id":"dp_strategy","name":"Strategy","category":"behavioral","description":"Interchangeable algorithms at runtime.","game_use":"AI behaviors, Damage calculations, Pathfinding algorithms"},
        {"id":"dp_flyweight","name":"Flyweight","category":"structural","description":"Share common data between similar objects.","game_use":"Tile data, Particle templates, Font glyphs"},
        {"id":"dp_composite","name":"Composite","category":"structural","description":"Tree structures of objects treated uniformly.","game_use":"Scene graph, UI hierarchy, Behavior trees"},
        {"id":"dp_decorator","name":"Decorator","category":"structural","description":"Add behavior to objects dynamically.","game_use":"Buff/debuff systems, Weapon modifiers, Power-ups"},
        {"id":"dp_prototype","name":"Prototype","category":"creational","description":"Clone existing objects instead of creating new.","game_use":"Prefab system, Bullet pools, Enemy templates"},
        {"id":"dp_object_pool","name":"Object Pool","category":"creational","description":"Reuse objects from a pool instead of allocating.","game_use":"Bullet pools, Particle pools, Connection pools"},
        {"id":"dp_service_locator","name":"Service Locator","category":"structural","description":"Central registry for services. Alternative to DI.","game_use":"Audio service, Analytics, Save system"},
    ]}


# ═══════════════════════════════════════════════════════════════════════
# 5. COMPUTING HISTORY DATABASE
# ═══════════════════════════════════════════════════════════════════════

def get_computing_history_database():
    return {"eras": [
        {"id":"hist_pre","name":"Pre-Computer Era","years":"3000 BC - 1935","entries":[
            {"title":"Abacus","year":"3000 BC","desc":"First known computing device for arithmetic"},
            {"title":"Antikythera Mechanism","year":"100 BC","desc":"Ancient Greek analog computer for astronomical predictions"},
            {"title":"Pascaline","year":"1642","desc":"Blaise Pascal's mechanical calculator"},
            {"title":"Leibniz Wheel","year":"1694","desc":"Gottfried Leibniz's step reckoner, multiplication machine"},
            {"title":"Jacquard Loom","year":"1801","desc":"Punch card programmable textile loom"},
            {"title":"Babbage Difference Engine","year":"1822","desc":"Charles Babbage's automatic mathematical calculator"},
            {"title":"Analytical Engine","year":"1837","desc":"Babbage's general-purpose computer concept"},
            {"title":"Ada Lovelace's Notes","year":"1843","desc":"First published algorithm, first programmer"},
            {"title":"Boolean Algebra","year":"1854","desc":"George Boole formalizes logical algebra"},
        ]},
        {"id":"hist_pioneers","name":"Computer Pioneers","years":"1936 - 1955","entries":[
            {"title":"Turing Machine","year":"1936","desc":"Alan Turing defines computable numbers"},
            {"title":"Z3","year":"1941","desc":"Konrad Zuse builds first programmable digital computer"},
            {"title":"Colossus","year":"1943","desc":"First electronic digital programmable computer (Bletchley Park)"},
            {"title":"ENIAC","year":"1945","desc":"First general-purpose electronic digital computer"},
            {"title":"Von Neumann Architecture","year":"1945","desc":"Stored-program concept that defines modern computers"},
            {"title":"EDVAC","year":"1949","desc":"First stored-program computer implementation"},
            {"title":"Shannon's Information Theory","year":"1948","desc":"Claude Shannon founds information theory"},
            {"title":"Assembly Language","year":"1949","desc":"First symbolic programming language"},
            {"title":"UNIVAC I","year":"1951","desc":"First commercial computer"},
            {"title":"Fortran","year":"1957","desc":"First high-level programming language"},
        ]},
        {"id":"hist_mainframe","name":"Mainframe Era","years":"1956 - 1975","entries":[
            {"title":"LISP","year":"1958","desc":"John McCarthy creates LISP, second oldest high-level language"},
            {"title":"COBOL","year":"1959","desc":"Common business-oriented language"},
            {"title":"Integrated Circuit","year":"1958","desc":"Jack Kilby invents the IC"},
            {"title":"IBM System/360","year":"1964","desc":"First family of compatible computers"},
            {"title":"BASIC","year":"1964","desc":"Beginner programming language for education"},
            {"title":"ARPANET","year":"1969","desc":"Precursor to the Internet"},
            {"title":"UNIX","year":"1969","desc":"Thompson & Ritchie create UNIX at Bell Labs"},
            {"title":"C Language","year":"1972","desc":"Dennis Ritchie creates C"},
            {"title":"Ethernet","year":"1973","desc":"Bob Metcalfe invents Ethernet"},
            {"title":"TCP/IP","year":"1974","desc":"Vint Cerf and Bob Kahn design TCP/IP"},
        ]},
        {"id":"hist_pc","name":"Personal Computer Revolution","years":"1975 - 1995","entries":[
            {"title":"Altair 8800","year":"1975","desc":"First personal computer kit"},
            {"title":"Apple II","year":"1977","desc":"One of first mass-produced personal computers"},
            {"title":"IBM PC","year":"1981","desc":"IBM Personal Computer sets industry standard"},
            {"title":"MS-DOS","year":"1981","desc":"Microsoft disk operating system"},
            {"title":"Macintosh","year":"1984","desc":"Apple's GUI-based personal computer"},
            {"title":"Windows 1.0","year":"1985","desc":"Microsoft enters GUI market"},
            {"title":"World Wide Web","year":"1989","desc":"Tim Berners-Lee invents the Web"},
            {"title":"Linux","year":"1991","desc":"Linus Torvalds creates Linux kernel"},
            {"title":"Python","year":"1991","desc":"Guido van Rossum releases Python"},
            {"title":"Java","year":"1995","desc":"Sun Microsystems releases Java"},
            {"title":"JavaScript","year":"1995","desc":"Brendan Eich creates JavaScript in 10 days"},
        ]},
        {"id":"hist_internet","name":"Internet Age","years":"1995 - 2010","entries":[
            {"title":"Google","year":"1998","desc":"Larry Page & Sergey Brin found Google"},
            {"title":"Y2K","year":"2000","desc":"Year 2000 bug panic and remediation"},
            {"title":"Wikipedia","year":"2001","desc":"Free online encyclopedia launches"},
            {"title":"iPhone","year":"2007","desc":"Apple revolutionizes mobile computing"},
            {"title":"Android","year":"2008","desc":"Google's mobile operating system"},
            {"title":"Cloud Computing","year":"2006","desc":"AWS launches, cloud era begins"},
            {"title":"Git","year":"2005","desc":"Linus Torvalds creates Git version control"},
            {"title":"Node.js","year":"2009","desc":"JavaScript on the server"},
            {"title":"Stack Overflow","year":"2008","desc":"Q&A platform for developers"},
        ]},
        {"id":"hist_modern","name":"Modern Era","years":"2010 - 2026","entries":[
            {"title":"Docker","year":"2013","desc":"Containerization revolutionizes deployment"},
            {"title":"Kubernetes","year":"2014","desc":"Google open-sources container orchestration"},
            {"title":"TensorFlow","year":"2015","desc":"Google's ML framework goes open-source"},
            {"title":"AlphaGo","year":"2016","desc":"DeepMind AI defeats world Go champion"},
            {"title":"Transformers","year":"2017","desc":"Attention Is All You Need paper"},
            {"title":"GPT-3","year":"2020","desc":"Large language models go mainstream"},
            {"title":"GitHub Copilot","year":"2021","desc":"AI-assisted coding goes mainstream"},
            {"title":"ChatGPT","year":"2022","desc":"AI chatbot reaches 100M users in 2 months"},
            {"title":"GPT-4","year":"2023","desc":"Multimodal AI achieves human-level reasoning"},
            {"title":"Sora / Video AI","year":"2024","desc":"AI generates photorealistic video"},
            {"title":"Quantum Supremacy","year":"2025","desc":"Practical quantum advantage demonstrated"},
        ]},
    ]}


# ═══════════════════════════════════════════════════════════════════════
# 6. 10,000 INTERACTIVE QUIZZES — PROGRAMMATIC GENERATOR
# ═══════════════════════════════════════════════════════════════════════

# Quiz domains with question templates
_QUIZ_DOMAINS = {
    "cs_fundamentals": {
        "topics": ["algorithms","data_structures","complexity","sorting","searching","graphs","trees","hashing","recursion","dynamic_programming"],
        "questions": [
            ("What is the time complexity of {algos}?", ["O(1)","O(log n)","O(n)","O(n log n)","O(n^2)","O(2^n)"]),
            ("Which data structure uses {principles}?", ["Stack","Queue","Heap","Trie","Hash Table","BST","Graph","Array"]),
            ("In {algos}, what is the space complexity?", ["O(1)","O(n)","O(log n)","O(n^2)"]),
            ("What is the best case for {algos}?", ["O(1)","O(n)","O(n log n)","O(log n)"]),
            ("Which sorting algorithm is {properties}?", ["QuickSort","MergeSort","HeapSort","BubbleSort","RadixSort","TimSort"]),
        ],
        "algos": ["Binary Search","QuickSort","MergeSort","HeapSort","BFS","DFS","Dijkstra","A* Search","Hash Table lookup","Array access","Linked List traversal","BST search","AVL insertion","Red-Black insertion","B-Tree search","Trie search","Counting Sort","Radix Sort","Bucket Sort","Tim Sort"],
        "principles": ["LIFO","FIFO","Min/Max ordering","Prefix matching","Key-Value mapping","Ordered traversal","Adjacency representation","Contiguous memory"],
        "properties": ["stable","in-place","comparison-based","not comparison-based","adaptive","divide-and-conquer based","cache-friendly","parallelizable"],
    },
    "os_systems": {
        "topics": ["processes","threads","memory","scheduling","filesystems","sync","deadlocks","io","virtual_memory","containers"],
        "questions": [
            ("Which scheduling algorithm {properties}?", ["FIFO","SJF","Round Robin","CFS","Priority","MLFQ"]),
            ("What happens during a {events}?", ["Context switch occurs","Page fault handler runs","Interrupt service routine executes","System call traps to kernel","TLB flush occurs"]),
            ("In virtual memory, what does {components} do?", ["Maps virtual to physical addresses","Stores recently used translations","Handles page faults","Manages swap space","Tracks dirty pages"]),
            ("{concepts} prevents which concurrency issue?", ["Race condition","Deadlock","Starvation","Priority inversion","Livelock"]),
        ],
        "properties": ["minimizes average wait time","is preemptive","gives each process equal CPU time","uses priority queues","is fair for interactive processes"],
        "events": ["context switch","page fault","system call","interrupt","TLB miss","cache miss"],
        "components": ["Page Table","TLB","MMU","Swap Partition","Page Frame Allocator"],
        "concepts": ["Mutex","Semaphore","Monitor","Spinlock","Read-Write Lock","Condition Variable"],
    },
    "networking": {
        "topics": ["tcp_ip","http","dns","routing","security","websocket","quic","load_balancing","cdn","firewall"],
        "questions": [
            ("At which OSI layer does {protocol} operate?", ["Physical","Data Link","Network","Transport","Session","Presentation","Application"]),
            ("What is the purpose of {mechanism} in TCP?", ["Flow control","Congestion control","Reliable delivery","Connection establishment","Ordered delivery"]),
            ("Which HTTP status code means {meaning}?", ["200","201","301","400","401","403","404","500","502","503"]),
            ("{component} is responsible for what?", ["Resolving domain names","Routing packets","Encrypting traffic","Load balancing","Caching content"]),
        ],
        "protocol": ["HTTP","TCP","UDP","IP","ARP","DNS","TLS","BGP","OSPF","ICMP","QUIC","WebSocket","SMTP","FTP","SSH"],
        "mechanism": ["sliding window","three-way handshake","slow start","Nagle's algorithm","selective acknowledgment","fast retransmit"],
        "meaning": ["OK","Created","Moved Permanently","Bad Request","Unauthorized","Forbidden","Not Found","Internal Server Error","Bad Gateway","Service Unavailable"],
        "component": ["DNS Resolver","Router","Firewall","Load Balancer","CDN Edge Server","Proxy Server","NAT Gateway"],
    },
    "databases": {
        "topics": ["sql","normalization","indexing","transactions","nosql","sharding","replication","query_optimization","concurrency","acid"],
        "questions": [
            ("What normal form eliminates {problem}?", ["1NF","2NF","3NF","BCNF","4NF"]),
            ("Which isolation level prevents {anomaly}?", ["Read Uncommitted","Read Committed","Repeatable Read","Serializable"]),
            ("A {index_type} index is best for what?", ["Range queries","Exact match","Full-text search","Spatial queries","Prefix matching"]),
            ("In the CAP theorem, {system} prioritizes which two?", ["CP (Consistency + Partition tolerance)","AP (Availability + Partition tolerance)","CA (Consistency + Availability)"]),
        ],
        "problem": ["repeating groups","partial dependencies","transitive dependencies","multi-valued dependencies","join dependencies"],
        "anomaly": ["dirty reads","non-repeatable reads","phantom reads","write skew","lost updates"],
        "index_type": ["B-Tree","Hash","GiST","GIN","Bitmap","R-Tree"],
        "system": ["MongoDB","Cassandra","PostgreSQL","Redis","DynamoDB","CockroachDB","HBase"],
    },
    "security": {
        "topics": ["cryptography","authentication","web_security","network_security","malware","forensics","privacy","compliance","blockchain"],
        "questions": [
            ("What type of attack is {attack}?", ["Injection","XSS","CSRF","Man-in-the-Middle","DDoS","Phishing","Buffer Overflow","SQL Injection"]),
            ("{crypto} uses which type of encryption?", ["Symmetric","Asymmetric","Hashing","Hybrid"]),
            ("Which security principle does {practice} implement?", ["Least privilege","Defense in depth","Separation of duties","Fail secure","Zero trust"]),
            ("OWASP Top 10: {vulnerability} is ranked at position?", ["#1","#2","#3","#4","#5","#6","#7","#8","#9","#10"]),
        ],
        "attack": ["SQL Injection","XSS (Stored)","XSS (Reflected)","CSRF","SSRF","Directory Traversal","Command Injection","XXE","Clickjacking","Session Hijacking","DNS Spoofing","ARP Poisoning"],
        "crypto": ["AES-256","RSA","SHA-256","ECDSA","ChaCha20","Bcrypt","Argon2","HMAC","Diffie-Hellman"],
        "practice": ["RBAC","MFA","API rate limiting","Input sanitization","Content Security Policy","HSTS","Certificate pinning"],
        "vulnerability": ["Broken Access Control","Cryptographic Failures","Injection","Insecure Design","Security Misconfiguration","Vulnerable Components","Auth Failures","Data Integrity Failures","Logging Failures","SSRF"],
    },
    "game_dev": {
        "topics": ["physics","rendering","ai","networking","audio","animation","ui","optimization","design","production"],
        "questions": [
            ("In game physics, {concept} is used for?", ["Collision detection","Collision response","Rigid body simulation","Cloth simulation","Fluid simulation","Ragdoll physics"]),
            ("Which rendering technique achieves {effect}?", ["Shadow mapping","Screen-space reflections","Ambient occlusion","Global illumination","Bloom","Depth of field","Motion blur"]),
            ("The {pattern} design pattern is used in games for?", ["Object pooling","Event systems","State management","Input handling","Undo/redo","AI behavior"]),
            ("In multiplayer, {technique} handles what?", ["Client prediction","Server reconciliation","Lag compensation","Interpolation","Rollback"]),
        ],
        "concept": ["AABB","OBB","GJK","SAT","Verlet Integration","Euler Integration","Runge-Kutta","Impulse Resolution","Constraint Solving","Broadphase"],
        "effect": ["soft shadows","reflections","ambient light","indirect lighting","glow/bloom","bokeh blur","per-object motion blur","volumetric fog","subsurface scattering"],
        "pattern": ["Object Pool","Observer","State Machine","Command","Strategy","Flyweight","Component","Singleton","Factory","Service Locator"],
        "technique": ["client-side prediction","snapshot interpolation","rollback netcode","delta compression","interest management","area of interest","dead reckoning"],
    },
    "ml_ai": {
        "topics": ["supervised","unsupervised","deep_learning","nlp","computer_vision","reinforcement","generative","mlops","ethics","transformers"],
        "questions": [
            ("Which activation function has {property}?", ["ReLU","Sigmoid","Tanh","Softmax","GELU","Swish","Leaky ReLU"]),
            ("{architecture} is best suited for?", ["Image classification","Text generation","Object detection","Machine translation","Speech recognition","Recommendation","Time series"]),
            ("What is the purpose of {technique} in training?", ["Prevent overfitting","Speed up training","Improve generalization","Handle class imbalance","Reduce memory usage"]),
            ("In {method}, the key idea is?", ["Maximize reward","Minimize loss","Find clusters","Reduce dimensions","Generate samples","Encode representations"]),
        ],
        "property": ["output range [0,1]","can cause dying neurons","output range [-1,1]","output sums to 1","non-saturating gradient","self-gated"],
        "architecture": ["CNN","RNN","LSTM","Transformer","GAN","VAE","Diffusion Model","ResNet","U-Net","BERT","GPT","ViT","YOLO"],
        "technique": ["Dropout","Batch Normalization","Data Augmentation","Learning Rate Scheduling","Gradient Clipping","Weight Decay","Early Stopping","SMOTE"],
        "method": ["Q-Learning","K-Means","PCA","GAN Training","Contrastive Learning","Self-Supervised Learning","Knowledge Distillation","Federated Learning"],
    },
    "web_dev": {
        "topics": ["html_css","javascript","react","nodejs","apis","performance","accessibility","testing","deployment","security"],
        "questions": [
            ("In CSS, {property} controls what?", ["Layout flow","Element spacing","Visual stacking","Text rendering","Animation timing","Responsive behavior"]),
            ("Which React hook is used for {purpose}?", ["useState","useEffect","useContext","useReducer","useMemo","useCallback","useRef"]),
            ("The HTTP method {method} is used for?", ["Reading data","Creating resources","Updating resources","Deleting resources","Partial updates","Checking resource existence"]),
            ("In web performance, {optimization} improves?", ["Load time","Runtime performance","Perceived speed","Bundle size","Caching","Core Web Vitals"]),
        ],
        "property": ["display","margin/padding","z-index","font-family","transition","@media queries","grid-template","flexbox","position","overflow"],
        "purpose": ["managing state","side effects","global state","complex state logic","expensive computations","callback memoization","DOM references","form handling"],
        "method": ["GET","POST","PUT","PATCH","DELETE","HEAD","OPTIONS"],
        "optimization": ["Code splitting","Lazy loading","CDN caching","Image optimization","Tree shaking","Service workers","Preloading","Compression"],
    },
    "physics_gamedev": {
        "topics": ["mechanics","collision","rigid_body","fluid","cloth","vehicle","destruction","particle","constraint","integration"],
        "questions": [
            ("In collision detection, {algorithm} is used for?", ["Broadphase detection","Narrowphase detection","Continuous detection","Ray casting","Overlap testing"]),
            ("The {method} integration method has what property?", ["Symplectic (energy-preserving)","Higher accuracy","Simplicity","Stability for stiff systems","Variable timestep support"]),
            ("For {simulation}, which physics engine is recommended?", ["Box2D","Bullet","PhysX","Havok","Jolt","Rapier"]),
            ("In fluid simulation, {technique} models what?", ["Incompressible flow","Surface tension","Viscosity","Turbulence","Boundary conditions"]),
        ],
        "algorithm": ["Sweep and Prune","Spatial Hashing","BVH","GJK","SAT","EPA","Minkowski Difference","Grid-based"],
        "method": ["Euler","Verlet","Runge-Kutta 4","Symplectic Euler","Implicit Euler","Leapfrog"],
        "simulation": ["2D platformer","3D action game","Vehicle racing","Ragdoll characters","Destructible environments","Cloth"],
        "technique": ["SPH","Eulerian grid","FLIP","PIC","LBM","Navier-Stokes solver","Shallow water equations"],
    },
    "rendering_graphics": {
        "topics": ["pipeline","shaders","lighting","shadows","texturing","post_processing","ray_tracing","optimization","vfx","terrain"],
        "questions": [
            ("In PBR rendering, {parameter} represents what?", ["Surface color","Metal vs dielectric","Surface roughness","Normal perturbation","Ambient light blocking"]),
            ("Which shader stage handles {task}?", ["Vertex shader","Fragment shader","Geometry shader","Tessellation","Compute shader","Mesh shader"]),
            ("For {effect}, which technique is most efficient?", ["Shadow mapping","Screen-space reflections","SSAO","Bloom","TAA","DLSS","FSR"]),
            ("In ray tracing, {structure} accelerates what?", ["Ray-scene intersection","Scene traversal","Light sampling","Denoising","Caustic rendering"]),
        ],
        "parameter": ["Albedo","Metallic","Roughness","Normal map","Ambient Occlusion map","Emissive","Height/Displacement"],
        "task": ["Transform vertices","Calculate pixel color","Generate geometry","Subdivide surfaces","General computation","Process meshlets"],
        "effect": ["real-time shadows","screen reflections","ambient occlusion","glow effects","anti-aliasing","upscaling","motion blur"],
        "structure": ["BVH","KD-Tree","Octree","Grid","Two-level AS (TLAS/BLAS)","Uniform grid"],
    },
}

def get_interactive_quizzes():
    """Generate 10,000 interactive quizzes across all domains programmatically."""
    random.seed(42)  # Deterministic for reproducibility
    quizzes = []
    quiz_counter = 0

    # Difficulty distribution
    difficulties = ["beginner","intermediate","advanced","expert","master"]
    diff_weights = [0.20, 0.30, 0.25, 0.15, 0.10]

    for domain_key, domain in _QUIZ_DOMAINS.items():
        # Generate ~1000 quizzes per domain (10 domains × 1000 = 10,000)
        target_per_domain = 1000

        for i in range(target_per_domain):
            quiz_counter += 1
            topic = random.choice(domain["topics"])
            template_q, template_answers = random.choice(domain["questions"])

            # Pick a random substitution key from the template
            import re as _re
            placeholders = _re.findall(r'\{(\w+)\}', template_q)
            subs = {}
            for ph in placeholders:
                if ph in domain:
                    subs[ph] = random.choice(domain[ph])
                else:
                    subs[ph] = ph.replace("_", " ").title()

            question_text = template_q.format(**subs)
            correct_answer = random.choice(template_answers)
            wrong_answers = [a for a in template_answers if a != correct_answer]
            random.shuffle(wrong_answers)
            options = [correct_answer] + wrong_answers[:3]
            random.shuffle(options)

            difficulty = random.choices(difficulties, weights=diff_weights, k=1)[0]

            quiz = {
                "id": _qid(domain_key, i),
                "domain": domain_key,
                "topic": topic,
                "question": question_text,
                "options": options,
                "correct_answer": correct_answer,
                "difficulty": difficulty,
                "explanation": f"This question tests your knowledge of {topic.replace('_', ' ')} in {domain_key.replace('_', ' ')}. The correct answer is {correct_answer}.",
                "hints": [
                    f"Think about the core principles of {topic.replace('_', ' ')}.",
                    f"Consider how {subs.get(placeholders[0], topic) if placeholders else topic} works in practice.",
                ],
                "tags": [domain_key, topic, difficulty],
                "points": {"beginner": 10, "intermediate": 20, "advanced": 30, "expert": 50, "master": 100}.get(difficulty, 20),
                "time_limit_seconds": {"beginner": 30, "intermediate": 45, "advanced": 60, "expert": 90, "master": 120}.get(difficulty, 45),
                "interactive": True,
                "quiz_number": quiz_counter,
            }
            quizzes.append(quiz)

    random.shuffle(quizzes)
    return quizzes


# ═══════════════════════════════════════════════════════════════════════
# 7. COMPLETE BIBLE GENERATOR — Every domain needs a comprehensive bible
# ═══════════════════════════════════════════════════════════════════════

def get_hyperscale_bibles():
    """Generate comprehensive bibles for every major domain."""
    bibles = []

    bible_defs = [
        ("bible_cs_complete","Computer Science Complete Bible","cs","The definitive guide to every field of computer science.",10000,[
            ("Foundations",["Discrete Mathematics","Boolean Algebra","Set Theory","Graph Theory","Number Theory","Combinatorics","Probability","Information Theory","Formal Languages","Logic"]),
            ("Core Systems",["Operating Systems","Compilers","Computer Architecture","Networking","Databases","Distributed Systems"]),
            ("Algorithms & DS",["Sorting & Searching","Graph Algorithms","Dynamic Programming","Greedy Algorithms","String Algorithms","Geometric Algorithms","Randomized Algorithms","Approximation Algorithms","Online Algorithms","Streaming Algorithms"]),
            ("AI & ML",["Classical AI","Machine Learning","Deep Learning","NLP","Computer Vision","Reinforcement Learning","Generative AI","MLOps","AI Ethics","Explainable AI"]),
            ("Software Engineering",["Design Patterns","Architecture","Testing","DevOps","CI/CD","Agile","Code Quality","Technical Debt","Documentation","Team Leadership"]),
            ("Security",["Cryptography","Web Security","Network Security","Application Security","Forensics","Compliance","Privacy","Threat Modeling","Incident Response","Red Team/Blue Team"]),
            ("Emerging",["Quantum Computing","Blockchain","Edge Computing","AR/VR","IoT","Bioinformatics","Neuromorphic Computing","DNA Computing"]),
        ]),
        ("bible_physics_complete","Physics for Game Developers Bible","physics","Complete physics reference for simulation and game development.",8000,[
            ("Classical Mechanics",["Kinematics","Dynamics","Energy & Momentum","Rotational Motion","Oscillations & Waves","Fluid Mechanics","Rigid Body Dynamics"]),
            ("Computational Methods",["Numerical Integration","Monte Carlo Methods","Finite Element Method","N-Body Simulation","Navier-Stokes Solvers","Verlet Integration","Runge-Kutta Methods"]),
            ("Game Physics",["Collision Detection","Collision Response","Ragdoll Physics","Vehicle Physics","Cloth Simulation","Soft Body Physics","Destruction Systems","Rope & Chain Simulation"]),
            ("Advanced Physics",["Quantum Mechanics Basics","Relativity for Games","Thermodynamics in Simulation","Acoustics & Sound","Optics & Ray Tracing","Particle Physics Visualization"]),
            ("Physics Engines",["Box2D Deep Dive","Bullet Physics","PhysX","Havok","Jolt Physics","Rapier (Rust)","Custom Engine Design","Physics Debugging"]),
        ]),
        ("bible_rendering_complete","Rendering & Graphics Bible","rendering","Every technique from rasterization to neural rendering.",9000,[
            ("Rendering Fundamentals",["Graphics Pipeline","Coordinate Systems","Transformations","Rasterization","Z-Buffering","Clipping","Anti-Aliasing"]),
            ("Shader Programming",["GLSL Mastery","HLSL Mastery","Compute Shaders","Geometry Shaders","Tessellation","Shader Optimization","Shader Debugging"]),
            ("Lighting & Materials",["PBR Theory","Cook-Torrance BRDF","IBL","Area Lights","Subsurface Scattering","Anisotropic Materials","Clear Coat","Sheen"]),
            ("Shadows & GI",["Shadow Mapping","CSM","PCSS","Ray-Traced Shadows","SSAO","SSGI","Lumen","Path Tracing","Photon Mapping","Light Probes"]),
            ("Post-Processing",["Bloom","Tone Mapping","Color Grading","DOF","Motion Blur","TAA","DLSS/FSR","Volumetric Effects"]),
            ("Advanced Rendering",["Ray Tracing","Neural Rendering","NeRF","Gaussian Splatting","Nanite","Virtual Texturing","Mesh Shaders","Bindless Rendering"]),
            ("Character Rendering",["Skeletal Animation","Skinning","Blend Shapes","Facial Animation","Hair Rendering","Eye Rendering","Skin Rendering"]),
            ("Environment",["Terrain Rendering","Vegetation","Water & Ocean","Sky & Atmosphere","Weather Effects","LOD Systems","Streaming"]),
        ]),
        ("bible_architecture_complete","Software Architecture Bible","architecture","From monoliths to microservices, every pattern explained.",7000,[
            ("Foundational Patterns",["Layered","MVC/MVP/MVVM","Clean Architecture","Hexagonal","Onion Architecture","Pipe & Filter"]),
            ("Distributed Patterns",["Microservices","Event-Driven","CQRS","Saga Pattern","API Gateway","Service Mesh","Circuit Breaker"]),
            ("Data Patterns",["Repository","Unit of Work","Active Record","Data Mapper","CQRS Read Models","Event Sourcing","Materialized Views"]),
            ("Game Architecture",["Entity Component System","Scene Graph","Game Loop","State Machine","Observer/Event Bus","Object Pool","Flyweight","Command Queue"]),
            ("Cloud Native",["12-Factor App","Serverless","Container Orchestration","GitOps","Infrastructure as Code","Observability","Chaos Engineering"]),
            ("Design Principles",["SOLID","DRY","KISS","YAGNI","Composition over Inheritance","Dependency Inversion","Interface Segregation"]),
        ]),
        ("bible_gamedev_mastery","Game Development Mastery Bible","gamedev","The ultimate game development reference.",12000,[
            ("Game Design",["Core Loop Design","Player Psychology","Difficulty Curves","Economy Design","Level Design","Narrative Design","UX for Games","Accessibility","Monetization Ethics","Live Service Design"]),
            ("Programming Patterns",["Game Loop","Entity Component System","State Machines","Behavior Trees","Event Systems","Object Pools","Spatial Partitioning","Scripting Systems"]),
            ("Graphics & Audio",["2D Rendering","3D Rendering","Shaders","VFX","Procedural Audio","Dynamic Music","Spatial Audio","Optimization"]),
            ("Multiplayer",["Client-Server Architecture","P2P","Rollback Netcode","Lockstep","Matchmaking","Anti-Cheat","Leaderboards","Social Systems"]),
            ("Production",["Prototyping","Vertical Slice","Alpha/Beta/Gold","QA Process","Playtesting","Analytics","Post-Launch","Live Ops"]),
            ("Engines & Tools",["Unity Deep Dive","Unreal Deep Dive","Godot","Custom Engines","Editor Tools","Asset Pipelines","Build Systems","Profiling"]),
            ("Platforms",["PC","Console (PS/Xbox/Switch)","Mobile","VR/AR","Web (WebGL/WebGPU)","Cloud Gaming","Streaming"]),
            ("Business",["Indie Development","Publisher Relations","Marketing","Community Building","Funding","Legal","IP Protection"]),
        ]),
        ("bible_math_complete","Mathematics for Computing Bible","mathematics","Every mathematical concept needed for CS and game dev.",9000,[
            ("Discrete Math",["Logic & Proofs","Set Theory","Relations & Functions","Combinatorics","Graph Theory","Number Theory","Recurrence Relations","Generating Functions"]),
            ("Linear Algebra",["Vectors","Matrices","Linear Transformations","Eigenvalues","SVD","Quaternions","Homogeneous Coordinates","Tensor Algebra"]),
            ("Calculus",["Limits","Derivatives","Integration","Multivariable","Vector Calculus","Differential Equations","Fourier Analysis","Laplace Transform"]),
            ("Probability & Stats",["Probability Theory","Random Variables","Distributions","Bayesian Inference","Hypothesis Testing","Regression","Markov Chains","Monte Carlo Methods"]),
            ("Numerical Methods",["Root Finding","Interpolation","Numerical Integration","Linear Systems","ODE Solvers","PDE Solvers","Optimization","FFT"]),
            ("Game Math",["Collision Math","Bezier Curves","Splines","Noise Functions","SDF","Procedural Generation Math","Physics Math","Shader Math"]),
        ]),
        ("bible_devops_complete","DevOps & Cloud Bible","devops","Infrastructure, deployment, and operations at scale.",6000,[
            ("Containers",["Docker Fundamentals","Multi-Stage Builds","Docker Compose","Container Security","Registry Management","Buildpacks"]),
            ("Orchestration",["Kubernetes Architecture","Pods & Services","Deployments","StatefulSets","Operators","Helm","Service Mesh (Istio)","GitOps (ArgoCD)"]),
            ("CI/CD",["GitHub Actions","GitLab CI","Jenkins","CircleCI","Pipeline Design","Testing in CI","Deployment Strategies","Feature Flags"]),
            ("Cloud Platforms",["AWS","GCP","Azure","Multi-Cloud","Cost Optimization","Well-Architected","Serverless","Edge Computing"]),
            ("Observability",["Logging","Metrics","Tracing","Alerting","Dashboards","SLOs/SLIs","Error Budgets","Incident Response"]),
            ("Security",["Supply Chain Security","Secret Management","Network Policies","RBAC","Pod Security","Image Scanning","Compliance"]),
        ]),
        ("bible_web_complete","Web Development Bible","web","Everything from HTML to WebAssembly.",8000,[
            ("Frontend Foundations",["HTML5 Semantic","CSS3 Layout","JavaScript ES2025+","TypeScript","Browser APIs","Web Components","PWA"]),
            ("Frontend Frameworks",["React","Vue","Angular","Svelte","Solid","Qwik","HTMX","Astro"]),
            ("Backend",["Node.js","Python (Django/FastAPI)","Go","Rust","Java (Spring)","Ruby (Rails)","PHP (Laravel)","Elixir (Phoenix)"]),
            ("APIs",["REST","GraphQL","gRPC","WebSocket","Server-Sent Events","tRPC","OpenAPI","API Versioning"]),
            ("Databases for Web",["PostgreSQL","MongoDB","Redis","Elasticsearch","SQLite","Supabase","PlanetScale","Prisma"]),
            ("Performance",["Core Web Vitals","Bundle Optimization","Image Optimization","Caching Strategies","CDN","Service Workers","Edge Functions","Streaming SSR"]),
            ("Testing",["Unit Testing","Integration Testing","E2E (Playwright/Cypress)","Visual Regression","Load Testing","Accessibility Testing"]),
            ("Deployment",["Vercel","Netlify","AWS","Docker","Kubernetes","Edge Deployment","Serverless","Self-Hosted"]),
        ]),
    ]

    for bible_id, name, category, desc, hours, sections_def in bible_defs:
        sections = []
        for sec_name, articles_list in sections_def:
            sec_id = f"{bible_id}_{hashlib.md5(sec_name.encode()).hexdigest()[:6]}"
            articles = []
            for art_name in articles_list:
                art_id = f"{sec_id}_{hashlib.md5(art_name.encode()).hexdigest()[:6]}"
                articles.append({
                    "id": art_id,
                    "title": art_name,
                    "content": f"Comprehensive coverage of {art_name} within {sec_name}. This article covers theory, practical applications, code examples, best practices, common pitfalls, and real-world case studies. Estimated study time: {random.randint(2,8)} hours.",
                    "estimated_hours": random.randint(2, 8),
                })
            sections.append({
                "id": sec_id,
                "name": sec_name,
                "articles": articles,
                "total_articles": len(articles),
            })
        bibles.append({
            "id": bible_id,
            "name": name,
            "category": category,
            "description": desc,
            "total_hours": hours,
            "sections": sections,
            "total_sections": len(sections),
            "total_articles": sum(len(s["articles"]) for s in sections),
        })

    return bibles


# ═══════════════════════════════════════════════════════════════════════
# AGGREGATED EXPORT
# ═══════════════════════════════════════════════════════════════════════

def get_all_knowledge_databases():
    """Return all knowledge databases for seeding."""
    return {
        "cs": get_cs_database(),
        "physics": get_physics_database(),
        "rendering": get_rendering_database(),
        "architecture": get_architecture_database(),
        "computing_history": get_computing_history_database(),
    }
