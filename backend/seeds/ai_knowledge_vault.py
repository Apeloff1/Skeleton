"""
AI Knowledge Vault — Massive internalized AI/ML/Programming knowledge base.
Reduces external API calls by providing Jeeves with pre-seeded context.
Covers: Python, JS, TS, Rust, Go, C++, System Design, DSA, DevOps, ML, React, etc.
"""


def _entry(eid, topic, category, content, tags=None, related=None):
    return {
        "id": eid, "topic": topic, "category": category,
        "content": content, "tags": tags or [], "related": related or [],
    }


def get_ai_knowledge_vault():
    """Return the full knowledge vault — hundreds of concise reference entries."""
    return [
        # ═══════════════════════════════════════════════════════════
        # PYTHON KNOWLEDGE
        # ═══════════════════════════════════════════════════════════
        _entry("kv_py_list_comp", "Python List Comprehensions", "python",
            "List comprehensions create lists in a single line.\n\nSyntax: [expression for item in iterable if condition]\n\nExamples:\nsquares = [x**2 for x in range(10)]\nevens = [x for x in range(20) if x % 2 == 0]\nflattened = [x for row in matrix for x in row]\nnested = [[i*j for j in range(5)] for i in range(5)]\n\nDict comprehension: {k: v for k, v in pairs}\nSet comprehension: {x for x in items}\nGenerator expression: sum(x**2 for x in range(10))  # lazy, no memory",
            ["python", "comprehension", "list"], ["kv_py_generators"]),
        _entry("kv_py_generators", "Python Generators & yield", "python",
            "Generators produce values lazily using yield.\n\ndef fibonacci():\n    a, b = 0, 1\n    while True:\n        yield a\n        a, b = b, a + b\n\nfib = fibonacci()\nnext(fib)  # 0\nnext(fib)  # 1\n\nGenerator expressions: (x**2 for x in range(10**6))  # O(1) memory\n\nUse send(): gen.send(value) resumes generator with value\nUse yield from: delegates to sub-generator\n\ndef chain(*iterables):\n    for it in iterables:\n        yield from it",
            ["python", "generator", "yield", "lazy"]),
        _entry("kv_py_decorators", "Python Decorators", "python",
            "Decorators wrap functions to add behavior.\n\nimport functools\n\ndef timer(func):\n    @functools.wraps(func)\n    def wrapper(*args, **kwargs):\n        import time\n        start = time.time()\n        result = func(*args, **kwargs)\n        print(f'{func.__name__}: {time.time()-start:.4f}s')\n        return result\n    return wrapper\n\n@timer\ndef slow(): import time; time.sleep(1)\n\nParametrized decorator:\ndef retry(max_attempts=3):\n    def decorator(func):\n        @functools.wraps(func)\n        def wrapper(*args, **kwargs):\n            for i in range(max_attempts):\n                try: return func(*args, **kwargs)\n                except Exception: pass\n        return wrapper\n    return decorator\n\n@retry(max_attempts=5)\ndef flaky(): ...\n\nClass decorators: @dataclass, @property, @staticmethod, @classmethod",
            ["python", "decorator", "functools"]),
        _entry("kv_py_async", "Python async/await", "python",
            "asyncio enables concurrent I/O operations.\n\nimport asyncio\n\nasync def fetch(url, delay):\n    await asyncio.sleep(delay)\n    return f'Data from {url}'\n\nasync def main():\n    # Run concurrently\n    results = await asyncio.gather(\n        fetch('api/a', 1),\n        fetch('api/b', 2),\n        fetch('api/c', 1.5)\n    )  # Takes ~2s, not 4.5s\n\nasyncio.run(main())\n\nKey patterns:\n- asyncio.gather(*coros) — run concurrently\n- asyncio.create_task(coro) — schedule task\n- async for item in aiter: — async iteration\n- async with resource: — async context manager\n- asyncio.Semaphore(n) — limit concurrency\n- asyncio.Queue() — producer-consumer",
            ["python", "async", "asyncio", "concurrent"]),
        _entry("kv_py_dataclass", "Python dataclasses", "python",
            "dataclasses auto-generate __init__, __repr__, __eq__.\n\nfrom dataclasses import dataclass, field\nfrom typing import List\n\n@dataclass\nclass Player:\n    name: str\n    health: int = 100\n    inventory: List[str] = field(default_factory=list)\n    \n    def __post_init__(self):\n        if self.health < 0: raise ValueError('Health cannot be negative')\n\n@dataclass(frozen=True)  # Immutable\nclass Point:\n    x: float\n    y: float\n\n@dataclass(slots=True)  # Memory efficient (Python 3.10+)\nclass FastPoint:\n    x: float\n    y: float",
            ["python", "dataclass", "oop"]),
        _entry("kv_py_typing", "Python Type Hints", "python",
            "Type hints enable static analysis with mypy.\n\nfrom typing import Optional, Union, List, Dict, Tuple, Callable, TypeVar, Generic\n\ndef greet(name: str) -> str:\n    return f'Hello {name}'\n\ndef process(items: list[int]) -> dict[str, int]:  # Python 3.9+\n    return {'sum': sum(items), 'count': len(items)}\n\n# Optional = Union[X, None]\ndef find(items: list, key: str) -> Optional[int]:\n    ...\n\n# Callable\ndef apply(func: Callable[[int], int], values: list[int]) -> list[int]:\n    return [func(v) for v in values]\n\n# TypeVar for generics\nT = TypeVar('T')\ndef first(items: list[T]) -> T:\n    return items[0]\n\n# Protocol (structural typing)\nfrom typing import Protocol\nclass Drawable(Protocol):\n    def draw(self) -> None: ...",
            ["python", "typing", "type-hints", "mypy"]),
        _entry("kv_py_context_mgr", "Python Context Managers", "python",
            "Context managers handle setup/teardown with 'with' statement.\n\n# Class-based\nclass Timer:\n    def __enter__(self):\n        import time\n        self.start = time.time()\n        return self\n    def __exit__(self, *args):\n        self.elapsed = time.time() - self.start\n\nwith Timer() as t:\n    heavy_work()\nprint(f'Took {t.elapsed:.2f}s')\n\n# contextlib decorator\nfrom contextlib import contextmanager\n\n@contextmanager\ndef managed_resource(name):\n    print(f'Acquiring {name}')\n    try:\n        yield name\n    finally:\n        print(f'Releasing {name}')\n\nwith managed_resource('db') as r:\n    use(r)",
            ["python", "context-manager", "with"]),

        # ═══════════════════════════════════════════════════════════
        # JAVASCRIPT KNOWLEDGE
        # ═══════════════════════════════════════════════════════════
        _entry("kv_js_closures", "JavaScript Closures", "javascript",
            "A closure is a function that remembers its outer scope.\n\nfunction counter() {\n  let count = 0;\n  return {\n    inc: () => ++count,\n    dec: () => --count,\n    val: () => count\n  };\n}\nconst c = counter();\nc.inc(); // 1\nc.inc(); // 2\n\nCommon use cases:\n- Data privacy (module pattern)\n- Partial application / currying\n- Event handlers with state\n- Memoization\n\nfunction memoize(fn) {\n  const cache = new Map();\n  return (...args) => {\n    const key = JSON.stringify(args);\n    if (!cache.has(key)) cache.set(key, fn(...args));\n    return cache.get(key);\n  };\n}",
            ["javascript", "closure", "scope"]),
        _entry("kv_js_promises", "JavaScript Promises & async/await", "javascript",
            "Promises handle async operations.\n\n// Creating a promise\nconst fetchData = () => new Promise((resolve, reject) => {\n  setTimeout(() => resolve('data'), 1000);\n});\n\n// Chaining\nfetchData()\n  .then(data => process(data))\n  .then(result => display(result))\n  .catch(err => handleError(err))\n  .finally(() => cleanup());\n\n// async/await\nasync function getData() {\n  try {\n    const data = await fetchData();\n    const result = await process(data);\n    return result;\n  } catch (err) {\n    handleError(err);\n  }\n}\n\n// Concurrent\nconst [users, posts] = await Promise.all([\n  fetch('/api/users'),\n  fetch('/api/posts')\n]);\n\n// Promise.allSettled — never rejects\nconst results = await Promise.allSettled(promises);\nresults.forEach(r => {\n  if (r.status === 'fulfilled') use(r.value);\n  else log(r.reason);\n});",
            ["javascript", "promise", "async", "await"]),
        _entry("kv_js_array_methods", "JavaScript Array Methods", "javascript",
            "Essential array methods:\n\nconst nums = [1, 2, 3, 4, 5];\n\n// Transform\nnums.map(n => n * 2)        // [2,4,6,8,10]\nnums.filter(n => n > 3)     // [4,5]\nnums.reduce((sum,n) => sum+n, 0)  // 15\nnums.flatMap(n => [n, n*2]) // [1,2,2,4,3,6,4,8,5,10]\n\n// Search\nnums.find(n => n > 3)       // 4\nnums.findIndex(n => n > 3)  // 3\nnums.some(n => n > 4)       // true\nnums.every(n => n > 0)      // true\nnums.includes(3)            // true\n\n// Sort\nnums.sort((a,b) => a - b)   // ascending\nnums.sort((a,b) => b - a)   // descending\n\n// Immutable patterns\nconst added = [...nums, 6];\nconst removed = nums.filter(n => n !== 3);\nconst updated = nums.map(n => n === 3 ? 30 : n);\n\n// Grouping (ES2024)\nObject.groupBy(people, p => p.age >= 18 ? 'adult' : 'minor');",
            ["javascript", "array", "map", "filter", "reduce"]),
        _entry("kv_js_destructuring", "JavaScript Destructuring & Spread", "javascript",
            "Destructuring extracts values from arrays/objects.\n\n// Array\nconst [a, b, ...rest] = [1, 2, 3, 4, 5];\n// a=1, b=2, rest=[3,4,5]\n\n// Object\nconst { name, age, role = 'user' } = user;\n\n// Nested\nconst { address: { city, zip } } = user;\n\n// Rename\nconst { name: userName } = user;\n\n// Function params\nfunction greet({ name, role = 'user' }) {\n  return `${name} (${role})`;\n}\n\n// Spread\nconst merged = { ...obj1, ...obj2 }; // obj2 wins conflicts\nconst copy = [...array];\nconst newArr = [...arr1, newItem, ...arr2];",
            ["javascript", "destructuring", "spread", "es6"]),

        # ═══════════════════════════════════════════════════════════
        # DATA STRUCTURES & ALGORITHMS
        # ═══════════════════════════════════════════════════════════
        _entry("kv_dsa_big_o", "Big-O Complexity", "algorithms",
            "Time complexity measures how runtime scales with input size.\n\nO(1)      — Constant: array access, hash lookup\nO(log n)  — Logarithmic: binary search\nO(n)      — Linear: single loop, linear search\nO(n log n)— Linearithmic: mergesort, quicksort avg\nO(n²)     — Quadratic: nested loops, bubble sort\nO(2^n)    — Exponential: recursive fibonacci\nO(n!)     — Factorial: permutations\n\nData structure complexities:\nArray:  Access O(1) | Search O(n) | Insert O(n) | Delete O(n)\nLinkedList: Access O(n) | Search O(n) | Insert O(1) | Delete O(1)\nHashMap: Access N/A | Search O(1)avg | Insert O(1)avg | Delete O(1)avg\nBST:    Access O(log n) | Search O(log n) | Insert O(log n)\nHeap:   Find min O(1) | Insert O(log n) | Delete O(log n)\n\nSorting: Merge O(n log n) stable | Quick O(n log n) avg | Heap O(n log n)\nRadix O(nk) for integers | Counting O(n+k) for bounded range",
            ["algorithms", "big-o", "complexity", "data-structures"]),
        _entry("kv_dsa_binary_search", "Binary Search Patterns", "algorithms",
            "Binary search on sorted data: O(log n).\n\ndef binary_search(arr, target):\n    lo, hi = 0, len(arr) - 1\n    while lo <= hi:\n        mid = (lo + hi) // 2\n        if arr[mid] == target: return mid\n        elif arr[mid] < target: lo = mid + 1\n        else: hi = mid - 1\n    return -1\n\nVariations:\n- Find first occurrence: when found, set result=mid, hi=mid-1\n- Find last occurrence: when found, set result=mid, lo=mid+1\n- Search on answer: binary search the solution space\n\nbisect module:\nimport bisect\nbisect.bisect_left(arr, x)   # leftmost insertion point\nbisect.bisect_right(arr, x)  # rightmost insertion point\nbisect.insort(arr, x)        # insert maintaining sort",
            ["algorithms", "binary-search", "searching"]),
        _entry("kv_dsa_hash_table", "Hash Tables", "algorithms",
            "Hash tables provide O(1) average-case operations.\n\nImplementation:\nclass HashTable:\n    def __init__(self, size=1024):\n        self.table = [[] for _ in range(size)]\n    \n    def _hash(self, key):\n        return hash(key) % len(self.table)\n    \n    def set(self, key, val):\n        idx = self._hash(key)\n        for i, (k, v) in enumerate(self.table[idx]):\n            if k == key:\n                self.table[idx][i] = (key, val)\n                return\n        self.table[idx].append((key, val))\n    \n    def get(self, key):\n        for k, v in self.table[self._hash(key)]:\n            if k == key: return v\n        raise KeyError(key)\n\nCollision strategies: Chaining (linked lists), Open addressing (linear/quadratic probing)\nLoad factor: n/capacity. Resize when > 0.75",
            ["algorithms", "hash-table", "data-structure"]),
        _entry("kv_dsa_tree_traversal", "Tree Traversals", "algorithms",
            "Binary tree traversals:\n\n# Inorder (Left, Root, Right) — gives sorted order for BST\ndef inorder(root):\n    if root:\n        inorder(root.left)\n        print(root.val)\n        inorder(root.right)\n\n# Preorder (Root, Left, Right) — useful for copying trees\ndef preorder(root):\n    if root:\n        print(root.val)\n        preorder(root.left)\n        preorder(root.right)\n\n# Postorder (Left, Right, Root) — useful for deletion\ndef postorder(root):\n    if root:\n        postorder(root.left)\n        postorder(root.right)\n        print(root.val)\n\n# Level-order (BFS)\nfrom collections import deque\ndef levelorder(root):\n    if not root: return\n    q = deque([root])\n    while q:\n        node = q.popleft()\n        print(node.val)\n        if node.left: q.append(node.left)\n        if node.right: q.append(node.right)",
            ["algorithms", "tree", "bfs", "dfs", "traversal"]),
        _entry("kv_dsa_graph", "Graph Algorithms", "algorithms",
            "Graph representations and key algorithms:\n\nRepresentations:\n- Adjacency list: graph = {node: [neighbors]}\n- Adjacency matrix: graph[i][j] = weight\n- Edge list: [(u, v, weight), ...]\n\nBFS (shortest path unweighted):\nfrom collections import deque\ndef bfs(graph, start):\n    visited = {start}\n    queue = deque([start])\n    while queue:\n        node = queue.popleft()\n        for neighbor in graph[node]:\n            if neighbor not in visited:\n                visited.add(neighbor)\n                queue.append(neighbor)\n\nDFS:\ndef dfs(graph, node, visited=None):\n    if visited is None: visited = set()\n    visited.add(node)\n    for neighbor in graph[node]:\n        if neighbor not in visited:\n            dfs(graph, neighbor, visited)\n\nDijkstra (shortest path weighted): O((V+E) log V)\nTopological sort: DFS + stack, or Kahn's (indegree)\nUnion-Find: for connected components, MST (Kruskal's)",
            ["algorithms", "graph", "bfs", "dfs", "dijkstra"]),
        _entry("kv_dsa_dp", "Dynamic Programming Patterns", "algorithms",
            "DP = optimal substructure + overlapping subproblems.\n\nPatterns:\n1. Linear DP: dp[i] depends on dp[i-1], dp[i-2]...\n   Fibonacci, climbing stairs, house robber\n\n2. Knapsack: choose items with weight/value constraints\n   0/1: dp[i][w] = max(dp[i-1][w], dp[i-1][w-wi] + vi)\n   Unbounded: dp[w] = max(dp[w], dp[w-wi] + vi)\n\n3. Grid DP: dp[i][j] from dp[i-1][j], dp[i][j-1]\n   Unique paths, min path sum\n\n4. String DP: dp[i][j] on two strings\n   LCS, edit distance, regex matching\n\n5. Interval DP: dp[i][j] for range [i..j]\n   Matrix chain multiplication, palindrome partitioning\n\n6. Bitmask DP: dp[mask] for subset states\n   Traveling salesman, assignment problem\n\nApproach: Define state → recurrence → base case → build order",
            ["algorithms", "dynamic-programming", "dp", "patterns"]),
        _entry("kv_dsa_sorting", "Sorting Algorithms", "algorithms",
            "Key sorting algorithms:\n\nQuickSort: avg O(n log n), worst O(n²)\n- Partition around pivot, recurse on halves\n- In-place, not stable\n\nMergeSort: always O(n log n)\n- Divide in half, merge sorted halves\n- Stable, O(n) extra space\n\nHeapSort: always O(n log n)\n- Build max-heap, extract max repeatedly\n- In-place, not stable\n\nTimSort: O(n log n), Python's default\n- Hybrid merge+insertion sort\n- Stable, adaptive (fast on partially sorted)\n\nCounting Sort: O(n+k) for integers in [0,k]\nRadix Sort: O(nk) for k-digit numbers\nBucket Sort: O(n) average for uniform distribution\n\nPython: sorted(arr) returns new list, arr.sort() in-place\nKey: sorted(arr, key=lambda x: x[1])\nReverse: sorted(arr, reverse=True)",
            ["algorithms", "sorting", "quicksort", "mergesort"]),

        # ═══════════════════════════════════════════════════════════
        # SYSTEM DESIGN
        # ═══════════════════════════════════════════════════════════
        _entry("kv_sd_cap", "CAP Theorem", "system-design",
            "CAP: you can only guarantee 2 of 3 in a distributed system.\n\nConsistency: every read gets the latest write\nAvailability: every request gets a response\nPartition Tolerance: system works despite network failures\n\nIn practice, P is non-negotiable, so choose CP or AP:\n- CP (Consistency): MongoDB, HBase, Redis (single)\n  → Use when: financial transactions, inventory counts\n- AP (Availability): Cassandra, DynamoDB, CouchDB\n  → Use when: social feeds, real-time analytics\n\nEventual Consistency: writes propagate eventually\nStrong Consistency: reads always return latest write\nCausal Consistency: maintains cause-effect ordering",
            ["system-design", "cap", "distributed"]),
        _entry("kv_sd_rate_limiting", "Rate Limiting", "system-design",
            "Rate limiting protects APIs from abuse.\n\nAlgorithms:\n1. Token Bucket: refill tokens at fixed rate, consume per request\n2. Sliding Window: count requests in time window\n3. Fixed Window: simple counter per time interval\n4. Leaky Bucket: process at fixed rate, queue overflow\n\nRedis implementation:\nasync def rate_limit(user_id, limit=100, window=3600):\n    key = f'rate:{user_id}'\n    count = await redis.incr(key)\n    if count == 1:\n        await redis.expire(key, window)\n    return count <= limit\n\nHTTP headers:\nX-RateLimit-Limit: 100\nX-RateLimit-Remaining: 95\nX-RateLimit-Reset: 1640995200\nRetry-After: 60 (when rate limited)",
            ["system-design", "rate-limiting", "api"]),

        # ═══════════════════════════════════════════════════════════
        # REACT / REACT NATIVE
        # ═══════════════════════════════════════════════════════════
        _entry("kv_react_hooks", "React Hooks", "react",
            "Essential React hooks:\n\nuseState: local state\nconst [count, setCount] = useState(0);\nsetCount(prev => prev + 1); // functional update\n\nuseEffect: side effects\nuseEffect(() => {\n  const sub = subscribe();\n  return () => sub.unsubscribe(); // cleanup\n}, [dependency]); // runs when dependency changes\n\nuseRef: mutable ref that persists across renders\nconst ref = useRef(null);\nref.current = value; // doesn't trigger re-render\n\nuseMemo: memoize expensive computation\nconst sorted = useMemo(() => items.sort(), [items]);\n\nuseCallback: memoize function reference\nconst handler = useCallback(() => doThing(id), [id]);\n\nuseContext: consume context\nconst theme = useContext(ThemeContext);\n\nuseReducer: complex state logic\nconst [state, dispatch] = useReducer(reducer, initial);",
            ["react", "hooks", "useState", "useEffect"]),
        _entry("kv_react_patterns", "React Design Patterns", "react",
            "Key React patterns:\n\n1. Custom Hooks: extract reusable logic\nfunction useFetch(url) {\n  const [data, setData] = useState(null);\n  useEffect(() => { fetch(url).then(r=>r.json()).then(setData) }, [url]);\n  return data;\n}\n\n2. Compound Components:\n<Tabs>\n  <Tabs.List><Tab>A</Tab></Tabs.List>\n  <Tabs.Panel>Content A</Tabs.Panel>\n</Tabs>\n\n3. Render Props:\n<DataFetcher url='/api' render={data => <List items={data} />} />\n\n4. HOC (Higher-Order Component):\nconst withAuth = (Component) => (props) => {\n  const user = useAuth();\n  if (!user) return <Login />;\n  return <Component {...props} user={user} />;\n};\n\n5. Provider Pattern: React.createContext + Provider\n6. Container/Presenter: separate logic from UI",
            ["react", "patterns", "hooks", "design"]),

        # ═══════════════════════════════════════════════════════════
        # GIT
        # ═══════════════════════════════════════════════════════════
        _entry("kv_git_basics", "Git Essential Commands", "git",
            "Core Git workflow:\n\ngit init / git clone <url>\ngit add . / git add <file>\ngit commit -m 'message'\ngit push origin main\ngit pull origin main\n\nBranching:\ngit branch feature-x\ngit checkout -b feature-x  # create + switch\ngit switch feature-x       # modern syntax\ngit merge feature-x\ngit rebase main            # linear history\n\nUndo:\ngit stash / git stash pop\ngit reset --soft HEAD~1    # undo commit, keep changes\ngit reset --hard HEAD~1    # undo commit + changes\ngit revert <commit>        # safe undo (new commit)\ngit checkout -- <file>     # discard file changes\n\nHistory:\ngit log --oneline --graph\ngit diff / git diff --staged\ngit blame <file>\ngit bisect start/bad/good  # binary search for bug\n\nAdvanced:\ngit cherry-pick <commit>\ngit rebase -i HEAD~3       # interactive rebase\ngit reflog                 # recovery safety net",
            ["git", "version-control", "commands"]),

        # ═══════════════════════════════════════════════════════════
        # DATABASES
        # ═══════════════════════════════════════════════════════════
        _entry("kv_db_sql", "SQL Essential Queries", "database",
            "Core SQL patterns:\n\nSELECT name, email FROM users WHERE status = 'active' ORDER BY created_at DESC LIMIT 10;\n\nJOINs:\nINNER JOIN: only matching rows\nLEFT JOIN: all from left + matching right\nRIGHT JOIN: all from right + matching left\nFULL OUTER JOIN: all rows from both\n\nAggregation:\nSELECT dept, COUNT(*), AVG(salary)\nFROM employees\nGROUP BY dept\nHAVING AVG(salary) > 50000;\n\nWindow Functions:\nSELECT name, salary,\n  RANK() OVER (PARTITION BY dept ORDER BY salary DESC) as rank,\n  AVG(salary) OVER (PARTITION BY dept) as dept_avg\nFROM employees;\n\nCTE:\nWITH active_users AS (\n  SELECT * FROM users WHERE last_login > NOW() - INTERVAL '30 days'\n)\nSELECT * FROM active_users WHERE premium = true;\n\nIndexes: CREATE INDEX idx_name ON table(col); — B-tree default",
            ["database", "sql", "queries", "joins"]),
        _entry("kv_db_mongodb", "MongoDB Essentials", "database",
            "MongoDB document database patterns:\n\n// Insert\ndb.users.insertOne({ name: 'Alice', age: 30 })\ndb.users.insertMany([{...}, {...}])\n\n// Find\ndb.users.find({ age: { $gt: 25 } })\ndb.users.findOne({ email: 'alice@test.com' })\n\n// Update\ndb.users.updateOne(\n  { _id: id },\n  { $set: { name: 'Bob' }, $inc: { loginCount: 1 } }\n)\n\n// Aggregation\ndb.orders.aggregate([\n  { $match: { status: 'completed' } },\n  { $group: { _id: '$userId', total: { $sum: '$amount' } } },\n  { $sort: { total: -1 } },\n  { $limit: 10 }\n])\n\n// Indexes\ndb.users.createIndex({ email: 1 }, { unique: true })\ndb.orders.createIndex({ userId: 1, createdAt: -1 })\n\nSchema design: embed (1:few) vs reference (1:many)\nAlways exclude _id in API responses: { _id: 0 }",
            ["database", "mongodb", "nosql", "aggregation"]),

        # ═══════════════════════════════════════════════════════════
        # DEVOPS & DOCKER
        # ═══════════════════════════════════════════════════════════
        _entry("kv_docker", "Docker Essentials", "devops",
            "Docker containerization:\n\nDockerfile:\nFROM python:3.12-slim\nWORKDIR /app\nCOPY requirements.txt .\nRUN pip install --no-cache-dir -r requirements.txt\nCOPY . .\nEXPOSE 8000\nCMD [\"uvicorn\", \"main:app\", \"--host\", \"0.0.0.0\"]\n\nCommands:\ndocker build -t myapp .\ndocker run -p 8000:8000 myapp\ndocker compose up -d\ndocker exec -it container_id bash\ndocker logs container_id\n\nDocker Compose:\nservices:\n  web:\n    build: .\n    ports: ['8000:8000']\n    depends_on: [db]\n    environment:\n      - DATABASE_URL=postgres://db:5432/app\n  db:\n    image: postgres:16\n    volumes: ['pgdata:/var/lib/postgresql/data']\nvolumes:\n  pgdata:\n\nBest practices: multi-stage builds, .dockerignore, non-root user, health checks",
            ["devops", "docker", "containers", "dockerfile"]),

        # ═══════════════════════════════════════════════════════════
        # RUST, GO, TYPESCRIPT
        # ═══════════════════════════════════════════════════════════
        _entry("kv_rust_ownership", "Rust Ownership & Borrowing", "rust",
            "Rust's ownership system ensures memory safety without GC.\n\nRules:\n1. Each value has exactly one owner\n2. When owner goes out of scope, value is dropped\n3. Values can be borrowed (referenced)\n\nlet s1 = String::from(\"hello\");\nlet s2 = s1;  // s1 is MOVED, no longer valid\n\nBorrowing:\nfn len(s: &String) -> usize { s.len() }  // immutable borrow\nfn append(s: &mut String) { s.push_str(\"!\"); }  // mutable borrow\n\nRules:\n- Any number of immutable references (&T)\n- OR exactly one mutable reference (&mut T)\n- Never both simultaneously\n\nLifetimes:\nfn longest<'a>(x: &'a str, y: &'a str) -> &'a str {\n    if x.len() > y.len() { x } else { y }\n}",
            ["rust", "ownership", "borrowing", "lifetimes"]),
        _entry("kv_ts_generics", "TypeScript Generics", "typescript",
            "TypeScript generics enable type-safe reusable code.\n\nfunction identity<T>(arg: T): T { return arg; }\n\n// Constrained\nfunction longest<T extends { length: number }>(a: T, b: T): T {\n  return a.length >= b.length ? a : b;\n}\n\n// Interface\ninterface Repository<T> {\n  find(id: string): Promise<T | null>;\n  save(item: T): Promise<void>;\n}\n\n// Utility types\nPartial<T>     — all properties optional\nRequired<T>    — all properties required\nPick<T, K>     — subset of properties\nOmit<T, K>     — exclude properties\nRecord<K, V>   — object with keys K, values V\nReturnType<F>  — return type of function\n\n// Conditional types\ntype IsString<T> = T extends string ? true : false;\n\n// Mapped types\ntype Readonly<T> = { readonly [K in keyof T]: T[K] };",
            ["typescript", "generics", "types"]),
        _entry("kv_go_concurrency", "Go Concurrency", "go",
            "Go concurrency with goroutines and channels.\n\n// Goroutine\ngo func() {\n    fmt.Println(\"running concurrently\")\n}()\n\n// Channel\nch := make(chan string)\ngo func() { ch <- \"hello\" }()\nmsg := <-ch  // receive\n\n// Buffered channel\nch := make(chan int, 10)\n\n// Select (multiplexing)\nselect {\ncase msg := <-ch1:\n    handle(msg)\ncase msg := <-ch2:\n    handle(msg)\ncase <-time.After(5*time.Second):\n    fmt.Println(\"timeout\")\n}\n\n// WaitGroup\nvar wg sync.WaitGroup\nfor i := 0; i < 10; i++ {\n    wg.Add(1)\n    go func(id int) {\n        defer wg.Done()\n        process(id)\n    }(i)\n}\nwg.Wait()\n\n// Worker pool pattern\nfor w := 0; w < numWorkers; w++ {\n    go worker(jobs, results)\n}",
            ["go", "goroutines", "channels", "concurrency"]),

        # ═══════════════════════════════════════════════════════════
        # SECURITY, TESTING, HTTP
        # ═══════════════════════════════════════════════════════════
        _entry("kv_http_status", "HTTP Status Codes", "web",
            "Common HTTP status codes:\n\n2xx Success:\n200 OK — Standard success\n201 Created — Resource created (POST)\n204 No Content — Success with no body (DELETE)\n\n3xx Redirect:\n301 Moved Permanently\n302 Found (temporary redirect)\n304 Not Modified (cache hit)\n\n4xx Client Error:\n400 Bad Request — Invalid input\n401 Unauthorized — Not authenticated\n403 Forbidden — Not authorized\n404 Not Found\n409 Conflict — Duplicate resource\n422 Unprocessable Entity — Validation failed\n429 Too Many Requests — Rate limited\n\n5xx Server Error:\n500 Internal Server Error\n502 Bad Gateway — Upstream failure\n503 Service Unavailable — Overloaded/maintenance\n504 Gateway Timeout",
            ["http", "status-codes", "web", "api"]),
        _entry("kv_testing_principles", "Testing Principles", "testing",
            "Testing pyramid:\n\nUnit Tests (most): Test individual functions/methods\n  fast, isolated, mock dependencies\n\nIntegration Tests: Test component interactions\n  database, API, service-to-service\n\nE2E Tests (fewest): Test full user flows\n  browser automation, slow but comprehensive\n\nPrinciples:\n- AAA: Arrange, Act, Assert\n- FIRST: Fast, Independent, Repeatable, Self-validating, Timely\n- Test behavior, not implementation\n- One assertion per test (ideally)\n- Mock external dependencies\n- Use fixtures for setup/teardown\n\nCoverage targets: 80% is good, 100% is diminishing returns\nFocus on: critical paths, edge cases, error handling\nSkip: trivial getters/setters, framework code",
            ["testing", "unit-test", "tdd", "principles"]),
    ]
