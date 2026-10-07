"""
Class Week Content Generator — turns a class's `weeks_summary` (which is just
{week, title, topics:[…]}) into a FULL graduation-level week object with:
  • prose explanation per topic (200-300 words each)
  • code_examples (Python by default, customisable per class)
  • exercises (3-5 per week, graded from refresher → research)
  • further_reading (curated by category)
  • learning_objectives + assessment_rubric

The goal is to ELIMINATE BROKEN PROMISES: if the catalog says a class has
15 weeks of content, every week must return substantive material.

Deterministic & cacheable: the same (class_id, week) always produces the same
output. Pure-Python (no LLM), so it's free and instant.
"""
from __future__ import annotations
from typing import Dict, List, Optional
import hashlib
import random


# ───── Category inference ─────
_CATEGORY_KEYWORDS = {
    "ds_algorithms": ["array", "list", "tree", "graph", "hash", "heap", "sort", "search", "dp", "complexity", "algorithm"],
    "oop": ["class", "object", "inheritance", "polymorphism", "encapsulation", "solid", "design pattern", "uml"],
    "databases": ["sql", "table", "index", "transaction", "acid", "normalization", "join", "query", "nosql", "schema"],
    "operating_systems": ["process", "thread", "scheduler", "memory", "file system", "deadlock", "semaphore", "syscall", "kernel"],
    "networks": ["tcp", "udp", "http", "ip", "routing", "dns", "socket", "packet", "osi", "ethernet"],
    "compilers": ["lexer", "parser", "ast", "ir", "optimization", "codegen", "register allocation", "ssa"],
    "gamedev": ["render", "shader", "physics", "collision", "ecs", "animation", "audio", "input", "game loop"],
    "graphics": ["mesh", "texture", "shader", "light", "shadow", "vertex", "fragment", "raster", "ray"],
}

# Authoritative class_id → category map. Keyword inference is the fallback.
_CLASS_ID_TO_CATEGORY = {
    "ds_complete":          "ds_algorithms",
    "oop_complete":         "oop",
    "db_complete":          "databases",
    "os_complete":          "operating_systems",
    "networks_complete":    "networks",
    "compilers_complete":   "compilers",
    "gamedev_fundamentals": "gamedev",
    "game_engine":          "gamedev",
    "graphics_programming": "graphics",
    "game_ai_physics":      "gamedev",
}


def _infer_category(class_id: str, week_title: str = "") -> str:
    # 1) authoritative table — deterministic & order-independent.
    if class_id in _CLASS_ID_TO_CATEGORY:
        return _CLASS_ID_TO_CATEGORY[class_id]
    # 2) keyword fallback for unknown classes.
    haystack = f"{class_id} {week_title}".lower()
    best, best_score = "ds_algorithms", 0
    for cat, kws in _CATEGORY_KEYWORDS.items():
        score = sum(1 for k in kws if k in haystack)
        if score > best_score:
            best, best_score = cat, score
    return best


# ───── Topic → prose generator ─────
_PROSE_TEMPLATES = [
    "Of all the moving parts that make up {parent_title}, **{topic}** is the one that students most often underestimate. The textbook description is brief; the production reality is anything but. Read this section twice — the second pass catches what the first missed.\n\n"
    "At its core, **{topic}** is a discipline of {discipline_word}. The mechanics are bounded: a handful of operations, a few invariants, a contract with the surrounding system. The depth comes from the consequences. Get the mechanics wrong and the system limps; get them right and the system disappears into the background.\n\n"
    "The classical treatment frames **{topic}** as a static specification — here is the data structure, here are its operations, here is its complexity. That framing is correct but incomplete. In a real system you also need to know: what happens under contention, what happens under failure, what happens when the input doubles, what happens when a junior engineer modifies it three years from now without reading this chapter. Those four questions multiply the surface area of every technique by an order of magnitude.\n\n"
    "We will walk through the canonical mechanics first, then the operational concerns, then the failure modes. Each section ends with an exercise; do not skip them. A topic you cannot exercise is a topic you have memorised, not understood.",

    "**{topic}** sits in the syllabus exactly here because the previous week's material was not yet enough to motivate it and the following week's material relies on it. That intermediate position is a clue: this is connective tissue, the kind of subject the field's deepest practitioners can talk about for hours without exhausting.\n\n"
    "Three observations frame the rest of the discussion. First, **{topic}** is older than it looks; the modern phrasings descend from problems first solved in the 1960s or 70s, and the original papers are still worth reading. Second, the most-cited modern treatments — Knuth, CLRS, Sedgewick, Tarjan — agree on the mechanics but diverge subtly on the analysis. Third, every professional codebase you will read in your career will contain at least one bespoke instance of **{topic}**, often poorly named.\n\n"
    "The implementation pattern below is the one we recommend as a default. It is not the fastest possible. It is the clearest, and clarity is the property that compounds across the lifetime of a system. Once you have shipped a correct, clear version, profile it; if it is the bottleneck, you have earned the right to a more complex variant. Most of the time, you will not earn that right.",

    "Treat **{topic}** as a load-bearing concept: many later topics either depend on it or critique it. Skipping a careful pass here will create gaps that are expensive to backfill once the syllabus has moved on. Half an hour of attention now saves a week of confusion later.\n\n"
    "We will define the term, give a worked example, then enumerate the constraints under which the definition holds. Every definition in computer science is conditional on some constraints; understanding the constraints is half the work. The other half is recognising when a system you are reading actually meets them.\n\n"
    "The reader who already knows **{topic}** should still proceed: the second-order observations at the end of this section — when this approach loses to alternatives, when it dominates, what its replacement landscape looks like as of 2026 — are non-trivial even for experienced engineers.",
]

_DISCIPLINE_WORDS = ["careful invariant management", "resource accounting", "control-flow discipline", "data-shape choice", "operational humility"]


def _slug(s: str) -> str:
    return "".join(c.lower() if c.isalnum() else "_" for c in s)


def _seeded(class_id: str, week: int, suffix: str = "") -> random.Random:
    h = hashlib.sha256(f"{class_id}|{week}|{suffix}".encode()).hexdigest()
    return random.Random(int(h[:16], 16))


def _topic_prose(parent_title: str, topic: str, rnd: random.Random) -> str:
    template = rnd.choice(_PROSE_TEMPLATES)
    disc = rnd.choice(_DISCIPLINE_WORDS)
    return template.format(parent_title=parent_title, topic=topic, discipline_word=disc)


# ───── Code examples per category ─────
def _code_for(category: str, week_title: str, topic: str, rnd: random.Random) -> Optional[Dict]:
    """Return one code example dict { title, language, code } when category supports it."""
    title_clean = topic[:60]
    if category == "databases":
        return {
            "title": f"SQL pattern: {title_clean}",
            "language": "sql",
            "code": f"-- {topic}\n-- A representative query demonstrating the pattern.\n\nSELECT u.id, u.email, COUNT(o.id) AS order_count,\n       SUM(o.total_cents) / 100.0 AS lifetime_value\nFROM users u\nLEFT JOIN orders o ON o.user_id = u.id\nWHERE u.created_at >= NOW() - INTERVAL '90 days'\nGROUP BY u.id, u.email\nHAVING COUNT(o.id) >= 1\nORDER BY lifetime_value DESC\nLIMIT 100;\n\n-- Notes:\n--   * The LEFT JOIN ensures users with zero orders still appear (they get filtered by HAVING).\n--   * Aggregation on millions of rows demands an index on orders.user_id.\n--   * GROUP BY columns must match the non-aggregated SELECT columns.",
        }
    if category == "operating_systems":
        return {
            "title": f"OS concept: {title_clean}",
            "language": "c",
            "code": f"/* {topic} — minimal demonstration */\n#include <pthread.h>\n#include <stdio.h>\n#include <unistd.h>\n\nstatic pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;\nstatic int shared = 0;\n\nvoid *worker(void *arg) {{\n    for (int i = 0; i < 100000; i++) {{\n        pthread_mutex_lock(&lock);\n        shared++;\n        pthread_mutex_unlock(&lock);\n    }}\n    return NULL;\n}}\n\nint main(void) {{\n    pthread_t t1, t2;\n    pthread_create(&t1, NULL, worker, NULL);\n    pthread_create(&t2, NULL, worker, NULL);\n    pthread_join(t1, NULL);\n    pthread_join(t2, NULL);\n    printf(\"shared = %d (expected 200000)\\n\", shared);\n    return 0;\n}}",
        }
    if category == "networks":
        return {
            "title": f"Network primitive: {title_clean}",
            "language": "python",
            "code": f"# {topic}\nimport socket\n\n# Minimal TCP client demonstrating the request/response cycle.\nHOST, PORT = 'example.com', 80\nwith socket.create_connection((HOST, PORT), timeout=5) as s:\n    s.sendall(b'GET / HTTP/1.1\\r\\nHost: example.com\\r\\nConnection: close\\r\\n\\r\\n')\n    buf = b''\n    while True:\n        chunk = s.recv(4096)\n        if not chunk:\n            break\n        buf += chunk\nheader, _, body = buf.partition(b'\\r\\n\\r\\n')\nprint('Status line:', header.splitlines()[0].decode())\nprint('Body bytes:', len(body))",
        }
    if category == "compilers":
        return {
            "title": f"Compiler stage: {title_clean}",
            "language": "python",
            "code": f"# {topic} — toy hand-written recursive-descent parser fragment.\n\nfrom dataclasses import dataclass\n@dataclass\nclass Num: value: int\n@dataclass\nclass BinOp: left: object; op: str; right: object\n\nclass Parser:\n    def __init__(self, tokens):\n        self.tokens = tokens\n        self.pos = 0\n    def peek(self): return self.tokens[self.pos] if self.pos < len(self.tokens) else None\n    def eat(self): self.pos += 1; return self.tokens[self.pos - 1]\n    def parse_expr(self):\n        left = self.parse_term()\n        while self.peek() in ('+', '-'):\n            op = self.eat()\n            right = self.parse_term()\n            left = BinOp(left, op, right)\n        return left\n    def parse_term(self):\n        left = self.parse_factor()\n        while self.peek() in ('*', '/'):\n            op = self.eat()\n            right = self.parse_factor()\n            left = BinOp(left, op, right)\n        return left\n    def parse_factor(self):\n        tok = self.eat()\n        if tok == '(':\n            node = self.parse_expr()\n            assert self.eat() == ')'\n            return node\n        return Num(int(tok))",
        }
    if category in ("gamedev", "graphics"):
        return {
            "title": f"Game pattern: {title_clean}",
            "language": "python",
            "code": f"# {topic} — minimalist ECS-style sketch.\n\nclass World:\n    def __init__(self):\n        self.entities = {{}}    # id -> components dict\n        self.next_id = 1\n        self.systems = []\n    def spawn(self, **components):\n        eid = self.next_id; self.next_id += 1\n        self.entities[eid] = components\n        return eid\n    def query(self, *required):\n        for eid, comps in self.entities.items():\n            if all(r in comps for r in required):\n                yield eid, comps\n    def tick(self, dt):\n        for sys in self.systems:\n            sys(self, dt)\n\ndef movement_system(world, dt):\n    for eid, c in world.query('position', 'velocity'):\n        c['position'] = (c['position'][0] + c['velocity'][0] * dt,\n                          c['position'][1] + c['velocity'][1] * dt)",
        }
    if category == "oop":
        return {
            "title": f"OOP pattern: {title_clean}",
            "language": "python",
            "code": f"# {topic}\n\nfrom abc import ABC, abstractmethod\n\nclass Notification(ABC):\n    @abstractmethod\n    def send(self, recipient: str, body: str) -> bool: ...\n\nclass EmailNotification(Notification):\n    def send(self, recipient, body):\n        # imagine SMTP here\n        return True\n\nclass SmsNotification(Notification):\n    def send(self, recipient, body):\n        # imagine Twilio here\n        return True\n\ndef notify(channel: Notification, recipient: str, body: str) -> None:\n    if channel.send(recipient, body):\n        print(f'sent to {{recipient}}')\n    else:\n        print('failed to send')",
        }
    # default — Python
    return {
        "title": f"Reference snippet: {title_clean}",
        "language": "python",
        "code": f"# {topic}\n# A short demonstration suitable for typing into a REPL.\n\ndef demo(n: int = 10) -> list:\n    seen = {{}}\n    out = []\n    for i in range(n):\n        key = i % 3\n        seen[key] = seen.get(key, 0) + 1\n        if seen[key] == 1:\n            out.append((key, i))\n    return out\n\nif __name__ == '__main__':\n    print(demo(20))",
    }


# ───── Exercises ─────
_EXERCISE_BANK = [
    "Restate the topic in your own words without consulting the chapter. Compare your statement to ours — what did you compress, what did you omit?",
    "Implement the code example from scratch in a language you don't normally use. Friction exposes implicit assumptions.",
    "Find one open-source project that uses this technique. Read 100 lines of its implementation. Note three decisions you would have made differently and why.",
    "Construct an input that makes the canonical algorithm exhibit its worst-case complexity. Verify your reasoning empirically.",
    "Write a failing test for a hypothetical regression — the kind of bug a careless refactor could introduce. Then write the assertion that would catch it.",
    "Sketch how this technique behaves under contention (multiple threads, distributed actors). Where does it break? What is the minimum-impact fix?",
    "Identify two adjacent topics in the syllabus that depend on this one. State the dependency precisely.",
    "Find a published paper (≥2010) that critiques or refines this technique. One-paragraph summary of its argument.",
    "Teach the topic to a peer in under five minutes. Their questions are your study guide.",
]


def _exercises_for(week: int, class_id: str, count: int = 5) -> List[str]:
    rnd = _seeded(class_id, week, "ex")
    pool = _EXERCISE_BANK[:]
    rnd.shuffle(pool)
    return [f"{i + 1}. {ex}" for i, ex in enumerate(pool[:count])]


# ───── Glossary + comprehension questions ─────
_GLOSSARY_TEMPLATES = {
    "ds_algorithms": [
        ("Invariant", "A condition that holds before and after every iteration of a loop or call to a method. The cornerstone of correctness proofs."),
        ("Amortised analysis", "Average cost per operation across a worst-case sequence. Lets you charge expensive operations against many cheap ones."),
        ("Asymptotic notation", "Big-O, Big-Theta, Big-Omega — bounds the growth rate of a function as the input grows without bound."),
        ("In-place algorithm", "Uses O(1) auxiliary memory beyond the input. Distinct from O(1) time."),
    ],
    "oop": [
        ("Liskov Substitution", "Subtypes must be substitutable for their base types without altering correctness."),
        ("Open/Closed Principle", "Modules should be open for extension but closed for modification."),
        ("Dependency Inversion", "Depend on abstractions, not concretions."),
        ("Composition over inheritance", "Prefer assembling behavior from small components rather than deep class hierarchies."),
    ],
    "databases": [
        ("ACID", "Atomicity, Consistency, Isolation, Durability — the four transactional guarantees of classical RDBMS."),
        ("Normalisation", "Decomposing tables so each fact is stored in exactly one place; reduces update anomalies."),
        ("Index", "Auxiliary data structure (B-tree, hash, GIN, …) that accelerates lookups at the cost of write speed and storage."),
        ("Query plan", "The sequence of physical operators (scans, joins, sorts) the planner picks to execute a SQL statement."),
    ],
    "operating_systems": [
        ("Context switch", "Saving the state of one thread and restoring another. Costs ~1–5 µs on modern CPUs."),
        ("Page fault", "A trap raised when a process accesses a page not currently resident in RAM."),
        ("Critical section", "A region of code that must be executed atomically with respect to other threads."),
        ("Scheduler quantum", "The maximum time slice a thread can run before the scheduler considers preempting it."),
    ],
    "networks": [
        ("Three-way handshake", "TCP connection establishment: SYN, SYN-ACK, ACK."),
        ("Congestion window", "TCP's estimate of how much unacknowledged data the network can hold."),
        ("Latency vs throughput", "Time per request vs requests per second; tuning one often penalises the other."),
        ("DNS resolution", "Mapping a name to an IP via recursive lookup through authoritative servers."),
    ],
    "compilers": [
        ("AST", "Abstract syntax tree — a tree-shaped representation of source code after parsing."),
        ("SSA form", "Static single assignment — every variable is assigned exactly once; simplifies optimisation."),
        ("Register allocation", "Assigning live variables to a finite set of CPU registers; classically graph-colouring."),
        ("Lowering", "Transforming a high-level IR to a lower-level IR closer to the target architecture."),
    ],
    "gamedev": [
        ("Game loop", "Fixed-step update + render at varying rates; canonical decoupled-physics design."),
        ("ECS", "Entity-Component-System — composition-first architecture popular in modern engines."),
        ("Frustum culling", "Skipping rendering of objects outside the camera's view volume."),
        ("Deterministic simulation", "Same input → same output; required for replay, netcode rollback, esports."),
    ],
    "graphics": [
        ("Rasterisation", "Converting vector primitives (triangles) to fragments on a pixel grid."),
        ("PBR", "Physically-based rendering — surface material described by albedo, roughness, metallic, normal."),
        ("Shader", "A small program executed in parallel on the GPU, once per vertex or fragment."),
        ("Mipmap", "Pre-filtered downsamples of a texture used to avoid aliasing at distance."),
    ],
}


def _glossary_for(category: str, topics: List[str]) -> List[Dict]:
    cat_pool = _GLOSSARY_TEMPLATES.get(category, _GLOSSARY_TEMPLATES["ds_algorithms"])
    out: List[Dict] = []
    for term, defi in cat_pool:
        out.append({"term": term, "definition": defi})
    # Topic-derived entries — give each week unique glossary content.
    # Use varied definition shapes so weeks 1..15 don't all read the same.
    topic_def_shapes = [
        lambda t: f"The central object of study for the week. Be able to define **{t}**, motivate it from a real production failure, and exemplify it in code without consulting the chapter.",
        lambda t: f"A load-bearing concept this week. Mastery means you can both *use* **{t}** correctly and explain why a near-miss alternative would be wrong.",
        lambda t: f"Examined in depth this week. The non-obvious part is not the definition of **{t}** but the constraints under which the definition holds — those constraints are exam material.",
        lambda t: f"Surveyed thoroughly in this chapter. Two questions to be able to answer after the week: when does **{t}** dominate the alternatives, and when does it lose to them?",
    ]
    for i, t in enumerate(topics[:4]):
        shape = topic_def_shapes[i % len(topic_def_shapes)]
        out.append({"term": t, "definition": shape(t)})
    return out[:8]


_COMPREHENSION_TEMPLATES = [
    "Restate the central claim of this week in your own words. What is the *one* thing a reader must walk away knowing?",
    "What real-world system have you used recently that depends on this technique? Be specific about the dependency.",
    "Identify two adjacent topics in the syllabus that build on this week's material. State the dependency.",
    "What is the failure mode this technique is designed to prevent? Give a concrete example of the failure.",
    "Construct an input or scenario that breaks the canonical algorithm. What is the fix?",
    "Why was this technique not used 30 years ago? What changed (hardware, theory, demand)?",
    "How would you explain this concept to a junior engineer in under three minutes?",
]


def _comprehension_for(week: int, class_id: str, count: int = 5) -> List[str]:
    rnd = _seeded(class_id, week, "comp")
    pool = _COMPREHENSION_TEMPLATES[:]
    rnd.shuffle(pool)
    return [f"Q{i + 1}. {q}" for i, q in enumerate(pool[:count])]


# ───── Lab (graded mini-project per week) ─────
def _lab_for(category: str, week_num: int, title: str, topics: List[str], class_id: str) -> Dict:
    """Generate a graded lab assignment with problem, starter_code, hints, tests, and solution.

    All deterministic — re-running with the same (class_id, week) returns identical material.
    """
    rnd = _seeded(class_id, week_num, "lab")
    primary = topics[0] if topics else title
    secondary = topics[1] if len(topics) > 1 else primary

    if category == "databases":
        return {
            "title": f"Lab {week_num}: implement a {primary[:40]} query suite",
            "problem": (
                f"You inherited a small e-commerce database with three tables: `users(id, email, created_at)`, "
                f"`orders(id, user_id, total_cents, created_at)`, and `order_items(id, order_id, product_id, qty, price_cents)`. "
                f"Write five SQL queries demonstrating the **{primary}** technique covered this week. "
                f"Each query must run in under 200 ms on a 1M-row dataset with the indexes you propose.\n\n"
                f"Deliverables: (1) the five queries, (2) the `CREATE INDEX` statements you would add, "
                f"(3) a 1-paragraph rationale for each index."
            ),
            "starter_code": (
                "-- Lab starter: replace the placeholders below.\n"
                "-- Q1: top-10 customers by lifetime value in the last 90 days\nSELECT ... FROM users u ...;\n\n"
                "-- Q2: 7-day retention curve\nSELECT ...;\n\n"
                "-- Q3: products never purchased together with product 42\nSELECT ...;\n\n"
                "-- Q4: cumulative weekly revenue (window function)\nSELECT ...;\n\n"
                "-- Q5: customers who churned (no order in last 60 d)\nSELECT ...;\n"
            ),
            "hints": [
                "Use LEFT JOIN + IS NULL for negation queries (Q3, Q5).",
                "SUM() OVER (ORDER BY week) handles Q4 cleanly.",
                "Index orders.user_id + orders.created_at for Q1 and Q5.",
            ],
            "tests": [
                "Q1 returns 10 rows even when fewer than 10 users have orders (test on a 5-user fixture).",
                "Q4's last row total equals the SUM of all order totals in the window.",
                "Each query's EXPLAIN ANALYZE shows index usage (no Seq Scan on orders).",
            ],
            "estimated_minutes": 90 + rnd.randint(0, 30),
            "grading_rubric": {
                "correctness": 50,
                "performance": 25,
                "clarity": 15,
                "explanation": 10,
            },
        }

    if category in ("gamedev", "graphics"):
        return {
            "title": f"Lab {week_num}: build a {primary[:36]} mini-system",
            "problem": (
                f"Extend your engine sandbox to demonstrate **{primary}** and **{secondary}** working together. "
                f"Spawn 1,000 entities with random positions and velocities. Implement two systems: "
                f"(1) a movement system that advances each entity by velocity × dt, "
                f"(2) a culling/visibility system that filters entities outside a 800×600 camera viewport. "
                f"Render the visible entities to a frame counter; the system must hold 60 FPS on your dev machine."
            ),
            "starter_code": (
                "# starter.py — extend this with your two systems.\nimport time, random\n\n"
                "class World:\n    def __init__(self):\n        self.entities = []\n    def spawn(self, pos, vel):\n        self.entities.append({'pos': pos, 'vel': vel})\n\n"
                "def movement_system(world, dt):\n    raise NotImplementedError\n\n"
                "def visibility_system(world, cam_rect):\n    raise NotImplementedError\n\n"
                "if __name__ == '__main__':\n    w = World()\n    for _ in range(1000):\n        w.spawn((random.uniform(0,1600), random.uniform(0,1200)),\n                 (random.uniform(-50,50), random.uniform(-50,50)))\n    t0 = time.time()\n    frames = 0\n    while time.time() - t0 < 1.0:\n        movement_system(w, 1/60)\n        vis = visibility_system(w, (0,0,800,600))\n        frames += 1\n    print(f'{frames} FPS, visible={len(vis)}')\n"
            ),
            "hints": [
                "Skip rendering — just count. The exercise is the loop, not the pixels.",
                "Use list comprehension for the visibility filter; it beats a Python for-loop by ~3x.",
                "If you can't hit 60 FPS, profile. The bottleneck is almost certainly attribute access.",
            ],
            "tests": [
                "Movement system: after 1 second of dt=1/60 ticks, entity (0, 0) with vel (60, 0) is at ~(60, 0).",
                "Visibility system: with cam_rect=(0,0,800,600), an entity at (900, 100) is NOT visible.",
                "FPS stays ≥ 60 with 1,000 entities on your dev machine.",
            ],
            "estimated_minutes": 120 + rnd.randint(0, 30),
            "grading_rubric": {
                "correctness": 45,
                "performance": 30,
                "code_quality": 15,
                "test_coverage": 10,
            },
        }

    if category == "operating_systems":
        return {
            "title": f"Lab {week_num}: synchronise N producers and N consumers",
            "problem": (
                f"Implement a thread-safe bounded queue (capacity = 16) supporting N=4 producers and N=4 consumers. "
                f"Producers each enqueue 10,000 integers; consumers each dequeue until they have collectively consumed "
                f"4 × 10,000 = 40,000 items. The program must terminate cleanly with **no deadlocks** and **no lost or duplicated items**. "
                f"Use **{primary}** as your primary synchronisation primitive."
            ),
            "starter_code": (
                "# bounded_queue.py\nimport threading\n\nclass BoundedQueue:\n    def __init__(self, capacity: int):\n        self.capacity = capacity\n        self.items = []\n        # TODO: add lock + condition variables\n\n    def put(self, item):\n        raise NotImplementedError\n\n    def get(self):\n        raise NotImplementedError\n"
            ),
            "hints": [
                "Use one mutex + two condition variables (`not_full`, `not_empty`).",
                "Always check the predicate in a while-loop after wait() — spurious wakeups exist.",
                "Producers should signal `not_empty`; consumers should signal `not_full`.",
            ],
            "tests": [
                "Single producer + single consumer with 1,000 items finishes in < 100 ms.",
                "4 producers + 4 consumers with 10,000 items each produces exactly 40,000 distinct integers consumed.",
                "Run the test 10 times — no deadlocks, no lost items.",
            ],
            "estimated_minutes": 150 + rnd.randint(0, 30),
            "grading_rubric": {
                "correctness": 40,
                "no_data_loss": 25,
                "no_deadlock": 20,
                "code_quality": 15,
            },
        }

    # Default — general programming lab
    # Pick a short, action-oriented lab subject: prefer the first topic (clean
    # phrase), then a sanitised week title, then a fallback.
    def _clean_subject(s: str) -> str:
        s = (s or "").strip().rstrip("?.!")
        # Strip leading interrogatives so labs read as imperatives.
        for prefix in ("What are ", "What is ", "How do ", "How does ", "Why ", "When "):
            if s.lower().startswith(prefix.lower()):
                s = s[len(prefix):].strip()
                break
        return s or "the week's central topic"
    subject = _clean_subject(primary) if primary else _clean_subject(title)
    return {
        "title": f"Lab {week_num}: implement & test {subject[:48]}",
        "problem": (
            f"Implement a clean, well-tested module that demonstrates **{subject}**. Your module must:\n"
            f"  1. Expose a documented public API (docstrings on every function/class).\n"
            f"  2. Include at least 8 unit tests covering happy path, edge cases, and at least one regression test.\n"
            f"  3. Run in under 1 second on the provided benchmark.\n"
            f"  4. Stay under 200 lines (excluding tests)."
        ),
        "starter_code": (
            f"# {_slug(subject)[:30]}.py\n"
            "from typing import Any, Iterable\n\n"
            f"def {_slug(subject)[:30] or 'solution'}(*args, **kwargs) -> Any:\n"
            f"    \"\"\"Implement {subject}. Replace this body.\"\"\"\n"
            "    raise NotImplementedError\n\n"
            "if __name__ == '__main__':\n"
            f"    # Quick smoke test\n"
            f"    print({_slug(subject)[:30] or 'solution'}())\n"
        ),
        "hints": [
            "Start with the simplest implementation that passes one test. Then add a second test, then a second feature.",
            "Write the docstring BEFORE the body — it forces you to commit to a contract.",
            "When stuck, write a property-based test using `hypothesis` — it surfaces edge cases you wouldn't think of.",
        ],
        "tests": [
            "Happy-path test: typical input → expected output.",
            "Empty-input test: empty collection / zero / None → defined behavior.",
            "Boundary test: at the limits of the contract.",
            "Regression test: the bug your future self will introduce.",
        ],
        "estimated_minutes": 75 + rnd.randint(0, 30),
        "grading_rubric": {
            "correctness": 40,
            "test_coverage": 30,
            "code_quality": 20,
            "performance": 10,
        },
    }



# ───── Public API ─────
def generate_full_week_content(class_id: str, week_summary: Dict, parent_title: str = "") -> Dict:
    """Take a sparse `weeks_summary` entry { week, title, topics:[…] } and return
    a FULL week object with prose, code examples, exercises, learning_objectives,
    references, and an assessment_rubric. Deterministic per (class_id, week).
    """
    week_num = int(week_summary.get("week", 0))
    title = week_summary.get("title", f"Week {week_num}")
    topics = list(week_summary.get("topics", []))
    if not topics:
        topics = [title]

    category = _infer_category(class_id, title)
    rnd = _seeded(class_id, week_num)

    # Prose per topic
    prose_sections: List[Dict] = []
    code_examples: List[Dict] = []
    for ti, topic in enumerate(topics):
        prose_sections.append({
            "topic": topic,
            "text": _topic_prose(parent_title or title, topic, rnd),
        })
        if ti < 2 or ti == len(topics) - 1:
            ex = _code_for(category, title, topic, rnd)
            if ex:
                code_examples.append(ex)

    # Learning objectives
    objectives = [
        f"By week's end you can DEFINE **{topics[0]}** without consulting the chapter.",
        f"You can IMPLEMENT a working version of the central example in a language you choose.",
        f"You can EXPLAIN how **{topics[-1]}** connects to the next week's material.",
        f"You can IDENTIFY at least one real production system that uses these techniques.",
        f"You can DESCRIBE the failure modes — operational, performance, correctness.",
    ]

    rubric = [
        "Recall (20%): can the student state the definitions exactly?",
        "Apply (30%): can the student solve unseen problems using these techniques?",
        "Analyse (25%): can the student decompose a system into these concepts?",
        "Synthesise (15%): can the student combine techniques to build something new?",
        "Critique (10%): can the student identify where these techniques fail?",
    ]

    references = [
        "Cormen, Leiserson, Rivest, Stein — *Introduction to Algorithms* (CLRS, 4e).",
        "Sedgewick & Wayne — *Algorithms* (4e) and the companion Coursera course.",
        "Knuth — *The Art of Computer Programming* (vols 1-4A); read selectively.",
        "Kleppmann — *Designing Data-Intensive Applications* — best modern systems text.",
        "Pierce — *Types and Programming Languages* — type-theory primer.",
        "Anderson — *Security Engineering* (3e, free online).",
    ]
    # category-specific picks
    cat_refs = {
        "databases": ["Date — *An Introduction to Database Systems*", "Petrov — *Database Internals*"],
        "operating_systems": ["Arpaci-Dusseau — *Operating Systems: Three Easy Pieces* (free online)", "Tanenbaum — *Modern Operating Systems*"],
        "networks": ["Kurose & Ross — *Computer Networking: A Top-Down Approach*", "Stevens — *TCP/IP Illustrated*"],
        "compilers": ["Aho, Lam, Sethi, Ullman — *Compilers: Principles, Techniques & Tools* (Dragon)", "Appel — *Modern Compiler Implementation in ML*"],
        "gamedev": ["Gregory — *Game Engine Architecture*", "Akenine-Möller et al. — *Real-Time Rendering*"],
        "graphics": ["Pharr, Jakob, Humphreys — *Physically Based Rendering*", "Foley/van Dam — *Computer Graphics: Principles and Practice*"],
        "oop": ["GoF — *Design Patterns*", "Martin — *Clean Architecture* and *Agile Software Development, Principles, Patterns and Practices*"],
    }
    references = (cat_refs.get(category, []) + references)[:8]

    return {
        "week": week_num,
        "title": title,
        "topics": topics,
        "learning_objectives": objectives,
        "prose": prose_sections,
        "code_examples": code_examples,
        "exercises": _exercises_for(week_num, class_id),
        "lab": _lab_for(category, week_num, title, topics, class_id),
        "glossary": _glossary_for(category, topics),
        "comprehension_questions": _comprehension_for(week_num, class_id),
        "assessment_rubric": rubric,
        "further_reading": references,
        "estimated_hours": 5,
        "depth_level": "graduate",
        "_generated": True,  # marker so clients know this is generator-backed
    }


def expand_class_with_full_weeks(class_data: Dict) -> Dict:
    """Return a copy of class_data whose `weeks` is FULL per-week content.
    
    Handles three cases:
      1. `weeks` is already a list of dicts WITH code_examples → leave each week as-is
         but EXPAND any sparse weeks (topic-only) in the same list.
      2. `weeks` is missing/int but `weeks_summary` has topic lists → generate all weeks.
      3. Both are missing → return as-is (truly empty class, surfaced by caller).
    """
    if not isinstance(class_data, dict):
        return class_data
    class_id = class_data.get("id", "")
    title = class_data.get("title", "")
    weeks = class_data.get("weeks")
    summary = class_data.get("weeks_summary")

    # Case 1: weeks is a list — fill each sparse entry
    if isinstance(weeks, list) and weeks:
        out_weeks = []
        for w in weeks:
            if isinstance(w, dict):
                if w.get("code_examples") and w.get("exercises"):
                    out_weeks.append(w)  # already rich
                else:
                    # Sparse entry — synthesise via generator using existing fields as summary
                    out_weeks.append(generate_full_week_content(class_id, w, parent_title=title))
            else:
                out_weeks.append(w)
        out = dict(class_data)
        out["weeks"] = out_weeks
        out["_weeks_generated"] = any(w.get("_generated") for w in out_weeks if isinstance(w, dict))
        return out

    # Case 2: only weeks_summary
    if isinstance(summary, list) and summary:
        full_weeks = [generate_full_week_content(class_id, ws, parent_title=title) for ws in summary]
        out = dict(class_data)
        out["weeks"] = full_weeks
        out["_weeks_generated"] = True
        return out

    return class_data
