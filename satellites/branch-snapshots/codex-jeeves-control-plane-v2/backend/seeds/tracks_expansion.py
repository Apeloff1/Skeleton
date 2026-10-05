"""
Massive Track Expansion — New academy tracks to push total to 10,000+ curriculum hours.
Java, Kotlin, Swift, C, Haskell, Elixir, Scala, PHP, Ruby, plus expanded subject academies.
"""
def get_expanded_tracks():
    # Deferred import: academy_data is heavy; keep it out of module top-level
    # so importing this module at boot stays cheap (cold-start win).
    from seeds.academy_data import _lesson, _module, _project, _assessment, _question
    return [
        {"id": "java", "name": "Java Mastery", "icon": "cafe", "color": "#E76F00", "total_hours": 3240,
         "category": "language", "description": "Master Java from OOP to Spring Boot, microservices, and enterprise patterns.",
         "prerequisites": [], "certificate": "Java Professional Developer",
         "modules": [
             _module("java_basics", "Java Fundamentals", "Syntax, OOP, collections, streams", 60, [
                 _lesson("j_b1", "Java Syntax & OOP", "Classes, interfaces, inheritance, polymorphism", 120, "beginner", ["java","oop"], "public class Animal {\n    protected String name;\n    public Animal(String name) { this.name = name; }\n    public String speak() { return name + \" makes a sound\"; }\n}\n\npublic class Dog extends Animal {\n    public Dog(String name) { super(name); }\n    @Override public String speak() { return name + \" barks\"; }\n}\n\n// Interfaces\ninterface Drawable { void draw(); default void clear() {} }\n// Records (Java 16+)\nrecord Point(double x, double y) {}"),
                 _lesson("j_b2", "Collections & Generics", "List, Map, Set, generics, iterators", 90, "beginner", ["java","collections","generics"], "List<String> names = new ArrayList<>(List.of(\"Alice\",\"Bob\"));\nMap<String,Integer> scores = new HashMap<>();\nscores.put(\"Alice\", 95);\nSet<Integer> unique = new TreeSet<>(List.of(3,1,4,1,5));\n\n// Generic class\npublic class Pair<A, B> {\n    private final A first; private final B second;\n    public Pair(A first, B second) { this.first = first; this.second = second; }\n}"),
                 _lesson("j_b3", "Streams & Lambdas", "Functional programming in Java", 90, "intermediate", ["java","streams","lambda"], "List<String> result = names.stream()\n    .filter(n -> n.length() > 3)\n    .map(String::toUpperCase)\n    .sorted()\n    .collect(Collectors.toList());\n\nMap<String,Long> freq = words.stream()\n    .collect(Collectors.groupingBy(w -> w, Collectors.counting()));"),
             ], _project("j_proj1", "REST API with Spring Boot", "Build a complete REST API", "intermediate", 25, ["Spring Boot app","CRUD endpoints","JPA + PostgreSQL","JWT auth","Swagger docs","Docker deploy"], tags=["java","spring"]),
                _assessment("j_assess1", "Java Fundamentals Assessment", [
                    _question("jq1", "Which is immutable?", ["ArrayList","HashMap","String","LinkedList"], "String", 10),
                    _question("jq2", "Streams are...", ["eager","lazy","synchronous","blocking"], "lazy", 10),
                ], 70)),
             _module("java_advanced", "Advanced Java", "Concurrency, JVM internals, Spring ecosystem", 80, [
                 _lesson("j_a1", "Concurrency & Virtual Threads", "ExecutorService, CompletableFuture, virtual threads", 120, "advanced", ["java","concurrency","virtual-threads"], "// Virtual threads (Java 21)\ntry (var executor = Executors.newVirtualThreadPerTaskExecutor()) {\n    for (int i = 0; i < 100_000; i++) {\n        executor.submit(() -> processRequest());\n    }\n}\n\n// CompletableFuture\nCompletableFuture.supplyAsync(() -> fetchUser(id))\n    .thenCompose(user -> fetchOrders(user.id))\n    .thenApply(orders -> calculateTotal(orders))\n    .exceptionally(ex -> handleError(ex));"),
                 _lesson("j_a2", "JVM Internals", "Memory model, GC, class loading, profiling", 90, "advanced", ["java","jvm","gc","memory"], "JVM Memory: Heap (Young Gen + Old Gen) + Metaspace + Stack\nGC algorithms: G1 (default), ZGC (low latency), Shenandoah\n\nTuning: -Xms512m -Xmx2g -XX:+UseG1GC\nProfiling: jconsole, VisualVM, async-profiler\nClass loading: Bootstrap → Extension → Application"),
             ], _project("j_proj2", "Microservices System", "Build distributed microservices", "advanced", 40, ["3 Spring Boot services","Kafka event bus","API Gateway","Circuit breakers","Docker Compose","Monitoring"], tags=["java","microservices"])),
         ]},
        {"id": "kotlin_full", "name": "Kotlin & Android", "icon": "logo-android", "color": "#7F52FF", "total_hours": 2970,
         "category": "language", "description": "Master Kotlin for Android, backend, and multiplatform development.",
         "prerequisites": [], "certificate": "Kotlin Developer Professional",
         "modules": [
             _module("kt_basics", "Kotlin Fundamentals", "Syntax, null safety, coroutines, collections", 50, [
                 _lesson("kt_b1", "Kotlin Syntax", "val/var, data classes, sealed classes, extensions", 90, "beginner", ["kotlin","syntax"], "val name = \"Alice\"\nvar age = 30\ndata class User(val name: String, val age: Int)\nsealed class Result<out T> { data class Success<T>(val data: T): Result<T>(); data class Error(val msg: String): Result<Nothing>() }\nfun String.exclaim() = this + \"!\""),
                 _lesson("kt_b2", "Coroutines", "Structured concurrency, flows, channels", 120, "intermediate", ["kotlin","coroutines","async"], "viewModelScope.launch {\n    val user = withContext(Dispatchers.IO) { api.getUser(id) }\n    _uiState.value = UiState.Success(user)\n}\n\n// Flow\nfun getUsers(): Flow<List<User>> = flow {\n    while(true) { emit(api.getUsers()); delay(5000) }\n}.flowOn(Dispatchers.IO)"),
             ], _project("kt_proj1", "Android App", "Build a modern Android app", "intermediate", 30, ["Jetpack Compose UI","MVVM architecture","Room database","Retrofit networking","Navigation","Material 3"], tags=["kotlin","android"])),
         ]},
        {"id": "swift_full", "name": "Swift & iOS", "icon": "logo-apple", "color": "#F05138", "total_hours": 2970,
         "category": "language", "description": "Master Swift for iOS, macOS, and server-side development.",
         "prerequisites": [], "certificate": "iOS Developer Professional",
         "modules": [
             _module("sw_basics", "Swift Fundamentals", "Optionals, protocols, closures, error handling", 50, [
                 _lesson("sw_b1", "Swift Syntax", "let/var, optionals, pattern matching, protocols", 90, "beginner", ["swift","syntax"], "let name = \"Alice\"\nvar score: Int? = nil\nif let s = score { print(s) }\nlet v = score ?? 0\n\nprotocol Drawable { func draw() }\nenum Shape { case circle(Double), rect(Double,Double) }"),
                 _lesson("sw_b2", "SwiftUI", "Declarative UI, state management, navigation", 120, "intermediate", ["swift","swiftui"], "struct ContentView: View {\n    @State private var count = 0\n    var body: some View {\n        VStack { Text(\"\\(count)\"); Button(\"+\") { count += 1 } }\n    }\n}\n\n@Observable class ViewModel { var items: [Item] = [] }"),
             ], _project("sw_proj1", "iOS App", "Build a complete iOS app", "intermediate", 30, ["SwiftUI interface","Core Data persistence","Combine/async-await","Push notifications","App Store submission","Widgets"], tags=["swift","ios"])),
         ]},
        {"id": "c_lang", "name": "C Programming", "icon": "code-slash", "color": "#555555", "total_hours": 2700,
         "category": "language", "description": "Master C for systems programming, embedded systems, and OS development.",
         "prerequisites": [], "certificate": "C Systems Programmer",
         "modules": [
             _module("c_basics", "C Fundamentals", "Pointers, memory, structs, file I/O", 60, [
                 _lesson("c_b1", "Pointers & Memory", "Pointer arithmetic, malloc, free, stack vs heap", 120, "intermediate", ["c","pointers","memory"], "#include <stdlib.h>\nint *arr = (int*)malloc(10 * sizeof(int));\nfor(int i=0; i<10; i++) arr[i] = i*i;\nfree(arr);\n\n// Pointer to pointer\nint **matrix = malloc(rows * sizeof(int*));\nfor(int i=0; i<rows; i++) matrix[i] = malloc(cols * sizeof(int));\n\n// Function pointers\nint (*compare)(const void*, const void*) = my_compare;\nqsort(arr, n, sizeof(int), compare);"),
                 _lesson("c_b2", "Structs & Data Structures", "Structs, linked lists, trees in C", 90, "intermediate", ["c","structs","data-structures"], "typedef struct Node { int data; struct Node *next; } Node;\n\nNode* create(int data) {\n    Node* n = malloc(sizeof(Node));\n    n->data = data; n->next = NULL;\n    return n;\n}\nvoid push(Node** head, int data) {\n    Node* n = create(data);\n    n->next = *head; *head = n;\n}"),
             ], _project("c_proj1", "Custom Memory Allocator", "Build a memory allocator", "advanced", 25, ["malloc/free implementation","Free list management","Coalescing","Alignment","Testing with benchmarks"], tags=["c","memory","systems"])),
         ]},
        {"id": "haskell_lang", "name": "Haskell & FP", "icon": "code", "color": "#5E5086", "total_hours": 2430,
         "category": "language", "description": "Master Haskell and functional programming paradigms.",
         "prerequisites": [], "certificate": "Functional Programming Specialist",
         "modules": [
             _module("hs_basics", "Haskell Fundamentals", "Types, pattern matching, higher-order functions", 40, [
                 _lesson("hs_b1", "Haskell Basics", "Functions, pattern matching, guards, where/let", 90, "intermediate", ["haskell","functional"], "factorial :: Integer -> Integer\nfactorial 0 = 1\nfactorial n = n * factorial (n-1)\n\nfib :: Int -> Int\nfib n = fibs !! n where fibs = 0 : 1 : zipWith (+) fibs (tail fibs)\n\nmap (*2) [1..10]  -- [2,4,6,...,20]\nfilter even [1..20]  -- [2,4,6,...,20]"),
             ]),
         ]},
        {"id": "elixir_lang", "name": "Elixir & Phoenix", "icon": "flash", "color": "#6E4A7E", "total_hours": 2430,
         "category": "language", "description": "Master Elixir for scalable, fault-tolerant applications with Phoenix.",
         "prerequisites": [], "certificate": "Elixir Developer",
         "modules": [
             _module("ex_basics", "Elixir Fundamentals", "Pattern matching, pipes, processes, OTP", 40, [
                 _lesson("ex_b1", "Elixir Basics", "Pattern matching, pipe operator, immutability", 90, "intermediate", ["elixir","pattern-matching"], "{:ok, result} = {:ok, 42}\n[head | tail] = [1,2,3]\n\n\"hello world\" |> String.split() |> Enum.map(&String.capitalize/1) |> Enum.join(\" \")\n\nEnum.map(1..10, &(&1 * 2))  # [2,4,...,20]\nEnum.reduce(1..100, 0, &+/2)  # 5050"),
             ]),
         ]},
        {"id": "scala_lang", "name": "Scala & Spark", "icon": "analytics", "color": "#DC322F", "total_hours": 2700,
         "category": "language", "description": "Master Scala for functional programming, Akka, and Apache Spark.",
         "prerequisites": [], "certificate": "Scala Developer",
         "modules": [
             _module("sc_basics", "Scala Fundamentals", "FP, pattern matching, implicits, Akka", 50, [
                 _lesson("sc_b1", "Scala Basics", "val/var, case classes, pattern matching, traits", 90, "intermediate", ["scala","functional"], "val nums = List(1,2,3,4,5)\nnums.filter(_ % 2 == 0).map(_ * 2)  // List(4,8)\nnums.foldLeft(0)(_ + _)  // 15\n\ncase class User(name: String, age: Int)\nval u = User(\"Alice\", 30)\nval u2 = u.copy(age = 31)"),
             ]),
         ]},
        {"id": "php_full", "name": "PHP & Laravel", "icon": "code-slash", "color": "#777BB3", "total_hours": 2430,
         "category": "language", "description": "Master modern PHP 8.x with Laravel for web application development.",
         "prerequisites": [], "certificate": "PHP Developer",
         "modules": [
             _module("php_basics", "Modern PHP", "PHP 8, enums, fibers, match, Laravel", 40, [
                 _lesson("php_b1", "PHP 8.x Features", "Named args, match, enums, readonly, fibers", 90, "intermediate", ["php","php8"], "function create(string $name, int $age, string $role='user'): array {\n    return compact('name','age','role');\n}\n$user = create(name: 'Alice', age: 30);\n\nenum Status: string { case Active='active'; case Inactive='inactive'; }\n$result = match($x) { 1 => 'one', 2 => 'two', default => 'other' };"),
             ]),
         ]},
        {"id": "ruby_full", "name": "Ruby & Rails", "icon": "diamond", "color": "#CC342D", "total_hours": 2430,
         "category": "language", "description": "Master Ruby and Ruby on Rails for rapid web development.",
         "prerequisites": [], "certificate": "Ruby Developer",
         "modules": [
             _module("rb_basics", "Ruby Fundamentals", "Blocks, procs, OOP, gems, Rails", 40, [
                 _lesson("rb_b1", "Ruby Basics", "Everything is an object, blocks, symbols, mixins", 90, "intermediate", ["ruby","blocks"], "5.times { |i| puts i }\n[1,2,3].map { |n| n * 2 }  # [2,4,6]\n(1..10).select(&:even?)     # [2,4,6,8,10]\n\nclass Dog\n  attr_accessor :name\n  def initialize(name) @name = name end\n  def speak() \"#{@name} says Woof!\" end\nend"),
             ]),
         ]},

        # ═══ EXPANDED SUBJECT ACADEMIES ═══
        {"id": "devops_academy", "name": "DevOps Engineering Academy", "icon": "server", "color": "#FF6B35", "total_hours": 2700,
         "category": "subject", "description": "Master CI/CD, containers, orchestration, monitoring, and infrastructure as code.",
         "modules": [
             _module("do_containers", "Containers & Orchestration", "Docker, Kubernetes, Helm, service mesh", 80, [
                 _lesson("do_c1", "Docker Deep Dive", "Multi-stage builds, compose, networking, volumes", 120, "intermediate", ["docker","containers"], "# Multi-stage\nFROM node:20-alpine AS builder\nWORKDIR /app\nCOPY . .\nRUN npm ci && npm run build\nFROM node:20-alpine\nCOPY --from=builder /app/dist ./dist\nUSER node\nCMD [\"node\",\"dist/main.js\"]"),
                 _lesson("do_c2", "Kubernetes Production", "Deployments, services, ingress, HPA, secrets", 120, "advanced", ["kubernetes","k8s"], "kubectl apply -f deployment.yaml\nkubectl scale deployment web --replicas=5\nkubectl rollout status deployment web\nkubectl rollout undo deployment web"),
             ]),
             _module("do_cicd", "CI/CD Pipelines", "GitHub Actions, Jenkins, ArgoCD, GitOps", 60, [
                 _lesson("do_cd1", "GitHub Actions", "Workflows, jobs, steps, secrets, environments", 90, "intermediate", ["cicd","github-actions"], "name: CI\non: push\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps: [checkout, setup-node, run tests, deploy]"),
             ]),
         ]},
        {"id": "ml_academy", "name": "Machine Learning Academy", "icon": "hardware-chip", "color": "#7C3AED", "total_hours": 3240,
         "category": "subject", "description": "Complete ML curriculum from linear regression to production LLM deployment.",
         "modules": [
             _module("ml_foundations", "ML Foundations", "Regression, classification, evaluation, feature engineering", 80, [
                 _lesson("ml_f1", "Supervised Learning", "Linear/logistic regression, decision trees, SVM, KNN", 120, "intermediate", ["ml","supervised"], "from sklearn.ensemble import RandomForestClassifier\npipe = Pipeline([('scaler',StandardScaler()),('clf',RandomForestClassifier())])\npipe.fit(X_train, y_train)\nprint(classification_report(y_test, pipe.predict(X_test)))"),
                 _lesson("ml_f2", "Deep Learning", "Neural networks, CNNs, RNNs, transformers", 120, "advanced", ["ml","deep-learning"], "model = nn.Sequential(nn.Linear(784,256),nn.ReLU(),nn.Dropout(0.5),nn.Linear(256,10))\nfor epoch in range(10):\n    for x,y in loader:\n        loss = criterion(model(x),y); loss.backward(); optimizer.step()"),
             ]),
             _module("ml_nlp_cv", "NLP & Computer Vision", "Transformers, object detection, image generation", 80, [
                 _lesson("ml_nc1", "Modern NLP", "BERT, GPT, fine-tuning, embeddings, RAG", 120, "advanced", ["ml","nlp","transformers"], "from transformers import pipeline\nsentiment = pipeline('sentiment-analysis')\nresult = sentiment('Great product!')  # POSITIVE 0.9998"),
             ]),
         ]},
        {"id": "security_academy", "name": "Cybersecurity Academy", "icon": "shield", "color": "#EF4444", "total_hours": 3240,
         "category": "subject", "description": "Master application security, network security, and ethical hacking.",
         "modules": [
             _module("sec_web", "Web Application Security", "OWASP, XSS, CSRF, injection, auth", 60, [
                 _lesson("sec_w1", "OWASP Top 10", "Common vulnerabilities and prevention", 120, "intermediate", ["security","owasp","xss","injection"], "Injection: always use parameterized queries\nXSS: escape output, CSP headers\nCSRF: tokens, SameSite cookies\nBroken Auth: bcrypt, MFA, session management"),
             ]),
             _module("sec_infra", "Infrastructure Security", "Network security, encryption, penetration testing", 60, [
                 _lesson("sec_i1", "Network Security", "Firewalls, VPN, IDS/IPS, TLS", 90, "advanced", ["security","network","firewall","tls"], "TLS 1.3: 1-RTT handshake, forward secrecy\nFirewall rules: deny by default, allow specific\nVPN: WireGuard, OpenVPN\nIDS: Snort, Suricata"),
             ]),
         ]},
        {"id": "data_science_academy", "name": "Data Science Academy", "icon": "bar-chart", "color": "#06B6D4", "total_hours": 2700,
         "category": "subject", "description": "Master statistics, data analysis, visualization, and ML for data science.",
         "modules": [
             _module("ds_stats", "Statistics & Probability", "Hypothesis testing, regression, Bayesian methods", 60, [
                 _lesson("ds_s1", "Statistical Foundations", "Distributions, CLT, hypothesis testing, confidence intervals", 120, "intermediate", ["statistics","probability","hypothesis"], "Normal distribution: μ=mean, σ=std\nCLT: sample means approach normal as n→∞\nHypothesis test: H0 (null), p-value < α → reject\nConfidence interval: x̄ ± z*(σ/√n)"),
             ]),
             _module("ds_analysis", "Data Analysis & Viz", "Pandas, matplotlib, seaborn, Jupyter, storytelling", 60, [
                 _lesson("ds_a1", "Pandas Mastery", "DataFrames, groupby, merge, pivot, time series", 120, "intermediate", ["pandas","analysis","dataframe"], "df.groupby('category')['revenue'].agg(['mean','sum','count'])\npd.merge(orders, customers, on='customer_id', how='left')\ndf.pivot_table(values='sales', index='month', columns='region', aggfunc='sum')"),
             ]),
         ]},
    ]
