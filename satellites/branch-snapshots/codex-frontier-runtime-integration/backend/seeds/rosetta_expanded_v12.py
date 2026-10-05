"""
╔══════════════════════════════════════════════════════════════════════════╗
║  ROSETTA WAVE 12 — HYPERSCALE EXPANSION                                  ║
║  bit_manipulation | tuples_records | default_parameters |               ║
║  variadic_functions                                                      ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

EXPANDED_V12 = {}

EXPANDED_V12["bit_manipulation"] = {
    "C": "int a = 5;  // 0101\nint b = 3;  // 0011\n\nint and_res = a & b;  // 0001 (1)\nint or_res = a | b;   // 0111 (7)\nint xor_res = a ^ b;  // 0110 (6)\nint not_res = ~a;     // 1010 (-6)\nint ls_res = a << 1;  // 1010 (10)\nint rs_res = a >> 1;  // 0010 (2)\n\n// Set bit 1 (0-indexed)\na |= (1 << 1);\n// Clear bit 0\na &= ~(1 << 0);\n// Toggle bit 2\na ^= (1 << 2);",
    "C++": "// Same as C, plus std::bitset\n#include <bitset>\nstd::bitset<8> b(\"0101\");\nb.set(1);   // Set bit 1\nb.reset(0); // Clear bit 0\nb.flip(2);  // Toggle bit 2\nstd::cout << b.count(); // Number of 1s",
    "Rust": "let a: u8 = 5;  // 0101\nlet b: u8 = 3;  // 0011\n\nlet and = a & b;      // 1\nlet or = a | b;       // 7\nlet xor = a ^ b;      // 6\nlet not = !a;         // 250 (u8)\nlet ls = a << 1;      // 10\nlet rs = a >> 1;      // 2\n\n// Methods\nlet count = a.count_ones();\nlet trailing = a.trailing_zeros();",
    "Go": "a := 5  // 0101\nb := 3  // 0011\n\nand := a & b    // 1\nor := a | b     // 7\nxor := a ^ b    // 6\nnot := ^a       // -6\nclear := a &^ b // 4 (AND NOT)\nls := a << 1    // 10\nrs := a >> 1    // 2\n\n// bits package\nimport \"math/bits\"\nones := bits.OnesCount(uint(a))",
    "Java": "int a = 5;  // 0101\nint b = 3;  // 0011\n\nint and = a & b;  // 1\nint or = a | b;   // 7\nint xor = a ^ b;  // 6\nint not = ~a;     // -6\nint ls = a << 1;  // 10\nint rs = a >> 1;  // 2\nint urs = a >>> 1; // Unsigned right shift\n\n// Integer methods\nInteger.bitCount(a);\nInteger.highestOneBit(a);",
    "Python": "a = 5  # 0101\nb = 3  # 0011\n\nand_res = a & b  # 1\nor_res = a | b   # 7\nxor_res = a ^ b  # 6\nnot_res = ~a     # -6\nls_res = a << 1  # 10\nrs_res = a >> 1  # 2\n\n# Python ints are arbitrary precision\n# bit_length and count\nprint(a.bit_length())\nprint(a.bit_count()) # Python 3.10+\nprint(bin(a)) # '0b101'",
    "JavaScript": "// Bitwise operations act on 32-bit signed integers\nlet a = 5;  // 0101\nlet b = 3;  // 0011\n\nlet and = a & b;  // 1\nlet or = a | b;   // 7\nlet xor = a ^ b;  // 6\nlet not = ~a;     // -6\nlet ls = a << 1;  // 10\nlet rs = a >> 1;  // 2\nlet urs = a >>> 1; // Unsigned right shift",
    "C#": "int a = 5;  // 0101\nint b = 3;  // 0011\n\nint and = a & b;  // 1\nint or = a | b;   // 7\nint xor = a ^ b;  // 6\nint not = ~a;     // -6\nint ls = a << 1;  // 10\nint rs = a >> 1;  // 2\nuint urs = (uint)a >>> 1; // C# 11+\n\n// BitOperations (C# 9+)\nusing System.Numerics;\nint count = BitOperations.PopCount((uint)a);"
}

EXPANDED_V12["tuples_records"] = {
    "Python": "# Tuples (immutable)\npoint = (10, 20)\nx, y = point\n\n# NamedTuple\nfrom collections import namedtuple\nPerson = namedtuple('Person', ['name', 'age'])\nalice = Person('Alice', 30)\nprint(alice.name, alice.age)\n\n# Dataclass (Mutable record)\nfrom dataclasses import dataclass\n@dataclass\nclass Record:\n    id: int\n    data: str",
    "Rust": "// Tuples\nlet tuple: (i32, f64, u8) = (500, 6.4, 1);\nlet (x, y, z) = tuple;\nprintln!(\"{}\", tuple.0); // 500\n\n// Structs (Records)\nstruct Point { x: i32, y: i32 }\nlet p = Point { x: 10, y: 20 };\n\n// Tuple structs\nstruct Color(i32, i32, i32);\nlet black = Color(0, 0, 0);",
    "C#": "// ValueTuple\n(int x, int y) point = (10, 20);\nConsole.WriteLine($\"{point.x}, {point.y}\");\n\n// Deconstruction\nvar (a, b) = point;\n\n// Records (C# 9+)\npublic record Person(string Name, int Age);\nvar alice = new Person(\"Alice\", 30);\n\n// Non-destructive mutation (with)\nvar olderAlice = alice with { Age = 31 };",
    "TypeScript": "// Tuple types\nlet point: [number, number] = [10, 20];\nlet [x, y] = point;\n\n// Records (Objects with known keys)\nconst record: Record<string, number> = {\n  a: 1,\n  b: 2\n};\n\n// Interfaces (Typed objects)\ninterface Person {\n  name: string;\n  age: number;\n}\nconst p: Person = { name: 'Alice', age: 30 };",
    "Haskell": "-- Tuples\npoint = (10, 20)\nx = fst point\ny = snd point\n\n-- Triples (need custom functions to extract)\ntriple = (1, \"hello\", True)\n\n-- Records\ndata Person = Person {\n  name :: String,\n  age  :: Int\n} deriving (Show)\n\nalice = Person { name = \"Alice\", age = 30 }\n-- Record update\nolderAlice = alice { age = 31 }",
    "Elixir": "# Tuples\npoint = {10, 20}\n{x, y} = point\n\n# Keyword lists\noptions = [color: \"red\", size: :large]\n\n# Maps (Records)\nperson = %{name: \"Alice\", age: 30}\nolder = %{person | age: 31}  # Update\n\n# Structs (Compile-time checked maps)\ndefmodule User do\n  defstruct name: \"\", age: 0\nend\nalice = %User{name: \"Alice\", age: 30}",
    "Swift": "// Tuples\nlet point = (x: 10, y: 20)\nprint(point.x, point.y)\n\nlet (a, b) = point\n\n// Structs (Value type records)\nstruct Person {\n    var name: String\n    var age: Int\n}\n\nvar alice = Person(name: \"Alice\", age: 30)\nalice.age = 31 // Mutating",
    "Go": "// Go has no built-in tuples. Use multiple returns or structs.\n\n// Multiple assignment\nfunc getPoint() (int, int) { return 10, 20 }\nx, y := getPoint()\n\n// Structs (Records)\ntype Person struct {\n    Name string\n    Age  int\n}\nalice := Person{\"Alice\", 30}\n\n// Anonymous struct\np := struct{ X, Y int }{10, 20}",
    "Java": "// Java Records (Java 14+)\npublic record Person(String name, int age) {}\n\nPerson alice = new Person(\"Alice\", 30);\nSystem.out.println(alice.name() + \", \" + alice.age());\n\n// Tuples (No built-in tuple, use generic class or libraries)\n// class Tuple<T, U> { T first; U second; }"
}

EXPANDED_V12["default_parameters"] = {
    "Python": "def greet(name='World', greeting='Hello'):\n    print(f'{greeting}, {name}!')\n\ngreet()               # Hello, World!\ngreet('Alice')        # Hello, Alice!\ngreet(greeting='Hi')  # Hi, World!\n\n# Beware of mutable defaults!\ndef add_item(item, lst=None):\n    if lst is None: lst = []\n    lst.append(item)\n    return lst",
    "JavaScript": "function greet(name = 'World', greeting = 'Hello') {\n  console.log(`${greeting}, ${name}!`);\n}\n\ngreet();             // Hello, World!\ngreet('Alice');      // Hello, Alice!\ngreet(undefined, 'Hi'); // Hi, World!\n\n// Evaluated at call time\nfunction generateId(id = Math.random()) { return id; }",
    "C++": "// Default arguments must be at the end of the parameter list\nvoid greet(std::string name = \"World\", std::string msg = \"Hello\") {\n    std::cout << msg << \", \" << name << \"!\\n\";\n}\n\n// Cannot skip arguments (unlike Python)\n// greet(\"Hello\"); // Error, treats \"Hello\" as 'name'",
    "C#": "void Greet(string name = \"World\", string msg = \"Hello\") {\n    Console.WriteLine($\"{msg}, {name}!\");\n}\n\nGreet();\nGreet(\"Alice\");\n\n// Named arguments allow skipping\nGreet(msg: \"Hi\");",
    "Ruby": "def greet(name = 'World', greeting = 'Hello')\n  puts \"#{greeting}, #{name}!\"\nend\n\ngreet\ngreet('Alice')\n\n# Keyword arguments with defaults\ndef config(host: 'localhost', port: 8080)\n  puts \"Connecting to #{host}:#{port}\"\nend\nconfig(port: 3000)",
    "PHP": "function greet($name = 'World', $greeting = 'Hello') {\n    echo \"$greeting, $name!\\n\";\n}\n\ngreet();\ngreet('Alice');\n\n// PHP 8+ Named arguments\ngreet(greeting: 'Hi');",
    "Kotlin": "fun greet(name: String = \"World\", greeting: String = \"Hello\") {\n    println(\"$greeting, $name!\")\n}\n\ngreet()\ngreet(\"Alice\")\n// Named arguments\ngreet(greeting = \"Hi\")",
    "Swift": "func greet(name: String = \"World\", greeting: String = \"Hello\") {\n    print(\"\\(greeting), \\(name)!\")\n}\n\ngreet()\ngreet(name: \"Alice\")\ngreet(greeting: \"Hi\")",
    "Rust": "// Rust does NOT have default parameters\n// Alternatives: Option, Builder pattern, or Default trait\n\n#[derive(Default)]\nstruct Config {\n    host: String,\n    port: u16,\n}\n\nlet c = Config { port: 8080, ..Default::default() };",
    "Go": "// Go does NOT have default parameters or function overloading\n// Alternatives: variadic options or config structs\n\ntype Options struct {\n    Name, Greeting string\n}\nfunc Greet(opts Options) {\n    if opts.Name == \"\" { opts.Name = \"World\" }\n    if opts.Greeting == \"\" { opts.Greeting = \"Hello\" }\n    fmt.Printf(\"%s, %s!\\n\", opts.Greeting, opts.Name)\n}"
}

EXPANDED_V12["variadic_functions"] = {
    "C": "#include <stdarg.h>\n\n// First arg is count\nint sum(int count, ...) {\n    va_list args;\n    va_start(args, count);\n    int total = 0;\n    for (int i = 0; i < count; i++) {\n        total += va_arg(args, int);\n    }\n    va_end(args);\n    return total;\n}",
    "C++": "// C-style variadic macros\n// Better: Variadic templates (C++11)\ntemplate<typename T>\nT sum(T v) { return v; }\n\ntemplate<typename T, typename... Args>\nT sum(T first, Args... args) {\n    return first + sum(args...);\n}\n\n// C++17 Fold expressions\ntemplate<typename... Args>\nauto sum_fold(Args... args) {\n    return (... + args);\n}",
    "Python": "def sum_all(*args):\n    return sum(args)\n\nprint(sum_all(1, 2, 3, 4)) # 10\n\ndef config(**kwargs):\n    for k, v in kwargs.items():\n        print(f\"{k} = {v}\")\n\nconfig(host='localhost', port=8080)",
    "JavaScript": "// Rest parameters\nfunction sumAll(...args) {\n  return args.reduce((a, b) => a + b, 0);\n}\n\nconsole.log(sumAll(1, 2, 3, 4)); // 10\n\n// Older JS used the implicit 'arguments' object\nfunction oldSum() {\n  return Array.from(arguments).reduce((a, b) => a + b, 0);\n}",
    "Java": "// Varargs\npublic int sumAll(int... numbers) {\n    int total = 0;\n    for (int n : numbers) {\n        total += n;\n    }\n    return total;\n}\n\n// Usage\nsumAll(1, 2, 3, 4);",
    "C#": "// Params keyword\npublic int SumAll(params int[] numbers) {\n    int total = 0;\n    foreach (int n in numbers) {\n        total += n;\n    }\n    return total;\n}\n\n// Usage\nSumAll(1, 2, 3, 4);",
    "Go": "// Variadic function\nfunc sumAll(nums ...int) int {\n    total := 0\n    for _, n := range nums {\n        total += n\n    }\n    return total\n}\n\n// Usage\nsumAll(1, 2, 3, 4)\n// Spread slice\nnums := []int{1, 2, 3, 4}\nsumAll(nums...)",
    "Rust": "// Rust does NOT have variadic functions\n// Uses macros (like println!) or slices/Vecs\n\nfn sum_all(nums: &[i32]) -> i32 {\n    nums.iter().sum()\n}\n\n// Usage\nsum_all(&[1, 2, 3, 4]);\n\n// Macro equivalent\nmacro_rules! sum {\n    ( $( $x:expr ),* ) => {\n        { 0 $( + $x )* }\n    };\n}\nlet total = sum!(1, 2, 3, 4);",
    "Ruby": "# Splat operator\ndef sum_all(*numbers)\n  numbers.sum\nend\n\nputs sum_all(1, 2, 3, 4) # 10\n\n# Keyword splat\ndef config(**options)\n  puts options[:host]\nend",
    "Swift": "// Variadic parameters\nfunc sumAll(_ numbers: Int...) -> Int {\n    return numbers.reduce(0, +)\n}\n\nprint(sumAll(1, 2, 3, 4)) // 10"
}
