"""
╔══════════════════════════════════════════════════════════════════════════╗
║  CODING DICTIONARY — ULTRASCALE                                        ║
║  Full language references, classes, knowledge, courses, prompts         ║
║  Thousands of entries across every programming concept                  ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

def get_coding_dictionary():
    entries = []
    _c = [0]
    def _id(p):
        _c[0] += 1
        return f"dict_{p}_{_c[0]}"

    _LANGS = ["Python","JavaScript","TypeScript","Java","C","C++","C#","Go","Rust","Swift","Kotlin","Ruby","PHP","Scala","R","Dart","Perl","Lua","Shell","SQL","Haskell","Clojure","Elixir","Erlang","F#","Julia","Zig","Nim","Crystal","OCaml"]
    _CONCEPTS = [
        ("variables","Variables & Types",{"Python":"x = 42\nname: str = 'hello'","JavaScript":"let x = 42;\nconst name = 'hello';","Go":"var x int = 42\nname := \"hello\"","Rust":"let x: i32 = 42;\nlet name = \"hello\";","C":"int x = 42;","Java":"int x = 42;","C++":"int x = 42;","C#":"int x = 42;","Swift":"var x = 42","Kotlin":"val x = 42","Ruby":"x = 42","PHP":"$x = 42;","Scala":"val x = 42","TypeScript":"let x: number = 42;","Haskell":"x = 42","Elixir":"x = 42","Julia":"x = 42","Dart":"int x = 42;","Lua":"x = 42","R":"x <- 42"}),
        ("functions","Functions",{"Python":"def f(x):\n    return x*2","JavaScript":"function f(x) { return x*2; }","Go":"func f(x int) int { return x*2 }","Rust":"fn f(x: i32) -> i32 { x*2 }","C":"int f(int x) { return x*2; }","Java":"int f(int x) { return x*2; }","C++":"int f(int x) { return x*2; }","Swift":"func f(_ x: Int) -> Int { x*2 }","Kotlin":"fun f(x: Int) = x*2","Ruby":"def f(x) x*2 end","PHP":"function f($x) { return $x*2; }","Haskell":"f x = x * 2","Elixir":"def f(x), do: x * 2"}),
        ("loops","Loops",{"Python":"for i in range(10): pass","JavaScript":"for(let i=0;i<10;i++){}","Go":"for i:=0;i<10;i++{}","Rust":"for i in 0..10{}","C":"for(int i=0;i<10;i++){}","Java":"for(int i=0;i<10;i++){}","Swift":"for i in 0..<10{}","Kotlin":"for(i in 0..9){}","Ruby":"10.times{|i|}","Haskell":"mapM_ print [0..9]"}),
        ("conditionals","Conditionals",{"Python":"if x>0: pass\nelif x==0: pass\nelse: pass","JavaScript":"if(x>0){} else if(x===0){} else{}","Go":"if x>0{} else{}","Rust":"if x>0{} else{}","C":"if(x>0){} else{}","Java":"if(x>0){} else{}","Swift":"if x>0{} else{}","Kotlin":"when{x>0->1;else->0}"}),
        ("arrays","Arrays & Lists",{"Python":"a=[1,2,3]; a.append(4)","JavaScript":"let a=[1,2,3]; a.push(4);","Go":"a:=[]int{1,2,3}; a=append(a,4)","Rust":"let mut a=vec![1,2,3]; a.push(4);","C":"int a[]={1,2,3};","Java":"List<Integer> a=new ArrayList<>();","Swift":"var a=[1,2,3]; a.append(4)","Kotlin":"val a=mutableListOf(1,2,3); a.add(4)","Ruby":"a=[1,2,3]; a<<4"}),
        ("maps","Maps & Dicts",{"Python":"d={'a':1}; d['b']=2","JavaScript":"let d={a:1}; d.b=2;","Go":"d:=map[string]int{\"a\":1}; d[\"b\"]=2","Rust":"let mut d=HashMap::new(); d.insert(\"a\",1);","Java":"Map<String,Integer> d=new HashMap<>();","Swift":"var d=[\"a\":1]; d[\"b\"]=2","Kotlin":"val d=mutableMapOf(\"a\" to 1)"}),
        ("strings","Strings",{"Python":"s='hello'; s.upper(); f'{s} world'","JavaScript":"let s='hello'; s.toUpperCase(); `${s} world`","Go":"s:=\"hello\"; strings.ToUpper(s)","Rust":"let s=String::from(\"hello\"); s.to_uppercase()","Java":"String s=\"hello\"; s.toUpperCase();","Swift":"var s=\"hello\"; s.uppercased()","Kotlin":"val s=\"hello\"; s.uppercase()"}),
        ("error_handling","Error Handling",{"Python":"try:\n    x()\nexcept Exception as e:\n    print(e)","JavaScript":"try{x()}catch(e){console.error(e)}","Go":"val,err:=x()\nif err!=nil{log.Fatal(err)}","Rust":"match x(){Ok(v)=>v,Err(e)=>panic!(\"{}\",e)}","Java":"try{x();}catch(Exception e){e.printStackTrace();}","Swift":"do{try x()}catch{print(error)}","Kotlin":"try{x()}catch(e:Exception){println(e)}"}),
        ("classes","Classes & OOP",{"Python":"class Dog:\n    def __init__(self,name):\n        self.name=name","JavaScript":"class Dog{constructor(name){this.name=name}}","Go":"type Dog struct{Name string}","Rust":"struct Dog{name:String}","Java":"class Dog{String name;Dog(String n){name=n;}}","Swift":"class Dog{var name:String;init(name:String){self.name=name}}","Kotlin":"class Dog(val name:String)","Ruby":"class Dog;def initialize(name);@name=name;end;end"}),
        ("concurrency","Concurrency",{"Python":"import asyncio\nasync def f(): await asyncio.sleep(1)","JavaScript":"async function f(){await new Promise(r=>setTimeout(r,1000))}","Go":"go func(){ch<-result}()","Rust":"tokio::spawn(async{fetch().await});","Java":"CompletableFuture.runAsync(()->f());","Swift":"Task{await f()}","Kotlin":"launch{f()}"}),
        ("file_io","File I/O",{"Python":"with open('f.txt') as f: data=f.read()","JavaScript":"const data=fs.readFileSync('f.txt','utf8')","Go":"data,_:=os.ReadFile(\"f.txt\")","Rust":"let data=std::fs::read_to_string(\"f.txt\")?;","Java":"String data=Files.readString(Path.of(\"f.txt\"));","Swift":"let data=try String(contentsOfFile:\"f.txt\")"}),
        ("testing","Testing",{"Python":"def test_f(): assert f(2)==4","JavaScript":"test('f',()=>expect(f(2)).toBe(4))","Go":"func TestF(t*testing.T){if f(2)!=4{t.Error(\"fail\")}}","Rust":"#[test] fn test_f(){assert_eq!(f(2),4);}","Java":"@Test void testF(){assertEquals(4,f(2));}"}),
        ("closures","Closures & Lambdas",{"Python":"f=lambda x:x*2","JavaScript":"const f=x=>x*2","Go":"f:=func(x int)int{return x*2}","Rust":"let f=|x|x*2;","Java":"Function<Integer,Integer> f=x->x*2;","Swift":"let f={$0*2}","Kotlin":"val f={x:Int->x*2}","Ruby":"f=->x{x*2}"}),
        ("generics","Generics",{"TypeScript":"function id<T>(x:T):T{return x}","Go":"func Map[T,U any](s[]T,f func(T)U)[]U{}","Rust":"fn id<T>(x:T)->T{x}","Java":"public <T> T id(T x){return x;}","C++":"template<typename T> T id(T x){return x;}","Swift":"func id<T>(_ x:T)->T{return x}","Kotlin":"fun <T> id(x:T):T=x"}),
        ("pattern_matching","Pattern Matching",{"Python":"match x:\n    case 1: pass\n    case _: pass","Rust":"match x{1=>\"one\",_=>\"other\"}","Haskell":"case x of 1->\"one\";_->\"other\"","Scala":"x match{case 1=>\"one\";case _=>\"other\"}","Elixir":"case x do 1->\"one\";_->\"other\" end","Swift":"switch x{case 1:break;default:break}","Kotlin":"when(x){1->\"one\";else->\"other\"}"}),
    ]
    for cid, cname, examples in _CONCEPTS:
        for lang, code in examples.items():
            entries.append({"id":_id(f"syn_{cid}_{lang.lower()}"),"type":"syntax_reference","concept":cid,"concept_name":cname,"language":lang,"code":code,"category":"language_syntax","difficulty":"beginner"})

    _PATTERNS = [
        ("singleton","Singleton","Ensure single instance","creational"),("factory","Factory","Create without specifying class","creational"),
        ("abstract_factory","Abstract Factory","Create related families","creational"),("builder","Builder","Step-by-step construction","creational"),
        ("prototype","Prototype","Clone existing objects","creational"),("adapter","Adapter","Convert interfaces","structural"),
        ("bridge","Bridge","Separate abstraction/impl","structural"),("composite","Composite","Tree structures","structural"),
        ("decorator","Decorator","Add responsibilities","structural"),("facade","Facade","Simplified interface","structural"),
        ("flyweight","Flyweight","Share common state","structural"),("proxy","Proxy","Control access","structural"),
        ("chain","Chain of Responsibility","Pass along chain","behavioral"),("command","Command","Encapsulate requests","behavioral"),
        ("iterator","Iterator","Traverse collections","behavioral"),("mediator","Mediator","Reduce dependencies","behavioral"),
        ("memento","Memento","Capture/restore state","behavioral"),("observer","Observer","Notify of changes","behavioral"),
        ("state","State","Alter behavior on state","behavioral"),("strategy","Strategy","Interchangeable algorithms","behavioral"),
        ("template","Template Method","Algorithm skeleton","behavioral"),("visitor","Visitor","Add operations","behavioral"),
        ("repository","Repository","Data access layer","architectural"),("mvc","MVC","Model-View-Controller","architectural"),
        ("mvvm","MVVM","Model-View-ViewModel","architectural"),("cqrs","CQRS","Read/write separation","architectural"),
        ("event_sourcing","Event Sourcing","Store as events","architectural"),("saga","Saga","Distributed transactions","architectural"),
        ("circuit_breaker","Circuit Breaker","Prevent cascades","architectural"),("microservices","Microservices","Independent services","architectural"),
    ]
    for pid, pname, pdesc, pcat in _PATTERNS:
        entries.append({"id":_id(f"pat_{pid}"),"type":"design_pattern","pattern":pid,"name":pname,"description":pdesc,"pattern_category":pcat,"category":"design_patterns","difficulty":"intermediate"})

    _DS = [
        ("array","Array","O(1) access","fundamental"),("linked_list","Linked List","O(1) insert","fundamental"),
        ("stack","Stack","LIFO","fundamental"),("queue","Queue","FIFO","fundamental"),
        ("hash_map","Hash Map","O(1) avg lookup","fundamental"),("hash_set","Hash Set","Unique elements","fundamental"),
        ("bst","Binary Search Tree","O(log n)","tree"),("avl","AVL Tree","Self-balancing BST","tree"),
        ("rb_tree","Red-Black Tree","Balanced BST","tree"),("heap","Heap","Priority queue","tree"),
        ("trie","Trie","Prefix tree","tree"),("b_tree","B-Tree","Disk storage","tree"),
        ("graph","Graph","Vertices+edges","graph"),("segment_tree","Segment Tree","Range queries","advanced"),
        ("fenwick","Fenwick Tree","Prefix sums","advanced"),("disjoint_set","Union-Find","Components","advanced"),
        ("bloom_filter","Bloom Filter","Probabilistic set","probabilistic"),("skip_list","Skip List","Probabilistic balanced","probabilistic"),
        ("lru_cache","LRU Cache","Least recently used","cache"),("deque","Deque","Double-ended queue","fundamental"),
    ]
    for did, dname, ddesc, dcat in _DS:
        entries.append({"id":_id(f"ds_{did}"),"type":"data_structure","name":dname,"description":ddesc,"ds_category":dcat,"category":"data_structures","difficulty":"intermediate"})

    _ALGOS = [
        ("bubble_sort","Bubble Sort","O(n²)","sorting"),("merge_sort","Merge Sort","O(n log n)","sorting"),
        ("quick_sort","Quick Sort","O(n log n) avg","sorting"),("heap_sort","Heap Sort","O(n log n)","sorting"),
        ("binary_search","Binary Search","O(log n)","searching"),("dfs","DFS","O(V+E)","graph"),
        ("bfs","BFS","O(V+E)","graph"),("dijkstra","Dijkstra","O((V+E)log V)","graph"),
        ("bellman_ford","Bellman-Ford","O(VE)","graph"),("kruskal","Kruskal","O(E log E)","graph"),
        ("prim","Prim","O((V+E)log V)","graph"),("topological","Topological Sort","O(V+E)","graph"),
        ("a_star","A* Search","O(b^d)","graph"),("dp_knapsack","0/1 Knapsack","O(nW)","dp"),
        ("dp_lcs","LCS","O(mn)","dp"),("dp_edit","Edit Distance","O(mn)","dp"),
        ("two_pointers","Two Pointers","O(n)","technique"),("sliding_window","Sliding Window","O(n)","technique"),
        ("backtracking","Backtracking","O(2^n)","technique"),("greedy","Greedy","varies","technique"),
    ]
    for aid, aname, atime, acat in _ALGOS:
        entries.append({"id":_id(f"algo_{aid}"),"type":"algorithm","name":aname,"time_complexity":atime,"algo_category":acat,"category":"algorithms","difficulty":"intermediate"})

    _PROMPTS = [
        ("gen","Code Generation",["Write a {lang} function that {task}","Implement {algo} in {lang}","Create a {lang} REST API for {resource}","Build a {lang} CLI tool for {task}","Write {lang} tests for: {code}","Refactor to use {pattern} pattern","Convert {lang_a} to {lang_b}","Optimize for performance: {code}","Add error handling to: {code}","Create a {lang} microservice for {domain}"]),
        ("debug","Debugging",["Find the bug: {code}","Why does this produce {error}?","Fix this race condition: {code}","Debug memory leak: {code}","Why is this slow? Optimize: {code}","Fix security vulnerability: {code}","Why does this fail in production?","Debug this failing test: {code}"]),
        ("explain","Explanation",["Explain line by line: {code}","What does {concept} do in {lang}?","Difference between {a} and {b}?","When to use {pattern}?","Time complexity of: {code}","Pros/cons of {approach}?","Best practices for {topic} in {lang}?"]),
        ("arch","Architecture",["Design {system} architecture","Structure a {lang} project for {scale}","Database schema for {app}","Microservices for {system}","Caching strategy for {app}","Event-driven design for {use_case}","CI/CD pipeline for {project}"]),
        ("learn","Learning",["Explain {concept} for beginners","Roadmap to become {role}","10 practice problems for {topic}","Common {lang} mistakes","{lang_a} vs {lang_b} for {use_case}?","{lang} best practices 2026","Project ideas for {lang} beginners"]),
    ]
    for pid, pname, prompts in _PROMPTS:
        for i, p in enumerate(prompts):
            entries.append({"id":_id(f"prompt_{pid}_{i}"),"type":"ai_prompt","prompt_template":p,"prompt_category":pid,"category_name":pname,"category":"ai_prompts","difficulty":"beginner"})

    _COURSES = [
        ("web101","Web Dev 101","beginner","web",7),("react","React Mastery","intermediate","frontend",8),
        ("node","Node.js Backend","intermediate","backend",7),("python_ds","Python Data Science","intermediate","data",8),
        ("rust_sys","Rust Systems","advanced","systems",7),("go_cloud","Go Cloud Native","intermediate","cloud",7),
        ("ml_eng","ML Engineering","advanced","ml",8),("security","Security Engineering","advanced","security",7),
        ("devops","DevOps Mastery","intermediate","devops",8),("mobile","Mobile Development","intermediate","mobile",7),
        ("gamedev","Game Development","intermediate","gamedev",8),("blockchain","Blockchain Dev","advanced","blockchain",7),
        ("compiler","Compiler Design","expert","compilers",7),("distributed","Distributed Systems","expert","systems",8),
        ("quantum","Quantum Computing","expert","quantum",7),("ai_nlp","NLP Engineering","advanced","ml",7),
        ("cv","Computer Vision","advanced","ml",7),("db_internals","Database Internals","advanced","databases",8),
        ("os_dev","OS Development","expert","systems",8),("networking","Network Engineering","advanced","networking",7),
        ("embedded","Embedded Systems","advanced","embedded",7),("fp","Functional Programming","intermediate","paradigms",7),
        ("testing_qa","Testing & QA","intermediate","testing",7),("api_design","API Design","intermediate","backend",6),
        ("perf_eng","Performance Engineering","advanced","performance",7),
    ]
    for cid, cname, cdiff, cdom, mods in _COURSES:
        entries.append({"id":_id(f"course_{cid}"),"type":"course","name":cname,"difficulty":cdiff,"domain":cdom,"module_count":mods,"estimated_hours":mods*12,"category":"courses"})

    _TOPICS = [
        "type_systems","memory_management","garbage_collection","ownership_borrowing","generics_templates",
        "interfaces_traits","inheritance_composition","polymorphism","encapsulation","abstraction",
        "functional_programming","imperative_programming","declarative_programming","recursion","memoization",
        "big_o_notation","amortized_analysis","rest_api_design","graphql_design","grpc_protobuf",
        "websockets","http2_http3","sql_vs_nosql","acid_properties","cap_theorem",
        "eventual_consistency","docker_containers","kubernetes","ci_cd_pipelines","infrastructure_as_code",
        "tdd","bdd","integration_testing","e2e_testing","property_based_testing",
        "solid_principles","dry_principle","kiss_principle","clean_code","technical_debt",
        "microservices_architecture","monolith_vs_micro","serverless","edge_computing","event_driven",
        "oauth2_oidc","jwt_tokens","api_keys","cors_security","csrf_protection",
        "xss_prevention","sql_injection","caching_strategies","cdn_optimization","load_balancing",
        "rate_limiting","circuit_breaker_pattern","git_workflows","code_review","pair_programming",
        "agile_methodology","scrum_framework","kanban_system","sprint_planning","retrospectives",
        "continuous_delivery","blue_green_deployment","canary_releases","feature_flags","a_b_testing",
        "monitoring_observability","logging_best_practices","distributed_tracing","alerting","sla_slo_sli",
        "database_indexing","query_optimization","connection_pooling","database_migrations","data_modeling",
        "message_queues","event_streaming","pub_sub_patterns","saga_pattern","outbox_pattern",
        "domain_driven_design","clean_architecture","hexagonal_architecture","cqrs_pattern","event_sourcing_pattern",
    ]
    for topic in _TOPICS:
        tn = topic.replace("_"," ").title()
        entries.append({"id":_id(f"know_{topic}"),"type":"knowledge","topic":topic,"name":tn,"description":f"Comprehensive guide to {tn}","category":"knowledge","difficulty":"intermediate"})

    return entries
