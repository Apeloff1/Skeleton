"""
╔══════════════════════════════════════════════════════════════════════════╗
║  TRUE ROSETTA STONE — REAL CODE for every concept × every language      ║
║  The world's most comprehensive cross-language syntax reference          ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

def _code(lang, concept_codes):
    return concept_codes.get(lang, f"// {lang}: See documentation")

# Every concept with REAL code in every supported language
ROSETTA = {}

ROSETTA["variables"] = {
    "Python": "x = 42\nname = 'Alice'\npi = 3.14\nis_valid = True",
    "JavaScript": "let x = 42;\nconst name = 'Alice';\nvar pi = 3.14;\nlet isValid = true;",
    "TypeScript": "let x: number = 42;\nconst name: string = 'Alice';\nlet pi: number = 3.14;\nlet isValid: boolean = true;",
    "Java": "int x = 42;\nString name = \"Alice\";\ndouble pi = 3.14;\nboolean isValid = true;",
    "C": "int x = 42;\nconst char* name = \"Alice\";\ndouble pi = 3.14;\nint is_valid = 1;",
    "C++": "int x = 42;\nstd::string name = \"Alice\";\ndouble pi = 3.14;\nbool isValid = true;",
    "C#": "int x = 42;\nstring name = \"Alice\";\ndouble pi = 3.14;\nbool isValid = true;",
    "Go": "x := 42\nname := \"Alice\"\npi := 3.14\nisValid := true",
    "Rust": "let x: i32 = 42;\nlet name = \"Alice\";\nlet pi: f64 = 3.14;\nlet is_valid = true;",
    "Swift": "var x = 42\nlet name = \"Alice\"\nvar pi = 3.14\nvar isValid = true",
    "Kotlin": "var x = 42\nval name = \"Alice\"\nvar pi = 3.14\nvar isValid = true",
    "Ruby": "x = 42\nname = 'Alice'\npi = 3.14\nis_valid = true",
    "PHP": "$x = 42;\n$name = 'Alice';\n$pi = 3.14;\n$isValid = true;",
    "Scala": "var x = 42\nval name = \"Alice\"\nvar pi = 3.14\nvar isValid = true",
    "R": "x <- 42\nname <- 'Alice'\npi <- 3.14\nis_valid <- TRUE",
    "Dart": "int x = 42;\nString name = 'Alice';\ndouble pi = 3.14;\nbool isValid = true;",
    "Perl": "my $x = 42;\nmy $name = 'Alice';\nmy $pi = 3.14;\nmy $is_valid = 1;",
    "Lua": "local x = 42\nlocal name = 'Alice'\nlocal pi = 3.14\nlocal is_valid = true",
    "Haskell": "x = 42\nname = \"Alice\"\npi' = 3.14\nisValid = True",
    "Clojure": "(def x 42)\n(def name \"Alice\")\n(def pi 3.14)\n(def is-valid true)",
    "Elixir": "x = 42\nname = \"Alice\"\npi = 3.14\nis_valid = true",
    "Erlang": "X = 42,\nName = \"Alice\",\nPi = 3.14,\nIsValid = true.",
    "F#": "let x = 42\nlet name = \"Alice\"\nlet pi = 3.14\nlet isValid = true",
    "Julia": "x = 42\nname = \"Alice\"\npi = 3.14\nis_valid = true",
    "Zig": "const x: i32 = 42;\nconst name = \"Alice\";\nconst pi: f64 = 3.14;\nconst is_valid = true;",
    "Nim": "var x = 42\nlet name = \"Alice\"\nvar pi = 3.14\nvar isValid = true",
    "Crystal": "x = 42\nname = \"Alice\"\npi = 3.14\nis_valid = true",
    "OCaml": "let x = 42\nlet name = \"Alice\"\nlet pi = 3.14\nlet is_valid = true",
    "Racket": "(define x 42)\n(define name \"Alice\")\n(define pi 3.14)\n(define is-valid #t)",
    "D": "int x = 42;\nstring name = \"Alice\";\ndouble pi = 3.14;\nbool isValid = true;",
}

ROSETTA["functions"] = {
    "Python": "def add(a, b):\n    return a + b\n\ndef greet(name='World'):\n    return f'Hello, {name}!'",
    "JavaScript": "function add(a, b) {\n  return a + b;\n}\n\nconst greet = (name = 'World') => `Hello, ${name}!`;",
    "TypeScript": "function add(a: number, b: number): number {\n  return a + b;\n}\n\nconst greet = (name: string = 'World'): string => `Hello, ${name}!`;",
    "Java": "static int add(int a, int b) {\n    return a + b;\n}\n\nstatic String greet(String name) {\n    return \"Hello, \" + name + \"!\";\n}",
    "C": "int add(int a, int b) {\n    return a + b;\n}\n\nvoid greet(const char* name) {\n    printf(\"Hello, %s!\\n\", name);\n}",
    "C++": "int add(int a, int b) {\n    return a + b;\n}\n\nstd::string greet(const std::string& name = \"World\") {\n    return \"Hello, \" + name + \"!\";\n}",
    "Go": "func add(a, b int) int {\n    return a + b\n}\n\nfunc greet(name string) string {\n    return \"Hello, \" + name + \"!\"\n}",
    "Rust": "fn add(a: i32, b: i32) -> i32 {\n    a + b\n}\n\nfn greet(name: &str) -> String {\n    format!(\"Hello, {}!\", name)\n}",
    "Swift": "func add(_ a: Int, _ b: Int) -> Int {\n    return a + b\n}\n\nfunc greet(_ name: String = \"World\") -> String {\n    return \"Hello, \\(name)!\"\n}",
    "Kotlin": "fun add(a: Int, b: Int): Int = a + b\n\nfun greet(name: String = \"World\"): String = \"Hello, $name!\"",
    "Ruby": "def add(a, b)\n  a + b\nend\n\ndef greet(name = 'World')\n  \"Hello, #{name}!\"\nend",
    "PHP": "function add($a, $b) {\n    return $a + $b;\n}\n\nfunction greet($name = 'World') {\n    return \"Hello, $name!\";\n}",
    "Scala": "def add(a: Int, b: Int): Int = a + b\n\ndef greet(name: String = \"World\"): String = s\"Hello, $name!\"",
    "Haskell": "add :: Int -> Int -> Int\nadd a b = a + b\n\ngreet :: String -> String\ngreet name = \"Hello, \" ++ name ++ \"!\"",
    "Clojure": "(defn add [a b]\n  (+ a b))\n\n(defn greet [name]\n  (str \"Hello, \" name \"!\"))",
    "Elixir": "def add(a, b), do: a + b\n\ndef greet(name \\\\ \"World\"), do: \"Hello, #{name}!\"",
    "Erlang": "add(A, B) -> A + B.\n\ngreet(Name) -> \"Hello, \" ++ Name ++ \"!\".",
    "Julia": "function add(a, b)\n    a + b\nend\n\ngreet(name=\"World\") = \"Hello, $name!\"",
    "Lua": "function add(a, b)\n    return a + b\nend\n\nfunction greet(name)\n    return \"Hello, \" .. (name or \"World\") .. \"!\"\nend",
    "R": "add <- function(a, b) a + b\n\ngreet <- function(name = 'World') paste0('Hello, ', name, '!')",
    "Dart": "int add(int a, int b) => a + b;\n\nString greet([String name = 'World']) => 'Hello, $name!';",
    "Perl": "sub add { return $_[0] + $_[1]; }\n\nsub greet { return \"Hello, \" . ($_[0] // 'World') . \"!\"; }",
    "Nim": "proc add(a, b: int): int = a + b\n\nproc greet(name = \"World\"): string = \"Hello, \" & name & \"!\"",
    "Crystal": "def add(a, b)\n  a + b\nend\n\ndef greet(name = \"World\")\n  \"Hello, #{name}!\"\nend",
    "OCaml": "let add a b = a + b\n\nlet greet name = \"Hello, \" ^ name ^ \"!\"",
    "F#": "let add a b = a + b\n\nlet greet name = sprintf \"Hello, %s!\" name",
    "Zig": "fn add(a: i32, b: i32) i32 {\n    return a + b;\n}",
    "Racket": "(define (add a b) (+ a b))\n\n(define (greet [name \"World\"]) (string-append \"Hello, \" name \"!\"))",
    "D": "int add(int a, int b) { return a + b; }\n\nstring greet(string name = \"World\") { return \"Hello, \" ~ name ~ \"!\"; }",
}

ROSETTA["loops"] = {
    "Python": "# For loop\nfor i in range(10):\n    print(i)\n\n# While loop\nx = 0\nwhile x < 10:\n    x += 1\n\n# For each\nfor item in [1, 2, 3]:\n    print(item)",
    "JavaScript": "// For loop\nfor (let i = 0; i < 10; i++) {\n  console.log(i);\n}\n\n// While loop\nlet x = 0;\nwhile (x < 10) { x++; }\n\n// For...of\nfor (const item of [1, 2, 3]) {\n  console.log(item);\n}",
    "Go": "// For loop (only loop in Go)\nfor i := 0; i < 10; i++ {\n    fmt.Println(i)\n}\n\n// While-style\nx := 0\nfor x < 10 {\n    x++\n}\n\n// Range\nfor _, item := range []int{1, 2, 3} {\n    fmt.Println(item)\n}",
    "Rust": "// For loop with range\nfor i in 0..10 {\n    println!(\"{}\", i);\n}\n\n// While loop\nlet mut x = 0;\nwhile x < 10 {\n    x += 1;\n}\n\n// Iterator\nfor item in vec![1, 2, 3].iter() {\n    println!(\"{}\", item);\n}",
    "Java": "// For loop\nfor (int i = 0; i < 10; i++) {\n    System.out.println(i);\n}\n\n// While\nint x = 0;\nwhile (x < 10) { x++; }\n\n// For-each\nfor (int item : List.of(1, 2, 3)) {\n    System.out.println(item);\n}",
    "C": "// For loop\nfor (int i = 0; i < 10; i++) {\n    printf(\"%d\\n\", i);\n}\n\n// While loop\nint x = 0;\nwhile (x < 10) { x++; }\n\n// Do-while\ndo { x--; } while (x > 0);",
    "C++": "// Range-based for (C++11)\nfor (auto item : {1, 2, 3}) {\n    std::cout << item << '\\n';\n}\n\n// Traditional for\nfor (int i = 0; i < 10; i++) {}\n\n// While\nint x = 0;\nwhile (x < 10) { x++; }",
    "Swift": "// For-in with range\nfor i in 0..<10 {\n    print(i)\n}\n\n// While\nvar x = 0\nwhile x < 10 { x += 1 }\n\n// For-each\nfor item in [1, 2, 3] {\n    print(item)\n}",
    "Kotlin": "// For with range\nfor (i in 0 until 10) {\n    println(i)\n}\n\n// While\nvar x = 0\nwhile (x < 10) { x++ }\n\n// ForEach\nlistOf(1, 2, 3).forEach { println(it) }",
    "Ruby": "# Times\n10.times { |i| puts i }\n\n# Each\n[1, 2, 3].each { |item| puts item }\n\n# While\nx = 0\nwhile x < 10\n  x += 1\nend\n\n# Until\nuntil x == 0\n  x -= 1\nend",
    "Haskell": "-- Map (no traditional loops)\nmap (\\x -> x * 2) [1..10]\n\n-- List comprehension\n[x * 2 | x <- [1..10]]\n\n-- Recursion\nloop 0 = return ()\nloop n = do putStrLn (show n); loop (n-1)",
    "Elixir": "# Enum.each\nEnum.each(1..10, fn i -> IO.puts(i) end)\n\n# For comprehension\nfor i <- 1..10, do: IO.puts(i)\n\n# Recursion (no while loops)\ndefp loop(0), do: :ok\ndefp loop(n), do: loop(n - 1)",
    "Clojure": ";; doseq\n(doseq [i (range 10)]\n  (println i))\n\n;; loop/recur\n(loop [x 0]\n  (when (< x 10)\n    (recur (inc x))))\n\n;; map\n(map #(* % 2) [1 2 3])",
    "Scala": "// For loop\nfor (i <- 0 until 10) println(i)\n\n// While\nvar x = 0\nwhile (x < 10) { x += 1 }\n\n// ForEach\nList(1, 2, 3).foreach(println)",
    "Julia": "# For loop\nfor i in 1:10\n    println(i)\nend\n\n# While\nx = 0\nwhile x < 10\n    x += 1\nend\n\n# Comprehension\n[x^2 for x in 1:10]",
    "Lua": "-- For loop\nfor i = 0, 9 do\n    print(i)\nend\n\n-- While\nlocal x = 0\nwhile x < 10 do\n    x = x + 1\nend\n\n-- For each (ipairs)\nfor _, v in ipairs({1,2,3}) do\n    print(v)\nend",
    "PHP": "// For loop\nfor ($i = 0; $i < 10; $i++) {\n    echo $i . \"\\n\";\n}\n\n// Foreach\nforeach ([1, 2, 3] as $item) {\n    echo $item . \"\\n\";\n}\n\n// While\n$x = 0;\nwhile ($x < 10) { $x++; }",
    "R": "# For loop\nfor (i in 1:10) {\n  print(i)\n}\n\n# While\nx <- 0\nwhile (x < 10) {\n  x <- x + 1\n}\n\n# Apply family\nsapply(1:10, function(x) x^2)",
    "Dart": "// For loop\nfor (var i = 0; i < 10; i++) {\n  print(i);\n}\n\n// For-in\nfor (var item in [1, 2, 3]) {\n  print(item);\n}\n\n// While\nvar x = 0;\nwhile (x < 10) { x++; }",
    "Perl": "# For loop\nfor my $i (0..9) {\n    print \"$i\\n\";\n}\n\n# While\nmy $x = 0;\nwhile ($x < 10) { $x++; }\n\n# Foreach\nforeach my $item (1, 2, 3) {\n    print \"$item\\n\";\n}",
    "Nim": "# For loop\nfor i in 0..<10:\n  echo i\n\n# While\nvar x = 0\nwhile x < 10:\n  inc x\n\n# For each\nfor item in @[1, 2, 3]:\n  echo item",
    "Crystal": "# Times\n10.times { |i| puts i }\n\n# Each\n[1, 2, 3].each { |item| puts item }\n\n# While\nx = 0\nwhile x < 10\n  x += 1\nend",
    "OCaml": "(* Recursion — no traditional loops *)\nlet rec loop i =\n  if i < 10 then begin\n    Printf.printf \"%d\\n\" i;\n    loop (i + 1)\n  end\n\n(* List.iter *)\nList.iter (fun x -> Printf.printf \"%d\\n\" x) [1; 2; 3]",
    "F#": "// For loop\nfor i in 0..9 do\n    printfn \"%d\" i\n\n// While\nlet mutable x = 0\nwhile x < 10 do\n    x <- x + 1\n\n// List.iter\n[1; 2; 3] |> List.iter (printfn \"%d\")",
    "Erlang": "% Recursion (no loops)\nloop(0) -> ok;\nloop(N) -> io:format(\"~p~n\", [N]), loop(N-1).\n\n% lists:foreach\nlists:foreach(fun(X) -> io:format(\"~p~n\", [X]) end, [1,2,3]).",
    "Zig": "// For loop\nvar i: usize = 0;\nwhile (i < 10) : (i += 1) {\n    std.debug.print(\"{d}\\n\", .{i});\n}\n\n// For each\nfor (items) |item| {\n    std.debug.print(\"{d}\\n\", .{item});\n}",
    "D": "// For loop\nfor (int i = 0; i < 10; i++) {}\n\n// Foreach\nforeach (item; [1, 2, 3]) {\n    writeln(item);\n}\n\n// While\nint x = 0;\nwhile (x < 10) { x++; }",
    "Racket": ";; For loop\n(for ([i (in-range 10)])\n  (displayln i))\n\n;; For/list\n(for/list ([x (in-range 10)]) (* x 2))\n\n;; Recursion\n(define (loop n)\n  (when (> n 0) (displayln n) (loop (- n 1))))",
    "C#": "// For loop\nfor (int i = 0; i < 10; i++) {\n    Console.WriteLine(i);\n}\n\n// Foreach\nforeach (var item in new[] {1, 2, 3}) {\n    Console.WriteLine(item);\n}\n\n// While\nint x = 0;\nwhile (x < 10) { x++; }",
}

ROSETTA["error_handling"] = {
    "Python": "try:\n    result = int('abc')\nexcept ValueError as e:\n    print(f'Error: {e}')\nexcept Exception as e:\n    print(f'Unexpected: {e}')\nfinally:\n    print('Done')\n\n# Custom exception\nclass MyError(Exception):\n    pass\nraise MyError('custom error')",
    "JavaScript": "try {\n  const result = JSON.parse('invalid');\n} catch (e) {\n  console.error('Error:', e.message);\n} finally {\n  console.log('Done');\n}\n\n// Custom error\nclass MyError extends Error {\n  constructor(msg) { super(msg); this.name = 'MyError'; }\n}\nthrow new MyError('custom');",
    "Go": "// Go uses explicit error returns, no exceptions\nresult, err := strconv.Atoi(\"abc\")\nif err != nil {\n    fmt.Println(\"Error:\", err)\n    return\n}\n\n// Custom error\ntype MyError struct {\n    Msg string\n}\nfunc (e *MyError) Error() string { return e.Msg }\n\n// Panic/recover (rare)\ndefer func() {\n    if r := recover(); r != nil {\n        fmt.Println(\"Recovered:\", r)\n    }\n}()\npanic(\"something bad\")",
    "Rust": "// Result type — no exceptions\nfn parse_int(s: &str) -> Result<i32, std::num::ParseIntError> {\n    s.parse::<i32>()\n}\n\nmatch parse_int(\"abc\") {\n    Ok(n) => println!(\"Got: {}\", n),\n    Err(e) => println!(\"Error: {}\", e),\n}\n\n// ? operator for propagation\nfn risky() -> Result<i32, Box<dyn std::error::Error>> {\n    let n = \"42\".parse::<i32>()?;\n    Ok(n)\n}\n\n// Custom error\n#[derive(Debug)]\nstruct MyError(String);\nimpl std::fmt::Display for MyError {\n    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {\n        write!(f, \"{}\", self.0)\n    }\n}",
    "Java": "try {\n    int result = Integer.parseInt(\"abc\");\n} catch (NumberFormatException e) {\n    System.out.println(\"Error: \" + e.getMessage());\n} catch (Exception e) {\n    System.out.println(\"Unexpected: \" + e);\n} finally {\n    System.out.println(\"Done\");\n}\n\n// Custom exception\nclass MyException extends Exception {\n    MyException(String msg) { super(msg); }\n}\nthrow new MyException(\"custom\");",
    "C": "// C has no exceptions — use error codes\nint result;\nerrno = 0;\nresult = strtol(\"abc\", NULL, 10);\nif (errno != 0) {\n    perror(\"Error\");\n}\n\n// Return codes\nint parse(const char* s, int* out) {\n    // return 0 on success, -1 on error\n    return -1;\n}",
    "Swift": "// Swift uses do/try/catch\ndo {\n    let data = try loadFile(\"missing.txt\")\n} catch FileError.notFound {\n    print(\"File not found\")\n} catch {\n    print(\"Error: \\(error)\")\n}\n\n// Optional try\nlet result = try? riskyFunction()\n\n// Custom error\nenum MyError: Error {\n    case invalidInput(String)\n    case networkFailed\n}",
    "Kotlin": "try {\n    val result = \"abc\".toInt()\n} catch (e: NumberFormatException) {\n    println(\"Error: ${e.message}\")\n} finally {\n    println(\"Done\")\n}\n\n// Kotlin has no checked exceptions\n// Custom exception\nclass MyException(msg: String) : Exception(msg)",
    "Haskell": "-- Haskell uses Either/Maybe, not exceptions\nimport Control.Exception\n\n-- Maybe for optional values\nsafeDivide :: Int -> Int -> Maybe Int\nsafeDivide _ 0 = Nothing\nsafeDivide x y = Just (x `div` y)\n\n-- Either for errors\nparseAge :: String -> Either String Int\nparseAge s = case reads s of\n    [(n, \"\")] -> Right n\n    _         -> Left \"Invalid age\"",
    "Elixir": "# Elixir uses pattern matching for errors\ncase File.read(\"file.txt\") do\n  {:ok, content} -> IO.puts(content)\n  {:error, reason} -> IO.puts(\"Error: #{reason}\")\nend\n\n# try/rescue\ntry do\n  raise \"oops\"\nrescue\n  e in RuntimeError -> IO.puts(\"Got: #{e.message}\")\nafter\n  IO.puts(\"Done\")\nend\n\n# Custom exception\ndefmodule MyError do\n  defexception message: \"custom error\"\nend",
    "Ruby": "begin\n  result = Integer('abc')\nrescue ArgumentError => e\n  puts \"Error: #{e.message}\"\nrescue => e\n  puts \"Unexpected: #{e}\"\nensure\n  puts 'Done'\nend\n\n# Custom exception\nclass MyError < StandardError; end\nraise MyError, 'custom error'",
    "Scala": "try {\n  val result = \"abc\".toInt\n} catch {\n  case e: NumberFormatException => println(s\"Error: ${e.getMessage}\")\n  case e: Exception => println(s\"Unexpected: $e\")\n} finally {\n  println(\"Done\")\n}\n\n// Scala also has Try monad\nimport scala.util.{Try, Success, Failure}\nTry(\"abc\".toInt) match {\n  case Success(n) => println(n)\n  case Failure(e) => println(e)\n}",
    "Clojure": ";; try/catch\n(try\n  (Integer/parseInt \"abc\")\n  (catch NumberFormatException e\n    (println \"Error:\" (.getMessage e)))\n  (finally\n    (println \"Done\")))\n\n;; ex-info for custom errors\n(throw (ex-info \"custom error\" {:type :my-error}))",
    "Julia": "# try/catch\ntry\n    parse(Int, \"abc\")\ncatch e\n    if isa(e, ArgumentError)\n        println(\"Error: \", e)\n    else\n        rethrow()\n    end\nfinally\n    println(\"Done\")\nend\n\n# Custom exception\nstruct MyError <: Exception\n    msg::String\nend",
    "PHP": "try {\n    $result = intval('abc');\n    if (!is_numeric('abc')) throw new InvalidArgumentException('Not a number');\n} catch (InvalidArgumentException $e) {\n    echo 'Error: ' . $e->getMessage();\n} catch (Exception $e) {\n    echo 'Unexpected: ' . $e;\n} finally {\n    echo 'Done';\n}\n\n// Custom exception\nclass MyException extends Exception {}",
    "Lua": "-- pcall for protected calls\nlocal ok, err = pcall(function()\n    error('something bad')\nend)\nif not ok then\n    print('Error: ' .. err)\nend\n\n-- xpcall with handler\nxpcall(function()\n    error('oops')\nend, function(err)\n    print('Caught: ' .. err)\nend)",
    "Dart": "try {\n  var result = int.parse('abc');\n} on FormatException catch (e) {\n  print('Error: ${e.message}');\n} catch (e) {\n  print('Unexpected: $e');\n} finally {\n  print('Done');\n}\n\n// Custom exception\nclass MyException implements Exception {\n  final String message;\n  MyException(this.message);\n}",
    "Nim": "try:\n  let x = parseInt(\"abc\")\nexcept ValueError:\n  echo \"Error: invalid number\"\nexcept:\n  echo \"Unexpected error\"\nfinally:\n  echo \"Done\"",
    "Erlang": "% try/catch\ntry\n    list_to_integer(\"abc\")\ncatch\n    error:badarg -> io:format(\"Bad argument~n\");\n    _:Reason -> io:format(\"Error: ~p~n\", [Reason])\nafter\n    io:format(\"Done~n\")\nend.",
    "F#": "try\n    let result = int \"abc\"\n    printfn \"%d\" result\nwith\n| :? System.FormatException as e -> printfn \"Error: %s\" e.Message\n| e -> printfn \"Unexpected: %A\" e",
    "OCaml": "(* OCaml exceptions *)\nexception MyError of string\n\nlet () =\n  try\n    let _ = int_of_string \"abc\" in ()\n  with\n  | Failure msg -> Printf.printf \"Error: %s\\n\" msg\n  | MyError msg -> Printf.printf \"Custom: %s\\n\" msg",
    "Zig": "// Zig uses error unions\nfn parseInt(s: []const u8) !i32 {\n    return std.fmt.parseInt(i32, s, 10);\n}\n\nconst result = parseInt(\"abc\") catch |err| {\n    std.debug.print(\"Error: {}\\n\", .{err});\n    return;\n};\n\n// try keyword\nconst value = try parseInt(\"42\");",
    "Racket": ";; with-handlers\n(with-handlers\n  ([exn:fail? (lambda (e) (displayln (exn-message e)))])\n  (string->number \"abc\"))\n\n;; Custom exception\n(struct my-error exn (data))\n(raise (my-error \"custom\" (current-continuation-marks) 42))",
    "C#": "try {\n    int result = int.Parse(\"abc\");\n} catch (FormatException e) {\n    Console.WriteLine($\"Error: {e.Message}\");\n} catch (Exception e) {\n    Console.WriteLine($\"Unexpected: {e}\");\n} finally {\n    Console.WriteLine(\"Done\");\n}\n\n// Custom exception\nclass MyException : Exception {\n    public MyException(string msg) : base(msg) {}\n}",
    "C++": "try {\n    int result = std::stoi(\"abc\");\n} catch (const std::invalid_argument& e) {\n    std::cerr << \"Error: \" << e.what() << '\\n';\n} catch (const std::exception& e) {\n    std::cerr << \"Unexpected: \" << e.what() << '\\n';\n}\n\n// Custom exception\nclass MyError : public std::runtime_error {\npublic:\n    MyError(const std::string& msg) : std::runtime_error(msg) {}\n};",
    "D": "try {\n    auto n = to!int(\"abc\");\n} catch (ConvException e) {\n    writeln(\"Error: \", e.msg);\n} finally {\n    writeln(\"Done\");\n}",
    "Perl": "# eval/die\neval {\n    die 'something bad';\n};\nif ($@) {\n    print \"Error: $@\\n\";\n}\n\n# Try::Tiny\nuse Try::Tiny;\ntry {\n    die 'oops';\n} catch {\n    print \"Caught: $_\\n\";\n};",
    "R": "tryCatch({\n  result <- as.integer('abc')\n}, warning = function(w) {\n  message('Warning: ', w)\n}, error = function(e) {\n  message('Error: ', e)\n}, finally = {\n  message('Done')\n})",
    "Crystal": "begin\n  result = \"abc\".to_i\nrescue ex : ArgumentError\n  puts \"Error: #{ex.message}\"\nrescue ex\n  puts \"Unexpected: #{ex}\"\nensure\n  puts \"Done\"\nend",
}

ROSETTA["closures"] = {
    "Python": "# Lambda\nadd = lambda x, y: x + y\n\n# Closure\ndef make_counter():\n    count = 0\n    def increment():\n        nonlocal count\n        count += 1\n        return count\n    return increment\n\ncounter = make_counter()\nprint(counter())  # 1\nprint(counter())  # 2",
    "JavaScript": "// Arrow function\nconst add = (x, y) => x + y;\n\n// Closure\nfunction makeCounter() {\n  let count = 0;\n  return () => ++count;\n}\n\nconst counter = makeCounter();\nconsole.log(counter()); // 1\nconsole.log(counter()); // 2",
    "Go": "// Function literal (closure)\nadd := func(x, y int) int { return x + y }\n\n// Closure capturing state\nfunc makeCounter() func() int {\n    count := 0\n    return func() int {\n        count++\n        return count\n    }\n}\n\ncounter := makeCounter()\nfmt.Println(counter()) // 1\nfmt.Println(counter()) // 2",
    "Rust": "// Closure\nlet add = |x, y| x + y;\n\n// Closure capturing mutable state\nlet mut count = 0;\nlet mut counter = || { count += 1; count };\nprintln!(\"{}\", counter()); // 1\nprintln!(\"{}\", counter()); // 2\n\n// Move closure (takes ownership)\nlet name = String::from(\"Alice\");\nlet greet = move || println!(\"Hello, {}!\", name);",
    "Java": "// Lambda\nBiFunction<Integer, Integer, Integer> add = (x, y) -> x + y;\n\n// Effectively-final closure\nfinal int[] count = {0};\nSupplier<Integer> counter = () -> ++count[0];",
    "Swift": "// Closure expression\nlet add = { (x: Int, y: Int) -> Int in x + y }\n\n// Trailing closure\nlet sorted = [3, 1, 2].sorted { $0 < $1 }\n\n// Capturing values\nfunc makeCounter() -> () -> Int {\n    var count = 0\n    return { count += 1; return count }\n}",
    "Kotlin": "// Lambda\nval add = { x: Int, y: Int -> x + y }\n\n// Closure\nfun makeCounter(): () -> Int {\n    var count = 0\n    return { ++count }\n}\n\nval counter = makeCounter()\nprintln(counter()) // 1",
    "Ruby": "# Lambda\nadd = ->(x, y) { x + y }\nadd.call(3, 4) # 7\n\n# Block/Proc closure\ndef make_counter\n  count = 0\n  Proc.new { count += 1; count }\nend\n\ncounter = make_counter\nputs counter.call # 1\nputs counter.call # 2",
    "Haskell": "-- All functions are closures in Haskell\nadd = \\x y -> x + y\n\n-- Partial application (natural closures)\naddFive = add 5\naddFive 3  -- 8\n\n-- Closure via let\nmakeGreeter prefix = \\name -> prefix ++ \", \" ++ name ++ \"!\"\nhello = makeGreeter \"Hello\"\nhello \"Alice\"  -- \"Hello, Alice!\"",
    "Scala": "// Lambda\nval add = (x: Int, y: Int) => x + y\n\n// Closure\ndef makeCounter(): () => Int = {\n  var count = 0\n  () => { count += 1; count }\n}\n\nval counter = makeCounter()\nprintln(counter()) // 1",
    "Elixir": "# Anonymous function\nadd = fn x, y -> x + y end\nadd.(3, 4) # 7\n\n# Capture operator\nadd = &(&1 + &2)\n\n# Closure (Elixir closures are immutable)\ngreeter = fn name -> \"Hello, #{name}!\" end",
    "Clojure": ";; Anonymous function\n(def add (fn [x y] (+ x y)))\n\n;; Short form\n(def add #(+ %1 %2))\n\n;; Closure\n(defn make-counter []\n  (let [count (atom 0)]\n    (fn [] (swap! count inc))))\n\n(def counter (make-counter))\n(counter) ;; 1\n(counter) ;; 2",
    "PHP": "// Arrow function (PHP 7.4+)\n$add = fn($x, $y) => $x + $y;\n\n// Closure with use\n$count = 0;\n$counter = function() use (&$count) {\n    return ++$count;\n};\necho $counter(); // 1\necho $counter(); // 2",
    "Lua": "-- Closure\nfunction makeCounter()\n    local count = 0\n    return function()\n        count = count + 1\n        return count\n    end\nend\n\nlocal counter = makeCounter()\nprint(counter()) -- 1\nprint(counter()) -- 2",
    "Julia": "# Anonymous function\nadd = (x, y) -> x + y\n\n# Closure\nfunction make_counter()\n    count = 0\n    return () -> begin count += 1; count end\nend\n\ncounter = make_counter()\nprintln(counter()) # 1",
    "Dart": "// Lambda\nvar add = (int x, int y) => x + y;\n\n// Closure\nFunction makeCounter() {\n  var count = 0;\n  return () => ++count;\n}\n\nvar counter = makeCounter();\nprint(counter()); // 1",
    "Nim": "# Closure\nproc makeCounter(): proc(): int =\n  var count = 0\n  return proc(): int =\n    inc count\n    return count\n\nlet counter = makeCounter()\necho counter() # 1",
    "Crystal": "# Proc (closure)\nadd = ->(x : Int32, y : Int32) { x + y }\n\n# Closure capturing state\ndef make_counter\n  count = 0\n  ->{ count += 1; count }\nend\n\ncounter = make_counter\nputs counter.call # 1",
    "OCaml": "(* Closure *)\nlet add = fun x y -> x + y\n\n(* Closure capturing state via ref *)\nlet make_counter () =\n  let count = ref 0 in\n  fun () -> incr count; !count\n\nlet counter = make_counter ()\nlet _ = counter ()  (* 1 *)",
    "F#": "// Lambda\nlet add = fun x y -> x + y\n\n// Closure\nlet makeCounter () =\n    let mutable count = 0\n    fun () -> count <- count + 1; count\n\nlet counter = makeCounter()\ncounter() |> printfn \"%d\" // 1",
    "Erlang": "% Fun (anonymous function)\nAdd = fun(X, Y) -> X + Y end,\nAdd(3, 4). % 7\n\n% Closure\n% Erlang closures are immutable\nGreeter = fun(Prefix) ->\n    fun(Name) -> Prefix ++ \", \" ++ Name ++ \"!\" end\nend,\nHello = Greeter(\"Hello\"),\nHello(\"Alice\"). % \"Hello, Alice!\"",
    "Zig": "// Zig has limited closure support\n// Use struct with state instead\nconst Counter = struct {\n    count: u32 = 0,\n    fn next(self: *Counter) u32 {\n        self.count += 1;\n        return self.count;\n    }\n};",
    "Racket": ";; Lambda\n(define add (lambda (x y) (+ x y)))\n\n;; Closure\n(define (make-counter)\n  (define count 0)\n  (lambda ()\n    (set! count (add1 count))\n    count))\n\n(define counter (make-counter))\n(counter) ;; 1\n(counter) ;; 2",
    "C#": "// Lambda\nFunc<int, int, int> add = (x, y) => x + y;\n\n// Closure\nFunc<int> MakeCounter() {\n    int count = 0;\n    return () => ++count;\n}\n\nvar counter = MakeCounter();\nConsole.WriteLine(counter()); // 1",
    "C++": "// Lambda (C++11)\nauto add = [](int x, int y) { return x + y; };\n\n// Closure capturing by reference\nint count = 0;\nauto counter = [&count]() { return ++count; };\nstd::cout << counter() << '\\n'; // 1\nstd::cout << counter() << '\\n'; // 2\n\n// Mutable lambda\nauto counter2 = [count = 0]() mutable { return ++count; };",
    "D": "// Lambda\nauto add = (int x, int y) => x + y;\n\n// Delegate (closure)\nauto makeCounter() {\n    int count = 0;\n    return () => ++count;\n}\nauto counter = makeCounter();\nwriteln(counter()); // 1",
    "Perl": "# Closure\nsub make_counter {\n    my $count = 0;\n    return sub { ++$count };\n}\n\nmy $counter = make_counter();\nprint $counter->(); # 1\nprint $counter->(); # 2",
    "R": "# Closure\nmake_counter <- function() {\n  count <- 0\n  function() {\n    count <<- count + 1\n    count\n  }\n}\n\ncounter <- make_counter()\ncounter() # 1\ncounter() # 2",
    "TypeScript": "// Arrow function\nconst add = (x: number, y: number): number => x + y;\n\n// Closure\nfunction makeCounter(): () => number {\n  let count = 0;\n  return () => ++count;\n}\n\nconst counter = makeCounter();\nconsole.log(counter()); // 1",
    "C": "// C doesn't have closures natively\n// Simulate with function pointers + context\ntypedef struct {\n    int count;\n} Counter;\n\nint counter_next(Counter* c) {\n    return ++c->count;\n}\n\nCounter c = {0};\nprintf(\"%d\\n\", counter_next(&c)); // 1",
}

ROSETTA["async_await"] = {
    "Python": "import asyncio\n\nasync def fetch_data(url):\n    await asyncio.sleep(1)  # Simulate network\n    return f'Data from {url}'\n\nasync def main():\n    # Sequential\n    data = await fetch_data('https://api.example.com')\n    \n    # Parallel\n    results = await asyncio.gather(\n        fetch_data('url1'),\n        fetch_data('url2'),\n        fetch_data('url3'),\n    )\n    print(results)\n\nasyncio.run(main())",
    "JavaScript": "async function fetchData(url) {\n  const response = await fetch(url);\n  return await response.json();\n}\n\n// Parallel execution\nasync function main() {\n  const [a, b, c] = await Promise.all([\n    fetchData('url1'),\n    fetchData('url2'),\n    fetchData('url3'),\n  ]);\n}\n\n// Error handling\ntry {\n  const data = await fetchData('url');\n} catch (err) {\n  console.error(err);\n}",
    "Go": "// Go uses goroutines + channels instead of async/await\nfunc fetchData(url string, ch chan<- string) {\n    resp, err := http.Get(url)\n    if err != nil {\n        ch <- \"\"\n        return\n    }\n    defer resp.Body.Close()\n    body, _ := io.ReadAll(resp.Body)\n    ch <- string(body)\n}\n\n// Parallel\nch := make(chan string, 3)\ngo fetchData(\"url1\", ch)\ngo fetchData(\"url2\", ch)\ngo fetchData(\"url3\", ch)\n\nfor i := 0; i < 3; i++ {\n    fmt.Println(<-ch)\n}",
    "Rust": "// Using tokio runtime\nuse tokio;\n\nasync fn fetch_data(url: &str) -> Result<String, reqwest::Error> {\n    let resp = reqwest::get(url).await?;\n    resp.text().await\n}\n\n#[tokio::main]\nasync fn main() {\n    // Sequential\n    let data = fetch_data(\"url\").await.unwrap();\n    \n    // Parallel with join!\n    let (a, b, c) = tokio::join!(\n        fetch_data(\"url1\"),\n        fetch_data(\"url2\"),\n        fetch_data(\"url3\"),\n    );\n}",
    "Swift": "// Swift async/await (Swift 5.5+)\nfunc fetchData(from url: URL) async throws -> Data {\n    let (data, _) = try await URLSession.shared.data(from: url)\n    return data\n}\n\n// Parallel with async let\nasync {\n    async let a = fetchData(from: url1)\n    async let b = fetchData(from: url2)\n    let results = try await [a, b]\n}",
    "Kotlin": "// Coroutines\nimport kotlinx.coroutines.*\n\nsuspend fun fetchData(url: String): String {\n    delay(1000) // Simulate network\n    return \"Data from $url\"\n}\n\nfun main() = runBlocking {\n    // Parallel\n    val deferred1 = async { fetchData(\"url1\") }\n    val deferred2 = async { fetchData(\"url2\") }\n    val results = awaitAll(deferred1, deferred2)\n    println(results)\n}",
    "C#": "async Task<string> FetchDataAsync(string url) {\n    using var client = new HttpClient();\n    return await client.GetStringAsync(url);\n}\n\n// Parallel\nvar tasks = new[] {\n    FetchDataAsync(\"url1\"),\n    FetchDataAsync(\"url2\"),\n    FetchDataAsync(\"url3\"),\n};\nvar results = await Task.WhenAll(tasks);",
    "Java": "// CompletableFuture\nCompletableFuture<String> fetchData(String url) {\n    return CompletableFuture.supplyAsync(() -> {\n        // HTTP call...\n        return \"data\";\n    });\n}\n\n// Parallel\nCompletableFuture.allOf(\n    fetchData(\"url1\"),\n    fetchData(\"url2\")\n).join();\n\n// Virtual threads (Java 21)\nThread.startVirtualThread(() -> {\n    var data = fetchData(\"url\").join();\n});",
    "Dart": "Future<String> fetchData(String url) async {\n  final response = await http.get(Uri.parse(url));\n  return response.body;\n}\n\nvoid main() async {\n  // Sequential\n  final data = await fetchData('url');\n  \n  // Parallel\n  final results = await Future.wait([\n    fetchData('url1'),\n    fetchData('url2'),\n  ]);\n}",
    "Elixir": "# Elixir uses Task for async\ntask1 = Task.async(fn -> fetch_data(\"url1\") end)\ntask2 = Task.async(fn -> fetch_data(\"url2\") end)\n\n# Await results\nresult1 = Task.await(task1)\nresult2 = Task.await(task2)\n\n# Or use Task.async_stream for parallel\nurls\n|> Task.async_stream(fn url -> fetch_data(url) end)\n|> Enum.to_list()",
    "Scala": "import scala.concurrent.Future\nimport scala.concurrent.ExecutionContext.Implicits.global\n\ndef fetchData(url: String): Future[String] = Future {\n  // HTTP call...\n  s\"Data from $url\"\n}\n\n// Parallel\nval futures = List(\"url1\", \"url2\").map(fetchData)\nval results = Future.sequence(futures)\n\n// For comprehension\nfor {\n  a <- fetchData(\"url1\")\n  b <- fetchData(\"url2\")\n} yield (a, b)",
    "Haskell": "import Control.Concurrent.Async\n\nfetchData :: String -> IO String\nfetchData url = do\n    threadDelay 1000000\n    return $ \"Data from \" ++ url\n\nmain :: IO ()\nmain = do\n    -- Parallel\n    (a, b) <- concurrently\n        (fetchData \"url1\")\n        (fetchData \"url2\")\n    putStrLn $ a ++ \" \" ++ b",
    "TypeScript": "async function fetchData(url: string): Promise<string> {\n  const res = await fetch(url);\n  return await res.text();\n}\n\n// Parallel with proper typing\nconst [a, b]: [string, string] = await Promise.all([\n  fetchData('url1'),\n  fetchData('url2'),\n]);",
    "Ruby": "# Ruby async with Async gem or Ractor\nrequire 'async'\n\nAsync do\n  internet = Async::HTTP::Internet.new\n  \n  # Parallel\n  task1 = Async { internet.get('url1') }\n  task2 = Async { internet.get('url2') }\n  \n  puts task1.wait.read\n  puts task2.wait.read\nend",
    "PHP": "// PHP 8.1+ Fibers\n$fiber = new Fiber(function (): void {\n    $value = Fiber::suspend('fiber');\n    echo \"Resumed with: $value\\n\";\n});\n\n$value = $fiber->start();\n$fiber->resume('hello');\n\n// Parallel with amphp\nuse function Amp\\\\async;\nuse function Amp\\\\Future\\\\await;\n\n$futures = [\n    async(fn() => fetchData('url1')),\n    async(fn() => fetchData('url2')),\n];\n$results = await($futures);",
}

ROSETTA["pattern_matching"] = {
    "Python": "# Match statement (3.10+)\nmatch command:\n    case 'quit':\n        exit()\n    case 'hello' | 'hi':\n        print('Hello!')\n    case ['go', direction]:\n        move(direction)\n    case {'action': action, 'target': target}:\n        perform(action, target)\n    case _:\n        print('Unknown')",
    "Rust": "match value {\n    0 => println!(\"zero\"),\n    1..=9 => println!(\"single digit\"),\n    n if n < 0 => println!(\"negative: {}\", n),\n    _ => println!(\"other\"),\n}\n\n// Destructuring\nmatch point {\n    (0, 0) => println!(\"origin\"),\n    (x, 0) => println!(\"on x-axis at {}\", x),\n    (0, y) => println!(\"on y-axis at {}\", y),\n    (x, y) => println!(\"at ({}, {})\", x, y),\n}\n\n// Enum matching\nmatch result {\n    Ok(value) => println!(\"Got: {}\", value),\n    Err(e) => eprintln!(\"Error: {}\", e),\n}",
    "Haskell": "-- Pattern matching on values\ndescribe :: Int -> String\ndescribe 0 = \"zero\"\ndescribe 1 = \"one\"\ndescribe n\n    | n < 0     = \"negative\"\n    | n < 10    = \"single digit\"\n    | otherwise = \"big\"\n\n-- Pattern matching on types\nhead' :: [a] -> Maybe a\nhead' []    = Nothing\nhead' (x:_) = Just x\n\n-- Case expression\nresult = case maybeValue of\n    Just x  -> show x\n    Nothing -> \"empty\"",
    "Scala": "value match {\n  case 0 => \"zero\"\n  case n if n < 0 => s\"negative: $n\"\n  case 1 | 2 | 3 => \"small\"\n  case _ => \"other\"\n}\n\n// Sealed trait matching\nsealed trait Shape\ncase class Circle(r: Double) extends Shape\ncase class Rect(w: Double, h: Double) extends Shape\n\ndef area(s: Shape): Double = s match {\n  case Circle(r) => math.Pi * r * r\n  case Rect(w, h) => w * h\n}",
    "Elixir": "case value do\n  0 -> \"zero\"\n  n when n < 0 -> \"negative\"\n  n when n < 10 -> \"small\"\n  _ -> \"other\"\nend\n\n# Function clause matching\ndef describe(0), do: \"zero\"\ndef describe(n) when n < 0, do: \"negative\"\ndef describe(_), do: \"other\"\n\n# Destructuring\n{:ok, value} = {:ok, 42}\n[head | tail] = [1, 2, 3]",
    "Swift": "switch value {\ncase 0:\n    print(\"zero\")\ncase 1...9:\n    print(\"single digit\")\ncase let n where n < 0:\n    print(\"negative: \\(n)\")\ndefault:\n    print(\"other\")\n}\n\n// Enum matching\nenum Result {\n    case success(Int)\n    case failure(String)\n}\n\nswitch result {\ncase .success(let value):\n    print(\"Got: \\(value)\")\ncase .failure(let error):\n    print(\"Error: \\(error)\")\n}",
    "Kotlin": "when (value) {\n    0 -> println(\"zero\")\n    in 1..9 -> println(\"single digit\")\n    is String -> println(\"string: $value\")\n    else -> println(\"other\")\n}\n\n// Sealed class matching\nsealed class Result\ndata class Success(val value: Int) : Result()\ndata class Failure(val error: String) : Result()\n\nwhen (result) {\n    is Success -> println(result.value)\n    is Failure -> println(result.error)\n}",
    "OCaml": "match value with\n| 0 -> \"zero\"\n| n when n < 0 -> \"negative\"\n| 1 | 2 | 3 -> \"small\"\n| _ -> \"other\"\n\n(* Variant matching *)\ntype shape = Circle of float | Rect of float * float\n\nlet area = function\n  | Circle r -> Float.pi *. r *. r\n  | Rect (w, h) -> w *. h",
    "F#": "match value with\n| 0 -> \"zero\"\n| n when n < 0 -> \"negative\"\n| 1 | 2 | 3 -> \"small\"\n| _ -> \"other\"\n\n// Active patterns\nlet (|Even|Odd|) n = if n % 2 = 0 then Even else Odd\n\nmatch 42 with\n| Even -> \"even\"\n| Odd -> \"odd\"",
    "Erlang": "case Value of\n    0 -> \"zero\";\n    N when N < 0 -> \"negative\";\n    N when N < 10 -> \"small\";\n    _ -> \"other\"\nend.\n\n% Function clause matching\ndescribe(0) -> \"zero\";\ndescribe(N) when N < 0 -> \"negative\";\ndescribe(_) -> \"other\".",
    "Clojure": ";; core.match\n(require '[clojure.core.match :refer [match]])\n\n(match [value]\n  [0] \"zero\"\n  [(_ :guard neg?)] \"negative\"\n  [_] \"other\")\n\n;; Multimethods\n(defmulti describe type)\n(defmethod describe Long [n] (str n))\n(defmethod describe String [s] (str \"string: \" s))",
    "Julia": "# Multiple dispatch (Julia's pattern matching)\nfunction describe(x::Int)\n    if x == 0 \"zero\"\n    elseif x < 0 \"negative\"\n    else \"positive\"\n    end\nend\n\ndescribe(x::String) = \"string: $x\"\ndescribe(x::Float64) = \"float: $x\"",
    "Ruby": "case value\nwhen 0\n  'zero'\nwhen 1..9\n  'single digit'\nwhen Integer\n  value < 0 ? 'negative' : 'big'\nwhen String\n  \"string: #{value}\"\nelse\n  'other'\nend\n\n# Pattern matching (Ruby 3.0+)\ncase [1, 2, 3]\nin [Integer => a, Integer => b, *]\n  puts \"a=#{a}, b=#{b}\"\nend",
    "C#": "var result = value switch {\n    0 => \"zero\",\n    < 0 => \"negative\",\n    > 0 and < 10 => \"small\",\n    _ => \"other\",\n};\n\n// Type pattern\nstring Describe(object obj) => obj switch {\n    int n when n > 0 => $\"positive: {n}\",\n    string s => $\"string: {s}\",\n    null => \"null\",\n    _ => \"unknown\",\n};",
    "Dart": "// Switch with patterns (Dart 3.0+)\nswitch (value) {\n  case 0:\n    print('zero');\n  case < 0:\n    print('negative');\n  case final n when n < 10:\n    print('small: $n');\n  default:\n    print('other');\n}\n\n// Destructuring\nvar (a, b) = (1, 2);",
    "Zig": "// Switch\nconst result = switch (value) {\n    0 => \"zero\",\n    1...9 => \"small\",\n    else => \"other\",\n};",
    "Nim": "case value\nof 0: echo \"zero\"\nof 1..9: echo \"small\"\nelse: echo \"other\"",
    "Racket": "(match value\n  [0 \"zero\"]\n  [(? negative?) \"negative\"]\n  [(list a b c) (format \"list: ~a ~a ~a\" a b c)]\n  [_ \"other\"])",
    "Go": "// Go doesn't have pattern matching\n// Use switch statement\nswitch {\ncase value == 0:\n    fmt.Println(\"zero\")\ncase value < 0:\n    fmt.Println(\"negative\")\ncase value < 10:\n    fmt.Println(\"small\")\ndefault:\n    fmt.Println(\"other\")\n}\n\n// Type switch\nswitch v := value.(type) {\ncase int:\n    fmt.Println(\"int:\", v)\ncase string:\n    fmt.Println(\"string:\", v)\n}",
    "JavaScript": "// No native pattern matching (TC39 proposal)\n// Use switch or if/else\nswitch (true) {\n  case value === 0: console.log('zero'); break;\n  case value < 0: console.log('negative'); break;\n  default: console.log('other');\n}\n\n// Destructuring (closest to pattern matching)\nconst { name, age } = person;\nconst [first, ...rest] = array;",
    "TypeScript": "// Discriminated union matching\ntype Shape = \n  | { kind: 'circle'; radius: number }\n  | { kind: 'rect'; width: number; height: number };\n\nfunction area(s: Shape): number {\n  switch (s.kind) {\n    case 'circle': return Math.PI * s.radius ** 2;\n    case 'rect': return s.width * s.height;\n  }\n}",
    "Java": "// Pattern matching (Java 21+)\nString result = switch (obj) {\n    case Integer i when i > 0 -> \"positive: \" + i;\n    case String s -> \"string: \" + s;\n    case null -> \"null\";\n    default -> \"unknown\";\n};\n\n// Record patterns\nrecord Point(int x, int y) {}\nif (obj instanceof Point(int x, int y)) {\n    System.out.println(x + \", \" + y);\n}",
    "C": "// C has no pattern matching — use switch/if\nswitch (value) {\n    case 0: printf(\"zero\\n\"); break;\n    case 1: case 2: case 3: printf(\"small\\n\"); break;\n    default: printf(\"other\\n\"); break;\n}",
    "C++": "// C++ has no native pattern matching\n// Use std::visit with std::variant (C++17)\nstd::visit([](auto&& arg) {\n    using T = std::decay_t<decltype(arg)>;\n    if constexpr (std::is_same_v<T, int>)\n        std::cout << \"int: \" << arg;\n    else if constexpr (std::is_same_v<T, std::string>)\n        std::cout << \"string: \" << arg;\n}, myVariant);",
    "Lua": "-- Lua has no pattern matching — use if/elseif\nif value == 0 then\n    print('zero')\nelseif value < 0 then\n    print('negative')\nelse\n    print('other')\nend",
    "Perl": "# given/when (experimental)\nuse feature 'switch';\ngiven ($value) {\n    when (0) { say 'zero' }\n    when ($_ < 0) { say 'negative' }\n    default { say 'other' }\n}",
    "R": "# switch\nresult <- switch(as.character(value),\n  '0' = 'zero',\n  'other'\n)",
    "PHP": "// match expression (PHP 8.0+)\n$result = match(true) {\n    $value === 0 => 'zero',\n    $value < 0 => 'negative',\n    $value < 10 => 'small',\n    default => 'other',\n};",
    "Crystal": "case value\nwhen 0\n  \"zero\"\nwhen .negative?\n  \"negative\"\nwhen 1..9\n  \"small\"\nelse\n  \"other\"\nend",
    "D": "switch (value) {\n    case 0: writeln(\"zero\"); break;\n    default: writeln(\"other\"); break;\n}",
}

ROSETTA["conditionals"] = {
    "Python": "if x > 0:\n    print('positive')\nelif x == 0:\n    print('zero')\nelse:\n    print('negative')\n\n# Ternary\nresult = 'yes' if x > 0 else 'no'\n\n# Match (3.10+)\nmatch status:\n    case 200: print('OK')\n    case 404: print('Not Found')\n    case _: print('Unknown')",
    "JavaScript": "if (x > 0) {\n  console.log('positive');\n} else if (x === 0) {\n  console.log('zero');\n} else {\n  console.log('negative');\n}\n\n// Ternary\nconst result = x > 0 ? 'yes' : 'no';\n\n// Nullish coalescing\nconst name = user?.name ?? 'Anonymous';",
    "Go": "if x > 0 {\n    fmt.Println(\"positive\")\n} else if x == 0 {\n    fmt.Println(\"zero\")\n} else {\n    fmt.Println(\"negative\")\n}\n\n// Switch (no fallthrough by default)\nswitch {\ncase x > 0:\n    fmt.Println(\"positive\")\ncase x == 0:\n    fmt.Println(\"zero\")\ndefault:\n    fmt.Println(\"negative\")\n}\n\n// Type switch\nswitch v := i.(type) {\ncase int:\n    fmt.Println(\"int\")\ncase string:\n    fmt.Println(\"string\")\n}",
    "Rust": "if x > 0 {\n    println!(\"positive\");\n} else if x == 0 {\n    println!(\"zero\");\n} else {\n    println!(\"negative\");\n}\n\n// if as expression\nlet label = if x > 0 { \"positive\" } else { \"negative\" };\n\n// match\nlet msg = match x {\n    0 => \"zero\",\n    1..=9 => \"single digit\",\n    _ => \"other\",\n};",
    "Java": "if (x > 0) {\n    System.out.println(\"positive\");\n} else if (x == 0) {\n    System.out.println(\"zero\");\n} else {\n    System.out.println(\"negative\");\n}\n\n// Switch expression (Java 14+)\nString result = switch (x) {\n    case 0 -> \"zero\";\n    case 1, 2, 3 -> \"small\";\n    default -> \"other\";\n};",
    "C": "if (x > 0) {\n    printf(\"positive\\n\");\n} else if (x == 0) {\n    printf(\"zero\\n\");\n} else {\n    printf(\"negative\\n\");\n}\n\n// Ternary\nconst char* result = x > 0 ? \"yes\" : \"no\";\n\n// Switch\nswitch (x) {\n    case 0: printf(\"zero\\n\"); break;\n    case 1: printf(\"one\\n\"); break;\n    default: printf(\"other\\n\");\n}",
    "C++": "if (x > 0) {\n    std::cout << \"positive\\n\";\n} else {\n    std::cout << \"non-positive\\n\";\n}\n\n// If with initializer (C++17)\nif (auto it = map.find(key); it != map.end()) {\n    std::cout << it->second;\n}\n\n// Constexpr if (compile-time)\nif constexpr (std::is_integral_v<T>) {\n    // integer-only code\n}",
    "Swift": "if x > 0 {\n    print(\"positive\")\n} else if x == 0 {\n    print(\"zero\")\n} else {\n    print(\"negative\")\n}\n\n// Switch (exhaustive required)\nswitch x {\ncase 0:\n    print(\"zero\")\ncase 1...9:\n    print(\"small\")\ncase let n where n < 0:\n    print(\"negative: \\(n)\")\ndefault:\n    print(\"other\")\n}\n\n// Guard\nguard let name = optionalName else { return }",
    "Kotlin": "if (x > 0) {\n    println(\"positive\")\n} else {\n    println(\"non-positive\")\n}\n\n// When (Kotlin's switch)\nwhen (x) {\n    0 -> println(\"zero\")\n    in 1..9 -> println(\"small\")\n    is String -> println(\"string\")\n    else -> println(\"other\")\n}\n\n// When as expression\nval label = when {\n    x > 0 -> \"positive\"\n    x == 0 -> \"zero\"\n    else -> \"negative\"\n}",
    "Ruby": "if x > 0\n  puts 'positive'\nelsif x == 0\n  puts 'zero'\nelse\n  puts 'negative'\nend\n\n# One-liner\nputs 'positive' if x > 0\nputs 'negative' unless x > 0\n\n# Case\ncase x\nwhen 0 then 'zero'\nwhen 1..9 then 'small'\nwhen Integer then x < 0 ? 'neg' : 'big'\nelse 'other'\nend",
    "Haskell": "-- Guards\ndescribe x\n    | x > 0     = \"positive\"\n    | x == 0    = \"zero\"\n    | otherwise = \"negative\"\n\n-- Case expression\nresult = case x of\n    0 -> \"zero\"\n    1 -> \"one\"\n    _ -> \"other\"\n\n-- If expression\nlet label = if x > 0 then \"positive\" else \"negative\"",
    "Elixir": "cond do\n  x > 0  -> \"positive\"\n  x == 0 -> \"zero\"\n  true   -> \"negative\"\nend\n\n# Case\ncase x do\n  0 -> \"zero\"\n  n when n > 0 -> \"positive\"\n  _ -> \"negative\"\nend\n\n# If/unless\nif x > 0, do: \"positive\", else: \"negative\"\nunless x == 0, do: \"non-zero\"",
    "Scala": "if (x > 0) println(\"positive\")\nelse if (x == 0) println(\"zero\")\nelse println(\"negative\")\n\n// Match expression\nval result = x match {\n  case 0 => \"zero\"\n  case n if n > 0 => \"positive\"\n  case _ => \"negative\"\n}",
    "Clojure": "(if (> x 0)\n  \"positive\"\n  \"non-positive\")\n\n(cond\n  (> x 0) \"positive\"\n  (= x 0) \"zero\"\n  :else   \"negative\")\n\n(when (> x 0)\n  (println \"positive\"))",
    "PHP": "if ($x > 0) {\n    echo 'positive';\n} elseif ($x === 0) {\n    echo 'zero';\n} else {\n    echo 'negative';\n}\n\n// Match (PHP 8.0+)\n$result = match(true) {\n    $x > 0 => 'positive',\n    $x === 0 => 'zero',\n    default => 'negative',\n};\n\n// Null coalescing\n$name = $user?->name ?? 'Anonymous';",
    "Lua": "if x > 0 then\n    print('positive')\nelseif x == 0 then\n    print('zero')\nelse\n    print('negative')\nend\n\n-- Ternary idiom\nlocal result = x > 0 and 'yes' or 'no'",
    "Julia": "if x > 0\n    println(\"positive\")\nelseif x == 0\n    println(\"zero\")\nelse\n    println(\"negative\")\nend\n\n# Ternary\nresult = x > 0 ? \"positive\" : \"negative\"",
    "TypeScript": "if (x > 0) {\n  console.log('positive');\n} else {\n  console.log('non-positive');\n}\n\n// Type narrowing\nif (typeof value === 'string') {\n  console.log(value.toUpperCase());\n}\n\n// Satisfies + switch\ntype Status = 'active' | 'inactive';\nswitch (status) {\n  case 'active': break;\n  case 'inactive': break;\n}",
    "Dart": "if (x > 0) {\n  print('positive');\n} else if (x == 0) {\n  print('zero');\n} else {\n  print('negative');\n}\n\n// Switch with patterns (Dart 3.0+)\nswitch (x) {\n  case == 0: print('zero');\n  case > 0: print('positive');\n  default: print('negative');\n}",
    "Nim": "if x > 0:\n  echo \"positive\"\nelif x == 0:\n  echo \"zero\"\nelse:\n  echo \"negative\"\n\n# Case\ncase x\nof 0: echo \"zero\"\nof 1..9: echo \"small\"\nelse: echo \"other\"",
    "Crystal": "if x > 0\n  puts \"positive\"\nelsif x == 0\n  puts \"zero\"\nelse\n  puts \"negative\"\nend\n\ncase x\nwhen 0 then \"zero\"\nwhen .negative? then \"negative\"\nwhen 1..9 then \"small\"\nelse \"other\"\nend",
    "OCaml": "if x > 0 then\n  print_endline \"positive\"\nelse if x = 0 then\n  print_endline \"zero\"\nelse\n  print_endline \"negative\"\n\n(* Match *)\nmatch x with\n| 0 -> \"zero\"\n| n when n > 0 -> \"positive\"\n| _ -> \"negative\"",
    "F#": "if x > 0 then\n    printfn \"positive\"\nelif x = 0 then\n    printfn \"zero\"\nelse\n    printfn \"negative\"\n\n// Match\nmatch x with\n| 0 -> \"zero\"\n| n when n > 0 -> \"positive\"\n| _ -> \"negative\"\n\n// Active patterns\nlet (|Even|Odd|) n = if n % 2 = 0 then Even else Odd",
    "Erlang": "case X of\n    0 -> \"zero\";\n    N when N > 0 -> \"positive\";\n    _ -> \"negative\"\nend.\n\nif\n    X > 0 -> \"positive\";\n    X =:= 0 -> \"zero\";\n    true -> \"negative\"\nend.",
    "R": "if (x > 0) {\n  print('positive')\n} else if (x == 0) {\n  print('zero')\n} else {\n  print('negative')\n}\n\n# ifelse (vectorized)\nresult <- ifelse(x > 0, 'positive', 'negative')\n\n# switch\nswitch(as.character(x), '0'='zero', 'other')",
    "Perl": "if ($x > 0) {\n    say 'positive';\n} elsif ($x == 0) {\n    say 'zero';\n} else {\n    say 'negative';\n}\n\n# Postfix\nsay 'positive' if $x > 0;\nsay 'negative' unless $x > 0;\n\n# Ternary\nmy $result = $x > 0 ? 'yes' : 'no';",
    "Zig": "if (x > 0) {\n    std.debug.print(\"positive\\n\", .{});\n} else if (x == 0) {\n    std.debug.print(\"zero\\n\", .{});\n} else {\n    std.debug.print(\"negative\\n\", .{});\n}\n\n// Switch\nconst result = switch (x) {\n    0 => \"zero\",\n    1...9 => \"small\",\n    else => \"other\",\n};",
    "Racket": "(if (> x 0)\n    (displayln \"positive\")\n    (displayln \"non-positive\"))\n\n(cond\n  [(> x 0) \"positive\"]\n  [(= x 0) \"zero\"]\n  [else    \"negative\"])\n\n(when (> x 0)\n  (displayln \"positive\"))",
    "D": "if (x > 0) {\n    writeln(\"positive\");\n} else if (x == 0) {\n    writeln(\"zero\");\n} else {\n    writeln(\"negative\");\n}\n\n// Ternary\nauto result = x > 0 ? \"yes\" : \"no\";",
    "C#": "if (x > 0)\n    Console.WriteLine(\"positive\");\nelse if (x == 0)\n    Console.WriteLine(\"zero\");\nelse\n    Console.WriteLine(\"negative\");\n\n// Switch expression (C# 8+)\nvar result = x switch {\n    > 0 => \"positive\",\n    0 => \"zero\",\n    _ => \"negative\",\n};\n\n// Pattern matching\nif (obj is string s && s.Length > 0) {\n    Console.WriteLine(s);\n}",
}

ROSETTA["arrays"] = {
    "Python": "# List\nnums = [1, 2, 3, 4, 5]\nnums.append(6)\nnums.extend([7, 8])\nsliced = nums[1:4]  # [2, 3, 4]\n\n# List comprehension\nsquares = [x**2 for x in range(10)]\nevens = [x for x in nums if x % 2 == 0]\n\n# Tuple (immutable)\npoint = (10, 20)\n\n# Set\nunique = {1, 2, 3, 2, 1}  # {1, 2, 3}\n\n# Dict\ndata = {'a': 1, 'b': 2}\ndata['c'] = 3",
    "JavaScript": "const nums = [1, 2, 3, 4, 5];\nnums.push(6);\nnums.unshift(0);\nconst sliced = nums.slice(1, 4);\n\n// Array methods\nconst doubled = nums.map(x => x * 2);\nconst evens = nums.filter(x => x % 2 === 0);\nconst sum = nums.reduce((a, b) => a + b, 0);\n\n// Spread\nconst merged = [...nums, ...other];\n\n// Destructuring\nconst [first, second, ...rest] = nums;",
    "Go": "// Slice\nnums := []int{1, 2, 3, 4, 5}\nnums = append(nums, 6, 7)\nsliced := nums[1:4] // [2, 3, 4]\n\n// Array (fixed size)\narr := [5]int{1, 2, 3, 4, 5}\n\n// Map\nm := map[string]int{\n    \"a\": 1,\n    \"b\": 2,\n}\nm[\"c\"] = 3\ndelete(m, \"a\")\n\n// Check existence\nif val, ok := m[\"b\"]; ok {\n    fmt.Println(val)\n}",
    "Rust": "// Vec\nlet mut nums = vec![1, 2, 3, 4, 5];\nnums.push(6);\nlet sliced = &nums[1..4]; // [2, 3, 4]\n\n// Array (fixed)\nlet arr: [i32; 5] = [1, 2, 3, 4, 5];\n\n// Iterator chains\nlet doubled: Vec<i32> = nums.iter().map(|x| x * 2).collect();\nlet evens: Vec<&i32> = nums.iter().filter(|x| *x % 2 == 0).collect();\nlet sum: i32 = nums.iter().sum();\n\n// HashMap\nuse std::collections::HashMap;\nlet mut map = HashMap::new();\nmap.insert(\"a\", 1);\nmap.entry(\"b\").or_insert(2);",
    "Java": "// ArrayList\nList<Integer> nums = new ArrayList<>(Arrays.asList(1, 2, 3, 4, 5));\nnums.add(6);\nnums.remove(Integer.valueOf(3));\n\n// Stream API\nList<Integer> doubled = nums.stream()\n    .map(x -> x * 2)\n    .collect(Collectors.toList());\n\nint sum = nums.stream().mapToInt(Integer::intValue).sum();\n\n// Array\nint[] arr = {1, 2, 3, 4, 5};\nArrays.sort(arr);\n\n// Map\nMap<String, Integer> map = new HashMap<>();\nmap.put(\"a\", 1);",
    "Swift": "var nums = [1, 2, 3, 4, 5]\nnums.append(6)\nnums.insert(0, at: 0)\nlet sliced = nums[1...3]\n\n// Functional\nlet doubled = nums.map { $0 * 2 }\nlet evens = nums.filter { $0 % 2 == 0 }\nlet sum = nums.reduce(0, +)\n\n// Dictionary\nvar dict: [String: Int] = [\"a\": 1, \"b\": 2]\ndict[\"c\"] = 3\n\n// Set\nvar set: Set<Int> = [1, 2, 3]",
    "Kotlin": "val nums = mutableListOf(1, 2, 3, 4, 5)\nnums.add(6)\nval sliced = nums.subList(1, 4)\n\n// Functional\nval doubled = nums.map { it * 2 }\nval evens = nums.filter { it % 2 == 0 }\nval sum = nums.sum()\n\n// Map\nval map = mutableMapOf(\"a\" to 1, \"b\" to 2)\nmap[\"c\"] = 3\n\n// Destructuring\nval (first, second) = listOf(1, 2)",
    "Ruby": "nums = [1, 2, 3, 4, 5]\nnums << 6\nnums.push(7)\nsliced = nums[1..3]  # [2, 3, 4]\n\n# Functional\ndoubled = nums.map { |x| x * 2 }\nevens = nums.select { |x| x.even? }\nsum = nums.reduce(:+)\n\n# Hash\nhash = { a: 1, b: 2 }\nhash[:c] = 3\n\n# Set\nrequire 'set'\nset = Set.new([1, 2, 3])",
    "Haskell": "-- Lists\nlet xs = [1, 2, 3, 4, 5]\nhead xs      -- 1\ntail xs      -- [2, 3, 4, 5]\nlength xs    -- 5\nxs !! 2      -- 3 (index)\n\n-- List comprehension\n[x * 2 | x <- xs, even x]  -- [4, 8]\n\n-- Functional\nmap (*2) xs\nfilter even xs\nfoldl (+) 0 xs  -- sum = 15\n\n-- Tuple\nlet point = (10, 20)\nfst point  -- 10\nsnd point  -- 20",
    "Elixir": "nums = [1, 2, 3, 4, 5]\n[head | tail] = nums  # head=1, tail=[2,3,4,5]\n\n# Enum module\nEnum.map(nums, &(&1 * 2))\nEnum.filter(nums, &(rem(&1, 2) == 0))\nEnum.reduce(nums, 0, &+/2)\n\n# Tuple\npoint = {10, 20}\nelem(point, 0)  # 10\n\n# Map\nmap = %{a: 1, b: 2}\nMap.put(map, :c, 3)\n\n# MapSet\nset = MapSet.new([1, 2, 3])",
    "Scala": "val nums = List(1, 2, 3, 4, 5)\nval doubled = nums.map(_ * 2)\nval evens = nums.filter(_ % 2 == 0)\nval sum = nums.sum\n\n// Mutable\nval buf = scala.collection.mutable.ArrayBuffer(1, 2, 3)\nbuf += 4\n\n// Map\nval map = Map(\"a\" -> 1, \"b\" -> 2)\nmap + (\"c\" -> 3)\n\n// Tuple\nval point = (10, 20)\npoint._1  // 10",
    "Clojure": ";; Vector\n(def v [1 2 3 4 5])\n(conj v 6)        ;; [1 2 3 4 5 6]\n(nth v 2)          ;; 3\n(subvec v 1 4)     ;; [2 3 4]\n\n;; Functional\n(map #(* % 2) v)   ;; (2 4 6 8 10)\n(filter even? v)   ;; (2 4)\n(reduce + v)       ;; 15\n\n;; Map\n(def m {:a 1 :b 2})\n(assoc m :c 3)\n(get m :a)\n\n;; Set\n(def s #{1 2 3})",
    "PHP": "$nums = [1, 2, 3, 4, 5];\n$nums[] = 6;\narray_push($nums, 7);\n$sliced = array_slice($nums, 1, 3);\n\n// Functional\n$doubled = array_map(fn($x) => $x * 2, $nums);\n$evens = array_filter($nums, fn($x) => $x % 2 === 0);\n$sum = array_sum($nums);\n\n// Associative array\n$map = ['a' => 1, 'b' => 2];\n$map['c'] = 3;",
    "C#": "var nums = new List<int> {1, 2, 3, 4, 5};\nnums.Add(6);\nvar sliced = nums.GetRange(1, 3);\n\n// LINQ\nvar doubled = nums.Select(x => x * 2).ToList();\nvar evens = nums.Where(x => x % 2 == 0).ToList();\nvar sum = nums.Sum();\n\n// Dictionary\nvar dict = new Dictionary<string, int> {{\"a\", 1}, {\"b\", 2}};\ndict[\"c\"] = 3;\n\n// Array\nint[] arr = {1, 2, 3, 4, 5};\nArray.Sort(arr);",
    "C": "// Array\nint nums[] = {1, 2, 3, 4, 5};\nint len = sizeof(nums) / sizeof(nums[0]);\n\n// Dynamic array (manual)\nint* dyn = malloc(10 * sizeof(int));\ndyn[0] = 42;\ndyn = realloc(dyn, 20 * sizeof(int));\nfree(dyn);\n\n// Iterate\nfor (int i = 0; i < len; i++) {\n    printf(\"%d \", nums[i]);\n}",
    "C++": "// vector\nstd::vector<int> nums = {1, 2, 3, 4, 5};\nnums.push_back(6);\nauto it = std::find(nums.begin(), nums.end(), 3);\n\n// Ranges (C++20)\nauto doubled = nums | std::views::transform([](int x) { return x * 2; });\n\n// map\nstd::map<std::string, int> m = {{\"a\", 1}, {\"b\", 2}};\nm[\"c\"] = 3;\n\n// set\nstd::set<int> s = {1, 2, 3};\n\n// array (fixed)\nstd::array<int, 5> arr = {1, 2, 3, 4, 5};",
    "Lua": "-- Table (array part)\nlocal nums = {1, 2, 3, 4, 5}\ntable.insert(nums, 6)\n#nums  -- length\nnums[1]  -- 1 (1-indexed!)\n\n-- Table (hash part)\nlocal map = {a = 1, b = 2}\nmap.c = 3\n\n-- Iterate\nfor i, v in ipairs(nums) do\n    print(i, v)\nend\nfor k, v in pairs(map) do\n    print(k, v)\nend",
    "Julia": "# Array\nnums = [1, 2, 3, 4, 5]\npush!(nums, 6)\nsliced = nums[2:4]  # [2, 3, 4] (1-indexed)\n\n# Functional\ndoubled = map(x -> x * 2, nums)\nevens = filter(iseven, nums)\nsum(nums)\n\n# Dict\nd = Dict(\"a\" => 1, \"b\" => 2)\nd[\"c\"] = 3\n\n# Tuple\npoint = (10, 20)\npoint[1]  # 10\n\n# Comprehension\n[x^2 for x in 1:10 if iseven(x)]",
    "Dart": "var nums = [1, 2, 3, 4, 5];\nnums.add(6);\nvar sliced = nums.sublist(1, 4);\n\n// Functional\nvar doubled = nums.map((x) => x * 2).toList();\nvar evens = nums.where((x) => x % 2 == 0).toList();\nvar sum = nums.reduce((a, b) => a + b);\n\n// Map\nvar map = {'a': 1, 'b': 2};\nmap['c'] = 3;\n\n// Set\nvar set = {1, 2, 3};",
    "Nim": "var nums = @[1, 2, 3, 4, 5]\nnums.add(6)\nlet sliced = nums[1..3]\n\n# Functional\nimport sequtils\nlet doubled = nums.mapIt(it * 2)\nlet evens = nums.filterIt(it mod 2 == 0)\n\n# Table\nimport tables\nvar t = {\"a\": 1, \"b\": 2}.toTable\nt[\"c\"] = 3",
    "Crystal": "nums = [1, 2, 3, 4, 5]\nnums << 6\nsliced = nums[1..3]\n\n# Functional\ndoubled = nums.map { |x| x * 2 }\nevens = nums.select(&.even?)\nsum = nums.sum\n\n# Hash\nhash = {\"a\" => 1, \"b\" => 2}\nhash[\"c\"] = 3",
    "OCaml": "(* List *)\nlet xs = [1; 2; 3; 4; 5]\nList.length xs  (* 5 *)\nList.hd xs      (* 1 *)\nList.tl xs      (* [2;3;4;5] *)\n\n(* Functional *)\nList.map (fun x -> x * 2) xs\nList.filter (fun x -> x mod 2 = 0) xs\nList.fold_left (+) 0 xs  (* 15 *)\n\n(* Array *)\nlet arr = [|1; 2; 3|]\narr.(0)  (* 1 *)",
    "F#": "let nums = [1; 2; 3; 4; 5]\n\n// Functional\nnums |> List.map (fun x -> x * 2)\nnums |> List.filter (fun x -> x % 2 = 0)\nnums |> List.sum\n\n// Array\nlet arr = [|1; 2; 3; 4; 5|]\n\n// Map\nlet map = Map.ofList [(\"a\", 1); (\"b\", 2)]\nMap.find \"a\" map  // 1\n\n// Seq (lazy)\nseq { for x in 1..10 do yield x * x }",
    "Erlang": "%% List\nList = [1, 2, 3, 4, 5],\nlength(List),         %% 5\nhd(List),             %% 1\ntl(List),             %% [2,3,4,5]\n\nlists:map(fun(X) -> X * 2 end, List),\nlists:filter(fun(X) -> X rem 2 =:= 0 end, List),\nlists:foldl(fun(X, Acc) -> X + Acc end, 0, List),\n\n%% Tuple\nTuple = {alice, 30},\nelement(1, Tuple),    %% alice\n\n%% Map\nMap = #{a => 1, b => 2},\nmaps:get(a, Map).",
    "R": "# Vector\nnums <- c(1, 2, 3, 4, 5)\nnums <- c(nums, 6)\nnums[2:4]  # c(2, 3, 4)\n\n# Vectorized operations\ndoubled <- nums * 2\nevens <- nums[nums %% 2 == 0]\nsum(nums)\n\n# List\ndata <- list(name='Alice', age=30)\ndata$score <- 95\n\n# Named vector\nx <- c(a=1, b=2, c=3)",
    "Perl": "my @nums = (1, 2, 3, 4, 5);\npush @nums, 6;\nmy @sliced = @nums[1..3];\n\n# Functional\nmy @doubled = map { $_ * 2 } @nums;\nmy @evens = grep { $_ % 2 == 0 } @nums;\n\n# Hash\nmy %map = (a => 1, b => 2);\n$map{c} = 3;\n\n# Hash slice\nmy @values = @map{qw(a b c)};",
    "Zig": "// Array (fixed)\nconst arr = [_]i32{1, 2, 3, 4, 5};\nconst slice = arr[1..4];\n\n// ArrayList\nvar list = std.ArrayList(i32).init(allocator);\ntry list.append(42);\n\n// HashMap\nvar map = std.StringHashMap(i32).init(allocator);\ntry map.put(\"a\", 1);",
    "Racket": "(define v (vector 1 2 3 4 5))\n(vector-ref v 0)  ;; 1\n(vector-length v)  ;; 5\n\n;; List\n(define xs '(1 2 3 4 5))\n(map (lambda (x) (* x 2)) xs)\n(filter even? xs)\n(foldl + 0 xs)  ;; 15\n\n;; Hash\n(define h (hash 'a 1 'b 2))\n(hash-ref h 'a)  ;; 1",
    "D": "int[] nums = [1, 2, 3, 4, 5];\nnums ~= 6;  // append\nauto sliced = nums[1..4];\n\n// Functional\nimport std.algorithm;\nauto doubled = nums.map!(x => x * 2);\nauto evens = nums.filter!(x => x % 2 == 0);\nauto sum = nums.sum;",
    "TypeScript": "const nums: number[] = [1, 2, 3, 4, 5];\nnums.push(6);\nconst sliced = nums.slice(1, 4);\n\n// Typed functional\nconst doubled: number[] = nums.map(x => x * 2);\nconst evens = nums.filter(x => x % 2 === 0);\nconst sum = nums.reduce((a, b) => a + b, 0);\n\n// Map\nconst map = new Map<string, number>();\nmap.set('a', 1);\n\n// Set\nconst set = new Set([1, 2, 3]);",
}

ROSETTA["strings"] = {
    "Python": "s = 'Hello World'\ns.upper()           # 'HELLO WORLD'\ns.lower()           # 'hello world'\ns.split(' ')        # ['Hello', 'World']\ns.replace('World', 'Python')\ns.strip()           # Remove whitespace\ns.startswith('Hello')  # True\nf'{s} has {len(s)} chars'\n' '.join(['a', 'b', 'c'])  # 'a b c'\ns[0:5]              # 'Hello'\ns[::-1]             # Reverse",
    "JavaScript": "const s = 'Hello World';\ns.toUpperCase();        // 'HELLO WORLD'\ns.toLowerCase();        // 'hello world'\ns.split(' ');           // ['Hello', 'World']\ns.replace('World', 'JS');\ns.trim();               // Remove whitespace\ns.startsWith('Hello');  // true\ns.includes('World');    // true\n`${s} has ${s.length} chars`;\ns.slice(0, 5);          // 'Hello'\ns.padStart(15, '*');    // '****Hello World'",
    "Go": "s := \"Hello World\"\nstrings.ToUpper(s)          // \"HELLO WORLD\"\nstrings.ToLower(s)          // \"hello world\"\nstrings.Split(s, \" \")       // [\"Hello\", \"World\"]\nstrings.Replace(s, \"World\", \"Go\", 1)\nstrings.TrimSpace(s)\nstrings.HasPrefix(s, \"Hello\") // true\nstrings.Contains(s, \"World\") // true\nfmt.Sprintf(\"%s has %d chars\", s, len(s))\ns[:5]                        // \"Hello\"",
    "Rust": "let s = String::from(\"Hello World\");\ns.to_uppercase()           // \"HELLO WORLD\"\ns.to_lowercase()           // \"hello world\"\nlet parts: Vec<&str> = s.split(' ').collect();\ns.replace(\"World\", \"Rust\")\ns.trim()\ns.starts_with(\"Hello\")    // true\ns.contains(\"World\")       // true\nformat!(\"{} has {} chars\", s, s.len())\n&s[0..5]                   // \"Hello\"\ns.chars().rev().collect::<String>()  // Reverse",
    "Java": "String s = \"Hello World\";\ns.toUpperCase();            // \"HELLO WORLD\"\ns.toLowerCase();            // \"hello world\"\ns.split(\" \");               // [\"Hello\", \"World\"]\ns.replace(\"World\", \"Java\");\ns.trim();                   // Remove whitespace\ns.startsWith(\"Hello\");     // true\ns.contains(\"World\");       // true\nString.format(\"%s has %d chars\", s, s.length());\ns.substring(0, 5);         // \"Hello\"\nString.join(\"-\", \"a\", \"b\", \"c\"); // \"a-b-c\"",
    "C": "char s[] = \"Hello World\";\nprintf(\"%lu\\n\", strlen(s));  // 11\n// C strings are char arrays\nchar upper[50];\nstrcpy(upper, s);\nfor (int i = 0; upper[i]; i++)\n    upper[i] = toupper(upper[i]);\n\nchar* found = strstr(s, \"World\");\nif (found) printf(\"Found at %ld\\n\", found - s);\n\nchar buf[100];\nsnprintf(buf, sizeof(buf), \"%s has %lu chars\", s, strlen(s));",
    "C++": "std::string s = \"Hello World\";\n// Transform\nstd::string upper = s;\nstd::transform(upper.begin(), upper.end(), upper.begin(), ::toupper);\n\nauto pos = s.find(\"World\");  // 6\ns.substr(0, 5);              // \"Hello\"\ns.replace(pos, 5, \"C++\");\ns.starts_with(\"Hello\");     // true (C++20)\ns.contains(\"World\");        // true (C++23)\nstd::format(\"{} has {} chars\", s, s.size()); // C++20",
    "Swift": "let s = \"Hello World\"\ns.uppercased()              // \"HELLO WORLD\"\ns.lowercased()              // \"hello world\"\ns.split(separator: \" \")    // [\"Hello\", \"World\"]\ns.replacingOccurrences(of: \"World\", with: \"Swift\")\ns.trimmingCharacters(in: .whitespaces)\ns.hasPrefix(\"Hello\")       // true\ns.contains(\"World\")        // true\n\"\\(s) has \\(s.count) chars\"\nString(s.prefix(5))         // \"Hello\"",
    "Kotlin": "val s = \"Hello World\"\ns.uppercase()               // \"HELLO WORLD\"\ns.lowercase()               // \"hello world\"\ns.split(\" \")               // [\"Hello\", \"World\"]\ns.replace(\"World\", \"Kotlin\")\ns.trim()\ns.startsWith(\"Hello\")      // true\ns.contains(\"World\")        // true\n\"$s has ${s.length} chars\"\ns.substring(0, 5)           // \"Hello\"\ns.reversed()                // \"dlroW olleH\"",
    "Ruby": "s = 'Hello World'\ns.upcase              # 'HELLO WORLD'\ns.downcase            # 'hello world'\ns.split(' ')          # ['Hello', 'World']\ns.gsub('World', 'Ruby')\ns.strip\ns.start_with?('Hello') # true\ns.include?('World')   # true\n\"#{s} has #{s.length} chars\"\ns[0..4]               # 'Hello'\ns.reverse             # 'dlroW olleH'\ns.chars.to_a          # ['H','e','l',...]",
    "Haskell": "import Data.Char (toUpper, toLower)\n\ns = \"Hello World\"\nmap toUpper s          -- \"HELLO WORLD\"\nmap toLower s          -- \"hello world\"\nwords s                -- [\"Hello\",\"World\"]\nunwords [\"Hello\",\"Haskell\"]\nlength s               -- 11\ntake 5 s               -- \"Hello\"\ndrop 6 s               -- \"World\"\nreverse s              -- \"dlroW olleH\"\n\"isPrefixOf\" `isPrefixOf` \"isPrefixOf abc\"  -- True",
    "Elixir": "s = \"Hello World\"\nString.upcase(s)          # \"HELLO WORLD\"\nString.downcase(s)        # \"hello world\"\nString.split(s, \" \")     # [\"Hello\", \"World\"]\nString.replace(s, \"World\", \"Elixir\")\nString.trim(s)\nString.starts_with?(s, \"Hello\")  # true\nString.contains?(s, \"World\")     # true\n\"#{s} has #{String.length(s)} chars\"\nString.slice(s, 0, 5)    # \"Hello\"\nString.reverse(s)        # \"dlroW olleH\"",
    "Scala": "val s = \"Hello World\"\ns.toUpperCase            // \"HELLO WORLD\"\ns.toLowerCase            // \"hello world\"\ns.split(\" \")            // Array(\"Hello\", \"World\")\ns.replace(\"World\", \"Scala\")\ns.trim\ns.startsWith(\"Hello\")   // true\ns.contains(\"World\")     // true\ns\"$s has ${s.length} chars\"\ns.substring(0, 5)        // \"Hello\"\ns.reverse                // \"dlroW olleH\"",
    "Clojure": "(def s \"Hello World\")\n(clojure.string/upper-case s)    ;; \"HELLO WORLD\"\n(clojure.string/lower-case s)    ;; \"hello world\"\n(clojure.string/split s #\" \")   ;; [\"Hello\" \"World\"]\n(clojure.string/replace s \"World\" \"Clojure\")\n(clojure.string/trim s)\n(clojure.string/starts-with? s \"Hello\") ;; true\n(clojure.string/includes? s \"World\")    ;; true\n(str s \" has \" (count s) \" chars\")\n(subs s 0 5)                     ;; \"Hello\"\n(apply str (reverse s))          ;; \"dlroW olleH\"",
    "PHP": "$s = 'Hello World';\nstrtoupper($s);              // 'HELLO WORLD'\nstrtolower($s);              // 'hello world'\nexplode(' ', $s);            // ['Hello', 'World']\nstr_replace('World', 'PHP', $s);\ntrim($s);\nstr_starts_with($s, 'Hello'); // true\nstr_contains($s, 'World');    // true\nsprintf('%s has %d chars', $s, strlen($s));\nsubstr($s, 0, 5);            // 'Hello'\nstrrev($s);                   // 'dlroW olleH'",
    "Lua": "local s = 'Hello World'\nstring.upper(s)              -- 'HELLO WORLD'\nstring.lower(s)              -- 'hello world'\n-- Split (manual)\nlocal parts = {}\nfor word in s:gmatch('%S+') do\n    table.insert(parts, word)\nend\nstring.gsub(s, 'World', 'Lua')\nstring.len(s)                -- 11\nstring.sub(s, 1, 5)          -- 'Hello'\nstring.format('%s has %d chars', s, #s)\nstring.find(s, 'World')      -- 7, 11\nstring.reverse(s)            -- 'dlroW olleH'",
    "Julia": "s = \"Hello World\"\nuppercase(s)                 # \"HELLO WORLD\"\nlowercase(s)                 # \"hello world\"\nsplit(s, \" \")               # [\"Hello\", \"World\"]\nreplace(s, \"World\" => \"Julia\")\nstrip(s)\nstartswith(s, \"Hello\")      # true\ncontains(s, \"World\")        # true\n\"$s has $(length(s)) chars\"\ns[1:5]                       # \"Hello\" (1-indexed)\nreverse(s)                   # \"dlroW olleH\"\njoin([\"a\",\"b\",\"c\"], \"-\")   # \"a-b-c\"",
    "Dart": "var s = 'Hello World';\ns.toUpperCase();              // 'HELLO WORLD'\ns.toLowerCase();              // 'hello world'\ns.split(' ');                 // ['Hello', 'World']\ns.replaceAll('World', 'Dart');\ns.trim();\ns.startsWith('Hello');        // true\ns.contains('World');          // true\n'$s has ${s.length} chars';\ns.substring(0, 5);            // 'Hello'\nString.fromCharCodes(s.codeUnits.reversed); // Reverse",
    "Nim": "let s = \"Hello World\"\nimport strutils\ns.toUpperAscii()             # \"HELLO WORLD\"\ns.toLowerAscii()             # \"hello world\"\ns.split(' ')                 # @[\"Hello\", \"World\"]\ns.replace(\"World\", \"Nim\")\ns.strip()\ns.startsWith(\"Hello\")        # true\ns.contains(\"World\")          # true\n&\"{s} has {s.len} chars\"\ns[0..4]                      # \"Hello\"",
    "Crystal": "s = \"Hello World\"\ns.upcase                     # \"HELLO WORLD\"\ns.downcase                   # \"hello world\"\ns.split(' ')                 # [\"Hello\", \"World\"]\ns.gsub(\"World\", \"Crystal\")\ns.strip\ns.starts_with?(\"Hello\")     # true\ns.includes?(\"World\")        # true\n\"#{s} has #{s.size} chars\"\ns[0..4]                      # \"Hello\"\ns.reverse                    # \"dlroW olleH\"",
    "OCaml": "let s = \"Hello World\"\nString.uppercase_ascii s     (* \"HELLO WORLD\" *)\nString.lowercase_ascii s     (* \"hello world\" *)\nString.split_on_char ' ' s   (* [\"Hello\"; \"World\"] *)\nString.length s              (* 11 *)\nString.sub s 0 5             (* \"Hello\" *)\nPrintf.sprintf \"%s has %d chars\" s (String.length s)",
    "F#": "let s = \"Hello World\"\ns.ToUpper()                  // \"HELLO WORLD\"\ns.ToLower()                  // \"hello world\"\ns.Split(' ')                 // [|\"Hello\"; \"World\"|]\ns.Replace(\"World\", \"F#\")\ns.Trim()\ns.StartsWith(\"Hello\")        // true\ns.Contains(\"World\")          // true\nsprintf \"%s has %d chars\" s s.Length\ns.Substring(0, 5)            // \"Hello\"",
    "Erlang": "S = \"Hello World\",\nstring:uppercase(S),          %% \"HELLO WORLD\"\nstring:lowercase(S),          %% \"hello world\"\nstring:split(S, \" \"),        %% [\"Hello\", \"World\"]\nstring:length(S),             %% 11\nstring:slice(S, 0, 5),       %% \"Hello\"\nstring:find(S, \"World\"),     %% 6\nlists:concat([S, \" has \", integer_to_list(length(S)), \" chars\"]).",
    "R": "s <- 'Hello World'\ntoupper(s)                   # 'HELLO WORLD'\ntolower(s)                   # 'hello world'\nstrsplit(s, ' ')[[1]]        # c('Hello', 'World')\ngsub('World', 'R', s)\ntrimws(s)\nstartsWith(s, 'Hello')       # TRUE\ngrepl('World', s)            # TRUE\nsprintf('%s has %d chars', s, nchar(s))\nsubstr(s, 1, 5)              # 'Hello'\npaste0(rev(strsplit(s,'')[[1]]), collapse='')  # Reverse",
    "Perl": "my $s = 'Hello World';\nuc($s);                      # 'HELLO WORLD'\nlc($s);                      # 'hello world'\nmy @parts = split(' ', $s);  # ('Hello', 'World')\n$s =~ s/World/Perl/;\nlength($s);                  # 11\nsubstr($s, 0, 5);           # 'Hello'\nsprintf('%s has %d chars', $s, length($s));\nindex($s, 'World');          # 6\nreverse($s);                 # 'dlroW olleH'\njoin('-', @parts);           # 'Hello-World'",
    "Zig": "const s = \"Hello World\";\n// Zig strings are byte slices\nconst len = s.len;  // 11\nconst hello = s[0..5];  // \"Hello\"\n// Compare\nstd.mem.eql(u8, s[0..5], \"Hello\");  // true\n// Format\nstd.debug.print(\"{s} has {d} chars\\n\", .{s, s.len});",
    "Racket": "(define s \"Hello World\")\n(string-upcase s)            ;; \"HELLO WORLD\"\n(string-downcase s)          ;; \"hello world\"\n(string-split s)             ;; '(\"Hello\" \"World\")\n(string-replace s \"World\" \"Racket\")\n(string-trim s)\n(string-prefix? \"Hello\" s)  ;; #t\n(string-contains? s \"World\") ;; #t\n(format \"~a has ~a chars\" s (string-length s))\n(substring s 0 5)            ;; \"Hello\"\n(list->string (reverse (string->list s)))  ;; Reverse",
    "D": "string s = \"Hello World\";\nimport std.string, std.uni;\ns.toUpper;                   // \"HELLO WORLD\"\ns.toLower;                   // \"hello world\"\ns.split(\" \");               // [\"Hello\", \"World\"]\ns.replace(\"World\", \"D\");\ns.strip;\ns.startsWith(\"Hello\");       // true\ns.canFind(\"World\");          // true\nformat(\"%s has %d chars\", s, s.length);\ns[0..5];                     // \"Hello\"",
    "C#": "string s = \"Hello World\";\ns.ToUpper();                 // \"HELLO WORLD\"\ns.ToLower();                 // \"hello world\"\ns.Split(' ');                // [\"Hello\", \"World\"]\ns.Replace(\"World\", \"C#\");\ns.Trim();\ns.StartsWith(\"Hello\");       // true\ns.Contains(\"World\");         // true\n$\"{s} has {s.Length} chars\";\ns.Substring(0, 5);           // \"Hello\"\nnew string(s.Reverse().ToArray());  // Reverse\nstring.Join(\"-\", \"a\", \"b\", \"c\");   // \"a-b-c\"",
    "TypeScript": "const s: string = 'Hello World';\ns.toUpperCase();             // 'HELLO WORLD'\ns.toLowerCase();             // 'hello world'\ns.split(' ');                // ['Hello', 'World']\ns.replace('World', 'TS');\ns.trim();\ns.startsWith('Hello');       // true\ns.includes('World');         // true\n`${s} has ${s.length} chars`;\ns.slice(0, 5);               // 'Hello'\n[...s].reverse().join('');   // Reverse",
}

ROSETTA["structs"] = {
    "Python": "from dataclasses import dataclass, field\nfrom typing import List\n\n@dataclass\nclass Person:\n    name: str\n    age: int\n    scores: List[float] = field(default_factory=list)\n    \n    def greet(self) -> str:\n        return f'Hi, I am {self.name} ({self.age})'\n    \n    @property\n    def avg_score(self) -> float:\n        return sum(self.scores) / len(self.scores) if self.scores else 0\n\nalice = Person('Alice', 30, [95, 87, 92])\nprint(alice.greet())\nprint(alice.avg_score)",
    "Go": "type Person struct {\n    Name   string\n    Age    int\n    Scores []float64\n}\n\nfunc NewPerson(name string, age int) *Person {\n    return &Person{Name: name, Age: age}\n}\n\nfunc (p *Person) Greet() string {\n    return fmt.Sprintf(\"Hi, I am %s (%d)\", p.Name, p.Age)\n}\n\nfunc (p *Person) AvgScore() float64 {\n    if len(p.Scores) == 0 { return 0 }\n    sum := 0.0\n    for _, s := range p.Scores { sum += s }\n    return sum / float64(len(p.Scores))\n}\n\nalice := NewPerson(\"Alice\", 30)\nalice.Scores = []float64{95, 87, 92}\nfmt.Println(alice.Greet())",
    "Rust": "#[derive(Debug, Clone)]\nstruct Person {\n    name: String,\n    age: u32,\n    scores: Vec<f64>,\n}\n\nimpl Person {\n    fn new(name: &str, age: u32) -> Self {\n        Person { name: name.to_string(), age, scores: vec![] }\n    }\n    \n    fn greet(&self) -> String {\n        format!(\"Hi, I am {} ({})\", self.name, self.age)\n    }\n    \n    fn avg_score(&self) -> f64 {\n        if self.scores.is_empty() { return 0.0; }\n        self.scores.iter().sum::<f64>() / self.scores.len() as f64\n    }\n}\n\nlet mut alice = Person::new(\"Alice\", 30);\nalice.scores = vec![95.0, 87.0, 92.0];\nprintln!(\"{}\", alice.greet());",
    "Java": "public class Person {\n    private String name;\n    private int age;\n    private List<Double> scores;\n    \n    public Person(String name, int age) {\n        this.name = name;\n        this.age = age;\n        this.scores = new ArrayList<>();\n    }\n    \n    public String greet() {\n        return String.format(\"Hi, I am %s (%d)\", name, age);\n    }\n    \n    public double avgScore() {\n        return scores.stream().mapToDouble(Double::doubleValue).average().orElse(0);\n    }\n}\n\n// Java 16+ Record\nrecord Point(double x, double y) {\n    double distance() { return Math.sqrt(x*x + y*y); }\n}",
    "C": "typedef struct {\n    char name[50];\n    int age;\n    double scores[100];\n    int score_count;\n} Person;\n\nvoid person_init(Person* p, const char* name, int age) {\n    strncpy(p->name, name, 49);\n    p->age = age;\n    p->score_count = 0;\n}\n\nvoid person_greet(const Person* p) {\n    printf(\"Hi, I am %s (%d)\\n\", p->name, p->age);\n}\n\ndouble person_avg(const Person* p) {\n    if (p->score_count == 0) return 0;\n    double sum = 0;\n    for (int i = 0; i < p->score_count; i++)\n        sum += p->scores[i];\n    return sum / p->score_count;\n}",
    "C++": "struct Person {\n    std::string name;\n    int age;\n    std::vector<double> scores;\n    \n    Person(std::string n, int a) : name(std::move(n)), age(a) {}\n    \n    std::string greet() const {\n        return std::format(\"Hi, I am {} ({})\", name, age);\n    }\n    \n    double avg_score() const {\n        if (scores.empty()) return 0;\n        return std::accumulate(scores.begin(), scores.end(), 0.0) / scores.size();\n    }\n};\n\nauto alice = Person(\"Alice\", 30);\nalice.scores = {95, 87, 92};",
    "Swift": "struct Person {\n    let name: String\n    var age: Int\n    var scores: [Double] = []\n    \n    func greet() -> String {\n        return \"Hi, I am \\(name) (\\(age))\"\n    }\n    \n    var avgScore: Double {\n        guard !scores.isEmpty else { return 0 }\n        return scores.reduce(0, +) / Double(scores.count)\n    }\n}\n\nvar alice = Person(name: \"Alice\", age: 30, scores: [95, 87, 92])\nprint(alice.greet())\nprint(alice.avgScore)",
    "Kotlin": "data class Person(\n    val name: String,\n    val age: Int,\n    val scores: MutableList<Double> = mutableListOf()\n) {\n    fun greet(): String = \"Hi, I am $name ($age)\"\n    \n    val avgScore: Double\n        get() = if (scores.isEmpty()) 0.0 else scores.average()\n}\n\nval alice = Person(\"Alice\", 30, mutableListOf(95.0, 87.0, 92.0))\nprintln(alice.greet())\nprintln(alice.avgScore)\n\n// Destructuring\nval (name, age) = alice",
    "Ruby": "class Person\n  attr_accessor :name, :age, :scores\n  \n  def initialize(name, age)\n    @name = name\n    @age = age\n    @scores = []\n  end\n  \n  def greet\n    \"Hi, I am #{@name} (#{@age})\"\n  end\n  \n  def avg_score\n    return 0 if @scores.empty?\n    @scores.sum.to_f / @scores.length\n  end\nend\n\nalice = Person.new('Alice', 30)\nalice.scores = [95, 87, 92]\nputs alice.greet\nputs alice.avg_score",
    "Haskell": "data Person = Person\n    { personName   :: String\n    , personAge    :: Int\n    , personScores :: [Double]\n    } deriving (Show)\n\ngreet :: Person -> String\ngreet p = \"Hi, I am \" ++ personName p ++ \" (\" ++ show (personAge p) ++ \")\"\n\navgScore :: Person -> Double\navgScore p = case personScores p of\n    [] -> 0\n    xs -> sum xs / fromIntegral (length xs)\n\nalice = Person \"Alice\" 30 [95, 87, 92]\nmain = do\n    putStrLn (greet alice)\n    print (avgScore alice)",
    "Elixir": "defmodule Person do\n  defstruct [:name, :age, scores: []]\n  \n  def greet(%Person{name: name, age: age}) do\n    \"Hi, I am #{name} (#{age})\"\n  end\n  \n  def avg_score(%Person{scores: []}) do 0.0 end\n  def avg_score(%Person{scores: scores}) do\n    Enum.sum(scores) / length(scores)\n  end\nend\n\nalice = %Person{name: \"Alice\", age: 30, scores: [95, 87, 92]}\nIO.puts Person.greet(alice)\nIO.puts Person.avg_score(alice)",
    "Scala": "case class Person(\n    name: String,\n    age: Int,\n    scores: List[Double] = Nil\n) {\n  def greet: String = s\"Hi, I am $name ($age)\"\n  \n  def avgScore: Double =\n    if (scores.isEmpty) 0 else scores.sum / scores.length\n}\n\nval alice = Person(\"Alice\", 30, List(95, 87, 92))\nprintln(alice.greet)\nprintln(alice.avgScore)\n\n// Copy with modification\nval bob = alice.copy(name = \"Bob\", age = 25)",
    "TypeScript": "interface Person {\n  name: string;\n  age: number;\n  scores: number[];\n}\n\nfunction createPerson(name: string, age: number): Person {\n  return { name, age, scores: [] };\n}\n\nfunction greet(p: Person): string {\n  return `Hi, I am ${p.name} (${p.age})`;\n}\n\nfunction avgScore(p: Person): number {\n  if (p.scores.length === 0) return 0;\n  return p.scores.reduce((a, b) => a + b, 0) / p.scores.length;\n}\n\nconst alice: Person = { name: 'Alice', age: 30, scores: [95, 87, 92] };",
    "C#": "public record Person(string Name, int Age)\n{\n    public List<double> Scores { get; init; } = new();\n    \n    public string Greet() => $\"Hi, I am {Name} ({Age})\";\n    \n    public double AvgScore =>\n        Scores.Count == 0 ? 0 : Scores.Average();\n}\n\nvar alice = new Person(\"Alice\", 30) { Scores = [95, 87, 92] };\nConsole.WriteLine(alice.Greet());\nConsole.WriteLine(alice.AvgScore);\n\n// With expression (copy + modify)\nvar bob = alice with { Name = \"Bob\", Age = 25 };",
    "Clojure": ";; Records\n(defrecord Person [name age scores])\n\n(defn greet [{:keys [name age]}]\n  (str \"Hi, I am \" name \" (\" age \")\"))\n\n(defn avg-score [{:keys [scores]}]\n  (if (empty? scores) 0\n    (/ (reduce + scores) (count scores))))\n\n(def alice (->Person \"Alice\" 30 [95 87 92]))\n(println (greet alice))\n(println (avg-score alice))\n\n;; Maps as structs\n(def bob {:name \"Bob\" :age 25 :scores []})",
    "PHP": "class Person {\n    public function __construct(\n        public readonly string $name,\n        public readonly int $age,\n        public array $scores = []\n    ) {}\n    \n    public function greet(): string {\n        return sprintf('Hi, I am %s (%d)', $this->name, $this->age);\n    }\n    \n    public function avgScore(): float {\n        if (empty($this->scores)) return 0;\n        return array_sum($this->scores) / count($this->scores);\n    }\n}\n\n$alice = new Person('Alice', 30, [95, 87, 92]);\necho $alice->greet();",
    "Lua": "-- Table as struct\nlocal Person = {}\nPerson.__index = Person\n\nfunction Person.new(name, age)\n    return setmetatable({\n        name = name,\n        age = age,\n        scores = {}\n    }, Person)\nend\n\nfunction Person:greet()\n    return string.format('Hi, I am %s (%d)', self.name, self.age)\nend\n\nfunction Person:avgScore()\n    if #self.scores == 0 then return 0 end\n    local sum = 0\n    for _, s in ipairs(self.scores) do sum = sum + s end\n    return sum / #self.scores\nend\n\nlocal alice = Person.new('Alice', 30)\nalice.scores = {95, 87, 92}",
    "Julia": "struct Person\n    name::String\n    age::Int\n    scores::Vector{Float64}\nend\n\nPerson(name, age) = Person(name, age, Float64[])\n\nfunction greet(p::Person)\n    \"Hi, I am $(p.name) ($(p.age))\"\nend\n\nfunction avg_score(p::Person)\n    isempty(p.scores) ? 0.0 : mean(p.scores)\nend\n\nalice = Person(\"Alice\", 30, [95.0, 87.0, 92.0])\nprintln(greet(alice))",
    "Dart": "class Person {\n  final String name;\n  final int age;\n  List<double> scores;\n  \n  Person(this.name, this.age, {this.scores = const []});\n  \n  String greet() => 'Hi, I am $name ($age)';\n  \n  double get avgScore {\n    if (scores.isEmpty) return 0;\n    return scores.reduce((a, b) => a + b) / scores.length;\n  }\n}\n\nfinal alice = Person('Alice', 30, scores: [95, 87, 92]);\nprint(alice.greet());\nprint(alice.avgScore);",
    "Nim": "type\n  Person = object\n    name: string\n    age: int\n    scores: seq[float]\n\nproc newPerson(name: string, age: int): Person =\n  Person(name: name, age: age, scores: @[])\n\nproc greet(p: Person): string =\n  \"Hi, I am \" & p.name & \" (\" & $p.age & \")\"\n\nproc avgScore(p: Person): float =\n  if p.scores.len == 0: return 0\n  var sum = 0.0\n  for s in p.scores: sum += s\n  sum / float(p.scores.len)\n\nvar alice = newPerson(\"Alice\", 30)\nalice.scores = @[95.0, 87.0, 92.0]",
    "Crystal": "struct Person\n  property name : String\n  property age : Int32\n  property scores : Array(Float64)\n  \n  def initialize(@name, @age, @scores = [] of Float64)\n  end\n  \n  def greet : String\n    \"Hi, I am #{@name} (#{@age})\"\n  end\n  \n  def avg_score : Float64\n    return 0.0 if @scores.empty?\n    @scores.sum / @scores.size\n  end\nend\n\nalice = Person.new(\"Alice\", 30, [95.0, 87.0, 92.0])\nputs alice.greet",
    "OCaml": "type person = {\n  name : string;\n  age  : int;\n  scores : float list;\n}\n\nlet greet p =\n  Printf.sprintf \"Hi, I am %s (%d)\" p.name p.age\n\nlet avg_score p =\n  match p.scores with\n  | [] -> 0.0\n  | xs -> List.fold_left (+.) 0.0 xs /. float_of_int (List.length xs)\n\nlet alice = { name = \"Alice\"; age = 30; scores = [95.; 87.; 92.] }\nlet () = print_endline (greet alice)",
    "F#": "type Person = {\n    Name: string\n    Age: int\n    Scores: float list\n}\n\nlet greet p = sprintf \"Hi, I am %s (%d)\" p.Name p.Age\n\nlet avgScore p =\n    match p.Scores with\n    | [] -> 0.0\n    | xs -> List.sum xs / float (List.length xs)\n\nlet alice = { Name = \"Alice\"; Age = 30; Scores = [95.0; 87.0; 92.0] }\nprintfn \"%s\" (greet alice)\nprintfn \"%f\" (avgScore alice)",
    "Erlang": "-record(person, {name, age, scores = []}).\n\ngreet(#person{name = Name, age = Age}) ->\n    io_lib:format(\"Hi, I am ~s (~p)\", [Name, Age]).\n\navg_score(#person{scores = []}) -> 0.0;\navg_score(#person{scores = Scores}) ->\n    lists:sum(Scores) / length(Scores).\n\nAlice = #person{name = \"Alice\", age = 30, scores = [95.0, 87.0, 92.0]},\nio:format(\"~s~n\", [greet(Alice)]).",
    "R": "# S3 class\nnew_person <- function(name, age, scores = numeric(0)) {\n  structure(list(\n    name = name,\n    age = age,\n    scores = scores\n  ), class = 'Person')\n}\n\ngreet.Person <- function(p) {\n  sprintf('Hi, I am %s (%d)', p$name, p$age)\n}\n\navg_score.Person <- function(p) {\n  if (length(p$scores) == 0) return(0)\n  mean(p$scores)\n}\n\nalice <- new_person('Alice', 30, c(95, 87, 92))\ncat(greet(alice), '\\n')\ncat(avg_score(alice), '\\n')",
    "Perl": "package Person;\nsub new {\n    my ($class, %args) = @_;\n    bless {\n        name   => $args{name},\n        age    => $args{age},\n        scores => $args{scores} // [],\n    }, $class;\n}\n\nsub greet {\n    my $self = shift;\n    return sprintf('Hi, I am %s (%d)', $self->{name}, $self->{age});\n}\n\nsub avg_score {\n    my $self = shift;\n    my @s = @{$self->{scores}};\n    return 0 unless @s;\n    my $sum = 0; $sum += $_ for @s;\n    return $sum / scalar @s;\n}\n\nmy $alice = Person->new(name => 'Alice', age => 30, scores => [95, 87, 92]);",
    "Zig": "const Person = struct {\n    name: []const u8,\n    age: u32,\n    scores: []const f64 = &[_]f64{},\n    \n    pub fn greet(self: Person) void {\n        std.debug.print(\"Hi, I am {s} ({d})\\n\", .{self.name, self.age});\n    }\n    \n    pub fn avgScore(self: Person) f64 {\n        if (self.scores.len == 0) return 0;\n        var sum: f64 = 0;\n        for (self.scores) |s| { sum += s; }\n        return sum / @as(f64, @floatFromInt(self.scores.len));\n    }\n};\n\nconst alice = Person{ .name = \"Alice\", .age = 30 };",
    "Racket": "(struct person (name age scores) #:transparent)\n\n(define (greet p)\n  (format \"Hi, I am ~a (~a)\" (person-name p) (person-age p)))\n\n(define (avg-score p)\n  (let ([scores (person-scores p)])\n    (if (null? scores) 0\n      (/ (apply + scores) (length scores)))))\n\n(define alice (person \"Alice\" 30 '(95 87 92)))\n(displayln (greet alice))\n(displayln (avg-score alice))",
    "D": "struct Person {\n    string name;\n    int age;\n    double[] scores;\n    \n    string greet() {\n        return format(\"Hi, I am %s (%d)\", name, age);\n    }\n    \n    double avgScore() {\n        if (scores.length == 0) return 0;\n        return scores.sum / scores.length;\n    }\n}\n\nauto alice = Person(\"Alice\", 30, [95.0, 87.0, 92.0]);\nwriteln(alice.greet());",
}

ROSETTA["generics"] = {
    "Python": "from typing import TypeVar, Generic, List, Callable\n\nT = TypeVar('T')\nU = TypeVar('U')\n\nclass Stack(Generic[T]):\n    def __init__(self) -> None:\n        self._items: List[T] = []\n    def push(self, item: T) -> None:\n        self._items.append(item)\n    def pop(self) -> T:\n        return self._items.pop()\n    def peek(self) -> T:\n        return self._items[-1]\n    def is_empty(self) -> bool:\n        return len(self._items) == 0\n\ndef map_list(items: List[T], f: Callable[[T], U]) -> List[U]:\n    return [f(x) for x in items]",
    "Go": "// Generic function (Go 1.18+)\nfunc Map[T any, U any](items []T, f func(T) U) []U {\n    result := make([]U, len(items))\n    for i, v := range items {\n        result[i] = f(v)\n    }\n    return result\n}\n\nfunc Filter[T any](items []T, pred func(T) bool) []T {\n    var result []T\n    for _, v := range items {\n        if pred(v) { result = append(result, v) }\n    }\n    return result\n}\n\n// Generic struct\ntype Stack[T any] struct {\n    items []T\n}\nfunc (s *Stack[T]) Push(item T) { s.items = append(s.items, item) }\nfunc (s *Stack[T]) Pop() T {\n    item := s.items[len(s.items)-1]\n    s.items = s.items[:len(s.items)-1]\n    return item\n}",
    "Rust": "// Generic function\nfn largest<T: PartialOrd>(list: &[T]) -> &T {\n    let mut largest = &list[0];\n    for item in &list[1..] {\n        if item > largest { largest = item; }\n    }\n    largest\n}\n\n// Generic struct with trait bounds\nstruct Stack<T> {\n    items: Vec<T>,\n}\n\nimpl<T> Stack<T> {\n    fn new() -> Self { Stack { items: Vec::new() } }\n    fn push(&mut self, item: T) { self.items.push(item); }\n    fn pop(&mut self) -> Option<T> { self.items.pop() }\n    fn is_empty(&self) -> bool { self.items.is_empty() }\n}\n\n// Generic with multiple trait bounds\nfn print_largest<T: PartialOrd + std::fmt::Display>(a: T, b: T) {\n    if a > b { println!(\"{}\", a); } else { println!(\"{}\", b); }\n}",
    "TypeScript": "// Generic function\nfunction identity<T>(arg: T): T {\n  return arg;\n}\n\n// Generic class\nclass Stack<T> {\n  private items: T[] = [];\n  push(item: T): void { this.items.push(item); }\n  pop(): T | undefined { return this.items.pop(); }\n  peek(): T | undefined { return this.items[this.items.length - 1]; }\n  isEmpty(): boolean { return this.items.length === 0; }\n}\n\n// Generic with constraints\nfunction getProperty<T, K extends keyof T>(obj: T, key: K): T[K] {\n  return obj[key];\n}\n\n// Generic utility types\ntype Partial<T> = { [P in keyof T]?: T[P] };\ntype Readonly<T> = { readonly [P in keyof T]: T[P] };",
    "Java": "// Generic method\npublic static <T extends Comparable<T>> T max(T a, T b) {\n    return a.compareTo(b) > 0 ? a : b;\n}\n\n// Generic class\npublic class Stack<T> {\n    private List<T> items = new ArrayList<>();\n    public void push(T item) { items.add(item); }\n    public T pop() { return items.remove(items.size() - 1); }\n    public T peek() { return items.get(items.size() - 1); }\n    public boolean isEmpty() { return items.isEmpty(); }\n}\n\n// Bounded wildcards\npublic static double sum(List<? extends Number> nums) {\n    return nums.stream().mapToDouble(Number::doubleValue).sum();\n}",
    "C++": "// Function template\ntemplate<typename T>\nT max(T a, T b) {\n    return a > b ? a : b;\n}\n\n// Class template\ntemplate<typename T>\nclass Stack {\n    std::vector<T> items;\npublic:\n    void push(const T& item) { items.push_back(item); }\n    T pop() { T item = items.back(); items.pop_back(); return item; }\n    bool empty() const { return items.empty(); }\n};\n\n// Concepts (C++20)\ntemplate<typename T>\nconcept Addable = requires(T a, T b) { a + b; };\n\ntemplate<Addable T>\nT add(T a, T b) { return a + b; }",
    "Swift": "// Generic function\nfunc swapValues<T>(_ a: inout T, _ b: inout T) {\n    let temp = a; a = b; b = temp\n}\n\n// Generic struct\nstruct Stack<Element> {\n    private var items: [Element] = []\n    mutating func push(_ item: Element) { items.append(item) }\n    mutating func pop() -> Element { return items.removeLast() }\n    var isEmpty: Bool { return items.isEmpty }\n}\n\n// Protocol constraint\nfunc largest<T: Comparable>(_ a: T, _ b: T) -> T {\n    return a > b ? a : b\n}",
    "Kotlin": "// Generic function\nfun <T : Comparable<T>> max(a: T, b: T): T = if (a > b) a else b\n\n// Generic class\nclass Stack<T> {\n    private val items = mutableListOf<T>()\n    fun push(item: T) { items.add(item) }\n    fun pop(): T = items.removeAt(items.size - 1)\n    fun isEmpty(): Boolean = items.isEmpty()\n}\n\n// Variance\nclass Producer<out T>(private val value: T) {\n    fun get(): T = value\n}\nclass Consumer<in T> {\n    fun consume(item: T) { /* use item */ }\n}\n\n// Reified generics\ninline fun <reified T> isType(value: Any): Boolean = value is T",
    "Scala": "// Generic function\ndef max[T: Ordering](a: T, b: T): T =\n  if (implicitly[Ordering[T]].gt(a, b)) a else b\n\n// Generic class\nclass Stack[T] {\n  private var items: List[T] = Nil\n  def push(item: T): Unit = items = item :: items\n  def pop(): T = { val h = items.head; items = items.tail; h }\n  def isEmpty: Boolean = items.isEmpty\n}\n\n// Covariance/Contravariance\nclass Container[+T](val value: T)  // Covariant\nclass Processor[-T] { def process(item: T): Unit = {} }  // Contravariant",
    "Haskell": "-- Type classes (Haskell's generics)\nclass Container f where\n    empty  :: f a\n    insert :: a -> f a -> f a\n    toList :: f a -> [a]\n\n-- Parametric polymorphism (built-in)\nidentity :: a -> a\nidentity x = x\n\nswap :: (a, b) -> (b, a)\nswap (x, y) = (y, x)\n\nmap' :: (a -> b) -> [a] -> [b]\nmap' _ []     = []\nmap' f (x:xs) = f x : map' f xs\n\n-- Constrained polymorphism\nlargest :: (Ord a) => [a] -> a\nlargest = foldl1 max",
    "C#": "// Generic method\npublic static T Max<T>(T a, T b) where T : IComparable<T>\n    => a.CompareTo(b) > 0 ? a : b;\n\n// Generic class\npublic class Stack<T> {\n    private List<T> items = new();\n    public void Push(T item) => items.Add(item);\n    public T Pop() { var item = items[^1]; items.RemoveAt(items.Count - 1); return item; }\n    public bool IsEmpty => items.Count == 0;\n}\n\n// Multiple constraints\npublic T Process<T>(T item) where T : class, IDisposable, new()\n{\n    // T must be reference type, implement IDisposable, and have parameterless ctor\n    return item;\n}",
    "Clojure": ";; Clojure uses protocols for generic behavior\n(defprotocol Stackable\n  (push-item [this item])\n  (pop-item [this])\n  (peek-item [this]))\n\n(extend-type clojure.lang.PersistentVector\n  Stackable\n  (push-item [this item] (conj this item))\n  (pop-item [this] (pop this))\n  (peek-item [this] (peek this)))\n\n;; Multimethods (ad-hoc polymorphism)\n(defmulti area :shape)\n(defmethod area :circle [{:keys [radius]}]\n  (* Math/PI radius radius))\n(defmethod area :rect [{:keys [width height]}]\n  (* width height))",
    "Elixir": "# Elixir uses protocols (like Clojure)\ndefprotocol Stringify do\n  @doc \"Convert to string representation\"\n  def to_str(value)\nend\n\ndefimpl Stringify, for: Integer do\n  def to_str(value), do: Integer.to_string(value)\nend\n\ndefimpl Stringify, for: Float do\n  def to_str(value), do: Float.to_string(value)\nend\n\n# Behaviours (interface contracts)\ndefmodule Stack do\n  @callback push(any(), any()) :: any()\n  @callback pop(any()) :: {any(), any()}\nend",
    "OCaml": "(* Parametric polymorphism *)\nlet identity (x : 'a) : 'a = x\n\nlet swap (a, b) = (b, a)\n\n(* Functors (module-level generics) *)\nmodule type COMPARABLE = sig\n  type t\n  val compare : t -> t -> int\nend\n\nmodule MakeSet (Elem : COMPARABLE) = struct\n  type t = Elem.t list\n  let empty = []\n  let add x s = x :: s\n  let mem x s = List.exists (fun y -> Elem.compare x y = 0) s\nend",
    "F#": "// Generic function\nlet identity (x: 'a) : 'a = x\n\nlet swap (a, b) = (b, a)\n\n// Generic class\ntype Stack<'T>() =\n    let mutable items: 'T list = []\n    member _.Push(item: 'T) = items <- item :: items\n    member _.Pop() =\n        let h = List.head items\n        items <- List.tail items\n        h\n    member _.IsEmpty = List.isEmpty items\n\n// Constraints\nlet inline add (a: ^T) (b: ^T) = a + b",
    "Ruby": "# Ruby uses duck typing — no formal generics\n# Convention-based generic programming\nclass Stack\n  def initialize\n    @items = []\n  end\n  \n  def push(item)\n    @items.push(item)\n    self\n  end\n  \n  def pop\n    @items.pop\n  end\n  \n  def empty?\n    @items.empty?\n  end\nend\n\n# Works with any type\ns = Stack.new\ns.push(42).push('hello').push([1,2])",
    "PHP": "// PHP generics via templates (PHPStan/Psalm)\n/** @template T */\nclass Stack {\n    /** @var list<T> */\n    private array $items = [];\n    \n    /** @param T $item */\n    public function push(mixed $item): void {\n        $this->items[] = $item;\n    }\n    \n    /** @return T */\n    public function pop(): mixed {\n        return array_pop($this->items);\n    }\n}\n\n/** @var Stack<int> */\n$intStack = new Stack();\n$intStack->push(42);",
    "Dart": "// Generic class\nclass Stack<T> {\n  final List<T> _items = [];\n  void push(T item) => _items.add(item);\n  T pop() => _items.removeLast();\n  bool get isEmpty => _items.isEmpty;\n}\n\n// Generic function\nT max<T extends Comparable<T>>(T a, T b) => a.compareTo(b) > 0 ? a : b;\n\n// Usage\nfinal intStack = Stack<int>();\nintStack.push(42);\nfinal strStack = Stack<String>();\nstrStack.push('hello');",
    "Nim": "# Generic proc\nproc identity[T](x: T): T = x\n\nproc max[T](a, b: T): T =\n  if a > b: a else: b\n\n# Generic type\ntype\n  Stack[T] = object\n    items: seq[T]\n\nproc push[T](s: var Stack[T], item: T) =\n  s.items.add(item)\n\nproc pop[T](s: var Stack[T]): T =\n  result = s.items[^1]\n  s.items.setLen(s.items.len - 1)",
    "Crystal": "# Generic class\nclass Stack(T)\n  def initialize\n    @items = [] of T\n  end\n  \n  def push(item : T)\n    @items << item\n  end\n  \n  def pop : T\n    @items.pop\n  end\n  \n  def empty? : Bool\n    @items.empty?\n  end\nend\n\nint_stack = Stack(Int32).new\nint_stack.push(42)",
    "Lua": "-- Lua has no generics — dynamic typing\n-- Create generic-like structures via metatables\nfunction Stack()\n    local items = {}\n    return {\n        push = function(item) table.insert(items, item) end,\n        pop = function() return table.remove(items) end,\n        isEmpty = function() return #items == 0 end,\n    }\nend\n\nlocal s = Stack()\ns.push(42)\ns.push('hello')\nprint(s.pop())  -- 'hello'",
    "Julia": "# Parametric types\nstruct Stack{T}\n    items::Vector{T}\nend\n\nStack{T}() where T = Stack{T}(T[])\n\npush!(s::Stack{T}, item::T) where T = push!(s.items, item)\npop!(s::Stack) = pop!(s.items)\nisempty(s::Stack) = isempty(s.items)\n\n# Usage\ns = Stack{Int}()\npush!(s, 42)\n\n# Multiple dispatch (Julia's polymorphism)\nmax_val(a::T, b::T) where {T} = a > b ? a : b",
    "Erlang": "%% Erlang is dynamically typed — no generics\n%% Use -spec for documentation\n-spec identity(T) -> T when T :: term().\nidentity(X) -> X.\n\n-spec stack_push(term(), list()) -> list().\nstack_push(Item, Stack) -> [Item | Stack].\n\n-spec stack_pop(list()) -> {term(), list()}.\nstack_pop([H | T]) -> {H, T}.",
    "R": "# R has no formal generics — use S4 methods\nsetGeneric('area', function(shape) standardGeneric('area'))\n\nsetClass('Circle', representation(radius = 'numeric'))\nsetClass('Rect', representation(width = 'numeric', height = 'numeric'))\n\nsetMethod('area', 'Circle', function(shape) pi * shape@radius^2)\nsetMethod('area', 'Rect', function(shape) shape@width * shape@height)\n\ncircle <- new('Circle', radius = 5)\nrect <- new('Rect', width = 4, height = 6)\narea(circle)  # 78.54\narea(rect)    # 24",
    "Perl": "# Perl uses duck typing — no formal generics\npackage Stack;\nsub new { bless { items => [] }, shift }\nsub push { push @{$_[0]{items}}, $_[1] }\nsub pop { pop @{$_[0]{items}} }\nsub is_empty { !@{$_[0]{items}} }\n\n# Works with any type\nmy $s = Stack->new;\n$s->push(42);\n$s->push('hello');\n$s->push([1,2,3]);",
    "Zig": "// Generic function via comptime\nfn Stack(comptime T: type) type {\n    return struct {\n        items: std.ArrayList(T),\n        \n        const Self = @This();\n        \n        pub fn init(allocator: std.mem.Allocator) Self {\n            return .{ .items = std.ArrayList(T).init(allocator) };\n        }\n        \n        pub fn push(self: *Self, item: T) !void {\n            try self.items.append(item);\n        }\n        \n        pub fn pop(self: *Self) ?T {\n            return self.items.popOrNull();\n        }\n    };\n}",
    "Racket": ";; Racket uses contracts for generic-like behavior\n(define/contract (identity x)\n  (-> any/c any/c)\n  x)\n\n;; Typed Racket has real generics\n;; (: identity (All (A) (-> A A)))\n;; (define (identity x) x)\n\n;; Generic stack via struct\n(struct stack (items) #:transparent)\n(define empty-stack (stack '()))\n(define (stack-push s item) (stack (cons item (stack-items s))))\n(define (stack-pop s) (values (car (stack-items s)) (stack (cdr (stack-items s)))))",
    "D": "// Template function\nT max(T)(T a, T b) {\n    return a > b ? a : b;\n}\n\n// Template struct\nstruct Stack(T) {\n    T[] items;\n    void push(T item) { items ~= item; }\n    T pop() {\n        auto item = items[$ - 1];\n        items = items[0 .. $ - 1];\n        return item;\n    }\n    bool empty() { return items.length == 0; }\n}\n\nauto s = Stack!int();\ns.push(42);",
}

ROSETTA["testing"] = {
    "Python": "import pytest\n\ndef add(a, b):\n    return a + b\n\ndef test_add():\n    assert add(2, 3) == 5\n    assert add(-1, 1) == 0\n    assert add(0, 0) == 0\n\ndef test_add_floats():\n    assert add(0.1, 0.2) == pytest.approx(0.3)\n\nwith pytest.raises(TypeError):\n    add('a', 1)\n\n# Parametrized tests\n@pytest.mark.parametrize('a,b,expected', [\n    (1, 2, 3),\n    (-1, -1, -2),\n    (0, 0, 0),\n])\ndef test_add_params(a, b, expected):\n    assert add(a, b) == expected",
    "JavaScript": "// Jest\ndescribe('add', () => {\n  test('adds positive numbers', () => {\n    expect(add(2, 3)).toBe(5);\n  });\n\n  test('adds negative numbers', () => {\n    expect(add(-1, -1)).toBe(-2);\n  });\n\n  test('handles floats', () => {\n    expect(add(0.1, 0.2)).toBeCloseTo(0.3);\n  });\n\n  test('throws on invalid input', () => {\n    expect(() => add('a', 1)).toThrow();\n  });\n});\n\n// Mock\njest.mock('./api');\nconst mockFetch = jest.fn().mockResolvedValue({ data: 'test' });",
    "Go": "func TestAdd(t *testing.T) {\n    tests := []struct {\n        a, b, want int\n    }{\n        {2, 3, 5},\n        {-1, 1, 0},\n        {0, 0, 0},\n    }\n    for _, tt := range tests {\n        got := add(tt.a, tt.b)\n        if got != tt.want {\n            t.Errorf(\"add(%d, %d) = %d, want %d\", tt.a, tt.b, got, tt.want)\n        }\n    }\n}\n\nfunc BenchmarkAdd(b *testing.B) {\n    for i := 0; i < b.N; i++ {\n        add(2, 3)\n    }\n}",
    "Rust": "#[cfg(test)]\nmod tests {\n    use super::*;\n\n    #[test]\n    fn test_add() {\n        assert_eq!(add(2, 3), 5);\n        assert_eq!(add(-1, 1), 0);\n    }\n\n    #[test]\n    fn test_add_floats() {\n        let result = add_f64(0.1, 0.2);\n        assert!((result - 0.3).abs() < f64::EPSILON);\n    }\n\n    #[test]\n    #[should_panic(expected = \"overflow\")]\n    fn test_overflow() {\n        add(i32::MAX, 1);\n    }\n}",
    "Java": "import org.junit.jupiter.api.*;\nimport static org.junit.jupiter.api.Assertions.*;\n\nclass CalculatorTest {\n    @Test\n    void testAdd() {\n        assertEquals(5, Calculator.add(2, 3));\n        assertEquals(0, Calculator.add(-1, 1));\n    }\n\n    @Test\n    void testAddFloats() {\n        assertEquals(0.3, Calculator.add(0.1, 0.2), 0.001);\n    }\n\n    @Test\n    void testDivideByZero() {\n        assertThrows(ArithmeticException.class, () -> {\n            Calculator.divide(1, 0);\n        });\n    }\n\n    @ParameterizedTest\n    @CsvSource({\"1,2,3\", \"-1,-1,-2\", \"0,0,0\"})\n    void testAddParams(int a, int b, int expected) {\n        assertEquals(expected, Calculator.add(a, b));\n    }\n}",
    "Swift": "import XCTest\n\nclass CalculatorTests: XCTestCase {\n    func testAdd() {\n        XCTAssertEqual(add(2, 3), 5)\n        XCTAssertEqual(add(-1, 1), 0)\n    }\n    \n    func testAddFloats() {\n        XCTAssertEqual(add(0.1, 0.2), 0.3, accuracy: 0.001)\n    }\n    \n    func testDivideByZero() {\n        XCTAssertThrowsError(try divide(1, 0))\n    }\n    \n    func testPerformance() {\n        measure {\n            for _ in 0..<10000 { _ = add(2, 3) }\n        }\n    }\n}",
    "Kotlin": "import kotlin.test.*\n\nclass CalculatorTest {\n    @Test\n    fun testAdd() {\n        assertEquals(5, add(2, 3))\n        assertEquals(0, add(-1, 1))\n    }\n    \n    @Test\n    fun testDivideByZero() {\n        assertFailsWith<ArithmeticException> {\n            divide(1, 0)\n        }\n    }\n}",
    "Ruby": "# RSpec\nRSpec.describe Calculator do\n  describe '#add' do\n    it 'adds positive numbers' do\n      expect(Calculator.add(2, 3)).to eq(5)\n    end\n    \n    it 'adds negative numbers' do\n      expect(Calculator.add(-1, -1)).to eq(-2)\n    end\n    \n    it 'handles floats' do\n      expect(Calculator.add(0.1, 0.2)).to be_within(0.001).of(0.3)\n    end\n  end\n  \n  describe '#divide' do\n    it 'raises on zero' do\n      expect { Calculator.divide(1, 0) }.to raise_error(ZeroDivisionError)\n    end\n  end\nend",
    "C#": "using Xunit;\n\npublic class CalculatorTests\n{\n    [Fact]\n    public void TestAdd()\n    {\n        Assert.Equal(5, Calculator.Add(2, 3));\n        Assert.Equal(0, Calculator.Add(-1, 1));\n    }\n    \n    [Theory]\n    [InlineData(1, 2, 3)]\n    [InlineData(-1, -1, -2)]\n    [InlineData(0, 0, 0)]\n    public void TestAddParams(int a, int b, int expected)\n    {\n        Assert.Equal(expected, Calculator.Add(a, b));\n    }\n    \n    [Fact]\n    public void TestDivideByZero()\n    {\n        Assert.Throws<DivideByZeroException>(() => Calculator.Divide(1, 0));\n    }\n}",
    "Haskell": "import Test.HUnit\nimport Test.QuickCheck\n\ntestAdd :: Test\ntestAdd = TestList\n    [ TestCase $ assertEqual \"2+3\" 5 (add 2 3)\n    , TestCase $ assertEqual \"-1+1\" 0 (add (-1) 1)\n    ]\n\n-- Property-based testing\nprop_addCommutative :: Int -> Int -> Bool\nprop_addCommutative a b = add a b == add b a\n\nprop_addAssociative :: Int -> Int -> Int -> Bool\nprop_addAssociative a b c = add (add a b) c == add a (add b c)\n\nmain = do\n    runTestTT testAdd\n    quickCheck prop_addCommutative\n    quickCheck prop_addAssociative",
    "Elixir": "defmodule CalculatorTest do\n  use ExUnit.Case\n  \n  test \"adds positive numbers\" do\n    assert Calculator.add(2, 3) == 5\n  end\n  \n  test \"adds negative numbers\" do\n    assert Calculator.add(-1, -1) == -2\n  end\n  \n  test \"divide by zero raises\" do\n    assert_raise ArithmeticError, fn ->\n      Calculator.divide(1, 0)\n    end\n  end\n  \n  # Doctest\n  doctest Calculator\nend",
    "Scala": "import org.scalatest.funsuite.AnyFunSuite\n\nclass CalculatorSuite extends AnyFunSuite {\n  test(\"add positive\") {\n    assert(add(2, 3) === 5)\n  }\n  \n  test(\"add negative\") {\n    assert(add(-1, 1) === 0)\n  }\n  \n  test(\"divide by zero\") {\n    assertThrows[ArithmeticException] {\n      divide(1, 0)\n    }\n  }\n}",
    "PHP": "use PHPUnit\\Framework\\TestCase;\n\nclass CalculatorTest extends TestCase\n{\n    public function testAdd(): void\n    {\n        $this->assertEquals(5, Calculator::add(2, 3));\n        $this->assertEquals(0, Calculator::add(-1, 1));\n    }\n    \n    public function testDivideByZero(): void\n    {\n        $this->expectException(DivisionByZeroError::class);\n        Calculator::divide(1, 0);\n    }\n    \n    /** @dataProvider addProvider */\n    public function testAddParams(int $a, int $b, int $expected): void\n    {\n        $this->assertEquals($expected, Calculator::add($a, $b));\n    }\n    \n    public static function addProvider(): array\n    {\n        return [[1,2,3], [-1,-1,-2], [0,0,0]];\n    }\n}",
    "TypeScript": "import { describe, it, expect } from 'vitest';\n\ndescribe('Calculator', () => {\n  it('adds positive numbers', () => {\n    expect(add(2, 3)).toBe(5);\n  });\n\n  it('adds negative numbers', () => {\n    expect(add(-1, -1)).toBe(-2);\n  });\n\n  it('handles floats', () => {\n    expect(add(0.1, 0.2)).toBeCloseTo(0.3);\n  });\n\n  it('type checks', () => {\n    // @ts-expect-error\n    add('a', 1);\n  });\n});",
    "C": "#include <assert.h>\n#include <stdio.h>\n\nvoid test_add() {\n    assert(add(2, 3) == 5);\n    assert(add(-1, 1) == 0);\n    assert(add(0, 0) == 0);\n    printf(\"test_add: PASSED\\n\");\n}\n\nvoid test_add_overflow() {\n    // Check for overflow behavior\n    int result = add(INT_MAX, 1);\n    printf(\"Overflow test: %d\\n\", result);\n}\n\nint main() {\n    test_add();\n    test_add_overflow();\n    printf(\"All tests passed!\\n\");\n    return 0;\n}",
    "C++": "#include <gtest/gtest.h>\n\nTEST(CalculatorTest, AddPositive) {\n    EXPECT_EQ(add(2, 3), 5);\n}\n\nTEST(CalculatorTest, AddNegative) {\n    EXPECT_EQ(add(-1, 1), 0);\n}\n\nTEST(CalculatorTest, AddFloats) {\n    EXPECT_NEAR(add(0.1, 0.2), 0.3, 0.001);\n}\n\nTEST(CalculatorTest, DivideByZero) {\n    EXPECT_THROW(divide(1, 0), std::runtime_error);\n}",
    "Lua": "-- Simple test framework\nlocal function assert_eq(a, b, msg)\n    if a ~= b then\n        error(string.format('%s: expected %s, got %s', msg or 'FAIL', tostring(b), tostring(a)))\n    end\nend\n\nassert_eq(add(2, 3), 5, 'add positive')\nassert_eq(add(-1, 1), 0, 'add negative')\nassert_eq(add(0, 0), 0, 'add zero')\n\n-- pcall for error testing\nlocal ok, err = pcall(function() divide(1, 0) end)\nassert(not ok, 'should throw on divide by zero')\n\nprint('All tests passed!')",
    "Julia": "using Test\n\n@testset \"Calculator\" begin\n    @test add(2, 3) == 5\n    @test add(-1, 1) == 0\n    @test add(0.1, 0.2) ≈ 0.3\n    @test_throws DivideError divide(1, 0)\nend\n\n# Property-based\nusing Test\n@testset \"Commutativity\" begin\n    for _ in 1:100\n        a, b = rand(Int, 2)\n        @test add(a, b) == add(b, a)\n    end\nend",
    "Dart": "import 'package:test/test.dart';\n\nvoid main() {\n  group('Calculator', () {\n    test('adds positive numbers', () {\n      expect(add(2, 3), equals(5));\n    });\n    \n    test('adds negative numbers', () {\n      expect(add(-1, -1), equals(-2));\n    });\n    \n    test('divide by zero throws', () {\n      expect(() => divide(1, 0), throwsA(isA<ArgumentError>()));\n    });\n  });\n}",
}

ROSETTA["modules"] = {
    "Python": "# math_utils.py\ndef add(a, b):\n    return a + b\n\ndef multiply(a, b):\n    return a * b\n\n# main.py\nfrom math_utils import add, multiply\nimport math_utils as mu\n\nresult = add(2, 3)\nresult2 = mu.multiply(4, 5)\n\n# Package structure:\n# mypackage/\n#   __init__.py\n#   math/\n#     __init__.py\n#     operations.py\n# from mypackage.math.operations import add",
    "JavaScript": "// math_utils.js (ES Modules)\nexport function add(a, b) { return a + b; }\nexport function multiply(a, b) { return a * b; }\nexport default class Calculator { /* ... */ }\n\n// main.js\nimport Calculator, { add, multiply } from './math_utils.js';\nimport * as math from './math_utils.js';\n\n// CommonJS\nconst { add } = require('./math_utils');\nmodule.exports = { add };",
    "Go": "// math/math.go\npackage math\n\nfunc Add(a, b int) int { return a + b }\nfunc Multiply(a, b int) int { return a * b }\n\n// Unexported (private)\nfunc helper() {} // lowercase = package-private\n\n// main.go\npackage main\n\nimport (\n    \"fmt\"\n    \"myapp/math\"\n)\n\nfunc main() {\n    fmt.Println(math.Add(2, 3))\n}\n\n// go.mod\n// module myapp\n// go 1.22",
    "Rust": "// lib.rs\npub mod math {\n    pub fn add(a: i32, b: i32) -> i32 { a + b }\n    pub fn multiply(a: i32, b: i32) -> i32 { a * b }\n    \n    // Private\n    fn helper() {}\n}\n\n// main.rs\nuse mylib::math;\nuse mylib::math::add;  // Direct import\n\nfn main() {\n    println!(\"{}\", math::add(2, 3));\n    println!(\"{}\", add(4, 5));\n}\n\n// Cargo.toml manages dependencies",
    "Java": "// src/com/example/math/MathUtils.java\npackage com.example.math;\n\npublic class MathUtils {\n    public static int add(int a, int b) { return a + b; }\n    public static int multiply(int a, int b) { return a * b; }\n    \n    // Package-private\n    static int helper() { return 0; }\n}\n\n// src/com/example/Main.java\npackage com.example;\nimport com.example.math.MathUtils;\nimport static com.example.math.MathUtils.add;\n\nMathUtils.add(2, 3);\nadd(4, 5);  // Static import",
    "TypeScript": "// math_utils.ts\nexport function add(a: number, b: number): number {\n  return a + b;\n}\n\nexport function multiply(a: number, b: number): number {\n  return a * b;\n}\n\nexport interface Calculator {\n  add(a: number, b: number): number;\n}\n\n// main.ts\nimport { add, multiply, type Calculator } from './math_utils';\nimport * as math from './math_utils';",
    "Swift": "// MathUtils.swift\npublic func add(_ a: Int, _ b: Int) -> Int { a + b }\npublic func multiply(_ a: Int, _ b: Int) -> Int { a * b }\n\n// Private to file\nprivate func helper() -> Int { 0 }\n\n// Module = Swift Package\n// Package.swift\n// import PackageDescription\n// let package = Package(name: \"MathLib\", ...)\n\n// Usage\nimport MathLib\nlet result = add(2, 3)",
    "Kotlin": "// MathUtils.kt\npackage com.example.math\n\nfun add(a: Int, b: Int): Int = a + b\nfun multiply(a: Int, b: Int): Int = a * b\n\n// Private to file\nprivate fun helper(): Int = 0\n\n// Main.kt\nimport com.example.math.add\nimport com.example.math.*\n\nfun main() {\n    println(add(2, 3))\n}",
    "Ruby": "# lib/math_utils.rb\nmodule MathUtils\n  def self.add(a, b)\n    a + b\n  end\n  \n  module_function\n  def multiply(a, b)\n    a * b\n  end\nend\n\n# main.rb\nrequire_relative 'lib/math_utils'\n# or: require 'math_utils'\n\nMathUtils.add(2, 3)\n\n# Mixin modules\nmodule Greetable\n  def greet\n    \"Hello, #{name}\"\n  end\nend",
    "Haskell": "-- MathUtils.hs\nmodule MathUtils (add, multiply) where\n\nadd :: Int -> Int -> Int\nadd = (+)\n\nmultiply :: Int -> Int -> Int\nmultiply = (*)\n\n-- Not exported (private)\nhelper :: Int\nhelper = 0\n\n-- Main.hs\nmodule Main where\nimport MathUtils (add, multiply)\nimport qualified MathUtils as M\n\nmain :: IO ()\nmain = print (add 2 3)",
    "C#": "// MathUtils.cs\nnamespace MyApp.Math;\n\npublic static class MathUtils\n{\n    public static int Add(int a, int b) => a + b;\n    public static int Multiply(int a, int b) => a * b;\n    \n    internal static int Helper() => 0; // Assembly-internal\n}\n\n// Main.cs\nusing MyApp.Math;\nusing static MyApp.Math.MathUtils; // Static import\n\nvar result = Add(2, 3); // Direct access",
    "Elixir": "# lib/math_utils.ex\ndefmodule MathUtils do\n  def add(a, b), do: a + b\n  def multiply(a, b), do: a * b\n  \n  # Private\n  defp helper, do: 0\nend\n\n# lib/main.ex\ndefmodule Main do\n  alias MathUtils, as: M\n  import MathUtils, only: [add: 2]\n  \n  def run do\n    add(2, 3)\n    M.multiply(4, 5)\n  end\nend",
    "Scala": "// MathUtils.scala\npackage com.example.math\n\nobject MathUtils {\n  def add(a: Int, b: Int): Int = a + b\n  def multiply(a: Int, b: Int): Int = a * b\n  \n  private def helper: Int = 0\n}\n\n// Main.scala\nimport com.example.math.MathUtils\nimport com.example.math.MathUtils.{add, multiply}\n\nadd(2, 3)\nMathUtils.multiply(4, 5)",
    "PHP": "// src/Math/MathUtils.php\nnamespace App\\Math;\n\nclass MathUtils {\n    public static function add(int $a, int $b): int {\n        return $a + $b;\n    }\n}\n\n// src/Main.php\nuse App\\Math\\MathUtils;\n\n$result = MathUtils::add(2, 3);\n\n// Autoloading via Composer\n// composer.json: { \"autoload\": { \"psr-4\": { \"App\\\\\": \"src/\" } } }",
    "C": "// math_utils.h\n#ifndef MATH_UTILS_H\n#define MATH_UTILS_H\nint add(int a, int b);\nint multiply(int a, int b);\n#endif\n\n// math_utils.c\n#include \"math_utils.h\"\nint add(int a, int b) { return a + b; }\nint multiply(int a, int b) { return a * b; }\nstatic int helper() { return 0; } // File-local\n\n// main.c\n#include \"math_utils.h\"\nint result = add(2, 3);",
    "C++": "// math_utils.hpp\n#pragma once\nnamespace math {\n    int add(int a, int b);\n    int multiply(int a, int b);\n    \n    namespace detail { // Convention for private\n        int helper();\n    }\n}\n\n// math_utils.cpp\n#include \"math_utils.hpp\"\nnamespace math {\n    int add(int a, int b) { return a + b; }\n}\n\n// main.cpp\n#include \"math_utils.hpp\"\nusing namespace math;\nauto result = add(2, 3);\n\n// C++20 modules\n// export module math;\n// export int add(int a, int b) { return a + b; }",
    "Clojure": ";; src/myapp/math.clj\n(ns myapp.math)\n\n(defn add [a b] (+ a b))\n(defn multiply [a b] (* a b))\n\n;; Private\n(defn- helper [] 0)\n\n;; src/myapp/core.clj\n(ns myapp.core\n  (:require [myapp.math :as math]\n            [myapp.math :refer [add]]))\n\n(add 2 3)\n(math/multiply 4 5)",
    "Lua": "-- math_utils.lua\nlocal M = {}\n\nfunction M.add(a, b)\n    return a + b\nend\n\nfunction M.multiply(a, b)\n    return a * b\nend\n\n-- Private\nlocal function helper()\n    return 0\nend\n\nreturn M\n\n-- main.lua\nlocal math = require('math_utils')\nprint(math.add(2, 3))\nprint(math.multiply(4, 5))",
    "Dart": "// lib/math_utils.dart\nlibrary math_utils;\n\nint add(int a, int b) => a + b;\nint multiply(int a, int b) => a * b;\n\n// Private (starts with _)\nint _helper() => 0;\n\n// main.dart\nimport 'package:myapp/math_utils.dart';\nimport 'package:myapp/math_utils.dart' as math;\nimport 'package:myapp/math_utils.dart' show add;\n\nvar result = add(2, 3);\nvar result2 = math.multiply(4, 5);",
    "Julia": "# MathUtils.jl\nmodule MathUtils\n\nexport add, multiply\n\nadd(a, b) = a + b\nmultiply(a, b) = a * b\n\n# Not exported\nhelper() = 0\n\nend\n\n# main.jl\nusing .MathUtils\nimport .MathUtils: multiply\n\nadd(2, 3)\nmultiply(4, 5)\nMathUtils.helper()  # Access non-exported",
    "Nim": "# math_utils.nim\nproc add*(a, b: int): int = a + b  # * = exported\nproc multiply*(a, b: int): int = a * b\n\nproc helper(): int = 0  # Not exported\n\n# main.nim\nimport math_utils\nfrom math_utils import add\n\necho add(2, 3)\necho multiply(4, 5)",
    "Erlang": "%% math_utils.erl\n-module(math_utils).\n-export([add/2, multiply/2]).\n\nadd(A, B) -> A + B.\nmultiply(A, B) -> A * B.\n\n%% Not exported\nhelper() -> 0.\n\n%% main.erl\n-module(main).\n-import(math_utils, [add/2]).\n\nstart() ->\n    add(2, 3),\n    math_utils:multiply(4, 5).",
    "OCaml": "(* math_utils.ml *)\nlet add a b = a + b\nlet multiply a b = a * b\n\n(* math_utils.mli — interface file *)\nval add : int -> int -> int\nval multiply : int -> int -> int\n(* helper is not in .mli = private *)\n\n(* main.ml *)\nopen Math_utils\nlet () = Printf.printf \"%d\\n\" (add 2 3)",
    "F#": "// MathUtils.fs\nmodule MathUtils\n\nlet add a b = a + b\nlet multiply a b = a * b\n\nlet private helper () = 0\n\n// Main.fs\nopen MathUtils\n\nprintfn \"%d\" (add 2 3)\nprintfn \"%d\" (multiply 4 5)",
    "Racket": ";; math-utils.rkt\n#lang racket\n(provide add multiply)\n\n(define (add a b) (+ a b))\n(define (multiply a b) (* a b))\n(define (helper) 0) ;; Not provided = private\n\n;; main.rkt\n#lang racket\n(require \"math-utils.rkt\")\n(require (prefix-in math: \"math-utils.rkt\"))\n\n(add 2 3)\n(math:multiply 4 5)",
    "R": "# math_utils.R\nadd <- function(a, b) a + b\nmultiply <- function(a, b) a * b\n\n# main.R\nsource('math_utils.R')\nadd(2, 3)\n\n# Or as a package\n# R/add.R\n#' @export\nadd <- function(a, b) a + b",
    "Perl": "# MathUtils.pm\npackage MathUtils;\nuse Exporter 'import';\nour @EXPORT_OK = qw(add multiply);\n\nsub add { $_[0] + $_[1] }\nsub multiply { $_[0] * $_[1] }\n\n1;  # Must return true\n\n# main.pl\nuse MathUtils qw(add multiply);\nprint add(2, 3);",
    "Zig": "// math_utils.zig\npub fn add(a: i32, b: i32) i32 {\n    return a + b;\n}\n\npub fn multiply(a: i32, b: i32) i32 {\n    return a * b;\n}\n\nfn helper() i32 { return 0; } // Not pub = private\n\n// main.zig\nconst math = @import(\"math_utils.zig\");\nconst result = math.add(2, 3);",
    "D": "// math_utils.d\nmodule math_utils;\n\nint add(int a, int b) { return a + b; }\nint multiply(int a, int b) { return a * b; }\nprivate int helper() { return 0; }\n\n// main.d\nimport math_utils;\nimport math_utils : add;  // Selective\n\nauto result = add(2, 3);",
    "Crystal": "# math_utils.cr\nmodule MathUtils\n  def self.add(a, b)\n    a + b\n  end\n  \n  def self.multiply(a, b)\n    a * b\n  end\nend\n\n# main.cr\nrequire \"./math_utils\"\nputs MathUtils.add(2, 3)",
}

ROSETTA["concurrency"] = {
    "Python": "import asyncio\nfrom concurrent.futures import ThreadPoolExecutor\nimport threading\n\n# Async/await\nasync def fetch(url):\n    await asyncio.sleep(1)\n    return f'Data from {url}'\n\nasync def main():\n    results = await asyncio.gather(\n        fetch('url1'), fetch('url2'), fetch('url3')\n    )\n\n# Threading\ndef worker(n):\n    print(f'Thread {n} running')\n\nthreads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]\nfor t in threads: t.start()\nfor t in threads: t.join()\n\n# Thread pool\nwith ThreadPoolExecutor(max_workers=4) as pool:\n    futures = [pool.submit(worker, i) for i in range(4)]",
    "JavaScript": "// Promises\nconst fetchData = (url) => new Promise((resolve) => {\n  setTimeout(() => resolve(`Data from ${url}`), 1000);\n});\n\n// Async/await\nasync function main() {\n  const result = await fetchData('url');\n  \n  // Parallel\n  const [a, b, c] = await Promise.all([\n    fetchData('url1'), fetchData('url2'), fetchData('url3')\n  ]);\n  \n  // Race\n  const fastest = await Promise.race([fetchData('a'), fetchData('b')]);\n}\n\n// Web Workers (true parallelism)\nconst worker = new Worker('worker.js');\nworker.postMessage({data: 'process'});\nworker.onmessage = (e) => console.log(e.data);",
    "Go": "// Goroutines — lightweight threads\ngo func() {\n    fmt.Println(\"goroutine running\")\n}()\n\n// Channels — typed communication\nch := make(chan string, 3)\ngo func() { ch <- \"hello\" }()\nmsg := <-ch\n\n// Fan-out/fan-in\nfunc worker(id int, jobs <-chan int, results chan<- int) {\n    for j := range jobs {\n        results <- j * 2\n    }\n}\njobs := make(chan int, 100)\nresults := make(chan int, 100)\nfor w := 0; w < 4; w++ {\n    go worker(w, jobs, results)\n}\n\n// Select — multiplexing\nselect {\ncase msg := <-ch1: fmt.Println(msg)\ncase msg := <-ch2: fmt.Println(msg)\ncase <-time.After(time.Second): fmt.Println(\"timeout\")\n}\n\n// WaitGroup\nvar wg sync.WaitGroup\nfor i := 0; i < 5; i++ {\n    wg.Add(1)\n    go func(n int) { defer wg.Done(); fmt.Println(n) }(i)\n}\nwg.Wait()\n\n// Mutex\nvar mu sync.Mutex\nmu.Lock()\ncounter++\nmu.Unlock()",
    "Rust": "use std::thread;\nuse std::sync::{Arc, Mutex, mpsc};\n\n// Spawn threads\nlet handles: Vec<_> = (0..4).map(|i| {\n    thread::spawn(move || {\n        println!(\"Thread {} running\", i);\n        i * 2\n    })\n}).collect();\nlet results: Vec<_> = handles.into_iter().map(|h| h.join().unwrap()).collect();\n\n// Channels\nlet (tx, rx) = mpsc::channel();\nfor i in 0..4 {\n    let tx = tx.clone();\n    thread::spawn(move || { tx.send(i * 2).unwrap(); });\n}\ndrop(tx);\nfor val in rx { println!(\"Got: {}\", val); }\n\n// Arc + Mutex (shared state)\nlet counter = Arc::new(Mutex::new(0));\nlet handles: Vec<_> = (0..4).map(|_| {\n    let counter = Arc::clone(&counter);\n    thread::spawn(move || { *counter.lock().unwrap() += 1; })\n}).collect();\nfor h in handles { h.join().unwrap(); }\n\n// Async (tokio)\nasync fn fetch(url: &str) -> String { /* ... */ }\nlet (a, b) = tokio::join!(fetch(\"url1\"), fetch(\"url2\"));",
    "Java": "// Thread\nThread t = new Thread(() -> System.out.println(\"Running\"));\nt.start();\nt.join();\n\n// ExecutorService\nvar executor = Executors.newFixedThreadPool(4);\nvar futures = List.of(\"url1\", \"url2\").stream()\n    .map(url -> executor.submit(() -> fetch(url)))\n    .toList();\nfor (var f : futures) System.out.println(f.get());\nexecutor.shutdown();\n\n// CompletableFuture\nCompletableFuture.supplyAsync(() -> fetch(\"url\"))\n    .thenApply(String::toUpperCase)\n    .thenAccept(System.out::println);\n\n// Virtual Threads (Java 21)\nThread.startVirtualThread(() -> {\n    var data = fetch(\"url\");\n    System.out.println(data);\n});\n\n// Synchronized\nsynchronized (lock) { counter++; }\n\n// AtomicInteger\nAtomicInteger counter = new AtomicInteger(0);\ncounter.incrementAndGet();",
    "C": "#include <pthread.h>\n\nvoid* worker(void* arg) {\n    int id = *(int*)arg;\n    printf(\"Thread %d running\\n\", id);\n    return NULL;\n}\n\n// Create threads\npthread_t threads[4];\nint ids[4];\nfor (int i = 0; i < 4; i++) {\n    ids[i] = i;\n    pthread_create(&threads[i], NULL, worker, &ids[i]);\n}\nfor (int i = 0; i < 4; i++) pthread_join(threads[i], NULL);\n\n// Mutex\npthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;\npthread_mutex_lock(&lock);\ncounter++;\npthread_mutex_unlock(&lock);\n\n// Semaphore\nsem_t sem;\nsem_init(&sem, 0, 3);  // Max 3 concurrent\nsem_wait(&sem);\n// critical section\nsem_post(&sem);",
    "C++": "#include <thread>\n#include <mutex>\n#include <future>\n\n// Threads\nstd::vector<std::thread> threads;\nfor (int i = 0; i < 4; i++) {\n    threads.emplace_back([i]() {\n        std::cout << \"Thread \" << i << \" running\\n\";\n    });\n}\nfor (auto& t : threads) t.join();\n\n// Mutex\nstd::mutex mtx;\n{ std::lock_guard<std::mutex> lock(mtx); counter++; }\n\n// Async/Future\nauto future = std::async(std::launch::async, []() {\n    return fetch(\"url\");\n});\nauto result = future.get();\n\n// Condition variable\nstd::condition_variable cv;\ncv.notify_one();\ncv.wait(lock, []{ return ready; });",
    "Swift": "// async/await (Swift 5.5+)\nfunc fetchAll() async {\n    async let a = fetch(\"url1\")\n    async let b = fetch(\"url2\")\n    let (resultA, resultB) = await (a, b)\n}\n\n// Task groups\nawait withTaskGroup(of: String.self) { group in\n    for url in urls {\n        group.addTask { await fetch(url) }\n    }\n    for await result in group {\n        print(result)\n    }\n}\n\n// Actors (thread-safe state)\nactor Counter {\n    private var count = 0\n    func increment() { count += 1 }\n    func value() -> Int { count }\n}",
    "Kotlin": "import kotlinx.coroutines.*\n\n// Coroutines\nrunBlocking {\n    // Sequential\n    val a = async { fetch(\"url1\") }\n    val b = async { fetch(\"url2\") }\n    println(a.await() + b.await())\n    \n    // Parallel\n    val results = (1..10).map { i ->\n        async(Dispatchers.IO) { fetch(\"url$i\") }\n    }.awaitAll()\n}\n\n// Channels\nval channel = Channel<Int>()\nlaunch { for (i in 1..5) channel.send(i) }\nlaunch { for (msg in channel) println(msg) }\n\n// Flow (reactive)\nflow { for (i in 1..10) { emit(i); delay(100) } }\n    .filter { it % 2 == 0 }\n    .collect { println(it) }",
    "Ruby": "# Threads\nthreads = 4.times.map { |i|\n  Thread.new(i) { |n| puts \"Thread #{n} running\" }\n}\nthreads.each(&:join)\n\n# Mutex\nmutex = Mutex.new\nmutex.synchronize { counter += 1 }\n\n# Ractor (Ruby 3.0+ — true parallelism)\nractors = 4.times.map { |i|\n  Ractor.new(i) { |n| n * 2 }\n}\nresults = ractors.map(&:take)  # [0, 2, 4, 6]\n\n# Fiber (cooperative)\nfib = Fiber.new do\n  Fiber.yield 1\n  Fiber.yield 2\n  3\nend\nfib.resume  # 1\nfib.resume  # 2",
    "Haskell": "import Control.Concurrent\nimport Control.Concurrent.Async\nimport Control.Concurrent.STM\n\n-- Async (parallel)\nmain = do\n    (a, b) <- concurrently\n        (fetch \"url1\")\n        (fetch \"url2\")\n    print (a, b)\n\n-- MVar (shared state)\nmvar <- newMVar 0\nmodifyMVar_ mvar (\\x -> return (x + 1))\n\n-- STM (Software Transactional Memory)\ncounter <- newTVarIO 0\natomically $ modifyTVar' counter (+1)\n\n-- Channels\nchan <- newChan\nforkIO $ writeChan chan \"hello\"\nmsg <- readChan chan",
    "Elixir": "# Processes (lightweight)\npid = spawn(fn -> IO.puts(\"Process running\") end)\n\n# Send/receive messages\nsend(pid, {:hello, \"world\"})\nreceive do\n  {:hello, msg} -> IO.puts(msg)\nafter\n  1000 -> IO.puts(\"timeout\")\nend\n\n# Task (async)\ntask1 = Task.async(fn -> fetch(\"url1\") end)\ntask2 = Task.async(fn -> fetch(\"url2\") end)\nresults = [Task.await(task1), Task.await(task2)]\n\n# GenServer (stateful process)\ndefmodule Counter do\n  use GenServer\n  def init(_), do: {:ok, 0}\n  def handle_call(:get, _from, state), do: {:reply, state, state}\n  def handle_cast(:inc, state), do: {:noreply, state + 1}\nend\n\n# Agent (simple state)\n{:ok, agent} = Agent.start_link(fn -> 0 end)\nAgent.update(agent, &(&1 + 1))\nAgent.get(agent, &(&1))  # 1",
    "Scala": "import scala.concurrent.{Future, Await}\nimport scala.concurrent.ExecutionContext.Implicits.global\nimport scala.concurrent.duration._\nimport akka.actor._\n\n// Futures\nval f1 = Future { fetch(\"url1\") }\nval f2 = Future { fetch(\"url2\") }\nval combined = for { a <- f1; b <- f2 } yield (a, b)\nval result = Await.result(combined, 10.seconds)\n\n// Actors (Akka)\nclass Counter extends Actor {\n  var count = 0\n  def receive = {\n    case \"inc\" => count += 1\n    case \"get\" => sender() ! count\n  }\n}",
    "Clojure": ";; Atoms (lock-free shared state)\n(def counter (atom 0))\n(swap! counter inc)\n@counter  ;; 1\n\n;; Futures\n(def f (future (fetch \"url\")))\n@f  ;; blocks until done\n\n;; Agents (async state)\n(def a (agent 0))\n(send a inc)\n(await a)\n@a  ;; 1\n\n;; core.async channels\n(require '[clojure.core.async :as async])\n(def ch (async/chan 10))\n(async/go (async/>! ch \"hello\"))\n(async/go (println (async/<! ch)))\n\n;; pmap (parallel map)\n(pmap #(fetch %) [\"url1\" \"url2\" \"url3\"])\n\n;; Refs + STM\n(def balance (ref 100))\n(dosync (alter balance + 50))",
    "C#": "// Task (async/await)\nasync Task<string> FetchAsync(string url) {\n    using var client = new HttpClient();\n    return await client.GetStringAsync(url);\n}\n\n// Parallel\nvar tasks = urls.Select(url => FetchAsync(url));\nvar results = await Task.WhenAll(tasks);\n\n// Thread\nvar thread = new Thread(() => Console.WriteLine(\"Running\"));\nthread.Start();\nthread.Join();\n\n// Lock\nlock (lockObj) { counter++; }\n\n// Parallel.ForEach\nParallel.ForEach(items, item => Process(item));\n\n// Channel\nvar channel = Channel.CreateBounded<int>(10);\nawait channel.Writer.WriteAsync(42);\nvar value = await channel.Reader.ReadAsync();",
    "TypeScript": "// Async/await\nasync function fetchAll(): Promise<string[]> {\n  const results = await Promise.all([\n    fetch('url1').then(r => r.text()),\n    fetch('url2').then(r => r.text()),\n  ]);\n  return results;\n}\n\n// Promise.allSettled\nconst results = await Promise.allSettled([\n  fetch('url1'), fetch('url2')\n]);\nresults.forEach(r => {\n  if (r.status === 'fulfilled') console.log(r.value);\n  else console.error(r.reason);\n});\n\n// Web Workers\nconst worker = new Worker('worker.ts');\nworker.postMessage({task: 'compute'});\nworker.onmessage = (e) => console.log(e.data);",
    "PHP": "// Fibers (PHP 8.1)\n$fiber = new Fiber(function(): void {\n    $value = Fiber::suspend('paused');\n    echo \"Resumed with: $value\\n\";\n});\n$result = $fiber->start();  // 'paused'\n$fiber->resume('hello');\n\n// Parallel (ext-parallel)\nuse parallel\\Runtime;\n$runtime = new Runtime();\n$future = $runtime->run(function() {\n    return file_get_contents('https://api.example.com');\n});\n$result = $future->value();",
    "Lua": "-- Coroutines (cooperative)\nlocal co = coroutine.create(function()\n    for i = 1, 5 do\n        coroutine.yield(i)\n    end\nend)\n\nwhile coroutine.status(co) ~= 'dead' do\n    local ok, val = coroutine.resume(co)\n    if ok then print(val) end\nend\n\n-- Producer-consumer\nlocal function producer()\n    return coroutine.wrap(function()\n        for i = 1, 10 do\n            coroutine.yield(i)\n        end\n    end)\nend\nfor val in producer() do print(val) end",
    "Julia": "# Tasks (green threads)\nt = @async begin\n    sleep(1)\n    return 42\nend\nresult = fetch(t)  # 42\n\n# Threads\nThreads.@threads for i in 1:10\n    println(\"Thread $(Threads.threadid()): $i\")\nend\n\n# Channels\nch = Channel{Int}(32)\n@async for i in 1:5; put!(ch, i); end\n@async for val in ch; println(val); end\n\n# Atomic\ncounter = Threads.Atomic{Int}(0)\nThreads.atomic_add!(counter, 1)\n\n# Distributed\nusing Distributed\naddprocs(4)\n@distributed (+) for i in 1:100; f(i); end",
    "Dart": "// Async/await\nFuture<String> fetchData(String url) async {\n  await Future.delayed(Duration(seconds: 1));\n  return 'Data from $url';\n}\n\nvoid main() async {\n  // Parallel\n  final results = await Future.wait([\n    fetchData('url1'), fetchData('url2'),\n  ]);\n  \n  // Stream\n  Stream.periodic(Duration(seconds: 1), (i) => i)\n      .take(5)\n      .listen((i) => print('Tick $i'));\n  \n  // Isolate (true parallelism)\n  final result = await Isolate.run(() => heavyComputation());\n}",
    "Erlang": "%% Processes\nPid = spawn(fun() ->\n    receive\n        {From, Msg} -> From ! {self(), \"Echo: \" ++ Msg}\n    end\nend),\nPid ! {self(), \"hello\"},\nreceive {Pid, Reply} -> io:format(\"~s~n\", [Reply]) end.\n\n%% Linked processes (fail together)\nPid2 = spawn_link(fun() -> exit(normal) end).\n\n%% Monitor\nRef = monitor(process, Pid),\nreceive {'DOWN', Ref, process, Pid, Reason} -> ok end.\n\n%% gen_server\n-behaviour(gen_server).\ninit([]) -> {ok, 0}.\nhandle_call(get, _From, State) -> {reply, State, State}.\nhandle_cast(inc, State) -> {noreply, State + 1}.",
    "OCaml": "(* Threads *)\nlet t = Thread.create (fun () -> print_endline \"thread\") ()\nThread.join t\n\n(* Mutex *)\nlet mutex = Mutex.create ()\nMutex.lock mutex;\ncounter := !counter + 1;\nMutex.unlock mutex\n\n(* Lwt (async) *)\nopen Lwt.Syntax\nlet* a = fetch \"url1\"\nand* b = fetch \"url2\" in\nLwt.return (a, b)\n\n(* Domain (OCaml 5 multicore) *)\nlet d = Domain.spawn (fun () -> heavy_computation ())\nlet result = Domain.join d",
    "F#": "// Async workflows\nlet fetchAsync url = async {\n    let! response = httpClient.GetStringAsync(url) |> Async.AwaitTask\n    return response\n}\n\n// Parallel\nlet! results =\n    [\"url1\"; \"url2\"; \"url3\"]\n    |> List.map fetchAsync\n    |> Async.Parallel\n\n// MailboxProcessor (actor)\nlet counter = MailboxProcessor.Start(fun inbox ->\n    let rec loop state = async {\n        let! msg = inbox.Receive()\n        match msg with\n        | \"inc\" -> return! loop (state + 1)\n        | \"get\" -> return! loop state\n    }\n    loop 0)",
    "Nim": "import std/[threadpool, locks]\n\n# Spawn threads\nvar lock: Lock\ninitLock(lock)\n\nproc worker(id: int) {.thread.} =\n  acquire(lock)\n  echo \"Thread \", id, \" running\"\n  release(lock)\n\nvar threads: array[4, Thread[int]]\nfor i in 0..3:\n  createThread(threads[i], worker, i)\njoinThreads(threads)\n\n# Async\nimport std/asyncdispatch\nproc fetch(url: string): Future[string] {.async.} =\n  await sleepAsync(1000)\n  return \"Data from \" & url",
    "Crystal": "# Fibers (cooperative)\nch = Channel(Int32).new\n\nspawn do\n  5.times { |i| ch.send(i) }\nend\n\n5.times { puts ch.receive }\n\n# Select\nselect\nwhen x = ch1.receive\n  puts x\nwhen ch2.send(42)\n  puts \"sent\"\nend\n\n# Parallel\nresults = Array(String).new\n3.times do |i|\n  spawn { results << fetch(\"url#{i}\") }\nend\nFiber.yield",
    "Zig": "const std = @import(\"std\");\n\n// Threads\nvar threads: [4]std.Thread = undefined;\nfor (&threads, 0..) |*t, i| {\n    t.* = try std.Thread.spawn(.{}, worker, .{i});\n}\nfor (threads) |t| t.join();\n\nfn worker(id: usize) void {\n    std.debug.print(\"Thread {} running\\n\", .{id});\n}\n\n// Mutex\nvar mutex = std.Thread.Mutex{};\nmutex.lock();\ndefer mutex.unlock();\ncounter += 1;",
    "Racket": ";; Threads\n(define t (thread (lambda () (displayln \"thread running\"))))\n(thread-wait t)\n\n;; Channels\n(define ch (make-channel))\n(thread (lambda () (channel-put ch 42)))\n(channel-get ch)  ;; 42\n\n;; Places (true parallelism)\n(define p (place ch\n  (place-channel-put ch (heavy-computation))))\n(place-channel-get p)\n\n;; Semaphore\n(define sem (make-semaphore 3))\n(semaphore-wait sem)\n;; critical section\n(semaphore-post sem)",
    "D": "import std.parallelism;\nimport std.concurrency;\nimport core.thread;\n\n// Parallel foreach\nauto results = taskPool.amap!((x) => x * 2)(data);\n\n// Threads\nauto t = new Thread({ writeln(\"Thread running\"); });\nt.start();\nt.join();\n\n// Message passing\nauto tid = spawn({\n    receive((int x) { writeln(\"Got: \", x); });\n});\ntid.send(42);\n\n// Mutex\nsynchronized (mutex) { counter++; }",
    "Perl": "use threads;\nuse threads::shared;\n\nmy $counter :shared = 0;\n\n# Create threads\nmy @threads = map {\n    threads->create(sub {\n        lock($counter);\n        $counter++;\n    })\n} 1..4;\n$_->join() for @threads;\nprint \"Counter: $counter\\n\";  # 4\n\n# Async with AnyEvent\nuse AnyEvent;\nmy $cv = AnyEvent->condvar;\n$cv->recv;",
    "R": "library(parallel)\n\n# mclapply (fork-based parallel)\nresults <- mclapply(1:10, function(x) x^2, mc.cores = 4)\n\n# parLapply (cluster-based)\ncl <- makeCluster(4)\nresults <- parLapply(cl, 1:10, function(x) x^2)\nstopCluster(cl)\n\n# future (async)\nlibrary(future)\nplan(multisession, workers = 4)\nf <- future(heavy_computation())\nresult <- value(f)",
}

ROSETTA["io"] = {
    "Python": "import json, csv, os\n\n# Read/write text\nwith open('data.txt', 'r') as f:\n    content = f.read()\nwith open('out.txt', 'w') as f:\n    f.write('Hello World\\n')\n\n# Line by line\nwith open('data.txt') as f:\n    for line in f:\n        print(line.strip())\n\n# JSON\nwith open('data.json') as f:\n    data = json.load(f)\njson.dump(data, open('out.json', 'w'), indent=2)\n\n# CSV\nwith open('data.csv') as f:\n    reader = csv.DictReader(f)\n    for row in reader:\n        print(row)\n\n# Stdin\nname = input('Enter name: ')\nprint(f'Hello, {name}!')\n\n# OS\nos.makedirs('dir/sub', exist_ok=True)\nos.listdir('.')",
    "JavaScript": "const fs = require('fs');\nconst path = require('path');\n\n// Read/write (sync)\nconst data = fs.readFileSync('data.txt', 'utf8');\nfs.writeFileSync('out.txt', 'Hello World');\n\n// Async\nconst content = await fs.promises.readFile('data.txt', 'utf8');\nawait fs.promises.writeFile('out.txt', 'Hello');\n\n// Line by line\nconst readline = require('readline');\nconst rl = readline.createInterface({ input: fs.createReadStream('data.txt') });\nfor await (const line of rl) console.log(line);\n\n// JSON\nconst json = JSON.parse(fs.readFileSync('data.json', 'utf8'));\nfs.writeFileSync('out.json', JSON.stringify(json, null, 2));\n\n// Stdin\nconst answer = await rl.question('Name? ');",
    "Go": "// Read file\ndata, err := os.ReadFile(\"data.txt\")\nif err != nil { log.Fatal(err) }\nfmt.Println(string(data))\n\n// Write file\nos.WriteFile(\"out.txt\", []byte(\"Hello World\"), 0644)\n\n// Line by line\nf, _ := os.Open(\"data.txt\")\nscanner := bufio.NewScanner(f)\nfor scanner.Scan() {\n    fmt.Println(scanner.Text())\n}\nf.Close()\n\n// JSON\nvar result map[string]interface{}\njson.Unmarshal(data, &result)\nout, _ := json.MarshalIndent(result, \"\", \"  \")\nos.WriteFile(\"out.json\", out, 0644)\n\n// Stdin\nreader := bufio.NewReader(os.Stdin)\nfmt.Print(\"Name? \")\nname, _ := reader.ReadString('\\n')\nfmt.Printf(\"Hello, %s\", strings.TrimSpace(name))\n\n// Directory\nos.MkdirAll(\"dir/sub\", 0755)\nentries, _ := os.ReadDir(\".\")",
    "Rust": "use std::fs;\nuse std::io::{self, BufRead, Write};\n\n// Read file\nlet content = fs::read_to_string(\"data.txt\")?;\n\n// Write file\nfs::write(\"out.txt\", \"Hello World\")?;\n\n// Line by line\nlet file = fs::File::open(\"data.txt\")?;\nfor line in io::BufReader::new(file).lines() {\n    println!(\"{}\", line?);\n}\n\n// JSON (serde)\nlet data: Value = serde_json::from_str(&content)?;\nlet json = serde_json::to_string_pretty(&data)?;\nfs::write(\"out.json\", json)?;\n\n// Stdin\nlet mut name = String::new();\nprint!(\"Name? \");\nio::stdout().flush()?;\nio::stdin().read_line(&mut name)?;\nprintln!(\"Hello, {}!\", name.trim());\n\n// Directory\nfs::create_dir_all(\"dir/sub\")?;\nfor entry in fs::read_dir(\".\")? {\n    println!(\"{}\", entry?.path().display());\n}",
    "Java": "// Read file\nString content = Files.readString(Path.of(\"data.txt\"));\n\n// Write file\nFiles.writeString(Path.of(\"out.txt\"), \"Hello World\");\n\n// Line by line\ntry (var reader = Files.newBufferedReader(Path.of(\"data.txt\"))) {\n    String line;\n    while ((line = reader.readLine()) != null) {\n        System.out.println(line);\n    }\n}\n\n// JSON (Jackson)\nObjectMapper mapper = new ObjectMapper();\nvar data = mapper.readValue(new File(\"data.json\"), Map.class);\nmapper.writerWithDefaultPrettyPrinter().writeValue(new File(\"out.json\"), data);\n\n// Stdin\nvar scanner = new Scanner(System.in);\nSystem.out.print(\"Name? \");\nvar name = scanner.nextLine();\n\n// Directory\nFiles.createDirectories(Path.of(\"dir/sub\"));\nFiles.list(Path.of(\".\")).forEach(System.out::println);",
    "C": "#include <stdio.h>\n#include <stdlib.h>\n\n// Read file\nFILE* f = fopen(\"data.txt\", \"r\");\nchar buf[4096];\nwhile (fgets(buf, sizeof(buf), f)) {\n    printf(\"%s\", buf);\n}\nfclose(f);\n\n// Write file\nFILE* out = fopen(\"out.txt\", \"w\");\nfprintf(out, \"Hello World\\n\");\nfclose(out);\n\n// Stdin\nchar name[100];\nprintf(\"Name? \");\nfgets(name, sizeof(name), stdin);\nprintf(\"Hello, %s\", name);\n\n// Binary\nFILE* bin = fopen(\"data.bin\", \"rb\");\nint nums[10];\nfread(nums, sizeof(int), 10, bin);\nfclose(bin);",
    "C++": "#include <fstream>\n#include <filesystem>\nnamespace fs = std::filesystem;\n\n// Read file\nstd::ifstream in(\"data.txt\");\nstd::string content((std::istreambuf_iterator<char>(in)),\n                     std::istreambuf_iterator<char>());\n\n// Write file\nstd::ofstream out(\"out.txt\");\nout << \"Hello World\" << std::endl;\n\n// Line by line\nstd::string line;\nwhile (std::getline(in, line)) {\n    std::cout << line << '\\n';\n}\n\n// Stdin\nstd::string name;\nstd::cout << \"Name? \";\nstd::getline(std::cin, name);\n\n// Directory (C++17)\nfs::create_directories(\"dir/sub\");\nfor (auto& entry : fs::directory_iterator(\".\")) {\n    std::cout << entry.path() << '\\n';\n}",
    "Swift": "import Foundation\n\n// Read file\nlet content = try String(contentsOfFile: \"data.txt\", encoding: .utf8)\n\n// Write file\ntry \"Hello World\".write(toFile: \"out.txt\", atomically: true, encoding: .utf8)\n\n// JSON\nlet jsonData = try Data(contentsOf: URL(fileURLWithPath: \"data.json\"))\nlet decoded = try JSONDecoder().decode(MyType.self, from: jsonData)\n\n// Stdin\nprint(\"Name? \", terminator: \"\")\nlet name = readLine()!\nprint(\"Hello, \\(name)!\")\n\n// Directory\ntry FileManager.default.createDirectory(atPath: \"dir/sub\", withIntermediateDirectories: true)\nlet items = try FileManager.default.contentsOfDirectory(atPath: \".\")",
    "Kotlin": "import java.io.File\nimport java.nio.file.*\n\n// Read/write\nval content = File(\"data.txt\").readText()\nFile(\"out.txt\").writeText(\"Hello World\")\n\n// Line by line\nFile(\"data.txt\").forEachLine { println(it) }\n\n// Buffered\nFile(\"data.txt\").bufferedReader().useLines { lines ->\n    lines.forEach { println(it) }\n}\n\n// JSON (kotlinx.serialization)\nval data = Json.decodeFromString<MyData>(jsonString)\nval json = Json.encodeToString(data)\n\n// Stdin\nprint(\"Name? \")\nval name = readLine()!!\nprintln(\"Hello, $name!\")\n\n// Directory\nFiles.createDirectories(Path(\"dir/sub\"))",
    "Ruby": "# Read/write\ncontent = File.read('data.txt')\nFile.write('out.txt', 'Hello World')\n\n# Line by line\nFile.foreach('data.txt') { |line| puts line }\n\n# JSON\nrequire 'json'\ndata = JSON.parse(File.read('data.json'))\nFile.write('out.json', JSON.pretty_generate(data))\n\n# CSV\nrequire 'csv'\nCSV.foreach('data.csv', headers: true) { |row| puts row }\n\n# Stdin\nprint 'Name? '\nname = gets.chomp\nputs \"Hello, #{name}!\"\n\n# Directory\nFileUtils.mkdir_p('dir/sub')\nDir.entries('.').each { |e| puts e }",
    "Haskell": "import System.IO\nimport System.Directory\nimport Data.Aeson (decode, encode)\n\n-- Read/write\ncontent <- readFile \"data.txt\"\nwriteFile \"out.txt\" \"Hello World\"\n\n-- Line by line\nhandle <- openFile \"data.txt\" ReadMode\ncontents <- hGetContents handle\nmapM_ putStrLn (lines contents)\nhClose handle\n\n-- Stdin\nputStr \"Name? \"\nhFlush stdout\nname <- getLine\nputStrLn $ \"Hello, \" ++ name ++ \"!\"\n\n-- Directory\ncreateDirectoryIfMissing True \"dir/sub\"\nentries <- listDirectory \".\"",
    "Elixir": "# Read/write\ncontent = File.read!(\"data.txt\")\nFile.write!(\"out.txt\", \"Hello World\")\n\n# Line by line\nFile.stream!(\"data.txt\")\n|> Enum.each(&IO.puts/1)\n\n# JSON\ndata = File.read!(\"data.json\") |> Jason.decode!()\njson = Jason.encode!(data, pretty: true)\nFile.write!(\"out.json\", json)\n\n# Stdin\nname = IO.gets(\"Name? \") |> String.trim()\nIO.puts(\"Hello, #{name}!\")\n\n# Directory\nFile.mkdir_p!(\"dir/sub\")\nFile.ls!(\".\")",
    "Scala": "import java.nio.file._\nimport scala.io.Source\n\n// Read\nval content = Source.fromFile(\"data.txt\").mkString\nval lines = Source.fromFile(\"data.txt\").getLines().toList\n\n// Write\nFiles.writeString(Path.of(\"out.txt\"), \"Hello World\")\n\n// JSON (circe)\nimport io.circe.parser._\nval json = parse(content)\n\n// Stdin\nprint(\"Name? \")\nval name = scala.io.StdIn.readLine()\nprintln(s\"Hello, $name!\")\n\n// Directory\nFiles.createDirectories(Path.of(\"dir/sub\"))",
    "PHP": "// Read/write\n$content = file_get_contents('data.txt');\nfile_put_contents('out.txt', 'Hello World');\n\n// Line by line\n$f = fopen('data.txt', 'r');\nwhile (($line = fgets($f)) !== false) {\n    echo $line;\n}\nfclose($f);\n\n// JSON\n$data = json_decode(file_get_contents('data.json'), true);\nfile_put_contents('out.json', json_encode($data, JSON_PRETTY_PRINT));\n\n// CSV\n$f = fopen('data.csv', 'r');\nwhile (($row = fgetcsv($f)) !== false) {\n    print_r($row);\n}\n\n// Stdin\necho 'Name? ';\n$name = trim(fgets(STDIN));\necho \"Hello, $name!\\n\";\n\n// Directory\nmkdir('dir/sub', 0755, true);\nscandir('.');",
    "Lua": "-- Read file\nlocal f = io.open('data.txt', 'r')\nlocal content = f:read('*all')\nf:close()\n\n-- Write file\nlocal f = io.open('out.txt', 'w')\nf:write('Hello World\\n')\nf:close()\n\n-- Line by line\nfor line in io.lines('data.txt') do\n    print(line)\nend\n\n-- Stdin\nio.write('Name? ')\nlocal name = io.read()\nprint('Hello, ' .. name .. '!')",
    "Julia": "# Read/write\ncontent = read(\"data.txt\", String)\nwrite(\"out.txt\", \"Hello World\")\n\n# Line by line\nfor line in eachline(\"data.txt\")\n    println(line)\nend\n\n# JSON\nusing JSON\ndata = JSON.parsefile(\"data.json\")\nopen(\"out.json\", \"w\") do f\n    JSON.print(f, data, 2)\nend\n\n# Stdin\nprint(\"Name? \")\nname = readline()\nprintln(\"Hello, $name!\")\n\n# Directory\nmkpath(\"dir/sub\")\nreaddir(\".\")",
    "Dart": "import 'dart:io';\nimport 'dart:convert';\n\n// Read/write\nfinal content = File('data.txt').readAsStringSync();\nFile('out.txt').writeAsStringSync('Hello World');\n\n// Line by line\nawait File('data.txt')\n    .openRead()\n    .transform(utf8.decoder)\n    .transform(LineSplitter())\n    .forEach(print);\n\n// JSON\nfinal data = jsonDecode(File('data.json').readAsStringSync());\nFile('out.json').writeAsStringSync(JsonEncoder.withIndent('  ').convert(data));\n\n// Stdin\nstdout.write('Name? ');\nfinal name = stdin.readLineSync();\nprint('Hello, $name!');",
    "Nim": "import std/[os, json, strutils]\n\n# Read/write\nlet content = readFile(\"data.txt\")\nwriteFile(\"out.txt\", \"Hello World\")\n\n# Line by line\nfor line in lines(\"data.txt\"):\n  echo line\n\n# JSON\nlet data = parseJson(readFile(\"data.json\"))\nwriteFile(\"out.json\", $data)\n\n# Stdin\nstdout.write(\"Name? \")\nlet name = readLine(stdin)\necho \"Hello, \", name, \"!\"\n\n# Directory\ncreateDir(\"dir/sub\")\nfor f in walkDir(\".\"):\n  echo f.path",
    "Crystal": "# Read/write\ncontent = File.read(\"data.txt\")\nFile.write(\"out.txt\", \"Hello World\")\n\n# Line by line\nFile.each_line(\"data.txt\") { |line| puts line }\n\n# JSON\nrequire \"json\"\ndata = JSON.parse(File.read(\"data.json\"))\nFile.write(\"out.json\", data.to_pretty_json)\n\n# Stdin\nprint \"Name? \"\nname = gets.not_nil!.chomp\nputs \"Hello, #{name}!\"\n\n# Directory\nDir.mkdir_p(\"dir/sub\")\nDir.entries(\".\").each { |e| puts e }",
    "TypeScript": "import * as fs from 'fs';\nimport * as path from 'path';\n\n// Read/write\nconst content: string = fs.readFileSync('data.txt', 'utf8');\nfs.writeFileSync('out.txt', 'Hello World');\n\n// Async\nconst data = await fs.promises.readFile('data.txt', 'utf8');\nawait fs.promises.writeFile('out.txt', 'Hello');\n\n// JSON (typed)\ninterface Config { port: number; host: string; }\nconst config: Config = JSON.parse(fs.readFileSync('config.json', 'utf8'));\n\n// Directory\nawait fs.promises.mkdir('dir/sub', { recursive: true });\nconst entries = await fs.promises.readdir('.');",
    "Erlang": "%% Read file\n{ok, Content} = file:read_file(\"data.txt\"),\nio:format(\"~s~n\", [Content]),\n\n%% Write file\nfile:write_file(\"out.txt\", \"Hello World\"),\n\n%% Line by line\n{ok, Device} = file:open(\"data.txt\", [read]),\nread_lines(Device).\n\nread_lines(Device) ->\n    case io:get_line(Device, \"\") of\n        eof -> file:close(Device);\n        Line -> io:format(\"~s\", [Line]), read_lines(Device)\n    end.\n\n%% Stdin\nio:format(\"Name? \"),\n{ok, Name} = io:fread(\"\", \"~s\"),\nio:format(\"Hello, ~s!~n\", [Name]).",
    "OCaml": "(* Read file *)\nlet content = In_channel.with_open_text \"data.txt\" In_channel.input_all\n\n(* Write file *)\nOut_channel.with_open_text \"out.txt\" (fun oc ->\n  Out_channel.output_string oc \"Hello World\")\n\n(* Line by line *)\nIn_channel.with_open_text \"data.txt\" (fun ic ->\n  try while true do\n    let line = In_channel.input_line ic in\n    print_endline line\n  done with End_of_file -> ())\n\n(* Stdin *)\nprint_string \"Name? \";\nlet name = read_line () in\nPrintf.printf \"Hello, %s!\\n\" name",
    "F#": "open System.IO\n\n// Read/write\nlet content = File.ReadAllText(\"data.txt\")\nFile.WriteAllText(\"out.txt\", \"Hello World\")\n\n// Line by line\nFile.ReadAllLines(\"data.txt\")\n|> Array.iter (printfn \"%s\")\n\n// JSON (System.Text.Json)\nopen System.Text.Json\nlet data = JsonSerializer.Deserialize<MyType>(content)\nlet json = JsonSerializer.Serialize(data, JsonSerializerOptions(WriteIndented = true))\n\n// Stdin\nprintf \"Name? \"\nlet name = System.Console.ReadLine()\nprintfn \"Hello, %s!\" name\n\n// Directory\nDirectory.CreateDirectory(\"dir/sub\") |> ignore",
    "Racket": ";; Read/write\n(define content (file->string \"data.txt\"))\n(display-to-file \"Hello World\" \"out.txt\" #:exists 'replace)\n\n;; Line by line\n(call-with-input-file \"data.txt\"\n  (lambda (in)\n    (for ([line (in-lines in)])\n      (displayln line))))\n\n;; JSON\n(require json)\n(define data (call-with-input-file \"data.json\" read-json))\n(call-with-output-file \"out.json\"\n  (lambda (out) (write-json data out))\n  #:exists 'replace)\n\n;; Stdin\n(display \"Name? \")\n(define name (read-line))\n(printf \"Hello, ~a!\\n\" name)",
    "D": "import std.file, std.stdio, std.json;\n\n// Read/write\nauto content = readText(\"data.txt\");\nstd.file.write(\"out.txt\", \"Hello World\");\n\n// Line by line\nauto f = File(\"data.txt\", \"r\");\nforeach (line; f.byLine()) {\n    writeln(line);\n}\n\n// JSON\nauto data = parseJSON(content);\n\n// Stdin\nwrite(\"Name? \");\nauto name = readln().strip;\nwritefln(\"Hello, %s!\", name);\n\n// Directory\nmkdirRecurse(\"dir/sub\");\nforeach (entry; dirEntries(\".\", SpanMode.shallow)) {\n    writeln(entry.name);\n}",
    "C#": "// Read/write\nstring content = File.ReadAllText(\"data.txt\");\nFile.WriteAllText(\"out.txt\", \"Hello World\");\n\n// Line by line\nforeach (var line in File.ReadLines(\"data.txt\"))\n    Console.WriteLine(line);\n\n// Async\nstring data = await File.ReadAllTextAsync(\"data.txt\");\n\n// JSON (System.Text.Json)\nvar obj = JsonSerializer.Deserialize<MyType>(content);\nstring json = JsonSerializer.Serialize(obj, new() { WriteIndented = true });\n\n// Stdin\nConsole.Write(\"Name? \");\nvar name = Console.ReadLine();\nConsole.WriteLine($\"Hello, {name}!\");\n\n// Directory\nDirectory.CreateDirectory(\"dir/sub\");\nDirectory.GetFiles(\".\");",
    "Perl": "# Read file\nopen(my $fh, '<', 'data.txt') or die $!;\nmy $content = do { local $/; <$fh> };\nclose $fh;\n\n# Write file\nopen(my $out, '>', 'out.txt') or die $!;\nprint $out \"Hello World\\n\";\nclose $out;\n\n# Line by line\nopen(my $f, '<', 'data.txt');\nwhile (<$f>) { print; }\nclose $f;\n\n# JSON\nuse JSON;\nmy $data = decode_json($content);\nmy $json = encode_json($data);\n\n# Stdin\nprint 'Name? ';\nchomp(my $name = <STDIN>);\nprint \"Hello, $name!\\n\";\n\n# Directory\nuse File::Path qw(make_path);\nmake_path('dir/sub');",
    "R": "# Read/write\ncontent <- readLines('data.txt')\nwriteLines('Hello World', 'out.txt')\n\n# CSV\ndata <- read.csv('data.csv')\nwrite.csv(data, 'out.csv', row.names = FALSE)\n\n# JSON\nlibrary(jsonlite)\ndata <- fromJSON('data.json')\nwrite(toJSON(data, pretty = TRUE), 'out.json')\n\n# Stdin\ncat('Name? ')\nname <- readLines(con = 'stdin', n = 1)\ncat(sprintf('Hello, %s!\\n', name))\n\n# Directory\ndir.create('dir/sub', recursive = TRUE)\nlist.files('.')",
    "Zig": "const std = @import(\"std\");\n\n// Read file\nconst file = try std.fs.cwd().openFile(\"data.txt\", .{});\ndefer file.close();\nconst content = try file.readToEndAlloc(allocator, 1024 * 1024);\n\n// Write file\nconst out = try std.fs.cwd().createFile(\"out.txt\", .{});\ndefer out.close();\ntry out.writeAll(\"Hello World\");\n\n// Stdin\nconst stdin = std.io.getStdIn().reader();\nconst stdout = std.io.getStdOut().writer();\ntry stdout.print(\"Name? \", .{});\nconst line = try stdin.readUntilDelimiter(buf, '\\n');",
}

def get_true_rosetta():
    """Generate the TRUE Rosetta Stone with real code."""
    # Merge expanded entries into ROSETTA
    try:
        from seeds.rosetta_expanded import EXPANDED
        for concept, langs in EXPANDED.items():
            if concept not in ROSETTA:
                ROSETTA[concept] = {}
            ROSETTA[concept].update(langs)
    except ImportError:
        pass

    # Merge v2 expanded entries
    try:
        from seeds.rosetta_expanded_v2 import EXPANDED_V2
        for concept, langs in EXPANDED_V2.items():
            if concept not in ROSETTA:
                ROSETTA[concept] = {}
            ROSETTA[concept].update(langs)
    except ImportError:
        pass

    # Merge v3 expanded entries
    try:
        from seeds.rosetta_expanded_v3 import EXPANDED_V3
        for concept, langs in EXPANDED_V3.items():
            if concept not in ROSETTA:
                ROSETTA[concept] = {}
            ROSETTA[concept].update(langs)
    except ImportError:
        pass

    # Merge v4 expanded entries
    try:
        from seeds.rosetta_expanded_v4 import EXPANDED_V4
        for concept, langs in EXPANDED_V4.items():
            if concept not in ROSETTA:
                ROSETTA[concept] = {}
            ROSETTA[concept].update(langs)
    except ImportError:
        pass

    # Merge v5 expanded entries
    try:
        from seeds.rosetta_expanded_v5 import EXPANDED_V5
        for concept, langs in EXPANDED_V5.items():
            if concept not in ROSETTA:
                ROSETTA[concept] = {}
            ROSETTA[concept].update(langs)
    except ImportError:
        pass

    # Merge v6 expanded entries
    try:
        from seeds.rosetta_expanded_v6 import EXPANDED_V6
        for concept, langs in EXPANDED_V6.items():
            if concept not in ROSETTA:
                ROSETTA[concept] = {}
            ROSETTA[concept].update(langs)
    except ImportError:
        pass

    # Merge v7 expanded entries
    try:
        from seeds.rosetta_expanded_v7 import EXPANDED_V7
        for concept, langs in EXPANDED_V7.items():
            if concept not in ROSETTA:
                ROSETTA[concept] = {}
            ROSETTA[concept].update(langs)
    except ImportError:
        pass

    # Merge v8 expanded entries
    try:
        from seeds.rosetta_expanded_v8 import EXPANDED_V8
        for concept, langs in EXPANDED_V8.items():
            if concept not in ROSETTA:
                ROSETTA[concept] = {}
            ROSETTA[concept].update(langs)
    except ImportError:
        pass

    # Merge v9 expanded entries
    try:
        from seeds.rosetta_expanded_v9 import EXPANDED_V9
        for concept, langs in EXPANDED_V9.items():
            if concept not in ROSETTA:
                ROSETTA[concept] = {}
            ROSETTA[concept].update(langs)
    except ImportError:
        pass

    
    # Merge v10 expanded entries
    try:
        from seeds.rosetta_expanded_v10 import EXPANDED_V10
        for concept, langs in EXPANDED_V10.items():
            if concept not in ROSETTA:
                ROSETTA[concept] = {}
            ROSETTA[concept].update(langs)
    except ImportError:
        pass

    
    # Merge v11 expanded entries
    try:
        from seeds.rosetta_expanded_v11 import EXPANDED_V11
        for concept, langs in EXPANDED_V11.items():
            if concept not in ROSETTA:
                ROSETTA[concept] = {}
            ROSETTA[concept].update(langs)
    except ImportError:
        pass

    
    # Merge v12 expanded entries
    try:
        from seeds.rosetta_expanded_v12 import EXPANDED_V12
        for concept, langs in EXPANDED_V12.items():
            if concept not in ROSETTA:
                ROSETTA[concept] = {}
            ROSETTA[concept].update(langs)
    except ImportError:
        pass

    
    # Merge v13 expanded entries
    try:
        from seeds.rosetta_expanded_v13 import EXPANDED_V13
        for concept, langs in EXPANDED_V13.items():
            if concept not in ROSETTA:
                ROSETTA[concept] = {}
            ROSETTA[concept].update(langs)
    except ImportError:
        pass

    
    # Merge v14 expanded entries
    try:
        from seeds.rosetta_expanded_v14 import EXPANDED_V14
        for concept, langs in EXPANDED_V14.items():
            if concept not in ROSETTA:
                ROSETTA[concept] = {}
            ROSETTA[concept].update(langs)
    except ImportError:
        pass

    
    # Merge v15 expanded entries
    try:
        from seeds.rosetta_expanded_v15 import EXPANDED_V15
        for concept, langs in EXPANDED_V15.items():
            if concept not in ROSETTA:
                ROSETTA[concept] = {}
            ROSETTA[concept].update(langs)
    except ImportError:
        pass

    
    # Merge v16-18 expanded entries
    try:
        from seeds.rosetta_expanded_v16_18 import EXPANDED_V16_18
        for concept, langs in EXPANDED_V16_18.items():
            if concept not in ROSETTA:
                ROSETTA[concept] = {}
            ROSETTA[concept].update(langs)
    except ImportError:
        pass

    
    # Merge v19-22 expanded entries
    try:
        from seeds.rosetta_expanded_v19_22 import EXPANDED_V19_22
        for concept, langs in EXPANDED_V19_22.items():
            if concept not in ROSETTA:
                ROSETTA[concept] = {}
            ROSETTA[concept].update(langs)
    except ImportError:
        pass

    
    try:
        from seeds.rosetta_expanded_v23_26 import EXPANDED_V23_26
        for concept, langs in EXPANDED_V23_26.items():
            if concept not in ROSETTA: ROSETTA[concept] = {}
            ROSETTA[concept].update(langs)
    except ImportError: pass

    try:
        from seeds.rosetta_expanded_v27_32 import EXPANDED_V27_32
        for concept, langs in EXPANDED_V27_32.items():
            if concept not in ROSETTA: ROSETTA[concept] = {}
            ROSETTA[concept].update(langs)
    except ImportError: pass

    
    try:
        from seeds.rosetta_expanded_v33_36 import EXPANDED_V33_36
        for concept, langs in EXPANDED_V33_36.items():
            if concept not in ROSETTA: ROSETTA[concept] = {}
            ROSETTA[concept].update(langs)
    except ImportError: pass

    
    try:
        from seeds.rosetta_expanded_v37_40 import EXPANDED_V37_40
        for concept, langs in EXPANDED_V37_40.items():
            if concept not in ROSETTA: ROSETTA[concept] = {}
            ROSETTA[concept].update(langs)
    except ImportError: pass

    
    try:
        from seeds.rosetta_expanded_v41_45 import EXPANDED_V41_45
        for concept, langs in EXPANDED_V41_45.items():
            if concept not in ROSETTA: ROSETTA[concept] = {}
            ROSETTA[concept].update(langs)
    except ImportError: pass

    
    try:
        from seeds.rosetta_expanded_v46_50 import EXPANDED_V46_50
        for concept, langs in EXPANDED_V46_50.items():
            if concept not in ROSETTA: ROSETTA[concept] = {}
            ROSETTA[concept].update(langs)
    except ImportError: pass

    
    try:
        from seeds.rosetta_expanded_v51_55 import EXPANDED_V51_55
        for concept, langs in EXPANDED_V51_55.items():
            if concept not in ROSETTA: ROSETTA[concept] = {}
            ROSETTA[concept].update(langs)
    except ImportError: pass

    
    try:
        from seeds.rosetta_expanded_v56_60 import EXPANDED_V56_60
        for concept, langs in EXPANDED_V56_60.items():
            if concept not in ROSETTA: ROSETTA[concept] = {}
            ROSETTA[concept].update(langs)
    except ImportError: pass

    
    try:
        from seeds.rosetta_expanded_v61_65 import EXPANDED_V61_65
        for concept, langs in EXPANDED_V61_65.items():
            if concept not in ROSETTA: ROSETTA[concept] = {}
            ROSETTA[concept].update(langs)
    except ImportError: pass

    
    try:
        from seeds.rosetta_expanded_v66_70 import EXPANDED_V66_70
        for concept, langs in EXPANDED_V66_70.items():
            if concept not in ROSETTA: ROSETTA[concept] = {}
            ROSETTA[concept].update(langs)
    except ImportError: pass

    
    try:
        from seeds.rosetta_expanded_v71_75 import EXPANDED_V71_75
        for concept, langs in EXPANDED_V71_75.items():
            if concept not in ROSETTA: ROSETTA[concept] = {}
            ROSETTA[concept].update(langs)
    except ImportError: pass

    
    try:
        from seeds.rosetta_expanded_v76_80 import EXPANDED_V76_80
        for concept, langs in EXPANDED_V76_80.items():
            if concept not in ROSETTA: ROSETTA[concept] = {}
            ROSETTA[concept].update(langs)
    except ImportError: pass

    
    try:
        from seeds.rosetta_expanded_v81_85 import EXPANDED_V81_85
        for concept, langs in EXPANDED_V81_85.items():
            if concept not in ROSETTA: ROSETTA[concept] = {}
            ROSETTA[concept].update(langs)
    except ImportError: pass

    
    try:
        from seeds.rosetta_expanded_v86_90 import EXPANDED_V86_90
        for concept, langs in EXPANDED_V86_90.items():
            if concept not in ROSETTA: ROSETTA[concept] = {}
            ROSETTA[concept].update(langs)
    except ImportError: pass

    
    try:
        from seeds.rosetta_expanded_v91_94 import EXPANDED_V91_94
        for concept, langs in EXPANDED_V91_94.items():
            if concept not in ROSETTA: ROSETTA[concept] = {}
            ROSETTA[concept].update(langs)
    except ImportError: pass

    
    try:
        from seeds.rosetta_expanded_v95_100 import EXPANDED_V95_100
        for concept, langs in EXPANDED_V95_100.items():
            if concept not in ROSETTA: ROSETTA[concept] = {}
            ROSETTA[concept].update(langs)
    except ImportError: pass

    
    try:
        from seeds.rosetta_expanded_massive import EXPANDED_MASSIVE
        for concept, langs in EXPANDED_MASSIVE.items():
            if concept not in ROSETTA: ROSETTA[concept] = {}
            ROSETTA[concept].update(langs)
    except ImportError: pass

    entries = []
    idx = 0
    for concept, lang_codes in ROSETTA.items():
        cn = concept.replace('_',' ').title()
        for lang, code in lang_codes.items():
            idx += 1
            entries.append({
                "id": f"rosetta_{idx}",
                "concept": concept,
                "concept_name": cn,
                "language": lang,
                "code": code,
                "category": "rosetta_stone",
                "has_code": True,
                "code_lines": len(code.split('\n')),
                "source": "handcrafted",
            })
    return entries
