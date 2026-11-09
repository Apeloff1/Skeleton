"""
╔══════════════════════════════════════════════════════════════════════════╗
║  READING CONTENT GENERATOR — substantive, deterministic, no-LLM         ║
║  Produces 5000+ word book-quality chapter prose from (book, chapter)    ║
║  keys. Content is:                                                       ║
║    • Deterministic (same seed → same text; reproducible E2E)            ║
║    • Domain-aware (CS / languages / architecture / gamedev / security)   ║
║    • Technical (real definitions, real examples, real pitfalls)         ║
║    • Structured (10 sections: history → first principles → core →       ║
║      examples → advanced → pitfalls → exercises → glossary → further    ║
║      reading → looking ahead)                                            ║
║  Stored in MongoDB and served to the Reading Visualizer.                 ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
from __future__ import annotations
import hashlib
import random
from typing import Dict, List, Tuple

from seeds.reading_content_expansion import (
    HISTORY_BY_CATEGORY,
    FIRST_PRINCIPLES_BY_CATEGORY,
    ADVANCED_BY_CATEGORY,
    GLOSSARY_TERMS_BY_CATEGORY,
    FURTHER_READING_BY_CATEGORY,
    EXPANDED_EXERCISES_BY_CATEGORY,
    COMMENTARY_BY_CATEGORY,
    COMMENTARY2_BY_CATEGORY,
    COMMENTARY3_BY_CATEGORY,
)
# 2026-05-13 — v2 expansion pack: deep-dive, case studies, misconceptions
from seeds.reading_content_expansion_v2 import (
    DEEP_DIVE_BY_CATEGORY,
    CASE_STUDIES_BY_CATEGORY,
    MISCONCEPTIONS_BY_CATEGORY,
)


# ────────────────────────────────────────────────────────────────────────
# Domain-specific knowledge banks (real educational content, not filler)
# ────────────────────────────────────────────────────────────────────────

_CS_FOUNDATIONS_BANK = {
    "recursion": [
        "Recursion is the technique of solving a problem by having a procedure call itself on a smaller instance of the same problem. Every recursive procedure must satisfy two properties: a base case that terminates the recursion, and a recursive case that reduces the problem toward the base case. Without either, the procedure diverges.",
        "Consider the factorial: `factorial(n) = 1 if n <= 1 else n * factorial(n-1)`. The base case is `n <= 1`; the recursive case is `n * factorial(n-1)`. Each invocation consumes a stack frame, so naive recursion on large inputs risks stack overflow. Languages with tail-call optimization rewrite terminal recursion into iteration, eliminating the frame growth.",
        "A subtle class of recursive algorithms are those that recurse multiple times per call — tree recursion. `fib(n) = fib(n-1) + fib(n-2)` illustrates the pitfall: exponential blowup from recomputed subproblems. The fix is memoization: cache each result by its argument so repeated calls return in O(1). Memoization transforms many exponential recursions into polynomial-time ones.",
    ],
    "algorithms": [
        "An algorithm is a finite, deterministic procedure that, for any input drawn from a specified domain, produces an output in a bounded number of steps. Its correctness is an argument — typically by induction on input size — that each step preserves an invariant leading to the correct output.",
        "Algorithmic analysis studies two things: correctness and cost. Cost is expressed in the RAM model as a count of elementary operations as a function of input size n. Big-O notation expresses the upper bound on this count asymptotically, discarding constants and lower-order terms. Big-Θ expresses tight bounds; Big-Ω expresses lower bounds.",
        "The fundamental algorithmic techniques are: divide-and-conquer (mergesort, quicksort, FFT), dynamic programming (Bellman's principle of optimality), greedy methods (Kruskal's MST, Huffman coding), and linear programming. Recognizing which technique fits a problem is often harder than coding the solution.",
    ],
    "data_structures": [
        "A data structure is a way of organizing data so that a specific set of operations is efficient. Each structure trades space for time or simplicity for flexibility. The array offers O(1) random access but O(n) insertion; the linked list inverts that. The hash table offers expected O(1) lookups but pays with worst-case O(n) collisions and amortized rehashing.",
        "Balanced search trees (AVL, red–black) guarantee O(log n) for insert, delete, and lookup by enforcing a height invariant after every mutation. B-trees generalize this to many children per node and are the workhorse of database indices because each node maps to a disk page, minimizing I/O.",
        "Choosing the wrong structure often dominates runtime more than any micro-optimization. Benchmark before you pick: a `std::vector` beats a linked list for most in-memory sequential workloads because cache lines move together. Always ask: what is the dominant operation, and what is its complexity in the structure I chose?",
    ],
    "memory": [
        "A computer's memory hierarchy spans from registers (nanoseconds, bytes) through L1/L2/L3 caches (10–300 cycles) to main memory (100+ ns) to SSD (µs) and HDD (ms). Every level is 10–100× slower than the previous. Good code exploits locality so hot data lives in the fast levels.",
        "Spatial locality means accessing memory near addresses we recently touched; temporal locality means reusing the same addresses. Row-major iteration over a 2D array has good spatial locality; column-major iteration over the same C array has terrible locality. A 10× slowdown from cache misses is routine on cache-hostile code.",
        "Virtual memory decouples the address space a process sees from physical RAM. Every memory access consults the MMU, which translates virtual → physical via the page table. A TLB caches recent translations; a TLB miss adds dozens of cycles. Thrashing happens when the working set exceeds physical memory and the OS pages aggressively to disk, collapsing performance.",
    ],
    "concurrency": [
        "Concurrency is the composition of independently executing processes; parallelism is their simultaneous execution. Threads share memory; processes do not. The central difficulty of shared-memory concurrency is the race condition: when two threads read-modify-write the same location, the final value depends on interleaving.",
        "Locks (mutexes) serialize access to shared state but introduce contention, priority inversion, and deadlock (a cycle of threads each holding a lock the next needs). The four deadlock preconditions — mutual exclusion, hold-and-wait, no preemption, circular wait — must all hold simultaneously; breaking any one prevents deadlock.",
        "Lock-free algorithms use atomic primitives (CAS — compare-and-swap) to advance state without locks. They are subtle: ABA bugs, memory reordering, and starvation are easy to introduce. For most application code, prefer immutable data, message passing, or well-tested lock-based designs over hand-rolled lock-free code.",
    ],
    "compilers": [
        "A compiler translates source text to a target representation in phases: lexing groups characters into tokens, parsing builds a syntax tree, semantic analysis enforces type and scope rules, IR generation produces a machine-independent intermediate form, optimization transforms the IR, and code generation emits target instructions.",
        "The front-end is concerned with the source language; the back-end with the target. A well-designed intermediate representation (SSA — static single assignment) makes optimization passes modular: constant folding, common-subexpression elimination, dead-code elimination, loop-invariant code motion, and register allocation all operate on the IR rather than source or target.",
        "Modern compilers often run 50+ optimization passes. Each is individually simple but their interaction is emergent: running GCSE before constant folding yields different code than the reverse. Compiler engineers spend enormous effort tuning pass ordering and deciding which passes to run at each `-O` level.",
    ],
}

_LANGUAGES_BANK = {
    "python": [
        "Python's object model is uniform: everything — integers, strings, functions, modules, classes — is a first-class object with attributes and methods. This uniformity is the foundation of Python's metaprogramming power. A class definition is itself an executable statement that builds an object of type `type`.",
        "Dunder methods (`__init__`, `__len__`, `__iter__`, `__enter__`) hook custom classes into Python's built-in operators and protocols. Implement `__len__` and `__getitem__` and your object is iterable; add `__contains__` for fast membership tests. The language's expressiveness comes from users extending built-in syntax via these protocols.",
        "Python's GIL (Global Interpreter Lock) serializes CPython bytecode execution across threads. CPU-bound code sees no speedup from threading; it needs multiprocessing or C extensions. I/O-bound code does benefit because the GIL is released during blocking calls. `asyncio` sidesteps the GIL entirely with cooperative single-threaded concurrency.",
    ],
    "rust": [
        "Rust's central innovation is the ownership system: every value has a single owner; when the owner goes out of scope, the value is dropped. References may borrow a value either immutably (`&T`, multiple allowed) or mutably (`&mut T`, unique). These rules are enforced at compile time and eliminate whole categories of memory-safety bugs without a garbage collector.",
        "Lifetimes annotate how long a reference is valid. Most lifetimes are elided by the compiler's rules; when they cannot be inferred, you must write them explicitly (`&'a str`). The borrow checker validates that every reference's lifetime is at most the lifetime of the referent, preventing dangling references.",
        "Traits are Rust's mechanism for ad-hoc polymorphism and zero-cost abstractions. `impl Trait` allows static dispatch with no runtime cost; `dyn Trait` provides dynamic dispatch through a vtable. Deriving `Debug`, `Clone`, `PartialEq`, `Serialize` removes boilerplate. Prefer bounds on functions over `where` clauses until the constraints become complex.",
    ],
    "javascript": [
        "JavaScript's scoping is lexical with a twist: `var` declarations are function-scoped and hoisted to the top of their containing function, producing the classic temporal dead-zone surprises. `let` and `const` are block-scoped and not accessible before their declaration within the block. Prefer `const` by default, `let` when reassignment is needed, and avoid `var` entirely.",
        "`this` in JavaScript is determined by call-site, not declaration-site. A method extracted from an object and invoked as a plain function loses its receiver. Arrow functions capture `this` lexically from their enclosing scope, which is usually what you want for callbacks — but occasionally not, for example in object methods where dynamic `this` is expected.",
        "The event loop runs the call stack to empty, then processes one task from the macrotask queue (setTimeout, I/O), then drains the microtask queue (Promises, queueMicrotask), then renders, then repeats. Understanding this ordering is the difference between smooth UIs and inexplicable lag.",
    ],
    "go": [
        "Go's concurrency model is built on two primitives: goroutines (lightweight cooperative tasks multiplexed onto OS threads) and channels (typed queues for value passing). The mantra 'don't communicate by sharing memory; share memory by communicating' captures the preferred style.",
        "Interfaces in Go are implicit: any type that implements the required methods satisfies the interface. This decouples producers from consumers and enables duck-typing with static safety. The empty interface `interface{}` (now `any`) matches every type and is used for generic-style APIs — though Go 1.18's generics are the modern solution.",
        "Error handling in Go is explicit and linear: every error is a return value, checked locally. There is no exception mechanism. `errors.Is` and `errors.As` support wrapped-error inspection. Panics exist for unrecoverable conditions but should be rare in library code; always recover at goroutine boundaries.",
    ],
}

_ARCHITECTURE_BANK = {
    "patterns": [
        "A design pattern is a reusable solution to a recurring problem in a context. The 'Gang of Four' book catalogs 23 such patterns in three families: creational (how objects are made), structural (how objects compose), and behavioral (how objects coordinate). Each pattern documents: intent, motivation, structure, participants, consequences, and known uses.",
        "Patterns are a vocabulary, not a checklist. The cost of introducing a pattern is indirection; the benefit is flexibility. Apply a pattern only when the flexibility will be exercised — premature pattern use creates over-engineered code that is harder to read than a simple direct implementation.",
        "Many patterns dissolve in languages with first-class functions and closures. The Strategy pattern reduces to passing a function. The Observer pattern is just subscribing callbacks. Command, Template Method, and Iterator simplify similarly. Always ask: is this pattern solving a language limitation or a genuine design concern?",
    ],
    "microservices": [
        "A microservice architecture decomposes a system into small, independently deployable services that communicate over a network. Benefits include independent scaling, technology heterogeneity, and fault isolation. Costs include operational complexity, distributed tracing, schema evolution across services, and the eight fallacies of distributed computing.",
        "The boundary of a microservice should follow domain boundaries — often aligned with Domain-Driven Design's bounded contexts — not technology boundaries. A service owned end-to-end by one small team, responsible for its own database, is the typical unit of deployment.",
        "Asynchronous messaging (Kafka, RabbitMQ, NATS) decouples services better than synchronous RPC. It smooths traffic spikes, survives downstream outages, and makes event sourcing natural. But it introduces eventual consistency, message ordering concerns, and exactly-once-delivery problems that synchronous systems avoid.",
    ],
    "clean_code": [
        "Clean code reads like prose. Functions do one thing at one level of abstraction. Names carry intent: `daysUntilExpiration` beats `d`, and `calculateTax(order)` beats `process(o)`. Comments explain *why*, not *what* — the code should already say *what*.",
        "The Single Responsibility Principle states that a module should have one reason to change. A class that formats an invoice AND persists it to a database has two reasons — split it. Cohesion rises and coupling falls. Testing each responsibility in isolation becomes trivial.",
        "Refactoring is the disciplined technique of restructuring code without changing its external behavior. Each refactoring is a small, reversible step backed by a test suite. Big-bang rewrites are risky; continuous refactoring under green tests is safe. The refactoring catalog (Fowler) is the reference.",
    ],
}

_GAMEDEV_BANK = {
    "rendering": [
        "The real-time rendering pipeline transforms a scene description into a 2D image. Key stages: vertex transformation (object → world → view → clip space), rasterization (triangles → fragments), fragment shading (color each pixel), and output merging (depth test, blending). Modern GPUs run hundreds of cores in parallel across each stage.",
        "Shaders are small programs that run per-vertex or per-fragment on the GPU. Vertex shaders transform geometry and prepare per-vertex attributes; fragment shaders compute the final color of each pixel. Lighting, texturing, shadow mapping, post-processing effects — all live in shaders. Modern engines may have 50+ shader permutations per material.",
        "Physically-based rendering (PBR) models surfaces using physical quantities: albedo, roughness, metallic, normal. The BRDF (bidirectional reflectance distribution function) describes how light reflects off a surface. Energy conservation ensures outgoing light never exceeds incoming light. The result is materials that look correct under any lighting condition.",
    ],
    "game_loop": [
        "The game loop is the heart of every game: read input, update state, render, repeat. The fundamental question is time: how much simulated time has passed since the last frame? Two approaches dominate: fixed timestep (simulation runs at a constant rate, e.g., 60 Hz) and variable timestep (each tick uses the real delta).",
        "Fixed timestep is favored for physics because it is deterministic and stable. Variable rendering on top of fixed simulation uses interpolation: render the scene at a position between the last two simulation states, weighted by the leftover time. This decouples frame rate from simulation rate and produces smooth motion even at 144 Hz displays.",
        "Frame budget is tight: 16.6 ms at 60 Hz, 4.2 ms at 240 Hz. A typical budget: 1 ms input/AI, 2 ms physics, 2 ms animation, 8 ms rendering, 2 ms post-processing, 1.6 ms overhead. Exceed the budget and you drop a frame. Profilers (RenderDoc, PIX, Tracy) are essential to find and fix hot spots.",
    ],
    "ai": [
        "Game AI is about believable behavior, not optimal behavior. A squad that plays perfectly frustrates players; one that makes human-like mistakes is satisfying. The toolkit includes finite state machines (FSM), behavior trees (BT), utility AI, goal-oriented action planning (GOAP), and hierarchical task networks (HTN).",
        "Behavior trees have become the industry standard for AAA games. A BT is a tree of nodes (selectors, sequences, decorators, leaves); each tick, the tree is evaluated root-to-leaf. They are composable, debuggable, and design-time editable. Halo 2's BT work in 2004 kicked off wide adoption.",
        "Pathfinding on a navigation mesh uses A* with a heuristic (usually straight-line distance). The navmesh is built offline from the level geometry: walkable polygons, portals between them. Runtime queries compute a path in a few ms on modern hardware. For dynamic obstacles, recast-style local avoidance (RVO, ORCA) steers around other agents.",
    ],
}

_SECURITY_BANK = {
    "web_security": [
        "The OWASP Top 10 catalogs the most common web vulnerabilities. Injection (SQL, OS, LDAP) tops the list: untrusted input flows into an interpreter. The fix is always parameterized queries, never string concatenation. ORMs help but don't eliminate the risk — raw query hatches still exist.",
        "Cross-Site Scripting (XSS) injects attacker-controlled script into a page. Reflected XSS abuses a query parameter echoed without escaping; stored XSS persists in a database. Mitigations: output-encode all interpolation, use a strict Content-Security-Policy, prefer frameworks (React, Vue) that escape by default, and mark sensitive cookies HttpOnly.",
        "Cross-Site Request Forgery (CSRF) abuses ambient authority: the browser attaches cookies to every request to a domain, so an attacker page can trigger authenticated actions on another site. Defense: SameSite cookies (default Lax blocks most CSRF), explicit anti-CSRF tokens on state-changing requests, and double-submit cookie patterns.",
    ],
    "cryptography": [
        "Cryptography makes certain computations expensive for attackers while remaining cheap for legitimate users. The two pillars are confidentiality (encryption) and authenticity (signatures, MACs). Symmetric ciphers (AES) use the same key for encrypt and decrypt; asymmetric (RSA, ECDSA, Ed25519) use a keypair.",
        "Hash functions (SHA-256, BLAKE3) produce fixed-size fingerprints. Good hashes are collision-resistant and pre-image-resistant. MD5 and SHA-1 are broken; never use them for security. For passwords use Argon2id or bcrypt with per-user salt — general-purpose hashes are too fast and enable brute-force attacks.",
        "Never implement crypto yourself in production. Use libsodium, BoringSSL, or platform APIs. The subtle bugs — timing side-channels, nonce reuse, padding oracles — are discovered regularly in hand-rolled implementations. Kerckhoffs's principle applies: a system is secure when its design is public and only the key is secret.",
    ],
}

_ML_BANK = {
    "training": [
        "Training a neural network iterates three steps: forward pass (compute predictions on a mini-batch), loss computation (compare prediction to label), and backward pass (propagate gradients via chain rule and update weights with an optimizer like SGD or Adam). This repeats for millions of steps.",
        "Overfitting happens when a model memorizes training data instead of learning generalizable patterns. Symptoms: training loss keeps dropping while validation loss rises. Remedies: more data, dropout, weight decay, data augmentation, and early stopping. Regularization trades training fit for test accuracy.",
        "Hyperparameter tuning — learning rate, batch size, architecture depth — dominates practical outcomes. Start with a learning-rate sweep, then batch size, then architecture. Bayesian optimization (Optuna) beats random search on expensive training runs. Always track experiments with W&B or MLflow.",
    ],
    "deep_learning": [
        "Deep learning uses stacked non-linear transformations to learn hierarchical representations. Early layers learn edges and textures; deeper layers learn objects and concepts. This hierarchy emerges from gradient descent, not from explicit programming — the models are universal function approximators constrained by architecture.",
        "Convolutional networks exploit the spatial locality of images: a learned kernel slides across the input, computing local features. Weight-sharing reduces parameters dramatically and bakes in translation invariance. ResNet's skip connections enable networks 100+ layers deep by providing direct gradient paths.",
        "Transformers replaced recurrence with attention. Each token attends to every other token in a sequence, computing weighted combinations of values. Multi-head attention runs this mechanism in parallel subspaces. Scaled up, transformers are the backbone of GPT, BERT, T5, and modern foundation models.",
    ],
}


_CATEGORY_BANKS = {
    "cs_foundations": _CS_FOUNDATIONS_BANK,
    "languages": _LANGUAGES_BANK,
    "architecture": _ARCHITECTURE_BANK,
    "gamedev": _GAMEDEV_BANK,
    "security": _SECURITY_BANK,
    "ml": _ML_BANK,
    "practices": _ARCHITECTURE_BANK,  # shares clean-code bank
    "devops": _ARCHITECTURE_BANK,
    "web": _LANGUAGES_BANK,
    "databases": _CS_FOUNDATIONS_BANK,
    "math": _CS_FOUNDATIONS_BANK,
    "blockchain": _SECURITY_BANK,
    "embedded": _CS_FOUNDATIONS_BANK,
    "data_science": _ML_BANK,
    "ui_ux": _ARCHITECTURE_BANK,
    "career": _ARCHITECTURE_BANK,
    "functional": _LANGUAGES_BANK,
    "networking_systems": _CS_FOUNDATIONS_BANK,
    "low_level": _CS_FOUNDATIONS_BANK,
}


# ────────────────────────────────────────────────────────────────────────
# Keyword → bank-key matcher. Routes chapter titles to the right prose set.
# ────────────────────────────────────────────────────────────────────────
_KEYWORD_MAP: List[Tuple[str, str]] = [
    ("recursion", "recursion"), ("recursive", "recursion"),
    ("algorithm", "algorithms"), ("analysis", "algorithms"), ("sorting", "algorithms"),
    ("searching", "algorithms"), ("divide", "algorithms"),
    ("data structure", "data_structures"), ("tree", "data_structures"),
    ("hash", "data_structures"), ("graph", "data_structures"), ("list", "data_structures"),
    ("memory", "memory"), ("cache", "memory"), ("virtual", "memory"),
    ("concurrency", "concurrency"), ("thread", "concurrency"),
    ("parallel", "concurrency"), ("lock", "concurrency"), ("async", "concurrency"),
    ("compiler", "compilers"), ("lexical", "compilers"), ("syntax", "compilers"),
    ("python", "python"), ("pythonic", "python"),
    ("rust", "rust"), ("ownership", "rust"), ("borrow", "rust"),
    ("javascript", "javascript"), ("typescript", "javascript"), ("promise", "javascript"),
    ("go ", "go"), ("goroutine", "go"), ("channel", "go"),
    ("pattern", "patterns"), ("design pattern", "patterns"),
    ("microservice", "microservices"), ("service", "microservices"),
    ("clean code", "clean_code"), ("refactor", "clean_code"), ("smell", "clean_code"),
    ("render", "rendering"), ("shader", "rendering"), ("graphics", "rendering"),
    ("game loop", "game_loop"), ("loop", "game_loop"),
    ("ai", "ai"), ("behavior", "ai"), ("pathfind", "ai"),
    ("web", "web_security"), ("xss", "web_security"), ("injection", "web_security"),
    ("crypto", "cryptography"), ("cipher", "cryptography"), ("hash function", "cryptography"),
    ("training", "training"), ("optimiz", "training"),
    ("deep", "deep_learning"), ("neural", "deep_learning"), ("transformer", "deep_learning"),
]


def _find_bank_key(category: str, chapter_name: str) -> str:
    """Match chapter keywords to a specific bank key within the category."""
    cn = chapter_name.lower()
    for kw, key in _KEYWORD_MAP:
        if kw in cn:
            bank = _CATEGORY_BANKS.get(category, _CS_FOUNDATIONS_BANK)
            if key in bank:
                return key
    # Fallback: first key in the category
    bank = _CATEGORY_BANKS.get(category, _CS_FOUNDATIONS_BANK)
    return next(iter(bank.keys()))


def _section_intro(book_title: str, author: str, chapter_name: str, category: str) -> str:
    """Produce a varied intro paragraph tying the chapter back to the book."""
    templates = [
        f"This chapter — *{chapter_name}* — is the backbone of **{book_title}**. "
        f"{author}'s goal here is to build your intuition before the formalism arrives in later chapters. "
        f"Read it with pen and paper nearby; the ideas compound.",
        f"*{chapter_name}* opens one of the richest veins in **{book_title}**. "
        f"Every working engineer returns to this material, often years later, and each time finds something new. "
        f"{author} writes to stay re-readable.",
        f"If you take nothing else from **{book_title}**, take this chapter. "
        f"*{chapter_name}* distils the working knowledge that separates a novice from a practitioner. "
        f"Pay particular attention to the examples — {author} chose each one to surface a specific trap.",
        f"**{book_title}** unfolds its argument chapter by chapter, and *{chapter_name}* is where the argument first becomes physical — "
        f"you will implement, run, and measure. Theory without practice is fragile; practice without theory is aimless. "
        f"{author} marries both here.",
    ]
    h = int(hashlib.md5(f"{book_title}|{chapter_name}|intro".encode()).hexdigest()[:8], 16)
    return templates[h % len(templates)]


def _code_example(book_title: str, category: str, chapter_name: str) -> str:
    """Return a short, category-appropriate code block."""
    cn = chapter_name.lower()
    if category in ("languages",) and "python" in cn:
        return (
            "```python\n"
            "def memoize(fn):\n"
            "    cache = {}\n"
            "    def wrapped(*args):\n"
            "        if args not in cache:\n"
            "            cache[args] = fn(*args)\n"
            "        return cache[args]\n"
            "    return wrapped\n\n"
            "@memoize\n"
            "def fib(n):\n"
            "    return n if n < 2 else fib(n - 1) + fib(n - 2)\n"
            "```"
        )
    if category in ("languages",) and ("rust" in cn or "ownership" in cn):
        return (
            "```rust\n"
            "fn longest<'a>(x: &'a str, y: &'a str) -> &'a str {\n"
            "    if x.len() > y.len() { x } else { y }\n"
            "}\n"
            "```"
        )
    if "algorithm" in cn or "sort" in cn:
        return (
            "```python\n"
            "def quicksort(arr):\n"
            "    if len(arr) < 2: return arr\n"
            "    p = arr[len(arr) // 2]\n"
            "    lo = [x for x in arr if x < p]\n"
            "    eq = [x for x in arr if x == p]\n"
            "    hi = [x for x in arr if x > p]\n"
            "    return quicksort(lo) + eq + quicksort(hi)\n"
            "```"
        )
    if category == "gamedev":
        return (
            "```glsl\n"
            "// Minimal PBR fragment shader sketch\n"
            "vec3 F = F0 + (1.0 - F0) * pow(1.0 - dot(H, V), 5.0);\n"
            "float G = GeometrySmith(N, V, L, roughness);\n"
            "float D = DistributionGGX(N, H, roughness);\n"
            "vec3 spec = (D * G * F) / max(4.0 * max(dot(N, V), 0.0) * max(dot(N, L), 0.0), 0.001);\n"
            "```"
        )
    if category == "security":
        return (
            "```sql\n"
            "-- Parameterized query — NEVER concatenate user input:\n"
            "SELECT id, email FROM users WHERE email = ? AND active = 1;\n"
            "-- The driver escapes `?` safely; there is no SQL-injection surface.\n"
            "```"
        )
    if category == "ml":
        return (
            "```python\n"
            "for epoch in range(epochs):\n"
            "    for x, y in loader:\n"
            "        opt.zero_grad()\n"
            "        loss = loss_fn(model(x), y)\n"
            "        loss.backward()\n"
            "        opt.step()\n"
            "```"
        )
    return (
        "```python\n"
        "# Illustrative sketch\n"
        "def process(items):\n"
        "    return [transform(x) for x in items if valid(x)]\n"
        "```"
    )


def _exercises(chapter_name: str, difficulty: str) -> str:
    lines = [
        "## Exercises",
        "",
        f"1. Re-express the core idea of *{chapter_name}* in your own words without looking back at the text. "
        f"If you cannot, you have not yet understood it — re-read the first two sections.",
        f"2. Implement the example above from scratch in a language you do not normally use. "
        f"Friction exposes assumptions that fluency hides.",
        f"3. Find an open-source project that applies the ideas of *{chapter_name}*. "
        f"Read 100 lines of its implementation. Note three decisions you would have made differently.",
    ]
    if difficulty in ("advanced", "expert"):
        lines.append(
            f"4. Identify one *limit* of the approach described in *{chapter_name}*. "
            f"Design a test case that exposes it. Propose a mitigation and its trade-offs."
        )
    return "\n".join(lines)


def _pitfalls(chapter_name: str) -> str:
    return (
        "## Common Pitfalls\n\n"
        f"- **Skipping the base case.** When learning *{chapter_name}*, practitioners often rush to the interesting part "
        f"and under-specify termination or edge conditions. Write the base case first.\n"
        f"- **Premature optimization.** The examples here favor clarity. In production, measure before you tune.\n"
        f"- **Ignoring invariants.** Every non-trivial piece of code has an invariant it maintains. "
        f"Name it explicitly in a comment; future-you will thank present-you."
    )


# ────────────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────────────

def generate_chapter_content(
    book_title: str,
    author: str,
    category: str,
    difficulty: str,
    chapter_name: str,
    chapter_idx: int,
    total_chapters: int,
) -> Dict:
    """
    Produce a complete, substantive chapter payload that the Reading Visualizer
    can render directly. Deterministic: same inputs → same output.

    Returns:
      {
        "chapter_name": str,
        "chapter_idx": int,
        "word_count": int,
        "reading_minutes": int,
        "body_md": str,            # rendered as Markdown in the visualizer
        "sections": [{title, text}],
        "has_code_example": bool,
      }
    """
    rnd = random.Random(
        int(hashlib.md5(f"{book_title}|{chapter_idx}|{chapter_name}".encode()).hexdigest()[:12], 16)
    )

    # Pick multiple distinct bank entries for body content
    bank_key = _find_bank_key(category, chapter_name)
    bank = _CATEGORY_BANKS.get(category, _CS_FOUNDATIONS_BANK)
    primary_paragraphs = bank[bank_key][:]
    rnd.shuffle(primary_paragraphs)
    # Sample MULTIPLE secondary bank keys for richer variety
    other_keys = [k for k in bank.keys() if k != bank_key]
    rnd.shuffle(other_keys)
    secondary_paragraphs: List[str] = []
    for k in other_keys[:3]:
        secondary_paragraphs.extend(bank[k])

    # ─── Pull from expansion packs ───
    history_bank = HISTORY_BY_CATEGORY.get(category, HISTORY_BY_CATEGORY["cs_foundations"])[:]
    rnd.shuffle(history_bank)
    history_text = "\n\n".join(history_bank[:3])

    first_principles_bank = FIRST_PRINCIPLES_BY_CATEGORY.get(
        category, FIRST_PRINCIPLES_BY_CATEGORY["cs_foundations"]
    )[:]
    rnd.shuffle(first_principles_bank)
    first_principles_text = "\n\n".join(first_principles_bank[:2])

    advanced_bank = ADVANCED_BY_CATEGORY.get(category, ADVANCED_BY_CATEGORY["cs_foundations"])[:]
    rnd.shuffle(advanced_bank)
    advanced_text = "\n\n".join(advanced_bank[:3])

    glossary = GLOSSARY_TERMS_BY_CATEGORY.get(
        category, GLOSSARY_TERMS_BY_CATEGORY["cs_foundations"]
    )[:]
    glossary_text = "\n\n".join(
        f"- **{g['term']}** — {g['def']}" for g in glossary
    )

    further = FURTHER_READING_BY_CATEGORY.get(
        category, FURTHER_READING_BY_CATEGORY["cs_foundations"]
    )[:]
    further_text = "\n\n".join(f"- {x}" for x in further)

    expanded_ex_bank = EXPANDED_EXERCISES_BY_CATEGORY.get(
        category, EXPANDED_EXERCISES_BY_CATEGORY["cs_foundations"]
    )[:]
    rnd.shuffle(expanded_ex_bank)

    commentary_bank = COMMENTARY_BY_CATEGORY.get(
        category, COMMENTARY_BY_CATEGORY["cs_foundations"]
    )[:]
    rnd.shuffle(commentary_bank)
    commentary2 = COMMENTARY2_BY_CATEGORY.get(
        category, COMMENTARY2_BY_CATEGORY["cs_foundations"]
    )[:]
    rnd.shuffle(commentary2)
    commentary3 = COMMENTARY3_BY_CATEGORY.get(
        category, COMMENTARY3_BY_CATEGORY["cs_foundations"]
    )[:]
    rnd.shuffle(commentary3)

    intro = _section_intro(book_title, author, chapter_name, category)
    code = _code_example(book_title, category, chapter_name)
    code2 = _code_example(book_title, category, f"alt_{chapter_name}")
    pitfalls = _pitfalls(chapter_name)

    # Build an expanded exercise list combining short + long-form
    base_ex_lines = [
        f"1. Re-express the core idea of *{chapter_name}* in your own words without looking back at the text. If you cannot, you have not yet understood it — re-read the first two sections.",
        f"2. Implement the example above from scratch in a language you do not normally use. Friction exposes assumptions that fluency hides.",
        f"3. Find an open-source project that applies the ideas of *{chapter_name}*. Read 100 lines of its implementation. Note three decisions you would have made differently.",
    ]
    long_ex_lines = [f"{i + 4}. {ex}" for i, ex in enumerate(expanded_ex_bank)]
    exercises_text = "\n\n".join(base_ex_lines + long_ex_lines)

    # Expanded section ordering — 13+ substantive sections, bulked per section
    # We now pull MULTIPLE paragraphs per section so each section is 300-600 words
    # rather than 100-200, bringing total past 5000 words.
    core_text = "\n\n".join(primary_paragraphs)  # Use all, not [:3]
    deeper_text = "\n\n".join(secondary_paragraphs)  # Use all, not [:4]

    # Pull theory bridging from a third bank
    theory_paragraphs: List[str] = []
    for k in other_keys[3:6]:
        if k in bank:
            theory_paragraphs.extend(bank[k])
    theory_text = "\n\n".join(theory_paragraphs) if theory_paragraphs else (
        f"The techniques above connect to a wider intellectual territory. "
        f"Every programming idea has neighbours — things it superficially resembles, things it subtly differs from, "
        f"things built on top of it. Mapping these neighbourhoods is how a practitioner develops taste."
    )

    # Patterns / case studies section — draw from remaining bank entries
    case_paragraphs: List[str] = []
    for k in other_keys[6:]:
        if k in bank:
            case_paragraphs.extend(bank[k])
    # If we ran out, reuse primary at new rotation
    if not case_paragraphs:
        case_paragraphs = primary_paragraphs[-2:] if len(primary_paragraphs) > 2 else primary_paragraphs

    sections = [
        {"title": "Orientation", "text": intro},
        {"title": "Historical Context", "text": "\n\n".join(history_bank)},
        {"title": "First Principles", "text": "\n\n".join(first_principles_bank)},
        {"title": "Core Concepts", "text": core_text},
        {"title": "Worked Example", "text": (
            "The best way to internalize the ideas above is to run them. "
            "The following short snippet distils the chapter's mechanics into code you can type, run, and modify. "
            "Read it twice before executing: once to predict what it does, once to confirm."
            f"\n\n{code}\n\n"
            "If your prediction matched the output, good — extend the snippet with an additional case. "
            "If it did not match, find the exact line where your mental model diverged from the machine's. "
            "That gap is the precise content of your misunderstanding; narrow it before moving on.\n\n"
            "A useful follow-up experiment: introduce a deliberate bug and observe how the failure mode surfaces. "
            "Is it a compile-time error, a runtime exception, or silent wrong output? The category of failure "
            "tells you which layer of the stack is doing the checking, and which is relying on your discipline."
        )},
        {"title": "Deeper Reading", "text": deeper_text + "\n\n" + "\n\n".join(commentary_bank[:2]) + "\n\n" + "\n\n".join(commentary2[:2])},
        {"title": "Theory Connections", "text": theory_text + "\n\n" + "\n\n".join(commentary_bank[2:4]) + "\n\n" + "\n\n".join(commentary2[2:])},
        {"title": "Second Worked Example", "text": (
            "Here is a variation on the same idea in a slightly different form. "
            "Compare the two implementations; the similarities reveal the essential mechanics, the differences "
            "reveal the design space the author had to navigate."
            f"\n\n{code2}\n\n"
            "A good exercise: re-implement this example after closing the book. Where you hesitate, you have "
            "found the non-obvious piece — that is where your study time pays the highest return.\n\n"
            "Another useful drill is to port this example into a language with different semantics "
            "(static vs dynamic typing, manual vs garbage-collected memory, eager vs lazy evaluation). "
            "The port will surface assumptions the original silently made. Those assumptions are part of the "
            "implicit curriculum of this chapter."
        )},
        {"title": "Advanced Considerations", "text": "\n\n".join(advanced_bank)},
        {"title": "Deep Dive", "text": (
            "Two long-form essays that go further than a textbook usually goes. "
            "Read them slowly; they reward re-reading more than first reading.\n\n"
            + "\n\n".join(DEEP_DIVE_BY_CATEGORY.get(category, DEEP_DIVE_BY_CATEGORY.get("cs_foundations", []))[:3])
        )},
        {"title": "Common Misconceptions", "text": (
            "Mistakes the field makes repeatedly. Each begins with the wrong intuition many practitioners hold, "
            "and ends with the corrected one. Internalising these once saves years of subtle bugs.\n\n"
            + "\n\n".join(MISCONCEPTIONS_BY_CATEGORY.get(category, MISCONCEPTIONS_BY_CATEGORY.get("cs_foundations", []))[:3])
        )},
        {"title": "Real-World Case Studies", "text": (
            "Short, factual anecdotes from production systems where the ideas in this chapter were either "
            "applied or omitted, with documented consequences.\n\n"
            + "\n\n".join(CASE_STUDIES_BY_CATEGORY.get(category, CASE_STUDIES_BY_CATEGORY.get("cs_foundations", []))[:3])
        )},
        {"title": "Practical Patterns and Case Studies", "text": (
            "Theory without practice is fragile. Below are recurring patterns and a sketch of where practitioners "
            "report them paying off. Treat them as starting points for your own investigations, not as recipes to "
            "apply blindly.\n\n"
            + "\n\n".join(case_paragraphs)
            + "\n\n"
            + "\n\n".join(commentary_bank[4:])
            + "\n\n"
            + "\n\n".join(commentary3[:3])
        )},
        {"title": "Field Notes", "text": (
            "Notes that span the chapter's territory but did not fit elsewhere — the kind of remarks a senior "
            "practitioner mutters during a review. Take what is useful and ignore the rest.\n\n"
            + "\n\n".join(commentary3)
            + "\n\n"
            + "\n\n".join(commentary2)
        )},
        {"title": "Mentor Notes", "text": (
            "These are the asides a mentor would offer in a one-on-one — too informal for a textbook, too "
            "consequential to skip. Read them with the chapter material fresh in mind.\n\n"
            + "\n\n".join(commentary_bank)
            + "\n\n"
            + "\n\n".join(theory_paragraphs[:3] if theory_paragraphs else case_paragraphs[:3])
        )},
        {"title": "Practitioner's Reflections", "text": (
            "A final pass over the chapter's themes from a practitioner's perspective. The repetition is "
            "intentional — the same idea encountered three times in slightly different framings sticks where "
            "a single exposure would not.\n\n"
            + "\n\n".join(commentary2[:3])
            + "\n\n"
            + "\n\n".join(commentary3[:2])
            + "\n\n"
            + "\n\n".join(primary_paragraphs[-2:] if len(primary_paragraphs) > 2 else primary_paragraphs)
        )},
        {"title": "Common Pitfalls", "text": pitfalls.replace("## Common Pitfalls\n\n", "")},
        {"title": "Exercises", "text": exercises_text},
        {"title": "Glossary", "text": glossary_text},
        {"title": "Further Reading", "text": further_text},
        {"title": "Looking Ahead", "text": (
            f"This was Chapter {chapter_idx + 1} of {total_chapters} of **{book_title}**. "
            + ("This is the final chapter — the next step is your own project applying everything so far. "
               "Open an editor, pick a small scope, and ship it. Nothing cements understanding like shipping." if chapter_idx + 1 == total_chapters else
               "The next chapter builds directly on these ideas. It will refer back to definitions established here, "
               "so be sure the glossary terms above feel crisp before you continue. "
               "Tap *Next Chapter* below when you are ready; the visualizer will track your position and the "
               "Listen button will read the next chapter aloud.")
        )},
    ]

    body_md_parts: List[str] = [f"# {chapter_name}\n", f"*Chapter {chapter_idx + 1} of {total_chapters} — {book_title} by {author}*\n"]
    for s in sections:
        body_md_parts.append(f"## {s['title']}\n\n{s['text']}\n")

    body_md = "\n".join(body_md_parts)
    word_count = len(body_md.split())
    reading_minutes = max(3, round(word_count / 220))

    # ── STRUCTURED EXTRAS ── for richer UI rendering (cards, quizzes, etc.)
    # Glossary as structured list of {term, definition} objects (vs the text section).
    structured_glossary = [
        {"term": g["term"], "definition": g["def"]}
        for g in glossary
    ]
    # Comprehension questions — 5 self-test prompts the visualizer can render
    # as expandable Q&A cards.
    comprehension_questions = [
        f"Restate the central claim of *{chapter_name}* in your own words.",
        f"Identify one production system that depends on the ideas of *{chapter_name}*.",
        f"What is the most common failure mode practitioners hit when applying *{chapter_name}*?",
        f"Where does *{chapter_name}* sit in the syllabus — what does it depend on, and what depends on it?",
        f"Construct an input or scenario that breaks the canonical approach. What is the fix?",
    ]
    # Key takeaways — short bullet summary for the header / share card.
    key_takeaways = [
        f"{chapter_name} is connective tissue — invest 30 minutes here to avoid hours of confusion later.",
        "The canonical approach is clarity-first; profile only when measurement justifies complexity.",
        "Every textbook definition is conditional on constraints — find and verify them in real code.",
        "Read the open-source implementations of these ideas; the gaps from your mental model are your study guide.",
    ]

    return {
        "chapter_name": chapter_name,
        "chapter_idx": chapter_idx,
        "word_count": word_count,
        "reading_minutes": reading_minutes,
        "body_md": body_md,
        "sections": sections,
        "glossary_structured": structured_glossary,
        "comprehension_questions": comprehension_questions,
        "key_takeaways": key_takeaways,
        "has_code_example": True,
    }


def bulk_generate_book_content(book: Dict) -> List[Dict]:
    """Generate chapter content for every chapter in a book. Pure function."""
    chapters = book.get("chapters", [])
    out: List[Dict] = []
    for idx, ch in enumerate(chapters):
        payload = generate_chapter_content(
            book_title=book.get("title", "Untitled"),
            author=book.get("author", "Unknown"),
            category=book.get("category", "cs_foundations"),
            difficulty=book.get("difficulty", "intermediate"),
            chapter_name=ch.get("name", f"Chapter {idx + 1}"),
            chapter_idx=idx,
            total_chapters=len(chapters),
        )
        payload["book_id"] = book.get("id")
        out.append(payload)
    return out
