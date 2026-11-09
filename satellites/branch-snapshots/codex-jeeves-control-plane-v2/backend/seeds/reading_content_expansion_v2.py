"""
Reading Content EXPANSION PACK 2 — additional prose banks (2026-05-13)
Adds DEEP DIVE, CASE STUDIES, MISCONCEPTIONS, and 5 new category groups
(ai_ethics, ux_design, distributed_systems, mobile_dev, performance_eng).
All original writing for educational reuse.
"""
from __future__ import annotations
from typing import Dict, List

# ───── DEEP DIVE — long-form essays unique to each chapter category ─────
DEEP_DIVE_BY_CATEGORY: Dict[str, List[str]] = {
    "cs_foundations": [
        "Algorithmic complexity is often taught as a recipe — count the loops, multiply nested ones, drop constants — but the real intellectual content sits one level deeper. Big-O is a statement about how an algorithm's resource use BEHAVES as the input grows without bound. The bound matters because it tells you which differences are stable across hardware, language, and compiler version, and which are not. A function that is O(n log n) will, given enough input, beat one that is O(n²) — guaranteed, on any future hardware. That guarantee is rare in software engineering, and it is what makes complexity theory worth your time.",
        "Decidability, NP-completeness, and the hierarchy of computational classes form a second layer of foundational results. Not every problem can be solved by a computer — Turing proved this in 1936 by showing that the halting problem has no general algorithm. Not every solvable problem can be solved efficiently — Cook and Levin proved this implicitly in 1971 by showing that 3-SAT is NP-complete. Every working programmer should know which corner of this landscape their daily problems sit in; mistaking an NP-hard problem for one with a polynomial algorithm is the source of countless wasted engineer-years.",
        "The pedagogical sequence that has held up over forty years is: arrays → linked structures → trees → graphs → hash tables → priority queues → balanced trees → string indexes → geometric structures. Each layer presupposes the previous and unlocks a new class of problem. By the time you finish the sequence you should be able to read an algorithm paper, recognize which data structures the author is implicitly assuming, and reproduce the running-time analysis without prompting.",
    ],
    "languages": [
        "Type systems exist on a spectrum from no types (assembly) through dynamic and structural systems (Lisp, Python, JavaScript) to nominal, dependent, and substructural systems (Coq, Idris, Agda, Rust's borrow checker). The further along the spectrum a language sits, the more invariants it can enforce at compile time — and the more cognitive overhead it imposes on the programmer. There is no universally correct point on this spectrum; the right answer depends on the failure modes you are most worried about.",
        "Lexical scope, closures, and first-class functions form the algebraic backbone of every modern language. Once you understand these three primitives you can implement anything: classes (closures over mutable state), monads (functions that thread context), continuations (closures over the rest of the computation), even type classes (records of functions parameterised by type). The languages that feel most powerful are usually the ones that take this small kernel seriously and refuse to bolt on inferior copies of it.",
    ],
    "architecture": [
        "Conway's Law — organisations ship their org chart — is the most important architectural observation of the last fifty years. The corollary is that you cannot design a clean architecture for a politically tangled organisation. Architecture is socio-technical: any module boundary you draw will sooner or later be tested by a team boundary, and the weaker side loses. Successful architects spend at least as much time on the team topology as on the system topology.",
        "Layered architectures, hexagonal architectures, onion architectures, clean architectures — these are all variations on a single theme: keep volatile concerns (UI, database, IO) outside, keep stable concerns (business rules) inside, and ensure dependencies point only inward. The diagram is easy; the discipline of refusing to leak a database concept into a business rule is hard. Every successful long-lived codebase has held this discipline; every brittle one has not.",
    ],
    "gamedev": [
        "Game architecture differs from business software in one critical way: the inner loop is hot. Sixty times a second, every system must finish its work in under 16ms or the player sees stutter. This frame budget forces decisions that business architects would call premature optimisation: data-oriented design, cache-coherent layouts, struct-of-arrays, manual memory management. None of these are 'cleaner' than the OO equivalents; they are 'faster', and in games faster is the cleanliness criterion.",
        "Entity-Component-System (ECS) is the architectural pattern that emerged when teams realised inheritance hierarchies could not scale to thousands of entity types. An entity is just an ID; components are data; systems are functions that operate on whichever components are present. The pattern unbundles identity from behaviour and makes composition cheaper than inheritance. It also maps beautifully onto cache hardware.",
    ],
    "security": [
        "The OWASP Top Ten changes slowly: injection, broken auth, sensitive data exposure, XML/external entity, broken access control, security misconfig, XSS, insecure deserialisation, vulnerable dependencies, insufficient logging. The same defects appear year after year because the underlying patterns — trusting input, mixing data with code, leaking state across users — are baked into how most frameworks default. The job of a secure programmer is to know these defaults and override them.",
        "Threat modelling — STRIDE, PASTA, attack trees — is the architectural counterpart of unit testing. You enumerate the things an adversary might want, then enumerate the paths to those things, then design defences for each path. The exercise feels paranoid until the day a real attacker proves it accurate; at that point the people who skipped threat modelling are in production fire-fighting and the people who did it are watching their alarms catch the attack early.",
    ],
    "ml": [
        "Modern deep learning rests on three pillars: differentiable parameterised functions, gradient-based optimisation, and abundant labelled (or self-labelled) data. Every architecture — CNN, RNN, Transformer, diffusion model — is a particular parameterisation. Every optimiser — SGD, Adam, Lion, Sophia — is a particular way of descending the loss landscape. Every training regime — supervised, self-supervised, RLHF — is a particular way of harvesting signal from data. Understand the three pillars and any new model becomes a recombination of familiar parts.",
        "Generalisation is the central mystery of deep learning. Why do models with billions of parameters not simply memorise their training set? The honest answer is that we do not fully know, but the working hypothesis combines implicit regularisation from SGD, the geometry of high-dimensional loss landscapes, and the structure of natural data. A practitioner should at least know that overparameterisation does not automatically destroy generalisation — a fact that runs counter to classical bias-variance intuition.",
    ],
    "practices": [
        "Code review is the most leveraged engineering practice we know. Every line that ships unreviewed accumulates a defect probability; every line that ships after a thoughtful review accumulates a lower one. The numbers are dramatic: Microsoft, Google, and a long line of academic studies converge on roughly a 10× reduction in defects per line for well-reviewed code. Skipping reviews is the engineering equivalent of skipping seat belts.",
        "Test pyramids — many unit tests, fewer integration tests, very few end-to-end tests — describe the steady-state any healthy codebase converges on. The shape exists for reasons of cost and speed: unit tests are cheap to run and easy to localise; end-to-end tests are slow and flaky and expensive to debug. Inverting the pyramid (an 'ice-cream cone' of mostly E2E tests) is the second most common cause of slow build pipelines, right after monolithic compilation.",
    ],
    "devops": [
        "Continuous delivery — the discipline of keeping main always shippable — sounds like a process change but is actually an architectural one. It requires that every change is small, every change is tested automatically, every change is feature-flagged or backwards-compatible, and every change is observed in production. Teams that cannot ship to production at 4pm on a Friday cannot ship to production safely at any other time either.",
        "Infrastructure-as-code reframes operations from a craft to a software-engineering problem. The system's running state should be reproducible from versioned code; the running state should drift from that code only briefly and only in observable ways. Terraform, Pulumi, CDK, and their successors are not configuration tools but compilers for the cloud — and they should be treated with the same engineering discipline as your application source.",
    ],
    "web": [
        "Performance budgets — explicit limits on JavaScript bundle size, time-to-interactive, largest-contentful-paint — are the single biggest determinant of web-app success in 2026. Every successful site has them; every failed site does not. The numbers that matter on a median 4G phone are roughly: 100KB compressed JS first-load, 2.5s LCP, 100ms input delay. These are non-negotiable because they map directly onto retention and conversion.",
        "The fundamental web tension is between three properties: ship one HTML page, run rich client code, and keep state correct across navigations. SSR-only solves the first; SPAs solve the second; islands and partial hydration are recent attempts to solve all three. There is no universally correct answer; the right one depends on your traffic shape and authorship workflow.",
    ],
    "databases": [
        "ACID and CAP are sometimes treated as competing slogans. They are not: ACID is a property of single-node transactions, CAP is a property of distributed systems under network partitions. A modern distributed SQL engine — Spanner, CockroachDB, YugabyteDB, FoundationDB — provides both within the limits CAP allows. Knowing which guarantee you actually need is more important than memorising the acronyms.",
        "Indexes are the single most leveraged optimisation in any database. The correct mental model is: an index is a separate, sorted copy of (a subset of) the table, with pointers back. Every query plan is a choice of which indexes to use and how to combine them. Reading EXPLAIN output until it feels natural is one of the highest-ROI skills a backend programmer can develop.",
    ],
    "math": [
        "Linear algebra is the lingua franca of modern computing. Computer graphics, machine learning, cryptography, search engines, recommendation systems, robotics — all are dense in matrix operations because matrices are how we encode large-scale linear transformations efficiently. Strang's textbook, MIT OCW 18.06, and 3Blue1Brown's video series each present the material once; mastering any one of them changes how you read the rest of computing.",
        "Probability and statistics are how we reason under uncertainty, which is most of the time. Bayes's theorem is the operating mechanism by which beliefs update when evidence arrives; the technique is universal, the implementations vary. Whether you are A/B testing an ad, training a classifier, or estimating an ETA, you are computing a posterior — explicitly or implicitly. Doing it explicitly is usually better.",
    ],
    # New categories
    "ai_ethics": [
        "AI ethics is not a constraint on capability; it is a sub-discipline of capability. A model that performs well on aggregate metrics but fails systematically for one demographic group is not better than a model that recognises the failure and refuses to predict — it is worse, because aggregate scores mask the harm. Fairness metrics (demographic parity, equalised odds, calibration) make these failure modes legible.",
        "Interpretability matters because every model is eventually questioned, audited, or contested. A black-box recommendation engine can survive in low-stakes consumer settings; the same model in lending, hiring, or criminal-justice settings cannot. The current practitioner's toolkit — LIME, SHAP, integrated gradients, mechanistic interpretability — is incomplete but improving fast, and the engineers who use it now will lead the field.",
    ],
    "ux_design": [
        "UX is a discipline of removing friction. The user did not come to your app to admire the interface; they came to accomplish a task. Every interaction that does not serve that task is overhead, and overhead compounds. The best interfaces feel inevitable in retrospect because every element earned its space.",
        "Heuristic evaluation (Nielsen's 10), user testing, and analytics-driven iteration form a three-legged stool. Skipping any leg produces lopsided design: pure heuristics yield beautiful unusable things; pure testing yields locally optimal but globally incoherent products; pure analytics yields features that move metrics but not lives. The mature designer triangulates.",
    ],
    "distributed_systems": [
        "Distributed systems is the engineering discipline of cooperation between unreliable components over unreliable networks. Every property you take for granted on a single machine — total ordering, consistent reads, atomic writes — must be re-derived, often at substantial cost, in a distributed setting. Lamport's 'Time, Clocks, and the Ordering of Events' (1978) is still the right paper to start with; nothing since has invalidated it.",
        "Consensus algorithms — Paxos, Raft, Viewstamped Replication — solve the same problem (agreement among machines that can fail) and are isomorphic under reasonable mappings. Raft is the clearest pedagogically; Paxos is the historically dominant; the implementation details that determine production reliability (log compaction, membership change, leader transfer) are where teams either succeed or quietly accumulate corruption bugs.",
    ],
    "mobile_dev": [
        "Mobile development inherits the constraints of embedded systems with the expectations of consumer software: 60fps animations, no jank, no battery drain, no crashes, all on a device the user can replace at any moment. Every successful mobile codebase respects the platform's threading model (Main thread is sacred), memory ceiling (the OS will kill you), and lifecycle (background ≠ paused ≠ killed).",
        "Cross-platform versus native is the perennial debate. The honest answer in 2026 is: for most consumer apps, a modern cross-platform stack (Flutter, React Native with Hermes/Fabric, Kotlin Multiplatform) gets you 90% of native performance with 30% of the engineering cost. The 10% of apps where the last performance percent matters — games, AR, capture-intensive media — still go native, but the share is smaller every year.",
    ],
    "performance_eng": [
        "Performance engineering is measurement-first. Every optimisation begins with a flame graph, a sampling profile, or a tracing histogram — not with a hunch. The most common career-limiting move for a programmer is to spend a week optimising code that contributes 0.3% of total time. Measurement is cheap; the wrong optimisation is expensive.",
        "Amdahl's Law sets the ceiling: even an infinite speedup of a part is bounded by the fraction of total time that part consumes. Gustafson's Law sets the floor: with larger workloads, parallel speedup approaches linear because the serial fraction shrinks relative to the parallel one. Both laws are decision tools — they tell you when to optimise serially and when to scale horizontally.",
    ],
}

# ───── CASE STUDIES — real-world anecdotes by category ─────
CASE_STUDIES_BY_CATEGORY: Dict[str, List[str]] = {
    "cs_foundations": [
        "Google's early advantage was not search quality — others matched it — but the engineering of PageRank's sparse-matrix iteration. Treating link counts as an eigenvalue problem and exploiting the matrix's sparsity reduced a problem theoretically requiring centuries of compute to one tractable on commodity hardware. Pure algorithms beat brute force.",
        "Facebook's News Feed ranking, in its first three years, was repeatedly bottlenecked not by ML model quality but by data-structure choices in the candidate-generation stage. Switching from list traversals to inverted-index lookups produced order-of-magnitude latency improvements that no model tweak could replicate.",
    ],
    "security": [
        "The 2017 Equifax breach exposed 147M people's PII. The root cause was a known Apache Struts vulnerability that had been patched two months earlier. Equifax's patch-management process did not surface it. The chapter's lesson: security is operational, not just architectural, and the slowest team in your delivery chain sets your attack-surface clock.",
        "The 2021 Log4Shell incident demonstrated supply-chain risk at internet scale. A single log4j flaw was exploitable in millions of unrelated systems because every Java project in the world had transitively pulled it in. Dependency hygiene matters; SBOM (software bill of materials) is the discipline that turns it into a habit.",
    ],
    "ml": [
        "OpenAI's GPT lineage from GPT-1 (2018, 117M parameters) to GPT-4 (2023, undisclosed but ≥1T parameters) was not a series of algorithmic breakthroughs but a series of scale-up engineering victories. The 'scaling laws' paper (Kaplan et al., 2020) made the recipe explicit: keep increasing model size, data, and compute in roughly fixed ratios; loss decreases predictably. That predictability funded the next round of capital.",
    ],
    "distributed_systems": [
        "Google's Spanner paper (2012) demonstrated externally-consistent global transactions over commodity hardware using TrueTime — a clock service with bounded uncertainty driven by GPS and atomic-clock fleets in every data centre. The paper changed the industry's view of what distributed databases could promise. Most competitors caught up only by adopting variants of the TrueTime idea.",
    ],
    "mobile_dev": [
        "Instagram's launch (2010) was famously built by two engineers using Django and Python because they refused to write platform-specific code prematurely. As they scaled past 10M users they pruned hot paths into C++ and split the monolith into services. The lesson is sequence: simplicity until the metrics force complexity.",
    ],
}

# ───── COMMON MISCONCEPTIONS ─────
MISCONCEPTIONS_BY_CATEGORY: Dict[str, List[str]] = {
    "cs_foundations": [
        "Misconception: 'Big-O notation tells you which algorithm is fastest.' Reality: Big-O describes asymptotic growth and ignores constants. For small or moderate n, a constant-heavy O(n log n) algorithm can lose to a simple O(n²) one. Always benchmark with realistic input sizes before declaring one algorithm 'better'.",
        "Misconception: 'Recursion is slower than iteration.' Reality: in modern languages with tail-call optimisation or trampolining, recursion compiles to equivalent loops. Where overhead exists, it is often dwarfed by the algorithmic structure that recursion makes possible. Choose for clarity first; profile if performance becomes a real constraint.",
    ],
    "ml": [
        "Misconception: 'More parameters always means better.' Reality: the relationship is conditional on dataset size and compute. Chinchilla scaling (2022) showed many large models were under-trained; given a compute budget, smaller models trained on more data outperformed larger ones. Capacity must match data, not exceed it.",
    ],
    "security": [
        "Misconception: 'HTTPS makes my site secure.' Reality: HTTPS protects data IN TRANSIT only. An XSS vulnerability, SQL injection, authentication weakness, or misconfigured S3 bucket is still fully exploitable over HTTPS. The TLS handshake is the front door's lock; the rest of your house still needs locks of its own.",
    ],
    "web": [
        "Misconception: 'A heavier framework means a slower site.' Reality: the framework's size matters less than how well its idioms cooperate with the platform (HTTP cache, code-splitting, streaming SSR, defer/async). A 200KB framework used well outperforms a 50KB one used badly. Measure the network waterfall, not the bundle size in isolation.",
    ],
}

# ───── FURTHER READING — curated next-step references ─────
FURTHER_READING_BY_CATEGORY: Dict[str, List[str]] = {
    "cs_foundations": [
        "Cormen, Leiserson, Rivest & Stein — *Introduction to Algorithms* (CLRS). The standard reference; deep but readable.",
        "Sedgewick & Wayne — *Algorithms* (Princeton). More applied than CLRS; includes runnable Java code.",
        "Aho, Lam, Sethi & Ullman — *Compilers: Principles, Techniques, and Tools* ('Dragon book') for the language end of foundations.",
    ],
    "languages": [
        "Pierce — *Types and Programming Languages*. The canonical type-theory primer.",
        "Friedman & Wand — *Essentials of Programming Languages*. Build interpreters; understand languages by building them.",
        "Krishnamurthi — *Programming Languages: Application and Interpretation* (free online).",
    ],
    "architecture": [
        "Martin — *Clean Architecture* and *Clean Code*.",
        "Vernon — *Implementing Domain-Driven Design*.",
        "Fowler — *Patterns of Enterprise Application Architecture* (still a useful classic).",
    ],
    "gamedev": [
        "Gregory — *Game Engine Architecture* (Naughty Dog). Encyclopaedic.",
        "Akenine-Möller, Haines, Hoffman — *Real-Time Rendering* (every edition is current art).",
        "Nystrom — *Game Programming Patterns* (free online).",
    ],
    "security": [
        "Anderson — *Security Engineering* (free 3rd edition online). The single best book on the subject.",
        "Howard & LeBlanc — *Writing Secure Code*.",
        "OWASP Top Ten + ASVS (verified standard) — keep close.",
    ],
    "ml": [
        "Bishop — *Pattern Recognition and Machine Learning* for classical foundations.",
        "Goodfellow, Bengio & Courville — *Deep Learning* (free online).",
        "Murphy — *Probabilistic Machine Learning* (two volumes).",
    ],
    "practices": [
        "Martin — *Clean Code*.",
        "Hunt & Thomas — *The Pragmatic Programmer*.",
        "Beck — *Test-Driven Development by Example*.",
    ],
    "devops": [
        "Forsgren, Humble & Kim — *Accelerate*. Data-driven evidence on what makes teams ship.",
        "Kim, Behr & Spafford — *The Phoenix Project*. Narrative form of the same ideas.",
        "Hightower, Burns & Beda — *Kubernetes: Up and Running*.",
    ],
    "web": [
        "MDN Web Docs — the canonical browser/standards reference.",
        "Web.dev — Google's curated performance, accessibility, and PWA guidance.",
        "Crockford — *JavaScript: The Good Parts* (historic but still influential).",
    ],
    "databases": [
        "Kleppmann — *Designing Data-Intensive Applications*. The best modern systems book, full stop.",
        "Date — *An Introduction to Database Systems* for the relational foundations.",
        "Petrov — *Database Internals* for the storage-engine side.",
    ],
    "math": [
        "Strang — *Introduction to Linear Algebra* and the MIT 18.06 lectures.",
        "Grimaldi — *Discrete and Combinatorial Mathematics*.",
        "Wasserman — *All of Statistics*.",
    ],
    "ai_ethics": [
        "Barocas, Hardt & Narayanan — *Fairness and Machine Learning* (free online).",
        "Mitchell — *Artificial Intelligence: A Guide for Thinking Humans*.",
        "Anthropic & OpenAI red-team papers.",
    ],
    "ux_design": [
        "Norman — *The Design of Everyday Things*.",
        "Krug — *Don't Make Me Think*.",
        "Nielsen — usability heuristics + research articles.",
    ],
    "distributed_systems": [
        "Tanenbaum & van Steen — *Distributed Systems*.",
        "Lamport — collected papers (esp. Time, Clocks; Paxos Made Simple).",
        "Kleppmann — same as databases entry; ch. 5–9 are gold.",
    ],
    "mobile_dev": [
        "Google + Apple developer documentation (Android Architecture, iOS HIG).",
        "Cinnamon — *Operating Systems: Three Easy Pieces* (free) for the underpinnings.",
        "Square's engineering blog for production patterns.",
    ],
    "performance_eng": [
        "Gregg — *Systems Performance* and *BPF Performance Tools*.",
        "Drepper — 'What Every Programmer Should Know About Memory' (long but essential).",
        "Patterson & Hennessy — *Computer Architecture: A Quantitative Approach*.",
    ],
}
