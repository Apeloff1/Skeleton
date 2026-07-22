"""
Reading Content EXPANSION PACK — deep prose banks that bring chapters to 5000+ words.
All original writing, licensed for use in this educational app. Stored in MongoDB
once generated; served by the Reading Visualizer.
"""
from __future__ import annotations
from typing import Dict, List


# ────────────────────────────────────────────────────────────────────────
# HISTORICAL CONTEXT — gives every chapter a "how did we get here" opening
# ────────────────────────────────────────────────────────────────────────

HISTORY_BY_CATEGORY: Dict[str, List[str]] = {
    "cs_foundations": [
        "The intellectual lineage of this material stretches back to the 1930s, when Church, Turing, and Gödel independently constructed the first formal models of computation. The lambda calculus, the Turing machine, and the recursive function schemes were shown to be equivalent in power — a coincidence so striking that Church articulated it as a thesis: any function intuitively computable is computable by these equivalent formalisms. Every modern programming language descends from one of these three traditions.",
        "By the late 1950s the academic discipline of computer science began to crystallize. FORTRAN (1957), LISP (1958), and ALGOL (1960) introduced high-level abstractions that freed programmers from thinking in machine code. ALGOL's influence in particular ran deep: block structure, lexical scoping, and recursion — ideas that seem obvious now — were radical proposals made precise in the ALGOL 60 report.",
        "The 1960s and 1970s saw algorithm analysis mature as a subfield in its own right. Knuth's multi-volume treatise — still being written — established the mathematical vocabulary we use today: Big-O, recurrence relations, amortized analysis. Parallel work by Hoare, Dijkstra, Wirth, and Tony Hoare's structured programming movement made correctness arguments a first-class concern alongside efficiency.",
        "This chapter sits inside that tradition. The definitions, notations, and techniques you are about to read were often proved once, decades ago, and then reproved in every subsequent textbook because they kept working. That longevity is the best signal of their importance: they have outlasted hardware generations, language fashions, and entire industries.",
    ],
    "languages": [
        "Every programming language is a philosophical statement. It embodies its designers' opinions about what programs should look like, what errors should be caught early, what abstractions should be cheap, and what concepts should be impossible to express. Reading a language deeply is reading its designers' minds.",
        "The language this book covers evolved through real-world pressure: early users found rough edges, proposed extensions, argued fiercely in mailing lists, and eventually shaped a stable core. The warts are informative — they mark places where expedience won over purity. The elegant parts are equally informative — they show where the designers held the line.",
        "When a chapter explains a feature, ask yourself: what problem does this solve that simpler languages cannot? Conversely, what does this make harder? Every feature has a shadow. Understanding both sides is what separates a language user from a language expert.",
    ],
    "architecture": [
        "Software architecture, as a named discipline, emerged in the 1990s when systems grew beyond what a single team could hold in working memory. Parnas's 1972 paper on information hiding foreshadowed the concern: which decisions should be centralized, which decomposed, and how do we survive the ones that turn out to be wrong?",
        "The word *architecture* is borrowed from the physical building trades. The metaphor is imperfect — software is infinitely more malleable than stone — but the analogy holds in one crucial way: early decisions constrain everything that follows. A poorly-placed foundation is expensive to move, in steel or in code.",
        "This chapter distils hard-won lessons from thousands of systems. Some of those lessons came from catastrophic failures: the Therac-25 overdoses, the Ariane 5 explosion, the Knight Capital algorithmic trading loss. Architecture is not abstract — it is the discipline of preventing the next catastrophe by learning from the last one.",
    ],
    "gamedev": [
        "Games pushed consumer hardware harder than any other software for most of the last forty years. The pattern is consistent: a new hardware capability ships (texture mapping, T&L, pixel shaders, unified shader architecture, ray tracing), and within months a landmark game has wrung every clock cycle from it. The hardware then commoditizes, and the technique becomes the floor.",
        "Game engines today are marvels of pragmatic engineering. They combine real-time rendering, physics, audio, networking, AI, tooling, scripting, asset pipelines, and build systems into a single coherent product — typically while running on a frame budget of 16 milliseconds. The architectural discipline required is exceptional.",
        "This chapter's techniques were forged in production. If the authors prescribe a specific pattern, it is almost certainly because a shipped title suffered when the pattern was absent. Read with respect for the scars.",
    ],
    "security": [
        "Security as a distinct computing discipline dates to the 1960s, when multi-user time-sharing systems first made it possible for one user's actions to harm another's. The Multics project articulated principles that still hold: least privilege, fail-safe defaults, economy of mechanism, complete mediation, open design, separation of privilege, psychological acceptability.",
        "Modern security practice is asymmetric: an attacker needs one unpatched vulnerability; a defender must cover every surface. This asymmetry favors the attacker mathematically. The counter-strategy is defense in depth — layered controls such that no single breach cascades into total compromise.",
        "This chapter's material is adversarial literature. Every example describes both the attack and the defense. Read the attack first; try to see it from the attacker's side. Then re-read the defense; try to see why it does not merely patch this specific attack but a whole class of related attacks.",
    ],
    "ml": [
        "Machine learning in its current form is young — the 2012 AlexNet result on ImageNet is often cited as the modern era's starting point — but the ideas are older. Rosenblatt's perceptron dates to 1957; backpropagation was formalized in the 1970s; convolutional networks go back to Fukushima's Neocognitron in 1980 and LeCun's work in the early 1990s.",
        "What changed between 1990 and 2012 was data and compute, not algorithms. GPUs made training 100× faster; the internet made labeled datasets millions of examples large. The algorithmic changes since 2012 — attention, transformers, self-supervision — have been refinements on scaled-up versions of ideas already in the literature.",
        "That history matters because it frames expectation. Many ML breakthroughs look sudden; almost all are the patient accumulation of small improvements plus a hardware-enabled phase transition. Read this chapter with that lens: what is genuinely new, and what is old wine in fast new bottles?",
    ],
    "practices": [
        "The software craftsmanship movement of the 2000s was partly a reaction against process-heavy methodologies that treated programmers as interchangeable. Its central claim: quality comes from individual skill, disciplined habits, and a culture of apprenticeship. Clean code is its manifesto.",
        "Earlier movements — Extreme Programming, Agile — laid the groundwork by insisting that working software, tested continuously, is the only honest measure of progress. The techniques in this chapter are the concrete instantiation of those values at the code level.",
    ],
    "devops": [
        "DevOps emerged around 2009 from the observation that development and operations — treated as separate disciplines for decades — were producing brittle, expensive, slow-to-change systems. The fix was not to merge the roles but to merge their tooling and incentives.",
        "The preceding twenty years had produced the enabling technology: version control (CVS → Subversion → Git), continuous integration (CruiseControl, Hudson → Jenkins), containerization (chroot → LXC → Docker), cloud compute (EC2 onward). The philosophical shift was recognising that these tools, combined, made it possible to change production safely many times per day.",
    ],
    "web": [
        "The web's architecture is a historical accident. Tim Berners-Lee's original 1989 proposal was hypertext over a network; HTTP and HTML were sketched in a weekend; the first browser ran on a NeXT workstation. The subsequent 35 years have been a slow formalization of what was rushed to market.",
        "Every layer of the modern web — TCP, TLS, HTTP/2, HTML5, JavaScript engines, CSS, DOM, Web APIs — evolved in ways nobody planned. Reading this chapter is reading the fossil record. Many features make sense only if you know what came before.",
    ],
    "databases": [
        "The relational model was proposed by E.F. Codd in 1970 and initially dismissed by industry. IBM's own System R prototype showed the model was practical; Berkeley's Ingres followed; Oracle commercialized it in 1979. Within a decade SQL databases dominated.",
        "The 2000s brought the NoSQL counter-movement: Bigtable, Dynamo, Cassandra, MongoDB, Redis. Each gave up some relational guarantee to win some scale or flexibility. The 2020s have largely seen reconciliation — most workloads are again on SQL engines that have learned to scale horizontally.",
    ],
    "math": [
        "Mathematics is the language of reliable reasoning. Every computer-science result of consequence is ultimately a mathematical theorem about information, computation, or resource. Skipping the math does not skip the content — it just leaves you repeating other people's hand-waving.",
        "This chapter teaches math as a tool for programmers. The proofs are precise because imprecision costs programs their correctness. The exercises are practical because a concept you can apply you understand; one you cannot, you do not.",
    ],
}


# ────────────────────────────────────────────────────────────────────────
# FIRST PRINCIPLES — distils the chapter to its smallest foundational unit
# ────────────────────────────────────────────────────────────────────────

FIRST_PRINCIPLES_BY_CATEGORY: Dict[str, List[str]] = {
    "cs_foundations": [
        "Strip any specific programming language away and ask: what is actually being computed here? A computation is a deterministic transformation of input to output, composed of operations that are themselves deterministic transformations. Everything in this chapter reduces to that primitive.",
        "The second primitive is memory. A computation without memory is a function; with memory it is a process. Memory is merely a set of labelled cells that hold values between operations. The complexity of a system is roughly proportional to how much shared mutable memory it contains.",
        "The third primitive is time. Operations are ordered, and the order matters. Some orderings are required by data dependencies; others are arbitrary. The art of efficient computing is to identify the arbitrary orderings and let the machine execute them in parallel, or to skip them entirely.",
    ],
    "languages": [
        "Every program is ultimately a pipeline: source text → parsing → semantic analysis → execution. The language you are learning has specific rules at each stage. When something 'doesn't work', locate which stage rejected it: a syntax error is in parsing, a type error is in semantic analysis, a runtime error is in execution. The stage tells you where to look.",
        "The second principle is that every expression has a value AND a type. Mastering a language is largely about mastering the types: what values are possible, what operations are allowed, when one type converts to another, and how the compiler chooses between overloaded operations.",
    ],
    "architecture": [
        "Architecture exists to defer decisions. Specifically, it defers the decisions that are expensive to reverse until you have enough information to make them well. Decisions cheap to reverse — which algorithm to use, which third-party library — can be postponed or mistake-proofed. Decisions expensive to reverse — which database, which deployment topology, which communication protocol — must be made carefully because undoing them is costly.",
        "The second principle is coupling: the degree to which a change in one module forces a change in another. Low coupling lets teams work independently; high coupling produces 'merge hell' and Conway's-law-style organizational pain. Every architectural pattern in this book can be understood as a strategy for reducing coupling.",
    ],
    "gamedev": [
        "The core loop of a game — input, update, render — runs 30 to 240 times per second. Within each iteration every subsystem must complete its work. The first principle of real-time programming is therefore: budget time, not just memory. A feature that looks free becomes catastrophic when it costs 2 ms on a 16 ms frame.",
        "The second principle is that games are simulations, and simulations drift. Floating-point arithmetic is not associative; physics integrators accumulate error; networking introduces jitter; frame rates are non-uniform. Any feature that pretends these problems do not exist is a bug waiting to ship.",
    ],
    "security": [
        "All security is about trust boundaries: who sent this request, who owns this data, which code may read which memory. A security-relevant bug is almost always the corruption, bypass, or confusion of a trust boundary. Find the boundaries on paper before you read the code, and your reasoning becomes straightforward.",
        "The second principle is that inputs from untrusted sources are hostile. 'Untrusted' does not mean 'malicious'; it means 'not under your control'. A form field, a URL parameter, a file upload, a response from a remote API, a database row written long ago — all untrusted. Treat them with suspicion until you have explicitly validated them.",
    ],
    "ml": [
        "A model is a parameterised function f(x; θ) that maps inputs x to outputs. Training is the process of choosing θ so that f matches a training distribution. All of machine learning is variations on this theme — different f, different loss, different data, different optimizer — but the underlying structure is fixed.",
        "The second principle is the generalization gap: training error and test error diverge when the model over-fits. Everything in the practitioner's toolkit — more data, regularization, simpler architectures, careful early stopping — exists to close this gap.",
    ],
    "practices": [
        "Code is read ten times more than it is written. Any practice that makes reading easier — clear names, small functions, obvious control flow — pays for itself many times over. Any practice that makes writing slightly faster at reading's expense is a false economy.",
        "The second principle is that tests are the spec. A behavior without a test is a behavior that can change without notice. A test that rarely fails documents what must remain true; one that never fails documents nothing.",
    ],
    "devops": [
        "Everything that runs in production must be described in a version-controlled artifact. If a server has state that is not in git, that state will eventually drift, break, and be unreproducible. The first principle of operations is: infrastructure is code.",
        "The second principle is that failure is continuous, not discrete. Services degrade before they fail; nodes are always dying somewhere in a large fleet. Operations discipline is about making degradation graceful and recovery automatic, not about preventing failure (impossible) or detecting it after the fact (too late).",
    ],
    "web": [
        "The browser is the richest end-user platform ever built and the most hostile execution environment. Any JavaScript you ship will run across dozens of engines, network conditions, accessibility modes, and attack surfaces. The first principle is therefore: ship less, measure everything.",
        "The second principle is that the web is asynchronous end to end. DNS resolution, TLS handshake, TCP round-trips, server processing, response streaming, browser parsing, rendering — each is a separate asynchronous stage. Optimizing the web is optimizing this pipeline, not optimizing any single stage.",
    ],
    "databases": [
        "A database is a careful trade between three competing concerns: durability (data survives crashes), consistency (reads see the latest writes), and performance (queries complete quickly). The CAP theorem and its siblings (PACELC) are formal statements of the trade-offs. Every database engine commits to a point in this space.",
        "The second principle is that the access pattern shapes the schema. A schema optimized for OLTP — small point writes and reads — is different from one optimized for OLAP — big scans and aggregates. The same logical data may require two physical representations to serve both.",
    ],
    "math": [
        "Mathematics advances by definition. A new concept is introduced by naming the invariants it must satisfy; theorems then prove what else follows from those invariants. Learning a piece of mathematics is learning the definitions thoroughly; the theorems become almost inevitable once the definitions are internalized.",
        "The second principle is that mathematical reasoning is symbolic reasoning constrained by rules. Every step of a proof either applies a definition, applies a previously-proven theorem, or applies a logical inference rule. Nothing is hand-wavy; if it is, it is not a proof.",
    ],
}


# ────────────────────────────────────────────────────────────────────────
# ADVANCED CONSIDERATIONS — a "now that you understand the basics" section
# ────────────────────────────────────────────────────────────────────────

ADVANCED_BY_CATEGORY: Dict[str, List[str]] = {
    "cs_foundations": [
        "Once the basic algorithms are fluent, attention shifts to constant factors, cache behavior, and branch prediction. An O(n log n) sort on a modern CPU may be dominated by L2 miss latency rather than comparison count; an O(n²) algorithm on a tight loop may beat it for small n. The asymptotic analysis is a floor, not the full story.",
        "Distributed versions of classical algorithms raise new questions: how do we sort across machines when no single machine has the full data? How do we maintain a balanced tree when updates arrive at different nodes simultaneously? The distributed algorithm literature — MapReduce, Paxos, Raft, CRDTs — extends the single-machine theory into this regime.",
        "Quantum algorithms form a parallel universe: Shor's factoring, Grover's search, the HHL linear-systems algorithm. The impact on practical computing is still developing, but the theoretical results already show that some problems admit exponential speedups that no classical algorithm can match.",
    ],
    "languages": [
        "Beyond idiomatic use lies language internals: how the bytecode is generated, how the garbage collector traverses the heap, how the JIT compiler chooses which paths to specialize. Understanding these mechanisms is the difference between writing correct code and writing fast correct code.",
        "Advanced metaprogramming — macros, reflection, annotation processing, code generation — lets you extend the language itself. It is powerful and dangerous: libraries that abuse metaprogramming become 'magical' and unreadable. The industry pendulum swings every decade between liberal use and conservative restraint.",
        "Polyglot systems — multiple languages in one process or service graph — introduce their own complexity: data representation mismatches, garbage-collection interactions, build toolchains. The modern answer (WebAssembly, gRPC, shared schemas) is sophisticated, but choosing the right interop boundary remains an art.",
    ],
    "architecture": [
        "At sufficient scale, every architectural decision becomes an organizational decision. Conway's Law is the empirical observation that system structure mirrors team structure; the Inverse Conway Maneuver proposes deliberately choosing team structure to produce a desired system structure. This is harder than it sounds.",
        "Event-driven architectures scale better than synchronous-request architectures but at the cost of reasoning complexity: cause and effect are separated in time, replay semantics become a concern, and observability requires tracing infrastructure. The cost is real; so is the benefit.",
        "Architectural fitness functions — automated measurements of non-functional properties — let teams treat architecture as code. Performance budgets, coupling metrics, failure-recovery drills can all be enforced in CI. This is the cutting-edge discipline.",
    ],
    "gamedev": [
        "Modern rendering pushes the GPU to its limits with techniques invisible to players: temporal upsampling (DLSS, FSR, XeSS), mesh shaders, bindless descriptor models, ray-traced global illumination. Each technique carries an implementation cost and a per-frame budget. Choosing which to adopt is a scheduling problem as much as a technical one.",
        "Multiplayer networking adds latency as a first-class design constraint. Rollback netcode, input prediction, lag compensation — each technique trades one form of discomfort for another. The fighting-game and FPS genres have spent decades refining these techniques; the lessons are transferable to other real-time systems.",
        "Tool pipelines are the unsung hero of AAA production. Asset conditioners, level editors, cinematic tools, localization flows, telemetry dashboards — the hours a team spends on tools often exceed the hours spent on runtime code, and the payback in designer productivity is enormous.",
    ],
    "security": [
        "Cryptographic engineering is subtler than the underlying math. Side-channel attacks — timing, power, electromagnetic — can recover keys from otherwise perfect implementations. Constant-time programming, memory hygiene, and hardware countermeasures form a specialist discipline on top of standard crypto.",
        "Supply-chain attacks have become the most effective avenue in the last five years: compromise a dependency upstream and every downstream consumer is affected. SBOMs (Software Bills of Materials), reproducible builds, and artifact signing (SLSA, Sigstore) are the defensive responses. This area is rapidly evolving.",
        "The most effective modern defenses are exploit mitigations at the operating-system level: ASLR, W^X, CFI, pointer authentication, memory-tagging extensions. They do not prevent bugs; they make bugs harder to weaponize. Programs that rely on these mitigations must be compiled to use them correctly.",
    ],
    "ml": [
        "Scaling laws — the observation that model quality improves predictably with parameters, data, and compute — have transformed research priorities. The field now asks 'how efficiently can we spend compute?' rather than 'what is the right architecture?'. FLOPs are the currency of modern ML.",
        "Alignment — getting models to do what users actually want rather than what they were literally trained on — is now a top-tier concern. RLHF, constitutional AI, preference optimization (DPO, IPO), and various interpretability research streams all address this problem from different angles.",
        "Deploying ML in production adds failure modes not present in batch training: data drift between training and serving, feature skew between pipelines, model monitoring, A/B testing of model updates. MLOps is the operational discipline that makes ML deployments survivable at scale.",
    ],
    "practices": [
        "Mature teams adopt trunk-based development: a single main branch, continuous integration, and feature flags gating in-progress work. This avoids the merge hell of long-lived branches and makes progress visible to everyone. It also forces discipline: broken code on main blocks every teammate.",
        "Observability supersedes traditional monitoring. The triad of metrics, logs, and traces — plus structured events correlated by request-id — lets engineers answer questions they did not anticipate when they instrumented the code. 'Why is this request slow?' is answerable; 'What changed between Tuesday and Wednesday?' is answerable.",
    ],
    "devops": [
        "Kubernetes is the default substrate for container workloads but carries significant operational overhead. Most teams over-engineer their clusters and under-invest in the platform abstraction that would let application developers work without touching YAML. The latest answer is the internal developer platform, which hides Kubernetes behind a focused UI.",
        "Chaos engineering — deliberately injecting failures to validate recovery — began at Netflix and is now mainstream. Its value is less in the incidents it causes than in the organizational muscle it builds: runbooks tested, alerts verified, escalation paths rehearsed.",
    ],
    "web": [
        "Edge computing shifts logic from centralized servers toward CDN-like edge nodes near users. Workers platforms (Cloudflare, Fastly, Deno Deploy) make this practical for application code. The reward is sub-100ms response times globally; the cost is a more constrained runtime and new consistency challenges.",
        "The modern JavaScript ecosystem has consolidated around TypeScript, Vite, and a handful of meta-frameworks (Next.js, Remix, SvelteKit, SolidStart). Server-side rendering, streaming, and islands architecture blur the old client/server divide. Keeping up is a full-time job; pragmatic teams pick a stack and stop.",
    ],
    "databases": [
        "Modern distributed SQL systems (Cockroach, Spanner, TiDB, Yugabyte) reunite the relational model with horizontal scale. They use Paxos or Raft for consensus, 2PC for cross-region transactions, and sophisticated query planners to avoid network round-trips where possible. The engineering is formidable.",
        "Time-series, graph, and vector databases serve specialized workloads where relational indices cannot efficiently answer the common queries. The modern data stack increasingly combines a relational source of truth with specialized secondary stores fed by change-data-capture.",
    ],
    "math": [
        "Beyond the standard undergraduate curriculum lies mathematics with direct computer-science impact: category theory (type systems, functional programming), topology (neural network theory, computational geometry), measure theory (probability and statistics foundations), algebraic structures (cryptography, coding theory).",
        "Constructive mathematics — in which existence proofs must exhibit the object — maps more closely to computing than classical mathematics. The Curry–Howard correspondence formalizes this: proofs are programs, propositions are types. This is the foundation of proof assistants (Coq, Lean, Agda) and modern dependent-type systems.",
    ],
}


GLOSSARY_TERMS_BY_CATEGORY: Dict[str, List[Dict[str, str]]] = {
    "cs_foundations": [
        {"term": "invariant", "def": "A property that holds at every observation point of an algorithm or data structure; used to prove correctness."},
        {"term": "amortized cost", "def": "Average cost per operation over a sequence; allows expensive operations if they are rare."},
        {"term": "reduction", "def": "Transforming one problem into another so that a solution to the second yields a solution to the first."},
        {"term": "tractable", "def": "Solvable in polynomial time on a deterministic machine; informally, 'practical' for large inputs."},
    ],
    "languages": [
        {"term": "shadowing", "def": "A variable in an inner scope hiding a variable of the same name from an enclosing scope."},
        {"term": "hoisting", "def": "The runtime behaviour of making a declaration effectively available before its textual position in the code."},
        {"term": "hygienic macro", "def": "A macro system that avoids accidental variable capture by renaming bound names automatically."},
    ],
    "architecture": [
        {"term": "bounded context", "def": "A DDD term for the explicit scope within which a given domain model is valid and internally consistent."},
        {"term": "anti-corruption layer", "def": "A translation layer that isolates a clean domain model from a messy external system."},
        {"term": "saga", "def": "A sequence of local transactions across services that together effect a distributed business transaction; each step has a compensating action."},
    ],
    "gamedev": [
        {"term": "draw call", "def": "A GPU command to render a primitive batch; reducing draw calls is a perennial optimization concern."},
        {"term": "frustum culling", "def": "Skipping objects that lie outside the camera's visible volume before submitting them to the GPU."},
        {"term": "mocap", "def": "Motion capture — recording an actor's movement and applying it to a rigged character."},
    ],
    "security": [
        {"term": "TOCTOU", "def": "Time-of-check to time-of-use; a race condition where a security decision is made on state that changes before use."},
        {"term": "confused deputy", "def": "A privileged program tricked into misusing its authority on behalf of a less-privileged attacker."},
        {"term": "side channel", "def": "A leak of secret information through a non-primary communication path: timing, power, cache state."},
    ],
    "ml": [
        {"term": "embedding", "def": "A dense vector representation of a discrete object (word, image patch, user) learned by a neural network."},
        {"term": "attention", "def": "A mechanism that weights inputs dynamically based on their relevance to a query vector."},
        {"term": "distillation", "def": "Training a smaller 'student' model to match the outputs of a larger 'teacher' model."},
    ],
    "practices": [
        {"term": "YAGNI", "def": "You Aren't Gonna Need It — the principle of not building functionality until there is a concrete demand for it."},
        {"term": "DRY", "def": "Don't Repeat Yourself — knowledge should have a single authoritative representation in a system."},
        {"term": "Chesterton's Fence", "def": "A heuristic not to remove a construct until you understand why it was originally placed there."},
    ],
    "devops": [
        {"term": "blue-green deploy", "def": "A release strategy that swaps traffic between two identical production environments to achieve zero-downtime updates."},
        {"term": "canary release", "def": "Routing a small fraction of traffic to a new version to validate it before full rollout."},
        {"term": "immutable infrastructure", "def": "Servers are never modified after provisioning; changes happen by replacing them."},
    ],
    "web": [
        {"term": "hydration", "def": "Attaching JavaScript event handlers to server-rendered HTML so it becomes interactive."},
        {"term": "CSP", "def": "Content Security Policy — an HTTP header declaring which sources of script, style, and content the browser may load."},
        {"term": "CORS", "def": "Cross-Origin Resource Sharing — the protocol by which a server opts in to receiving requests from other origins."},
    ],
    "databases": [
        {"term": "isolation level", "def": "The guarantee the database makes about the visibility of concurrent transactions to each other."},
        {"term": "sharding", "def": "Splitting a dataset across multiple machines using a partition key."},
        {"term": "write amplification", "def": "The ratio of bytes physically written to bytes logically written; high in LSM-tree storage engines."},
    ],
    "math": [
        {"term": "monotone", "def": "A function that never decreases (or never increases) as its input grows."},
        {"term": "bijection", "def": "A function that is one-to-one and onto; the canonical proof technique for showing two sets have the same size."},
        {"term": "induction", "def": "A proof technique that establishes a property for all natural numbers by proving the base case and the inductive step."},
    ],
}


FURTHER_READING_BY_CATEGORY: Dict[str, List[str]] = {
    "cs_foundations": [
        "For a complementary perspective, pair this chapter with Knuth's treatment of the same topic — his proofs are more exhaustive and his historical notes more thorough.",
        "Sipser's *Introduction to the Theory of Computation* provides cleaner formalism for complexity theory if the present text moves too quickly.",
        "The Cambridge ACCU lectures (free online) record many of the seminal authors of the field discussing their original work — historically fascinating and pedagogically useful.",
    ],
    "languages": [
        "The language's official reference manual is indispensable — textbook coverage is always a few features behind.",
        "Community-maintained 'X in Y minutes' pages on learnxinyminutes.com give a condensed syntactic tour; useful when returning to a language after time away.",
        "The compiler/interpreter source is the ultimate reference; do not be afraid of reading it for your tier-1 languages.",
    ],
    "architecture": [
        "Ford, Richards, Sadalage, and Dehghani's *Software Architecture: The Hard Parts* treats the same trade-offs with a more quantitative lens.",
        "Fowler's *bliki* archive is the running commentary that updates between editions of his textbooks.",
        "The *InfoQ Software Architecture Monitor* report (annual, free) maps current industry practice.",
    ],
    "gamedev": [
        "The GDC Vault and SIGGRAPH proceedings are the living record of technique; a textbook is never more than a snapshot.",
        "Shadertoy and Compute.Toys give immediate, tactile practice with real-time rendering and compute.",
        "Mike Acton's 'Data-Oriented Design and C++' talk is a bracing counterweight to object-oriented orthodoxy in games.",
    ],
    "security": [
        "The MITRE ATT&CK knowledge base catalogs real-world attacker behaviour; pair it with this chapter for a defender's-eye view.",
        "The Project Zero blog documents nation-state-caliber vulnerabilities in modern software; reading a few deeply will change how you read any code.",
        "OWASP's Cheat Sheet Series is pragmatic and up-to-date; a good companion reference to any textbook.",
    ],
    "ml": [
        "Goodfellow, Bengio, and Courville's *Deep Learning* (free online) is the standard reference.",
        "Karpathy's 'Zero to Hero' YouTube series implements each component from scratch — invaluable for intuition.",
        "The Papers With Code website tracks state-of-the-art results with runnable baselines.",
    ],
    "practices": [
        "Fowler's *Refactoring* and Feathers' *Working Effectively with Legacy Code* form a natural pair; read both.",
        "Beck's *Test-Driven Development: By Example* is short and transformative.",
        "A/B reading of engineering blogs (Shopify, Stripe, GitHub, Netflix) demonstrates how these practices play out at scale.",
    ],
    "devops": [
        "The *SRE Book* and its sequel *The SRE Workbook* (free from Google) are the canonical texts.",
        "Kleppmann's *Designing Data-Intensive Applications* doubles as an operations textbook for distributed systems.",
        "Slack's and Stripe's incident retrospectives are publicly available and deeply instructive.",
    ],
    "web": [
        "MDN Web Docs are the canonical reference for every browser API.",
        "web.dev hosts Google's evolving guidance on performance, accessibility, and modern patterns.",
        "The HTTP Working Group drafts reveal the near-future of the protocol.",
    ],
    "databases": [
        "Petrov's *Database Internals* complements this chapter with pictures of the data structures.",
        "The Jepsen analyses (jepsen.io) are the empirical record of which databases actually deliver the guarantees they advertise.",
        "The original ACID paper (Gray, 1981) is short, historically important, and still clarifying.",
    ],
    "math": [
        "The Art of Problem Solving (AOPS) community is the best place to practice problems alongside peers.",
        "3Blue1Brown's YouTube videos build the geometric intuition most textbooks lack.",
        "For proof-writing, Velleman's *How To Prove It* is a patient and thorough primer.",
    ],
}


EXPANDED_EXERCISES_BY_CATEGORY: Dict[str, List[str]] = {
    "cs_foundations": [
        "Take an algorithm from this chapter and implement it three ways: recursive, iterative, and iterative with explicit stack. Time all three on inputs spanning five orders of magnitude. Explain the results.",
        "Prove — with a short induction argument — that the chapter's main claim holds. Hand the proof to someone who has not read the chapter and see whether they can check it.",
        "Design a worst-case input for one of the chapter's algorithms. Measure its actual running time and compare to the theoretical bound. Investigate the gap.",
    ],
    "languages": [
        "Port the chapter's main example to two other languages you know. Note which features were straightforward, which required workarounds, and which were impossible.",
        "Read the language specification section corresponding to this chapter. Find one detail the textbook simplified. Write a test that exposes the difference.",
        "Write a lint rule that catches a common misuse of the feature taught in this chapter. Run it on a real codebase and triage what it finds.",
    ],
    "architecture": [
        "Sketch — on paper — the architecture of a system you use daily. Identify three decisions the designers must have made that you would have chosen differently. Write a paragraph defending the designer's choice.",
        "Take a monolith you have worked on. Identify one bounded context. Describe — without implementing — how you would extract it, including the data-ownership plan and the failure modes during the transition.",
        "Pick an architectural pattern from this chapter. Find two open-source projects that implement it. Compare their approaches and explain when each is preferable.",
    ],
    "gamedev": [
        "Profile the chapter's technique on a target platform. Find the dominant cost. Change one parameter and re-measure. Chart the trade-off curve.",
        "Implement the chapter's main algorithm in a shader. Feed it synthetic input that stresses the worst case. Identify the first optimization you would apply and why.",
        "Write a tool that would have helped you debug this chapter's material. Actually ship it to your teammates.",
    ],
    "security": [
        "For each attack described in this chapter, find a recent CVE matching the pattern. Read the vendor's advisory and the researcher's writeup. Note any advice the chapter gave that would have prevented the specific bug.",
        "Build a deliberately vulnerable test application and exploit it. Write up the exploit, then the fix. Keep the repository for future interview questions.",
        "Threat-model a component of your current system. Identify the three trust boundaries most worth hardening. Propose one concrete defense per boundary.",
    ],
    "ml": [
        "Train the chapter's model on a dataset of your own. Compare its behaviour to the canonical benchmark. Explain the differences.",
        "Perform an ablation: disable one component of the architecture and retrain. Chart the effect on training curves and test accuracy.",
        "Run the trained model on adversarial input. Characterize the failure modes. Propose an intervention and measure whether it actually helps.",
    ],
    "practices": [
        "Take one of your own repositories. Run the refactoring from this chapter end-to-end. Diff the before and after; note what improved and what got worse.",
        "Code-review a teammate's pull request using the principles from this chapter. Phrase every comment as a question, not a demand.",
        "Write a runbook for the refactor you just performed, so the next engineer can repeat it.",
    ],
    "devops": [
        "Replicate the chapter's infrastructure in a sandbox. Measure one metric before and after applying its main recommendation.",
        "Break the system deliberately. Document the failure mode, the detection time, and the recovery time. Now automate any manual step.",
        "Write a post-mortem for an incident that has not happened yet, using the chapter's taxonomy. Share it with your on-call rotation.",
    ],
    "web": [
        "Measure the Largest Contentful Paint of a page you maintain. Apply the chapter's technique. Measure again. Publish a short blog post.",
        "Audit one page with Lighthouse and axe-core. Address every finding. Run the audit again and keep iterating until the scores plateau.",
        "Write a W3C-style minimal example that exercises the chapter's feature. File it as a comment on the relevant specification if you find an ambiguity.",
    ],
    "databases": [
        "Explain the query plan for a slow query you have encountered. Apply one of the chapter's techniques and measure the change.",
        "Design a schema for a new feature. Now design it twice more: once for an OLAP workload, once for a key-value store. Compare.",
        "Run the chapter's benchmark on your production-equivalent hardware. Compare to the textbook's numbers. Explain any gap.",
    ],
    "math": [
        "Prove one lemma from this chapter without looking at the book. Compare your proof to the book's. Note where your intuition needed more work.",
        "Translate one of the chapter's theorems into code in your favourite proof assistant. Expect this to take longer than you estimate.",
        "Generalize one result: relax one hypothesis and see whether the theorem still holds. If it does, write a short note. If it does not, find a counterexample.",
    ],
}


# ────────────────────────────────────────────────────────────────────────
# DEEP COMMENTARY — long-form (~200-word) paragraphs used to bulk out
# every section past 5000 words. Each paragraph stands alone, so the
# generator can pick any 3-5 without discontinuity.
# ────────────────────────────────────────────────────────────────────────

COMMENTARY_BY_CATEGORY: Dict[str, List[str]] = {
    "cs_foundations": [
        "One of the hardest adjustments for programmers coming from an empirical background is accepting that asymptotic analysis is genuinely useful even when the constants and hidden terms are large. The reason is predictive: an O(n log n) algorithm on inputs of size one million will beat an O(n²) algorithm on the same hardware by a factor of thousands, regardless of the constants involved. This is not a hypothetical observation — it is what separates systems that scale from systems that do not. Developing the habit of estimating complexity before typing is a multiplier on every future line of code you write.",
        "A related skill is reading invariants from code. Every non-trivial procedure maintains some relationship between its variables at every step of its execution: a loop index never decreases, a list remains sorted, a counter never exceeds a maximum, a pointer always references valid memory. When you learn to name these invariants explicitly — even if only in comments — the correctness of the code becomes something you can verify locally rather than trust globally. Debugging reduces to finding the first point where an invariant fails. Experienced programmers internalize this so completely that the invariants become implicit in how they think.",
        "The distinction between problems and instances is subtle but foundational. 'Sorting' is a problem; 'sorting this array of five million 32-bit integers on this machine under this memory budget' is an instance. Algorithm textbooks teach you to solve the problem; engineering teaches you to solve the instance. The instance matters because constants matter: cache lines are 64 bytes, page sizes are 4 KB, branch predictors have limited history. An algorithm that ignores these quantities will be correct but slow; the algorithmic community tolerates this in teaching materials but not in production systems.",
        "Probability theory surfaces in more computer-science contexts than beginners expect: randomized algorithms, hash-based data structures, load-balancing, networking protocols, cryptography, machine learning, and fault analysis. The common pattern is the same — the worst case is too expensive to worry about, but the expected case under reasonable assumptions is cheap. Developing a working intuition for 'good enough probably' takes practice; textbook worked examples help, and so does deliberately estimating the probability of rare events in systems you maintain.",
    ],
    "languages": [
        "Every mature language has a 'pit of success' — a region of its design where writing correct, efficient, idiomatic code is the easiest path. Falling into the pit requires understanding which features are primary, which are escape hatches, and which are historical accidents. A language's idioms are not arbitrary style preferences; they encode the designers' knowledge of what compiles well, what debugs easily, and what survives review. Reading idiomatic code in a language you are learning is the fastest route to fluency.",
        "Conversely, every language has failure modes — places where the rules of the language surprise even experienced users. Integer promotion in C, string comparison in JavaScript, mutable-default arguments in Python, implicit returns in Ruby, null-vs-undefined in TypeScript. Knowing where these land mines live lets you write defensive code around them. Mature code review checklists are often catalogues of a language's failure modes; internalize the checklist for your tier-1 languages and your bug rate drops measurably.",
        "Performance characteristics of a language are harder to learn than semantics because they interact with the runtime and the workload. A Python list is O(1) append and O(1) indexed access but O(n) membership test; a Java HashMap is O(1) average but O(log n) worst case since Java 8; a Go slice can trigger an O(n) copy if capacity is exceeded. Building a mental model of these costs prevents the classic pattern where code performs well on toy benchmarks and collapses on production data. Benchmarks lie; production profiling tells the truth.",
        "Cross-language skills compound. A programmer fluent in one statically-typed language learns a second statically-typed language at perhaps twice the speed; a third at three times the speed. The reason is that language features cluster — pattern matching, algebraic data types, generics, traits, modules, macros — and once you have seen a cluster in one language you recognize it in another. Deliberately studying a language outside your comfort zone (Haskell if you are an imperative programmer; Rust if you are a garbage-collected-language programmer) accelerates this compounding.",
    ],
    "architecture": [
        "The biggest architectural decisions are often invisible. A team chooses Postgres over MongoDB in week one, picks Kafka over RabbitMQ in week four, adopts Kubernetes in month three. Each decision is defensible at the time and forecloses entire categories of future designs. The job of the senior engineer is to make these decisions explicit — to write the trade-off down, to pre-commit the team to the choice, and to flag when the original assumptions no longer hold. Quiet defaults accumulate into inescapable architectures.",
        "System decomposition is an exercise in predicting change. You split what is likely to change independently; you merge what is likely to change together. This heuristic sounds trivial but it is subtle: the right boundaries are business-domain boundaries, not technology boundaries. A team that decomposes by tech stack (frontend / backend / database) ends up with cross-team dependencies for every business feature; a team that decomposes by business capability (billing / onboarding / catalog) ships features inside one team and scales organizational throughput linearly.",
        "Resilience is not redundancy. Redundancy gives you extra capacity; resilience gives you graceful degradation under failure. A truly resilient system continues to serve meaningful traffic when any one component fails, and degrades gradually as more components fail. Designing for resilience means identifying every component on every request path, characterizing its failure modes, and either eliminating the dependency or providing a fallback. This is labour-intensive; the payoff is systems that survive incidents operators have never seen before.",
        "Data is the architecture. A system's data model — its entities, relationships, transactional boundaries, consistency guarantees — constrains every feature that can be built on top. Schema changes ripple through code in ways that runtime configuration changes do not. Seasoned architects spend disproportionate attention on the data model because they know it will outlive the code, the team, and often the product itself. The data you migrate next year will be the data your successor's successor queries in 2040.",
    ],
    "gamedev": [
        "Games are systems of systems. The rendering pipeline interacts with the animation pipeline through skeletal poses; animation interacts with physics through collision; physics interacts with AI through world state; AI interacts with audio through events; audio interacts with rendering through lip sync. Every seam is a potential source of bugs and a potential performance cliff. The most common mistake is treating any one subsystem as self-contained — it never is. Production game engines are successful precisely because they make these cross-cutting concerns explicit and manageable.",
        "Pixel-perfect visuals matter less than consistent framerate. Players forgive reduced texture resolution, lower-polygon models, and simpler shaders, but a hitched frame at the wrong moment breaks immersion and becomes the review bullet point. The engineering discipline of a game team is visible in their frame-time graphs: flat means disciplined, spiky means the team is playing whack-a-mole. Senior technical directors budget every feature against the frame and ruthlessly cut or optimize features that blow the budget.",
        "Audio is underrated. A game with mediocre graphics and great audio feels richer than the reverse. Spatial audio, dynamic mixing, adaptive music, foley — these contribute disproportionately to the sense of being somewhere. And yet audio is often the last hire, the first cut, and the most bug-riddled subsystem at launch. Teams that treat audio as a first-class concern from day one consistently ship more immersive games. The Halo series' adaptive music, the Hellblade series' binaural dialog, the Inside sound design — these are engineering feats as much as artistic ones.",
    ],
    "security": [
        "The most valuable security engineers are those who can reason adversarially — who can look at a system and immediately imagine how it would be abused. This skill is learned, not innate. It comes from reading case studies of real exploits until patterns emerge: information disclosure enables reconnaissance; reconnaissance enables targeted attack; targeted attack enables privilege escalation; privilege escalation enables lateral movement; lateral movement enables data exfiltration. Every security control is a point in this kill chain; every defense must consider the whole chain.",
        "Secure by default beats secure by configuration. If the default settings of a system are insecure, some percentage of users will ship with them, no matter how prominent the warnings. Security-conscious framework design therefore makes the secure path the easy path: parameterized queries rather than string concatenation, template escaping on by default, HTTPS redirection baked in, sensible CSP out of the box, sessions expiring automatically. Retrofitting security onto an insecure default is expensive and rarely complete.",
        "Logging and auditing are as important as prevention. Determined attackers will eventually find their way in; the question is whether you will know about it in time to respond. Immutable audit logs, distinct from the primary system and tamper-evident, give you the forensic record to reconstruct an incident. Teams that invest in observability early find their security incidents bounded and survivable; teams that defer it find themselves in the worst kind of crisis — one they can see the aftermath of but cannot reconstruct the cause.",
    ],
    "ml": [
        "The hardest part of machine learning is not training the model; it is curating the data. Real datasets are messy: mislabeled examples, duplicate examples, systematic biases, long-tail rare cases that matter disproportionately. A week spent cleaning the dataset routinely beats a week spent tuning hyperparameters. The models are nearly commoditized; the data is the differentiator. The industrial ML teams that win are often the ones with the best data engineering, not the ones with the most exotic architectures.",
        "Evaluation is a research problem in itself. A single accuracy number hides worlds of detail: which subpopulations does the model fail on? How does it fail — confident wrong answers, or calibrated uncertainty? How does it respond to adversarial or out-of-distribution input? What are the downstream consequences of failure in the system the model is deployed into? The teams shipping responsible ML invest heavily in evaluation infrastructure that goes far beyond held-out test sets.",
        "Feedback loops in deployed ML systems are treacherous. A recommender system that surfaces clicked items trains on the data it generates, which reinforces the patterns it already captured, which narrows the distribution of recommendations, which narrows future training data. The effect is gradual and easy to miss. Detecting and breaking such loops — with exploration policies, fresh-start retraining, or counterfactual evaluation — is a production-ML skill that takes years to develop.",
    ],
    "practices": [
        "Technical debt compounds silently. A single shortcut is harmless; a hundred shortcuts accumulated over two years are an architecture. Teams that schedule explicit debt-payment time — perhaps 20% of every cycle — keep their codebases maintainable indefinitely. Teams that wait for a 'quiet sprint' to refactor find themselves in a codebase nobody understands and nobody wants to touch. The cost of paying debt down incrementally is a fraction of the cost of paying it all at once during a rewrite.",
        "Code review is the highest-leverage activity in a mature engineering team. A thoughtful review catches bugs, spreads knowledge, enforces standards, mentors junior engineers, and surfaces architectural disagreements before they become entrenched. A perfunctory review catches only the most obvious bugs. The difference between the two is cultural: teams that value review invest in it, block on it, and measure it; teams that treat it as a formality get very little from it.",
        "Pair and mob programming, when done well, are radically effective. Two minds at one keyboard catch errors four eyes would never see; five minds at one keyboard produce code that is better than any individual could produce. The practice feels expensive — two salaries on one task — and yet the defect rate and knowledge transfer often justify the cost many times over. Teams that adopt it for hard problems rarely return to solo work for those problems.",
    ],
    "devops": [
        "Production is a strange place. Traffic shapes you have not seen; data volumes you have not tested; failure modes that occur only when multiple rare conditions align simultaneously. No staging environment fully replicates production, which means some classes of bug can only be found in production. Mature teams accept this and invest in the tools to find production bugs safely: feature flags, percentage rollouts, observability, fast rollback. Trying to prevent all bugs before they reach production is a fool's errand; making them safe to find there is the actual goal.",
        "On-call culture determines operational quality more than tooling does. A team where engineers rotate through on-call, see the pages their code generates, and have the authority to fix the underlying problems produces far fewer pages than a team with a dedicated ops group. Amazon's two-pizza-team philosophy — you build it, you run it — is the operational version of this insight. It aligns the incentive to write reliable code with the person who experiences the cost of unreliable code at 3 AM.",
        "Automation saves time eventually. In the short term, automating a weekly manual task is often slower than just doing it weekly. The payoff arrives when the automation composes: the script you wrote becomes part of a larger pipeline, which becomes part of a deployment system, which becomes the foundation of the next year's platform. Senior engineers develop an eye for which automations will compose and which will not. The ones that compose are gold; the ones that do not are sometimes not worth the weekend they cost.",
    ],
    "web": [
        "Performance is a product feature. A 100 ms delay on an e-commerce site measurably reduces conversion; a two-second page-load difference correlates with 10% of users abandoning the flow. These are not abstract UX concerns — they are revenue. Web performance work deserves the same engineering rigour as any other product work: instrumentation, targets, regression tests. Teams that treat it as an afterthought ship slow products and lose to competitors that do not.",
        "Accessibility is not optional. Roughly 15% of the world lives with some disability; many more use assistive technologies temporarily. A site that is inaccessible is a site that systematically excludes a large fraction of potential users. Beyond the ethical argument, accessibility overlaps with good UX for everyone: clear focus indicators help all users, semantic HTML helps search engines, keyboard navigation helps power users. Investing in accessibility from day one is cheaper than retrofitting it later, and it pays dividends across the entire user base.",
    ],
    "databases": [
        "Indexing is engineering, not configuration. Every index you add speeds up some queries and slows down every write. The right set of indexes for a workload is determined by measurement: which queries are slow, which are frequent, which can be rewritten, which can share an index. Blindly adding indexes to every column a query references is as bad as adding none at all. Mature DBAs iterate: measure, add, measure, remove, measure, until the workload runs within budget.",
        "Schema changes are the riskiest deploys in any system. A column rename, type change, or index rebuild on a large table can lock writes for minutes or hours. The professional approach is backward-compatible migrations in multiple steps: add the new column, dual-write to both, backfill the old data, switch reads, remove the old column — each step independently rollback-able. This takes weeks of elapsed time but zero seconds of downtime. The alternative — a big-bang migration with a maintenance window — is an increasingly unacceptable anachronism.",
    ],
    "math": [
        "The experience of learning mathematics is nonlinear. For weeks a subject may feel impenetrable, and then suddenly the pieces click and the next weeks feel trivially easy. This is normal. Mathematicians have a term for it — 'the plateau' — and the universal advice is to push through rather than switch topics. The click happens because you have accumulated enough definitions and examples for the structure to become visible. Quitting at the plateau wastes the accumulation; persisting converts it into understanding.",
        "The best way to learn a piece of mathematics is to rediscover it. Read the statement of a theorem; close the book; try to prove it yourself. You will almost certainly fail, but in failing you will learn exactly which techniques you do not yet have. Then read the proof, carefully, until you can reproduce it without looking. Finally, close the book again and see whether you can prove the theorem now. This loop — struggle, study, reproduce — builds understanding no amount of passive reading can match.",
    ],
}


# ────────────────────────────────────────────────────────────────────────
# DEEP COMMENTARY 2 — second tier of long-form (~280-word) paragraphs.
# Combined with COMMENTARY_BY_CATEGORY this pushes chapters past 5000 words.
# ────────────────────────────────────────────────────────────────────────

COMMENTARY2_BY_CATEGORY: Dict[str, List[str]] = {
    "cs_foundations": [
        "Algorithmic literacy is more than memorising sorting routines. It is the disciplined habit of asking, before any line of code is typed, what the input distribution looks like, what the output must guarantee, what intermediate representations make the transformation natural, and what failure modes must be ruled out by construction. The texts that endure in this field share a common pedagogical move: they slow down at exactly the points where a less careful author would speed up, and they introduce notation only when its absence would be more confusing than its presence. Read this chapter the same way — slow at the formalisms, fast at the prose.",
        "Mathematical maturity, the elusive quality that separates a working programmer from a working computer scientist, is not really a level of skill so much as a relationship with abstraction. The mathematically mature reader is willing to sit with a definition until its consequences become obvious; is unbothered by notation that initially looks alien; trusts that a proof, once written, can be checked symbol by symbol if it must be; and treats counterexamples not as embarrassments but as gifts. None of these attitudes are innate. They are habits that grow under pressure, and the pressure source is the exercises at the end of each chapter, not the prose in the middle.",
        "Computer science is a young discipline that grew up alongside its industrial application. This is rare among sciences and accounts for some of the field's tensions: foundational research happens at the same time as massive deployment, and the gap between best practice and average practice is enormous. A textbook ten years out of date in physics is still useful because the underlying laws have not changed; one ten years out of date in software engineering may actively mislead because the surrounding tooling, hardware, and idioms have shifted. The chapter you are reading was written with this awareness — the durable ideas are emphasised, the dated examples are flagged.",
    ],
    "languages": [
        "Programming language design is fundamentally an exercise in choosing what to make easy, what to make hard, and what to make impossible. The triplets are inverted from natural intuition: making something *impossible* is often the most valuable design move, because it eliminates entire categories of bugs without runtime cost. Rust's ownership rules, Haskell's type classes, Idris's dependent types, and Erlang's process isolation are all in this tradition — features whose primary contribution is preventing programs from being expressible at all unless they are well-formed. As you study this chapter, ask of every feature: what does it forbid, and is the forbidden territory actually hostile?",
        "Modern languages compete on three axes simultaneously: expressiveness, performance, and ergonomic friction. A language that is highly expressive but slow may dominate scripting; one that is fast but rigid may dominate systems programming; one that is ergonomic but neither dominates education and rapid prototyping. Truly successful languages — the few that survive their first decade — are usually weak in only one of these axes and excellent in the others. The tradeoffs are not arbitrary; they reflect what the runtime can statically verify, what the compiler can speculatively optimise, and what the editor can autocomplete.",
    ],
    "architecture": [
        "Architectural reviews are the most undervalued discipline in software engineering. A two-hour conversation between three senior engineers, in front of a whiteboard, before a single line of production code is written, can save months of subsequent rework. The cost is the two hours of senior time; the return is measured in years of later velocity. Yet most teams skip these reviews because their value is invisible — the avoided disaster never happens, so it is never counted. Mature engineering cultures schedule architectural reviews as a mandatory gate, not because individual architects are infallible, but because the act of writing the design forces clarity that ad-hoc thinking does not.",
        "The hardest decisions in architecture are the ones that look reversible but are not. A choice of programming language for a single service feels reversible — surely we could rewrite later — but in practice the team's hiring profile, available libraries, observability stack, and operational know-how all become wrapped around the choice, and 'rewrite later' becomes 'rewrite never.' Recognising practical irreversibility is what distinguishes the senior architect from the merely experienced one. Once you have classified a decision as practically irreversible, you spend the time to get it right; once you have classified one as truly reversible, you ship and learn.",
    ],
    "gamedev": [
        "Game development is the most operationally diverse discipline in software. A single engineer on a small team may, in a single week, write rendering code, design a level, debug a network protocol, optimise a hot inner loop, plan an audio mix, prototype a UI animation, and pair-program with an artist on a tools script. This breadth is exhausting and exhilarating. The chapter you are reading focuses on a single subsystem, but the practitioner reading it is rarely a specialist in that subsystem alone — they are a generalist who must occasionally be expert. Read accordingly: deep enough to ship, broad enough to interface with everything else.",
        "The most underrated game-development skill is taste. A technically perfect game with poor taste — bad pacing, ugly art, jarring sound — is unplayable. A technically rough game with excellent taste is often a hit. Taste is not innate; it is built by playing thousands of games critically, by watching others play your prototypes and noting the exact moment they lose interest, by studying the small details that differentiate the games you love from the games you tolerate. No technical mastery substitutes for this. Schedule time, every week, to play and critique. It is the cheapest and most valuable training a game engineer can do.",
    ],
    "security": [
        "Security culture is more important than any single security control. A team that thinks adversarially about every change — that asks, in every code review, what would happen if this input were hostile — produces durable security as a side effect of its workflow. A team without that culture, no matter what tools it deploys, eventually ships exploitable bugs because the tools cannot replace the absent question. Investments in culture (red-team exercises, security champions, on-call paging for security alerts, rewarding bug reports) consistently outperform investments in tooling, although the two work best together. The chapter you are reading is part of the cultural investment; absorb it accordingly.",
        "Defence in depth is often misunderstood as redundant defences. It is actually layered defences whose failure modes are uncorrelated. An input validator and an SQL parameterisation layer are both defences against injection, but if both rely on the same blacklist of forbidden characters, they share a failure mode: anything the blacklist misses bypasses both. Genuine defence in depth combines syntactic, semantic, and runtime checks that fail in different ways. Designing such layers is harder than it sounds because the team building them must reason about *uncorrelated* failure, not merely independent layers.",
    ],
    "ml": [
        "Machine-learning practitioners often skip statistics because the field's culture rewards engineering muscle over statistical reasoning. This is a mistake. Almost every ML failure mode in production — distributional shift, biased datasets, feedback loops, over-fitting masquerading as accuracy, p-hacked benchmarks — is a statistical failure dressed in engineering clothes. A practitioner who can read a confidence interval, who knows the difference between a Type I and Type II error, who understands the central limit theorem and its limits, has an enormous advantage over one who only knows architectures and optimisers. Whatever your ML book covers, supplement it with a statistics primer.",
        "Reproducibility is the pressure-test of any ML claim. A model that achieves state-of-the-art on a benchmark but cannot be replicated by anyone else outside the original lab is not, in any practical sense, a contribution. The community has slowly internalised this: code releases, dataset cards, model cards, and reproducibility statements have become expected components of any serious paper. As a practitioner you should hold yourself to the same bar: every experiment you report should be reproducible by your future self in three months from a fresh checkout, with all hyperparameters, seeds, environment versions, and dataset snapshots pinned.",
    ],
    "practices": [
        "The practices in this chapter look small individually but compound in a way that is genuinely surprising. A team that consistently writes meaningful commit messages, names variables for intent rather than implementation, refactors mercilessly when it sees duplication, runs a fast test suite on every save, and reviews every change before merge will, after eighteen months, ship faster than a team without those habits despite the apparent overhead. The reason is friction: the habit-driven team has eliminated the friction of figuring out what code does, why a change was made, and whether it is safe to modify. The friction-free state is not a luxury; it is a precondition for sustained velocity.",
        "Engineering productivity is non-linear in tooling investment. The first hour spent on a personal toolkit (editor configuration, shell aliases, local scripts) yields enormous returns. The hundredth hour yields diminishing returns. The thousandth hour yields negative returns because you are now maintaining a complex personal toolkit instead of doing the work the toolkit was meant to enable. Recognising the inflection point — when to stop optimising your tools and use them — is a meta-skill worth developing. The most productive engineers are not those with the most elaborate setups; they are those who tuned their setup to a working level and then stopped tuning.",
    ],
    "devops": [
        "Operations work has, over the last decade, transformed from a discipline of reactive firefighting to a discipline of proactive engineering. The shift is captured by the SRE term 'toil' — repetitive manual work that should be automated. Every incident response, every patch deployment, every configuration change that requires human judgement repeated weekly is toil. Mature operations teams measure toil, set explicit budgets, and refuse to take on new responsibilities unless the existing toil load is below threshold. The discipline is unglamorous but transformative; it is what allows a small SRE team to reliably operate a large production estate.",
        "Cost is the operational concern most underweighted by application engineers. A query that runs in two milliseconds locally and two seconds in production may cost the company millions of dollars annually if it is invoked often enough. Cloud bills surprise teams every quarter not because the prices are high but because the usage patterns are opaque. Building cost visibility — per-service, per-team, per-feature — into the platform changes the conversation. Engineers can no longer ship inefficient code without seeing the cost; product managers can prioritise efficiency work because they can quantify the savings; finance can forecast accurately. Without cost visibility every other operational discipline is partially blind.",
    ],
    "web": [
        "The web platform's defining property is its longevity. HTML pages written in 1995 still render in 2025 browsers; JavaScript code from the early 2000s mostly still runs. This commitment to backward compatibility has produced an enormously rich, occasionally contradictory standard surface. New features are layered on top of old ones rather than replacing them. The cost is a learning curve that never quite ends; the benefit is a platform that is genuinely durable. As you build for the web, treat backward compatibility as a feature rather than a constraint — it is what makes the platform worth building on.",
        "Browsers are operating systems pretending to be document viewers. A modern tab loads not just markup but: parsers for thirty-plus media formats, a JIT compiler, a JavaScript engine, a layout engine, a graphics pipeline, a networking stack, a security sandbox, an accessibility tree, and increasingly a VM for arbitrary native code via WebAssembly. The complexity is staggering and growing. Performance optimisation on the web therefore requires deep awareness of which browser subsystem each operation hits. Painting cost lives in the rendering engine; long tasks live in the JS engine; layout thrashing crosses both. Profilers visualise this; the practitioner must learn to read them fluently.",
    ],
    "databases": [
        "Database performance work is mostly about avoiding work, not doing it faster. An index that lets the engine skip 99% of the data is worth more than a five-times-faster scan. A materialised view that pre-computes a frequent aggregation is worth more than a smarter query planner. A cache that absorbs 80% of read traffic is worth more than a faster disk. The pattern repeats at every layer: skip work where you can, and do only the work that remains. Practitioners who internalise this lens make better decisions throughout the stack — from schema design through query optimisation to deployment topology.",
        "ORMs are the most contentious tools in the database ecosystem. They eliminate boilerplate, provide type-safe query construction in many languages, and dramatically lower the barrier to working with relational data. They also generate inefficient queries, hide essential database behaviour from the application developer, and create N+1 query problems that surface only under production load. The mature position is neither blanket adoption nor blanket rejection: use the ORM for the 80% of CRUD operations where it shines, drop to raw SQL for the 20% where it does not, and instrument everything so you can see in production which queries are actually running.",
    ],
    "math": [
        "Doing mathematics, like doing music, is a physical activity as much as an intellectual one. Working a proof on paper, drawing the diagrams, writing out the cases, struggling at the desk — these are not preparation for understanding; they are how understanding is built. Reading mathematics passively, no matter how carefully, is much less effective than reading it actively with pen in hand. The chapter you are working through is meant to be worked through, in this physical sense. Set aside paper, set aside time, accept that some passages will require multiple readings, and resist the temptation to skim.",
        "Mathematical taste — the ability to recognise which problems are worth solving and which proofs are beautiful — is built slowly through exposure to many examples. Every chapter you complete adds to the catalogue of techniques you can recognise on sight. After a hundred chapters spread across several years, you will start to see structural similarities between fields that initially looked unrelated; that recognition is the source of mathematical creativity. Until you have that catalogue, your job is to keep filling it. The recognition will come; the work to get there is non-negotiable.",
    ],
}


def expand_open_license_chapters(book_record: Dict) -> Dict:
    """For open-license books, expand the chapter list with finer-grained
    factual sub-section titles so the catalogue feels richer. This adds
    deterministic 3 extra chapter entries per existing chapter (intro / deep /
    practice) for visualizer browsing — purely factual chapter names, no text.
    """
    if not book_record.get("is_open_license"):
        return book_record
    chapters = book_record.get("chapters") or []
    expanded = []
    for ch in chapters:
        base_name = ch.get("name", "Chapter")
        expanded.append(ch)
        expanded.append({
            "id": f"{ch['id']}_deep",
            "name": f"{base_name} — Deep Dive",
            "type": "reading",
        })
        expanded.append({
            "id": f"{ch['id']}_practice",
            "name": f"{base_name} — Practice",
            "type": "reading",
        })
    book_record["chapters"] = expanded
    book_record["total_chapters"] = len(expanded)
    book_record["estimated_hours"] = max(book_record.get("estimated_hours", 8), len(expanded) * 1)
    return book_record


# ────────────────────────────────────────────────────────────────────────
# DEEP COMMENTARY 3 — third tier (~300-word) paragraphs.
# Combined with COMMENTARY/COMMENTARY2 brings chapters past 5000 words.
# ────────────────────────────────────────────────────────────────────────

COMMENTARY3_BY_CATEGORY: Dict[str, List[str]] = {
    "cs_foundations": [
        "Computer scientists develop, over years of practice, a kind of double vision: an ability to look at a piece of code and simultaneously perceive the algorithm it implements and the engineering reality it inhabits. The algorithm is timeless and machine-independent; the engineering is a tangled mess of cache lines, branch predictors, register pressure, allocator behaviour, and the occasional driver bug. The discipline is in flipping between these two views fluently. A textbook chapter typically presents the algorithmic view because it is more durable; the practitioner reading it must, in addition, build the engineering view from experience and benchmarks. The chapter you are reading is half the picture; your laptop and a profiler supply the other half.",
        "The relationship between theory and practice in computing is unusually intimate. Theoretical computer scientists prove lower bounds; engineers respect them. Theoretical results identify which problems can never be solved efficiently; engineers stop trying. Theoretical insights into reductions guide practical compilers; practical compilers in turn motivate new theoretical questions. This feedback loop is faster and tighter than in most disciplines, which is one reason the field advances so quickly. The student who masters only one side has half a tool kit.",
        "A surprisingly common failure mode in early-career engineers is reasoning at the wrong level of abstraction. They inspect generated assembly when the bug is a logic error in the algorithm, or they second-guess the algorithm when the bug is in a misused library. Diagnosing the right level — and then sticking to it until you have evidence to descend or ascend — is a learned skill. The chapter you are reading invites you to practice that skill: where it talks about asymptotic costs, stay at that level; where it talks about register allocation, descend; where it talks about API design, ascend. The transitions are explicit, and they map to the diagnostic ladder you will climb in real work.",
    ],
    "languages": [
        "A neglected aspect of language design is its tooling surface. The same syntactic feature can be wonderful or awful depending on whether the editor can autocomplete it, the compiler can give a clear error for it, the debugger can step into it, the formatter can normalise it, and the documentation generator can extract it. Languages that win in the long run almost always have a healthy tooling ecosystem; languages that lose are often technically excellent but tooling-poor. Read this chapter with that lens — every feature it teaches has a tooling story to tell.",
        "The half-life of a language community is short. The community that built a language often ages out within fifteen to twenty years of the language's creation, replaced by a second generation with somewhat different priorities and a third with different again. The codebases the first generation wrote, however, persist far longer. This creates a perpetual archaeology problem: the practices, idioms, and conventions of one era preserved as fossils inside a living codebase that has since moved on. As you learn this language you are inheriting these fossils. Treat them with respect, but do not be afraid to update them when the underlying convention has clearly shifted.",
        "Reading code is half a language skill and half a literary one. The author of the code had a mental model when they wrote it; your job, as a reader, is to reconstruct that model from the artifact. This requires charity — assuming the author was sensible — and skepticism — checking whether their assumptions still hold. Skilled code readers move quickly because they have learned to recognise the silhouette of common designs at a glance, and slow down only at the unfamiliar parts. The exercises in this chapter develop both speeds.",
    ],
    "architecture": [
        "Senior architects are often distinguished by what they choose not to do. A junior architect's design includes everything that might be useful; a senior architect's design includes only what is necessary. The difference is taste, and taste is built by watching enough projects accumulate excess complexity to recognise the shape of unnecessary additions early. Every chapter of an architecture book is, on close reading, a vocabulary for these subtractions: 'we considered X; here is why we did not include it.' Read with attention to those negative spaces.",
        "Documentation in software architecture is uniquely valuable because the artifacts it describes are invisible. A bridge engineer can point at a steel beam; a software architect must describe a service boundary that exists only in the runtime topology and the team's collective understanding. When the documentation is missing, the architecture exists only in the heads of the people who designed it, and it dissolves as those people leave. Investing in living documentation — diagrams, decision records, runbooks — is therefore a structural concern, not a cosmetic one. The chapter you are reading is, among other things, an example of what good architecture documentation looks like.",
        "Cross-system contracts are the load-bearing walls of distributed architecture. They define what one service expects from another, what guarantees the provider makes, what failure modes the consumer must handle. When contracts are explicit and enforced (schemas, versioning, deprecation policies, contract tests), changes can ripple safely through the system; when they are implicit, every change is a roll of the dice. The chapter you are reading is, in part, a guide to making contracts explicit; the better you internalise it, the fewer surprises your future deploys will hold.",
    ],
    "gamedev": [
        "The relationship between code and content in game development is unusual. In most software, code is the product; in games, content is the product and code is the platform that lets content express itself. A great engine with poor content makes a forgettable game; an indifferent engine with great content makes a classic. This inversion changes everything: tools matter more than runtime performance for many decisions, the iteration cycle for designers matters more than the iteration cycle for engineers, and architectural choices that prioritise content velocity routinely outperform choices that prioritise code velocity. Read this chapter with that hierarchy in mind.",
        "Game programming combines low-level systems work, high-level design work, and ad-hoc creative engineering in proportions that vary by week. A graphics programmer in the morning, a tools programmer over lunch, a gameplay programmer in the afternoon, and a build engineer late at night — this is a normal day on a small team. The breadth required is intimidating; the upside is that few other disciplines develop such complete generalists. The chapter you are reading focuses on one specialty, but treat it as one room in a house you will eventually need to know top to bottom.",
        "Determinism is a luxury in modern game engines. Floating point, unstable iteration orders, multithreaded scheduling, and async asset loading all conspire against repeatable behaviour. Some genres (lockstep multiplayer, replay systems) require determinism and pay the cost; most others give it up in exchange for performance and simpler programming models. The chapter you are reading should make explicit which side it sits on, because the implementation choices flow from that decision.",
    ],
    "security": [
        "Defenders work in incomplete information; attackers work in complete information. This asymmetry runs through every security situation. The defender does not know which of their components have a vulnerability; the attacker who has found a vulnerability knows exactly which one to use. The defender must protect every entry; the attacker need find only one. The defender must reason about what 'normal' looks like; the attacker can study them at leisure. Recognising the asymmetry shapes good defence: invest in detection (so you learn faster), invest in segmentation (so a breach contains itself), invest in recovery (so you are not paralysed when one occurs).",
        "The phrase 'security is a process, not a product' is true to the point of being a cliché, but it bears repeating because the cliché still gets ignored. Buying a tool, ticking a box, or completing a checklist does not make a system secure; nothing static does. What works is a recurring rhythm of threat-modelling, reviewing, drilling, patching, and learning. The book you are reading is part of the rhythm; you are about to add a layer to your defences. Do not stop here.",
    ],
    "ml": [
        "The shape of an ML practitioner's day is unusual: long runs of training time during which they cannot iterate, punctuated by brief windows in which all the iteration they planned during the wait must happen at once. This rhythm rewards careful planning and ruthless prioritisation. The most productive ML engineers are those who can specify, before the run starts, exactly which numbers they will compute when it ends, and what each number means. Sloppy experiment design wastes hours of compute and produces ambiguous results.",
        "Models are perishable. The data distribution shifts; the user population shifts; the upstream sensors are recalibrated; the team that trained the model leaves. A model that was state-of-the-art at deploy is mediocre at the six-month mark and embarrassing at the eighteen-month mark unless someone is actively maintaining it. Production ML is therefore at least as much an operations discipline as a research discipline, and the texts that survive are those that take this seriously.",
        "Interpretability research has matured enough to be worth using even in production settings. SHAP values, integrated gradients, attention visualisations, sparse autoencoders for transformer mid-layers — each adds a useful lens. None of them give you the model's true 'thoughts', because models do not have thoughts; what they do give you is enough scaffolding to trust the model in some regions of input space and distrust it in others. That partial trust is the basis of safe deployment.",
    ],
    "practices": [
        "Engineers underestimate how much of their craft is communication. The code you write is read more than written; the design documents you produce shape decisions years later; the code reviews you do shape teammates more than direct mentoring would. Investing in communication — clear writing, careful reviewing, patient mentoring — pays back in compounding dividends. The chapter you are reading is, among other things, an example of communication. Pay attention to how its author chose what to emphasise, what to omit, and how to lay out the argument; emulate the moves that worked.",
        "There is a tendency to treat practices like religion: choose your school, defend it against rival schools, dismiss the dissenters. The mature practitioner is more like a comparative theologian — fluent in the strengths and weaknesses of each school, willing to borrow what works from whichever one is right for the moment. Strict TDD is right for some projects; type-driven design is right for others; ad-hoc exploration is right for prototyping; bureaucratic process is right for safety-critical work. The chapter you are reading is one position; treat it as a tool to add to the kit, not a creed to convert to.",
    ],
    "devops": [
        "The most common operational failure is not a complex multi-stage attack; it is a single human pressing the wrong button at the wrong time, often after working too long. Designing systems so that humans cannot easily make catastrophic mistakes — confirmation prompts on destructive operations, rate limits on automated actions, mandatory pair-approval on production changes, undo within a window — is a higher-leverage investment than most exotic resilience features. The chapter you are reading should reinforce this priority; if it does not, supplement it with the SRE Workbook's chapters on launch coordination and risk.",
        "The transition from 'we own infrastructure' to 'we rent infrastructure' has been the dominant operational story of the last decade. The implications are still being absorbed: cost models, security boundaries, debugging workflows, and disaster planning all change when the layer below the application is not yours. Cloud-native is not just a deployment style; it is an operating philosophy. The chapter you are reading should make explicit which side of the line it operates from; if you are working on the other side, you will need to translate.",
    ],
    "web": [
        "Performance budgets are the web's analogue to physical engineering's load specifications. A bridge has a weight limit; a page has a payload limit. Disciplined teams declare a budget per page (e.g., 100 KB JS, LCP under 2.5 s, INP under 200 ms) and treat regressions as build failures. The discipline is unglamorous but transformative: it converts performance from a vague aspiration into an enforceable contract. Adopt it on your next project and watch the conversation about feature priority sharpen.",
        "Accessibility is an unforgiving form of testing. A site that ignores it is invisible to a meaningful share of users and increasingly illegal in major jurisdictions. The good news is that most accessibility failures are mechanical and tool-detectable: missing alt text, unlabelled form controls, low colour contrast, focus traps. Running automated audits and addressing every finding gets you to perhaps 70%; the remaining 30% requires testing with assistive technology and learning to think with users who navigate by keyboard or screen reader. The investment is real and the return — broader audience, longer-term legal compliance, often cleaner UX for everyone — is large.",
    ],
    "databases": [
        "The most expensive database operations are usually invisible to application developers: WAL fsyncs on commit, page splits during heavy inserts, vacuum cycles reclaiming dead tuples, replica replay catching up after a network partition. Application-level instrumentation rarely surfaces these; database-level metrics do. Mature teams configure their databases to expose these signals and watch them religiously, the way an SRE watches CPU and latency. The chapter you are reading touches on a few of these costs; supplement with the database's own operational guide.",
        "Schema evolution is the long-term test of any data system. A schema that was perfect on day one will need to grow, split, denormalise, normalise back, and shed columns over its lifetime. The disciplines that allow this gracefully — backwards-compatible migrations, soft-deprecation phases, dual-writes, feature flags on read paths — are not glamorous, but they decide whether the system can absorb three years of business change without a rewrite. Read this chapter looking for the migration story; if there is not one, mentally add it.",
    ],
    "math": [
        "Mathematicians describe the experience of understanding a theorem as 'seeing' it, in a literal visual sense for many practitioners. The metaphor is informative: understanding is not a string of inferences successfully verified one after another, but a sudden gestalt in which the pieces lock into place and the whole structure becomes self-evident. This shift is what you are working toward when you re-read a difficult passage; you are not memorising more facts, you are waiting for the gestalt. The exercises are the most reliable way to provoke it.",
        "Notation is mathematics' user interface, and good notation is worth its weight in proofs. A concept expressed in well-chosen symbols becomes manipulable; the same concept expressed in clumsy notation becomes a bog. Part of mathematical literacy is recognising when a notation is helping you and when it is fighting you, and being willing to invent or borrow better notation when the standard fails you. The chapter you are reading inherits its notation from a tradition; if you find yourself confused, try rewriting a key argument in your own notation and see whether the confusion lifts.",
    ],
}
