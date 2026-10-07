"""
╔══════════════════════════════════════════════════════════════════════════╗
║  STUDY PATH GENERATOR — 25+ Predefined Learning Journeys               ║
║  Each path chains tracks, books, quizzes, and knowledge bases           ║
║  into a step-by-step curriculum with milestones                         ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
import hashlib

def _pid(name):
    return f"path_{hashlib.md5(name.encode()).hexdigest()[:10]}"

def get_study_paths():
    paths = []
    defs = [
        ("Become a Game Developer","gamedev","beginner","expert",2400,"Master game development from zero to shipping titles.",[
            {"title":"Programming Fundamentals","type":"track","ref":"python","hours":100,"description":"Learn programming basics with Python."},
            {"title":"C++ for Game Dev","type":"track","ref":"cpp","hours":200,"description":"Master C++ — the language of game engines."},
            {"title":"Game Programming Patterns","type":"book","ref":"book_game_patterns","hours":25,"description":"Essential design patterns for games."},
            {"title":"Mathematics for 3D","type":"book","ref":"book_math_3d","hours":45,"description":"Linear algebra, vectors, matrices for games."},
            {"title":"Physics for Game Dev","type":"knowledge_db","ref":"phys_game","hours":500,"description":"Collision detection, rigid bodies, fluid sim."},
            {"title":"Rendering Pipeline","type":"knowledge_db","ref":"rend_pipeline","hours":400,"description":"Graphics pipeline from vertex to pixel."},
            {"title":"Unity Mastery","type":"knowledge_db","ref":"gd_unity_deep","hours":600,"description":"Complete Unity engine mastery."},
            {"title":"Game Engine Architecture","type":"book","ref":"book_gea","hours":60,"description":"How engines work under the hood."},
            {"title":"Game Dev Quiz Challenge","type":"quiz","ref":"game_dev","hours":20,"description":"1000 quizzes to test your game dev knowledge."},
            {"title":"Ship Your First Game","type":"milestone","hours":200,"description":"Build and release a complete game."},
        ]),
        ("Master Full-Stack Web Development","web","beginner","advanced",1800,"From HTML to deploying scalable web applications.",[
            {"title":"HTML, CSS, JavaScript","type":"track","ref":"javascript","hours":150,"description":"Web fundamentals — the building blocks."},
            {"title":"TypeScript Deep Dive","type":"knowledge_db","ref":"lang_typescript","hours":200,"description":"Type-safe JavaScript for production."},
            {"title":"React 19+ Mastery","type":"knowledge_db","ref":"api_frontend_fw","hours":300,"description":"Modern React with Server Components."},
            {"title":"Node.js Design Patterns","type":"book","ref":"book_nodejs","hours":40,"description":"Backend patterns for Node.js."},
            {"title":"REST & GraphQL API Design","type":"knowledge_db","ref":"api_rest_api","hours":250,"description":"Design and build production APIs."},
            {"title":"PostgreSQL Internals","type":"knowledge_db","ref":"db_postgresql","hours":200,"description":"Master your database."},
            {"title":"Docker & Kubernetes","type":"knowledge_db","ref":"devops_kubernetes","hours":300,"description":"Containerize and orchestrate."},
            {"title":"Web Dev Quiz Challenge","type":"quiz","ref":"web_dev","hours":20,"description":"1000 quizzes on web technologies."},
            {"title":"High Performance Browser Networking","type":"book","ref":"book_hpbn","hours":35,"description":"Understand the network stack."},
            {"title":"Deploy a Production App","type":"milestone","hours":150,"description":"Deploy a full-stack app with CI/CD."},
        ]),
        ("Master Rust","rust","beginner","expert",1200,"From zero to systems programming mastery with Rust.",[
            {"title":"The Rust Programming Language","type":"book","ref":"book_trpl","hours":40,"description":"The official Rust book — cover to cover."},
            {"title":"Rust Deep Dive","type":"knowledge_db","ref":"lang_rust","hours":700,"description":"Ownership, lifetimes, traits, async, macros."},
            {"title":"Programming Rust","type":"book","ref":"book_prog_rust","hours":50,"description":"Advanced Rust programming."},
            {"title":"Rust for Rustaceans","type":"book","ref":"book_rfr","hours":40,"description":"Expert-level Rust idioms."},
            {"title":"Systems Programming","type":"track","ref":"rust","hours":200,"description":"Build real systems in Rust."},
            {"title":"CS Fundamentals Quiz","type":"quiz","ref":"cs_fundamentals","hours":15,"description":"Test your CS knowledge."},
            {"title":"Build a Web Server in Rust","type":"milestone","hours":100,"description":"Build and benchmark a web server."},
        ]),
        ("ML Engineer Path","ml","intermediate","expert",2000,"From statistics to deploying ML models at scale.",[
            {"title":"Python for Data Science","type":"track","ref":"python","hours":100,"description":"Python fundamentals for ML."},
            {"title":"Mathematics for ML","type":"book","ref":"book_math_ml","hours":35,"description":"Linear algebra, calculus, probability."},
            {"title":"Hands-On Machine Learning","type":"book","ref":"book_homl","hours":50,"description":"Practical ML with scikit-learn and TensorFlow."},
            {"title":"Deep Learning Architectures","type":"knowledge_db","ref":"ml_dl_arch","hours":500,"description":"CNNs, RNNs, Transformers, Diffusion."},
            {"title":"NLP & LLMs","type":"knowledge_db","ref":"ml_nlp_llm","hours":600,"description":"Tokenization to RLHF to RAG."},
            {"title":"MLOps","type":"knowledge_db","ref":"ml_mlops_deep","hours":400,"description":"From notebook to production."},
            {"title":"ML/AI Quiz Challenge","type":"quiz","ref":"ml_ai","hours":20,"description":"1000 quizzes on ML concepts."},
            {"title":"Deploy a ML Model","type":"milestone","hours":200,"description":"Train, serve, and monitor a model."},
        ]),
        ("DevOps & Cloud Architect","devops","beginner","expert",2200,"Infrastructure, automation, and cloud at scale.",[
            {"title":"Linux Administration","type":"knowledge_db","ref":"devops_linux_systems","hours":400,"description":"Master Linux from kernel to shell."},
            {"title":"Docker Deep Dive","type":"book","ref":"book_docker","hours":25,"description":"Containers from scratch."},
            {"title":"Kubernetes Production","type":"knowledge_db","ref":"devops_kubernetes","hours":600,"description":"Production K8s with operators and GitOps."},
            {"title":"Terraform & IaC","type":"knowledge_db","ref":"devops_terraform","hours":400,"description":"Infrastructure as Code mastery."},
            {"title":"AWS Complete","type":"knowledge_db","ref":"devops_aws","hours":400,"description":"All major AWS services."},
            {"title":"Site Reliability Engineering","type":"book","ref":"book_sre","hours":40,"description":"Google's SRE practices."},
            {"title":"CI/CD Pipelines","type":"knowledge_db","ref":"devops_cicd","hours":200,"description":"Automated delivery."},
            {"title":"DevOps Quiz Challenge","type":"quiz","ref":"devops_expanded","hours":20,"description":"1000 quizzes on DevOps."},
            {"title":"Build a Production Platform","type":"milestone","hours":200,"description":"Design and operate infrastructure."},
        ]),
        ("Security Engineer","security","intermediate","expert",1500,"From web security to cryptography engineering.",[
            {"title":"Application Security","type":"knowledge_db","ref":"sec_appsec","hours":400,"description":"OWASP Top 10, auth, secrets."},
            {"title":"The Web Application Hacker's Handbook","type":"book","ref":"book_wahh","hours":45,"description":"Web pentesting bible."},
            {"title":"Cryptography Engineering","type":"knowledge_db","ref":"sec_crypto_eng","hours":350,"description":"AES to zero-knowledge proofs."},
            {"title":"Cloud Security","type":"knowledge_db","ref":"sec_cloud_sec","hours":300,"description":"Secure cloud infrastructure."},
            {"title":"Security Testing","type":"knowledge_db","ref":"testing_sec_testing","hours":250,"description":"SAST, DAST, fuzzing, pentesting."},
            {"title":"Security Quiz Challenge","type":"quiz","ref":"security","hours":20,"description":"1000 quizzes on security."},
            {"title":"Perform a Security Audit","type":"milestone","hours":100,"description":"Audit a real application."},
        ]),
        ("iOS Developer","mobile","beginner","advanced",1200,"Build production iOS apps with Swift and SwiftUI.",[
            {"title":"Swift Programming","type":"knowledge_db","ref":"lang_swift","hours":500,"description":"Swift language mastery."},
            {"title":"iOS Development","type":"knowledge_db","ref":"mobile_ios","hours":500,"description":"SwiftUI, UIKit, Core Data."},
            {"title":"Mobile Quiz Challenge","type":"quiz","ref":"mobile_expanded","hours":15,"description":"Mobile dev quizzes."},
            {"title":"Ship an App Store App","type":"milestone","hours":200,"description":"Build and publish to App Store."},
        ]),
        ("Android Developer","mobile","beginner","advanced",1200,"Build production Android apps with Kotlin and Compose.",[
            {"title":"Kotlin Programming","type":"knowledge_db","ref":"lang_kotlin","hours":500,"description":"Kotlin language mastery."},
            {"title":"Android Development","type":"knowledge_db","ref":"mobile_android","hours":500,"description":"Jetpack Compose, Architecture Components."},
            {"title":"Kotlin in Action","type":"book","ref":"book_kotlin","hours":30,"description":"Deep Kotlin knowledge."},
            {"title":"Ship a Play Store App","type":"milestone","hours":200,"description":"Build and publish to Play Store."},
        ]),
        ("Data Engineer","data","intermediate","expert",1800,"Build and operate data pipelines at scale.",[
            {"title":"SQL Mastery","type":"knowledge_db","ref":"db_sql_mastery","hours":400,"description":"Advanced SQL for data engineering."},
            {"title":"Apache Spark","type":"knowledge_db","ref":"data_spark","hours":500,"description":"Distributed data processing."},
            {"title":"Apache Kafka","type":"knowledge_db","ref":"data_kafka","hours":400,"description":"Event streaming platform."},
            {"title":"Data Warehousing","type":"knowledge_db","ref":"data_data_warehouse","hours":350,"description":"Snowflake, BigQuery, dbt."},
            {"title":"Data Lakes","type":"knowledge_db","ref":"data_data_lakes","hours":250,"description":"Delta Lake, Iceberg, Lakehouse."},
            {"title":"Build a Data Pipeline","type":"milestone","hours":150,"description":"End-to-end data pipeline."},
        ]),
        ("Computer Science Fundamentals","cs","beginner","advanced",2500,"A complete CS education — university-grade.",[
            {"title":"Discrete Mathematics","type":"book","ref":"book_discrete","hours":50,"description":"Logic, sets, graphs, combinatorics."},
            {"title":"Algorithms (CLRS)","type":"book","ref":"book_clrs","hours":80,"description":"The algorithm bible."},
            {"title":"Computer Systems (CSAPP)","type":"book","ref":"book_csapp","hours":60,"description":"How computers actually work."},
            {"title":"Operating Systems","type":"book","ref":"book_os","hours":50,"description":"Processes, memory, filesystems."},
            {"title":"Computer Networking","type":"book","ref":"book_networking","hours":45,"description":"Protocols, routing, security."},
            {"title":"Compilers","type":"book","ref":"book_compilers","hours":50,"description":"Build a programming language."},
            {"title":"Theory of Computation","type":"book","ref":"book_toc","hours":40,"description":"Automata, decidability, complexity."},
            {"title":"CS Fundamentals Quizzes","type":"quiz","ref":"cs_fundamentals","hours":20,"description":"1000 CS quizzes."},
            {"title":"OS Systems Quizzes","type":"quiz","ref":"os_systems","hours":20,"description":"1000 OS quizzes."},
            {"title":"Complete a Systems Project","type":"milestone","hours":200,"description":"Build an OS component or compiler."},
        ]),
        ("Frontend Specialist","web","beginner","expert",1500,"Master modern frontend development.",[
            {"title":"JavaScript Deep Dive","type":"knowledge_db","ref":"lang_javascript","hours":400,"description":"JS engine internals, closures, async."},
            {"title":"TypeScript Mastery","type":"knowledge_db","ref":"lang_typescript","hours":300,"description":"Advanced type system."},
            {"title":"Frontend Frameworks","type":"knowledge_db","ref":"api_frontend_fw","hours":500,"description":"React, Vue, Svelte, Angular deep dive."},
            {"title":"CSS: The Definitive Guide","type":"book","ref":"book_css","hours":40,"description":"CSS Grid, Flexbox, animations."},
            {"title":"Web Technologies","type":"knowledge_db","ref":"api_web_tech","hours":200,"description":"WebAssembly, PWA, WebGPU."},
            {"title":"Build a Component Library","type":"milestone","hours":100,"description":"Design system from scratch."},
        ]),
        ("Backend Specialist","web","intermediate","expert",1600,"Master server-side engineering.",[
            {"title":"Go Programming","type":"knowledge_db","ref":"lang_golang","hours":300,"description":"Go for high-performance backends."},
            {"title":"API Design (REST + GraphQL + gRPC)","type":"knowledge_db","ref":"api_rest_api","hours":250,"description":"Design production APIs."},
            {"title":"Database Internals","type":"knowledge_db","ref":"db_postgresql","hours":300,"description":"PostgreSQL deep dive."},
            {"title":"Redis Internals","type":"knowledge_db","ref":"db_redis_int","hours":150,"description":"Caching and data structures."},
            {"title":"System Design","type":"knowledge_db","ref":"se_sys_design","hours":400,"description":"Scalability patterns."},
            {"title":"Build a Distributed System","type":"milestone","hours":200,"description":"Design and implement a distributed service."},
        ]),
        ("Competitive Programming","algorithms","beginner","expert",1500,"Train for ICPC and Codeforces.",[
            {"title":"Algorithms (CLRS)","type":"book","ref":"book_clrs","hours":80,"description":"Algorithm foundations."},
            {"title":"CS Algorithms Deep Dive","type":"knowledge_db","ref":"cs_algorithms","hours":400,"description":"All algorithm families."},
            {"title":"Data Structures","type":"knowledge_db","ref":"cs_data_structures","hours":350,"description":"Every data structure."},
            {"title":"Concrete Mathematics","type":"book","ref":"book_concrete","hours":50,"description":"Mathematical foundations."},
            {"title":"Algorithm Challenges","type":"quiz","ref":"cs_fundamentals","hours":100,"description":"Grind 1000 algorithm quizzes."},
            {"title":"Win a Competition","type":"milestone","hours":300,"description":"Compete in online contests."},
        ]),
        ("Blockchain Developer","web3","intermediate","expert",1000,"Smart contracts, DeFi, and Web3 development.",[
            {"title":"Cryptography Engineering","type":"knowledge_db","ref":"sec_crypto_eng","hours":350,"description":"Crypto foundations for blockchain."},
            {"title":"Web3 Security","type":"knowledge_db","ref":"sec_web3_sec","hours":250,"description":"Smart contract security."},
            {"title":"JavaScript Deep Dive","type":"knowledge_db","ref":"lang_javascript","hours":200,"description":"JS for dApp frontends."},
            {"title":"Deploy a Smart Contract","type":"milestone","hours":200,"description":"Build and audit a DeFi protocol."},
        ]),
        ("Technical Leader","leadership","advanced","expert",800,"From senior engineer to tech lead.",[
            {"title":"Staff Engineer","type":"book","ref":"book_staff","hours":20,"description":"Staff+ engineering."},
            {"title":"System Design","type":"knowledge_db","ref":"se_sys_design","hours":400,"description":"Architecture at scale."},
            {"title":"Software Engineering Practices","type":"knowledge_db","ref":"se_code_quality","hours":200,"description":"Code quality and review."},
            {"title":"Lead a Major Project","type":"milestone","hours":200,"description":"Lead architecture for a team."},
        ]),
        ("Rendering Engineer","graphics","intermediate","expert",2000,"Master real-time and offline rendering.",[
            {"title":"Rendering Pipeline","type":"knowledge_db","ref":"rend_pipeline","hours":400,"description":"Graphics pipeline mastery."},
            {"title":"Shader Programming","type":"knowledge_db","ref":"rend_shaders","hours":500,"description":"GLSL, HLSL, compute shaders."},
            {"title":"Real-Time Rendering","type":"book","ref":"book_rtr","hours":70,"description":"The rendering bible."},
            {"title":"Ray Tracing","type":"knowledge_db","ref":"rend_raytracing","hours":400,"description":"Path tracing, BVH, denoising."},
            {"title":"PBR Bible","type":"book","ref":"book_pbr","hours":60,"description":"Physically based rendering."},
            {"title":"Rendering Quiz Challenge","type":"quiz","ref":"rendering_graphics","hours":20,"description":"1000 rendering quizzes."},
            {"title":"Build a Renderer","type":"milestone","hours":300,"description":"Build a software renderer."},
        ]),
        ("Python Master","python","beginner","expert",1200,"Complete Python mastery path.",[
            {"title":"Python Deep Dive","type":"knowledge_db","ref":"lang_python","hours":800,"description":"Every Python concept."},
            {"title":"Fluent Python","type":"book","ref":"book_fp","hours":50,"description":"Pythonic programming."},
            {"title":"Effective Python","type":"book","ref":"book_ep","hours":25,"description":"90 specific ways to write better Python."},
            {"title":"Python Cookbook","type":"book","ref":"book_pc","hours":40,"description":"Recipes for mastery."},
            {"title":"Build a Framework","type":"milestone","hours":200,"description":"Build a web framework or tool."},
        ]),
        ("Java Enterprise Developer","java","intermediate","expert",1500,"Enterprise Java mastery.",[
            {"title":"Java Deep Dive","type":"knowledge_db","ref":"lang_java","hours":800,"description":"JVM, generics, concurrency."},
            {"title":"Effective Java","type":"book","ref":"book_ej","hours":35,"description":"Best practices by Bloch."},
            {"title":"Spring Boot","type":"track","ref":"spring_full","hours":600,"description":"Spring ecosystem."},
            {"title":"Build an Enterprise Service","type":"milestone","hours":200,"description":"Microservices with Spring."},
        ]),
        ("C++ Systems Programmer","cpp","intermediate","expert",1500,"Low-level systems mastery with C++.",[
            {"title":"C++ Deep Dive","type":"knowledge_db","ref":"lang_cpp","hours":900,"description":"Modern C++ (20/23), templates, RAII."},
            {"title":"Effective Modern C++","type":"book","ref":"book_emc","hours":35,"description":"Scott Meyers' essential guide."},
            {"title":"Operating Systems","type":"knowledge_db","ref":"cs_os","hours":400,"description":"OS internals."},
            {"title":"Build a System Component","type":"milestone","hours":200,"description":"Build a database or OS component."},
        ]),
        ("Testing & QA Engineer","testing","beginner","advanced",1000,"Master all forms of software testing.",[
            {"title":"Unit Testing","type":"knowledge_db","ref":"testing_unit_testing","hours":250,"description":"TDD, mocking, coverage."},
            {"title":"Integration Testing","type":"knowledge_db","ref":"testing_integration_testing","hours":200,"description":"API and DB testing."},
            {"title":"E2E Testing","type":"knowledge_db","ref":"testing_e2e_testing","hours":250,"description":"Playwright, Cypress, Detox."},
            {"title":"Performance Testing","type":"knowledge_db","ref":"testing_perf_testing","hours":200,"description":"Load testing, profiling."},
            {"title":"Test Driven Development","type":"book","ref":"book_tdd","hours":20,"description":"TDD by example."},
            {"title":"Build a Test Suite","type":"milestone","hours":100,"description":"Comprehensive test coverage."},
        ]),
    ]

    for item in defs:
        if len(item) == 7:
            name, category, start_level, end_level, total_hours, description, steps = item
        else:
            continue
        milestones = [s for s in steps if s.get("type") == "milestone" or (isinstance(s, dict) and s.get("type") == "milestone")]
        paths.append({
            "id": _pid(name),
            "name": name,
            "category": category,
            "start_level": start_level,
            "end_level": end_level,
            "total_hours": total_hours,
            "description": description,
            "steps": steps,
            "total_steps": len(steps),
            "milestones": len(milestones),
        })
    return paths
