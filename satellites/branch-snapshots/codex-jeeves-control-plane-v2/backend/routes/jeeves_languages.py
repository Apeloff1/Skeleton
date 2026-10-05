"""
Jeeves All-Language Knowledge Base
Version: 1.0.0 | Complete Programming Language Tutoring
Teaches Jeeves every programming language with rich curriculum knowledge
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

router = APIRouter(prefix="/api/jeeves-languages", tags=["jeeves-languages"])

# =============================================================================
# JEEVES LANGUAGE KNOWLEDGE BASE
# =============================================================================

class LanguageKnowledge(BaseModel):
    language_id: str
    name: str
    teaching_style: str
    greeting: str
    core_concepts: List[str]
    common_mistakes: List[Dict[str, str]]
    best_practices: List[str]
    code_snippets: Dict[str, str]
    difficulty_tips: Dict[str, str]
    related_languages: List[str]
    ecosystem: List[str]
    history_note: str


# Jeeves' complete knowledge base for all languages
JEEVES_LANGUAGE_KB: Dict[str, LanguageKnowledge] = {
    "python": LanguageKnowledge(
        language_id="python",
        name="Python",
        teaching_style="Warm and encouraging — Python is the friendliest language to start with.",
        greeting="Ah, Python! An excellent choice, if I may say so. Shall we begin with something elegant?",
        core_concepts=[
            "Variables & Data Types (int, float, str, bool, list, dict, set, tuple)",
            "Control Flow (if/elif/else, for, while, match/case)",
            "Functions & Decorators (*args, **kwargs, closures, @decorator)",
            "Object-Oriented Programming (classes, inheritance, dunder methods)",
            "Iterators & Generators (yield, generator expressions)",
            "Context Managers (with statement, __enter__/__exit__)",
            "Async/Await (asyncio, coroutines, event loop)",
            "Type Hints & Generics (typing module, Protocol, TypeVar)",
            "Metaclasses & Descriptors (advanced OOP)",
            "Testing (pytest, unittest, mocking)"
        ],
        common_mistakes=[
            {"mistake": "Mutable default arguments", "fix": "Use None as default and create inside function"},
            {"mistake": "Not using list comprehensions", "fix": "Replace simple for-loops with comprehensions"},
            {"mistake": "Ignoring PEP 8", "fix": "Use black or autopep8 for formatting"},
            {"mistake": "Bare except clauses", "fix": "Always catch specific exceptions"},
            {"mistake": "Not using virtual environments", "fix": "Always use venv or poetry"}
        ],
        best_practices=[
            "Use type hints everywhere for better IDE support",
            "Prefer pathlib over os.path for file operations",
            "Use dataclasses or Pydantic for data models",
            "Write docstrings for all public functions",
            "Use f-strings for string formatting",
            "Leverage context managers for resource management"
        ],
        code_snippets={
            "hello": 'print("Hello, World!")',
            "list_comp": "squares = [x**2 for x in range(10) if x % 2 == 0]",
            "decorator": "from functools import wraps\ndef timer(func):\n    @wraps(func)\n    def wrapper(*args, **kwargs):\n        import time; start = time.time()\n        result = func(*args, **kwargs)\n        print(f'{func.__name__} took {time.time()-start:.2f}s')\n        return result\n    return wrapper",
            "async": "import asyncio\nasync def fetch(url):\n    await asyncio.sleep(1)\n    return f'Data from {url}'\nasyncio.run(fetch('https://api.example.com'))"
        },
        difficulty_tips={
            "beginner": "Start with print(), variables, and simple loops. Python reads like English!",
            "intermediate": "Master list comprehensions, OOP, and error handling.",
            "advanced": "Dive into async programming, metaclasses, and C extensions.",
            "expert": "Contribute to CPython, build frameworks, optimize with Cython."
        },
        related_languages=["Ruby", "JavaScript", "Julia"],
        ecosystem=["pip", "PyPI", "conda", "poetry", "venv"],
        history_note="Created by Guido van Rossum in 1991, named after Monty Python."
    ),
    "javascript": LanguageKnowledge(
        language_id="javascript",
        name="JavaScript",
        teaching_style="Dynamic and practical — the language of the web.",
        greeting="JavaScript! The Swiss Army knife of programming. Let's make the web dance, shall we?",
        core_concepts=[
            "Variables & Scope (var, let, const, hoisting, closures)",
            "Data Types & Coercion (primitives, objects, type coercion)",
            "Functions (arrow, higher-order, callbacks, IIFE)",
            "Prototypes & Classes (prototype chain, ES6 classes)",
            "Async Programming (callbacks, promises, async/await)",
            "Event Loop (call stack, task queue, microtasks)",
            "DOM Manipulation (selectors, events, virtual DOM concepts)",
            "Modules (ES modules, CommonJS, dynamic imports)",
            "Error Handling (try/catch, custom errors, error boundaries)",
            "Modern Features (destructuring, spread, optional chaining, nullish coalescing)"
        ],
        common_mistakes=[
            {"mistake": "Using == instead of ===", "fix": "Always use strict equality ==="},
            {"mistake": "Callback hell", "fix": "Use async/await or Promise chains"},
            {"mistake": "Not understanding 'this'", "fix": "Use arrow functions or .bind()"},
            {"mistake": "Forgetting var creates globals", "fix": "Always use let or const"},
            {"mistake": "Mutating objects accidentally", "fix": "Use spread operator or structuredClone"}
        ],
        best_practices=[
            "Use const by default, let when needed, never var",
            "Prefer async/await over raw Promises",
            "Use optional chaining (?.) and nullish coalescing (??)",
            "Leverage destructuring for cleaner code",
            "Use TypeScript for large projects",
            "Always handle Promise rejections"
        ],
        code_snippets={
            "hello": 'console.log("Hello, World!");',
            "async": "const fetchData = async (url) => {\n  try {\n    const res = await fetch(url);\n    return await res.json();\n  } catch (err) {\n    console.error('Fetch failed:', err);\n  }\n};",
            "destructure": "const { name, age, ...rest } = user;\nconst [first, ...others] = items;",
            "class": "class EventEmitter {\n  #listeners = new Map();\n  on(event, fn) { this.#listeners.set(event, [...(this.#listeners.get(event) || []), fn]); }\n  emit(event, ...args) { this.#listeners.get(event)?.forEach(fn => fn(...args)); }\n}"
        },
        difficulty_tips={
            "beginner": "Start with console.log, variables, and DOM manipulation.",
            "intermediate": "Master async/await, closures, and the event loop.",
            "advanced": "Build with Node.js, understand V8 internals, and design patterns.",
            "expert": "Optimize bundle sizes, build compilers, contribute to V8."
        },
        related_languages=["TypeScript", "Python", "Dart"],
        ecosystem=["npm", "yarn", "pnpm", "webpack", "vite", "esbuild"],
        history_note="Created by Brendan Eich in 10 days at Netscape in 1995."
    ),
    "typescript": LanguageKnowledge(
        language_id="typescript",
        name="TypeScript",
        teaching_style="Precise and methodical — type safety is your friend.",
        greeting="TypeScript! Ah, JavaScript's more disciplined sibling. Let's write code that practically documents itself.",
        core_concepts=[
            "Type System (primitives, objects, arrays, tuples, enums)",
            "Interfaces & Type Aliases (structural typing, extends, implements)",
            "Generics (functions, classes, constraints, conditional types)",
            "Utility Types (Partial, Required, Pick, Omit, Record, Exclude)",
            "Union & Intersection Types (discriminated unions, type guards)",
            "Type Narrowing (typeof, instanceof, in, custom guards)",
            "Decorators (class, method, property, parameter)",
            "Module System (ES modules, declaration files, triple-slash)",
            "Advanced Patterns (mapped types, template literals, infer)",
            "Configuration (tsconfig.json, strict mode, project references)"
        ],
        common_mistakes=[
            {"mistake": "Using 'any' everywhere", "fix": "Use 'unknown' and type guards instead"},
            {"mistake": "Ignoring strict mode", "fix": "Enable strict: true in tsconfig"},
            {"mistake": "Overcomplicating types", "fix": "Start simple, refine as needed"},
            {"mistake": "Not using discriminated unions", "fix": "Add a 'type' or 'kind' discriminant"},
            {"mistake": "Forgetting null checks", "fix": "Enable strictNullChecks"}
        ],
        best_practices=[
            "Enable strict mode in tsconfig.json",
            "Use discriminated unions for state machines",
            "Prefer interfaces for object shapes, type aliases for unions",
            "Leverage generic constraints for reusable code",
            "Write .d.ts files for untyped libraries",
            "Use const assertions for literal types"
        ],
        code_snippets={
            "generics": "function first<T>(arr: T[]): T | undefined {\n  return arr[0];\n}",
            "discriminated": "type Shape =\n  | { kind: 'circle'; radius: number }\n  | { kind: 'rect'; width: number; height: number };\n\nfunction area(s: Shape): number {\n  switch (s.kind) {\n    case 'circle': return Math.PI * s.radius ** 2;\n    case 'rect': return s.width * s.height;\n  }\n}",
            "utility": "type UserUpdate = Partial<Pick<User, 'name' | 'email'>>;"
        },
        difficulty_tips={
            "beginner": "Learn basic types first: string, number, boolean, arrays.",
            "intermediate": "Master generics and utility types.",
            "advanced": "Build type-safe APIs with conditional and mapped types.",
            "expert": "Create type-level programming and compiler plugins."
        },
        related_languages=["JavaScript", "C#", "Java"],
        ecosystem=["tsc", "ts-node", "tsx", "tsup", "dts-gen"],
        history_note="Created by Anders Hejlsberg at Microsoft in 2012."
    ),
    "rust": LanguageKnowledge(
        language_id="rust",
        name="Rust",
        teaching_style="Patient but demanding — the borrow checker is your best teacher.",
        greeting="Rust! A language that demands excellence. Don't worry, I'll guide you through every lifetime.",
        core_concepts=[
            "Ownership & Borrowing (move semantics, references, lifetimes)",
            "Pattern Matching (match, if let, while let, destructuring)",
            "Traits & Generics (trait bounds, associated types, impl)",
            "Error Handling (Result, Option, ? operator, custom errors)",
            "Enums & Structs (algebraic data types, methods, derive)",
            "Concurrency (threads, channels, Mutex, Arc, Send/Sync)",
            "Async Programming (Future, async/await, Tokio)",
            "Unsafe Rust (raw pointers, FFI, union types)",
            "Macros (declarative and procedural)",
            "Cargo & Crates (dependency management, workspaces)"
        ],
        common_mistakes=[
            {"mistake": "Fighting the borrow checker", "fix": "Think in terms of ownership first"},
            {"mistake": "Cloning everything", "fix": "Use references and lifetimes properly"},
            {"mistake": "Not using Result/Option", "fix": "Embrace Rust's error handling"},
            {"mistake": "Ignoring clippy warnings", "fix": "Run cargo clippy regularly"},
            {"mistake": "Overusing unsafe", "fix": "Only use when absolutely necessary"}
        ],
        best_practices=[
            "Let the compiler guide you — read error messages carefully",
            "Use cargo clippy and cargo fmt religiously",
            "Prefer &str over String for function parameters",
            "Use derive macros for common traits",
            "Write tests with #[cfg(test)] modules",
            "Use enum for state machines"
        ],
        code_snippets={
            "hello": 'fn main() {\n    println!("Hello, World!");\n}',
            "ownership": "fn take_ownership(s: String) {\n    println!(\"{}\", s);\n} // s is dropped here\n\nfn borrow(s: &str) {\n    println!(\"{}\", s);\n} // s is NOT dropped",
            "enum": "enum Shape {\n    Circle(f64),\n    Rectangle(f64, f64),\n}\nimpl Shape {\n    fn area(&self) -> f64 {\n        match self {\n            Shape::Circle(r) => std::f64::consts::PI * r * r,\n            Shape::Rectangle(w, h) => w * h,\n        }\n    }\n}"
        },
        difficulty_tips={
            "beginner": "Focus on ownership. Once you grok it, Rust clicks.",
            "intermediate": "Master traits, generics, and error handling.",
            "advanced": "Build async systems with Tokio, write macros.",
            "expert": "Contribute to the compiler, write no_std embedded code."
        },
        related_languages=["C++", "Haskell", "OCaml"],
        ecosystem=["cargo", "crates.io", "rustup", "clippy", "rustfmt"],
        history_note="Created by Graydon Hoare at Mozilla, first stable release in 2015."
    ),
    "go": LanguageKnowledge(
        language_id="go",
        name="Go",
        teaching_style="Direct and simple — Go values clarity over cleverness.",
        greeting="Go! The language of cloud-native infrastructure. Simple, fast, and concurrent. Shall we build something?",
        core_concepts=[
            "Variables & Types (declaration, inference, zero values)",
            "Functions (multiple returns, named returns, defer)",
            "Structs & Methods (value vs pointer receivers, embedding)",
            "Interfaces (implicit implementation, composition)",
            "Goroutines & Channels (concurrency, fan-in/fan-out, select)",
            "Error Handling (error interface, wrapping, sentinel errors)",
            "Packages & Modules (go mod, imports, visibility)",
            "Slices & Maps (make, append, range, capacity)",
            "Context (cancellation, deadlines, values)",
            "Generics (type parameters, constraints, Go 1.18+)"
        ],
        common_mistakes=[
            {"mistake": "Goroutine leaks", "fix": "Always use context for cancellation"},
            {"mistake": "Nil pointer dereference", "fix": "Check nil before using pointers"},
            {"mistake": "Forgetting to close channels", "fix": "Use defer close(ch)"},
            {"mistake": "Not handling errors", "fix": "Always check returned errors"},
            {"mistake": "Race conditions", "fix": "Use -race flag and sync primitives"}
        ],
        best_practices=[
            "Accept interfaces, return structs",
            "Use context.Context for cancellation",
            "Keep functions small and focused",
            "Use go vet and golangci-lint",
            "Write table-driven tests",
            "Prefer channels over shared memory"
        ],
        code_snippets={
            "hello": 'package main\nimport "fmt"\nfunc main() {\n    fmt.Println("Hello, World!")\n}',
            "goroutines": "func worker(id int, jobs <-chan int, results chan<- int) {\n    for j := range jobs {\n        results <- j * 2\n    }\n}",
            "interface": "type Writer interface {\n    Write(data []byte) (int, error)\n}"
        },
        difficulty_tips={
            "beginner": "Go is simple by design. Focus on goroutines early.",
            "intermediate": "Master interfaces and concurrent patterns.",
            "advanced": "Build high-performance HTTP servers and CLI tools.",
            "expert": "Contribute to the Go compiler, write runtime optimizations."
        },
        related_languages=["C", "Python", "Rust"],
        ecosystem=["go mod", "go vet", "golangci-lint", "delve"],
        history_note="Created at Google by Rob Pike, Ken Thompson, and Robert Griesemer in 2009."
    ),
    "java": LanguageKnowledge(
        language_id="java",
        name="Java",
        teaching_style="Structured and enterprise-ready — the backbone of large systems.",
        greeting="Java! The workhorse of enterprise software. Let's build something robust and scalable.",
        core_concepts=[
            "OOP (classes, interfaces, abstract classes, inheritance)",
            "Generics (bounded types, wildcards, type erasure)",
            "Collections Framework (List, Set, Map, Queue, Stream)",
            "Concurrency (threads, ExecutorService, CompletableFuture)",
            "Streams API (filter, map, reduce, collect)",
            "Records & Sealed Classes (Java 17+)",
            "Pattern Matching (instanceof, switch, Java 21)",
            "Virtual Threads (Project Loom, Java 21)",
            "Modules (JPMS, module-info.java)",
            "JVM Internals (GC, JIT, classloading)"
        ],
        common_mistakes=[
            {"mistake": "Not closing resources", "fix": "Use try-with-resources"},
            {"mistake": "Using raw types", "fix": "Always specify generic type parameters"},
            {"mistake": "Mutable shared state", "fix": "Use concurrent collections or synchronization"},
            {"mistake": "Catching Exception", "fix": "Catch specific exceptions"},
            {"mistake": "Ignoring equals/hashCode", "fix": "Override both or use records"}
        ],
        best_practices=[
            "Use records for DTOs (Java 17+)",
            "Prefer composition over inheritance",
            "Use Optional instead of null",
            "Leverage Stream API for collections",
            "Use sealed classes for closed hierarchies",
            "Write unit tests with JUnit 5"
        ],
        code_snippets={
            "hello": 'public class Main {\n    public static void main(String[] args) {\n        System.out.println("Hello, World!");\n    }\n}',
            "record": "record Point(double x, double y) {\n    double distance() { return Math.sqrt(x*x + y*y); }\n}",
            "stream": "var result = items.stream()\n    .filter(i -> i.getPrice() > 100)\n    .map(Item::getName)\n    .collect(Collectors.toList());"
        },
        difficulty_tips={
            "beginner": "Start with classes, objects, and the main method.",
            "intermediate": "Master generics, collections, and streams.",
            "advanced": "Learn concurrency, JVM tuning, and Spring Boot.",
            "expert": "Optimize GC, build custom classloaders, contribute to OpenJDK."
        },
        related_languages=["Kotlin", "Scala", "C#"],
        ecosystem=["Maven", "Gradle", "Spring Boot", "JUnit", "IntelliJ IDEA"],
        history_note="Created by James Gosling at Sun Microsystems in 1995."
    ),
    "cpp": LanguageKnowledge(
        language_id="cpp",
        name="C++",
        teaching_style="Challenging but rewarding — raw power with modern elegance.",
        greeting="C++! The language that powers game engines and operating systems. Ready for some real power?",
        core_concepts=[
            "Memory Management (pointers, references, RAII, smart pointers)",
            "OOP (classes, virtual functions, multiple inheritance)",
            "Templates (function, class, variadic, SFINAE, concepts)",
            "STL (containers, algorithms, iterators)",
            "Move Semantics (rvalue references, std::move, perfect forwarding)",
            "Lambdas (captures, generic lambdas, constexpr lambdas)",
            "Concurrency (threads, mutexes, atomics, futures)",
            "Coroutines (co_await, co_yield, co_return)",
            "Modules (import, export, module partitions)",
            "Concepts & Ranges (C++20 constraints, views, adapters)"
        ],
        common_mistakes=[
            {"mistake": "Memory leaks", "fix": "Use smart pointers (unique_ptr, shared_ptr)"},
            {"mistake": "Dangling references", "fix": "Understand object lifetimes"},
            {"mistake": "Not using RAII", "fix": "Wrap resources in classes with destructors"},
            {"mistake": "Undefined behavior", "fix": "Use sanitizers and static analysis"},
            {"mistake": "Overusing inheritance", "fix": "Prefer composition and templates"}
        ],
        best_practices=[
            "Use unique_ptr by default for ownership",
            "Prefer const& parameters for read-only access",
            "Use constexpr for compile-time computation",
            "Enable warnings: -Wall -Wextra -Wpedantic",
            "Use std::optional instead of null pointers",
            "Leverage ranges and views for data processing"
        ],
        code_snippets={
            "hello": '#include <iostream>\nint main() {\n    std::cout << "Hello, World!" << std::endl;\n    return 0;\n}',
            "smart_ptr": "auto ptr = std::make_unique<Widget>();\nauto shared = std::make_shared<Data>(42);",
            "concept": "template<typename T>\nconcept Numeric = std::integral<T> || std::floating_point<T>;"
        },
        difficulty_tips={
            "beginner": "Start with basic I/O, variables, and functions.",
            "intermediate": "Master pointers, classes, and STL containers.",
            "advanced": "Learn templates, move semantics, and concurrency.",
            "expert": "Optimize compilers, write game engines, contribute to standards."
        },
        related_languages=["C", "Rust", "D"],
        ecosystem=["CMake", "vcpkg", "Conan", "clang-tidy", "Valgrind"],
        history_note="Created by Bjarne Stroustrup at Bell Labs in 1979 as 'C with Classes'."
    ),
    "c": LanguageKnowledge(
        language_id="c",
        name="C",
        teaching_style="Foundational and precise — understanding C means understanding computers.",
        greeting="C! The mother of modern programming. Let's get close to the metal, shall we?",
        core_concepts=[
            "Types & Variables (int, char, float, sizeof, typedef)",
            "Pointers (address-of, dereference, pointer arithmetic)",
            "Memory (malloc, calloc, realloc, free, stack vs heap)",
            "Arrays & Strings (char arrays, string.h, buffer management)",
            "Structs & Unions (composite types, bit fields)",
            "Functions (prototypes, function pointers, callbacks)",
            "Preprocessor (macros, conditional compilation, include guards)",
            "File I/O (fopen, fread, fwrite, fclose)",
            "Linked Data Structures (linked lists, trees, graphs)",
            "System Programming (signals, processes, sockets)"
        ],
        common_mistakes=[
            {"mistake": "Buffer overflows", "fix": "Always check bounds and use strncpy"},
            {"mistake": "Memory leaks", "fix": "Free every malloc, use valgrind"},
            {"mistake": "Uninitialized variables", "fix": "Always initialize variables"},
            {"mistake": "Off-by-one errors", "fix": "Careful with array indexing"},
            {"mistake": "Dangling pointers", "fix": "Set pointers to NULL after free"}
        ],
        best_practices=[
            "Compile with -Wall -Wextra -Werror",
            "Use valgrind to detect memory issues",
            "Follow the single responsibility principle",
            "Write header files with include guards",
            "Use const for read-only parameters",
            "Document all function signatures"
        ],
        code_snippets={
            "hello": '#include <stdio.h>\nint main() {\n    printf("Hello, World!\\n");\n    return 0;\n}',
            "malloc": "int *arr = malloc(n * sizeof(int));\nif (!arr) { perror(\"malloc\"); exit(1); }\n// ... use arr ...\nfree(arr);"
        },
        difficulty_tips={
            "beginner": "Start with printf, variables, and control flow.",
            "intermediate": "Master pointers and dynamic memory.",
            "advanced": "Build data structures, understand system calls.",
            "expert": "Write kernel modules, build compilers, optimize assembly."
        },
        related_languages=["C++", "Rust", "Zig"],
        ecosystem=["GCC", "Clang", "Make", "CMake", "Valgrind"],
        history_note="Created by Dennis Ritchie at Bell Labs in 1972."
    ),
    "kotlin": LanguageKnowledge(
        language_id="kotlin", name="Kotlin",
        teaching_style="Modern and concise — Java, but better.",
        greeting="Kotlin! Google's preferred language for Android. Clean, safe, and a joy to write.",
        core_concepts=["Null Safety", "Data Classes", "Coroutines", "Extension Functions", "Sealed Classes", "Delegation", "DSLs", "Inline Functions", "Multiplatform", "Flow API"],
        common_mistakes=[{"mistake": "Overusing !!", "fix": "Use safe calls ?. and let"}, {"mistake": "Ignoring coroutine scope", "fix": "Use structured concurrency"}],
        best_practices=["Use val over var", "Leverage data classes", "Use coroutines for async", "Prefer sealed classes for state"],
        code_snippets={"hello": 'fun main() = println("Hello, World!")', "null_safe": "val len = name?.length ?: 0"},
        difficulty_tips={"beginner": "If you know Java, Kotlin is an easy transition.", "intermediate": "Master coroutines and Flow.", "advanced": "Build Compose Multiplatform apps.", "expert": "Write compiler plugins."},
        related_languages=["Java", "Scala", "Swift"],
        ecosystem=["Gradle", "IntelliJ IDEA", "Android Studio", "Ktor"],
        history_note="Created by JetBrains, first released in 2011."
    ),
    "swift": LanguageKnowledge(
        language_id="swift", name="Swift",
        teaching_style="Elegant and safe — Apple's modern language.",
        greeting="Swift! The language that powers every iPhone and Mac. Let's craft something beautiful.",
        core_concepts=["Optionals", "Protocols", "Generics", "Closures", "Actors", "Async/Await", "SwiftUI", "Property Wrappers", "Result Builders", "Macros (Swift 5.9)"],
        common_mistakes=[{"mistake": "Force unwrapping", "fix": "Use if let or guard let"}, {"mistake": "Retain cycles", "fix": "Use [weak self] in closures"}],
        best_practices=["Use guard for early returns", "Prefer value types (structs)", "Use protocols for abstraction", "Leverage SwiftUI for UI"],
        code_snippets={"hello": 'print("Hello, World!")', "optional": "guard let name = user?.name else { return }"},
        difficulty_tips={"beginner": "Start with Playgrounds in Xcode.", "intermediate": "Master protocols and generics.", "advanced": "Build with SwiftUI and async/await.", "expert": "Write Swift macros and contribute to open-source Swift."},
        related_languages=["Kotlin", "Rust", "C#"],
        ecosystem=["Xcode", "SPM", "CocoaPods", "SwiftUI", "Combine"],
        history_note="Created by Chris Lattner at Apple, announced in 2014."
    ),
    "csharp": LanguageKnowledge(
        language_id="csharp", name="C#",
        teaching_style="Versatile and powerful — from games to enterprise.",
        greeting="C#! The language of Unity and .NET. Let's build something extraordinary.",
        core_concepts=["LINQ", "Async/Await", "Generics", "Records", "Pattern Matching", "Nullable Reference Types", "Spans", "Source Generators", "Minimal APIs", "Blazor"],
        common_mistakes=[{"mistake": "Not using async properly", "fix": "Avoid async void, always await"}, {"mistake": "Ignoring IDisposable", "fix": "Use using statements"}],
        best_practices=["Use records for DTOs", "Leverage LINQ for queries", "Enable nullable reference types", "Use dependency injection"],
        code_snippets={"hello": 'Console.WriteLine("Hello, World!");', "linq": "var adults = people.Where(p => p.Age >= 18).OrderBy(p => p.Name);"},
        difficulty_tips={"beginner": "Start with Console apps and basic OOP.", "intermediate": "Master LINQ and async patterns.", "advanced": "Build with Blazor and .NET MAUI.", "expert": "Write Roslyn analyzers and optimize hot paths."},
        related_languages=["Java", "TypeScript", "F#"],
        ecosystem=[".NET SDK", "NuGet", "Visual Studio", "Rider", "Unity"],
        history_note="Created by Anders Hejlsberg at Microsoft, released in 2000."
    ),
    "ruby": LanguageKnowledge(
        language_id="ruby", name="Ruby",
        teaching_style="Joyful and expressive — optimized for developer happiness.",
        greeting="Ruby! Where developer happiness is the goal. Everything is an object here.",
        core_concepts=["Everything is an Object", "Blocks & Procs & Lambdas", "Mixins (modules)", "Metaprogramming", "Symbols", "Gems", "Duck Typing", "Enumerable", "Rails Conventions", "Testing with RSpec"],
        common_mistakes=[{"mistake": "Monkey-patching too much", "fix": "Use refinements instead"}, {"mistake": "Not using symbols", "fix": "Use symbols for hash keys"}],
        best_practices=["Follow Ruby conventions", "Use blocks idiomatically", "Write tests with RSpec", "Keep methods short"],
        code_snippets={"hello": 'puts "Hello, World!"', "block": "[1,2,3].map { |x| x * 2 }"},
        difficulty_tips={"beginner": "Ruby reads like English. Start with irb.", "intermediate": "Master blocks, procs, and metaprogramming.", "advanced": "Build with Rails and understand ActiveRecord.", "expert": "Contribute to CRuby or write C extensions."},
        related_languages=["Python", "Perl", "Crystal"],
        ecosystem=["Bundler", "RubyGems", "Rails", "RSpec", "Puma"],
        history_note="Created by Yukihiro Matsumoto in 1995."
    ),
    "php": LanguageKnowledge(
        language_id="php", name="PHP",
        teaching_style="Practical and web-focused — powers most of the web.",
        greeting="PHP! It powers WordPress, Facebook's roots, and millions of sites. Modern PHP is surprisingly elegant.",
        core_concepts=["OOP (PHP 8)", "Type System (union, intersection, enums)", "Fibers (async)", "Attributes", "Named Arguments", "Match Expression", "Readonly Properties", "Composer", "Laravel", "Testing with PHPUnit"],
        common_mistakes=[{"mistake": "SQL injection", "fix": "Use prepared statements"}, {"mistake": "Not using Composer", "fix": "Always use autoloading"}],
        best_practices=["Use PHP 8.3+ features", "Follow PSR standards", "Use type declarations everywhere", "Leverage Laravel or Symfony"],
        code_snippets={"hello": '<?php echo "Hello, World!";', "enum": "enum Color: string {\n    case Red = 'red';\n    case Blue = 'blue';\n}"},
        difficulty_tips={"beginner": "Start with basic scripts and forms.", "intermediate": "Master OOP and Laravel.", "advanced": "Build APIs and use Fibers.", "expert": "Contribute to PHP internals."},
        related_languages=["Python", "JavaScript", "Ruby"],
        ecosystem=["Composer", "Packagist", "Laravel", "Symfony", "PHPStan"],
        history_note="Created by Rasmus Lerdorf in 1995."
    ),
    "haskell": LanguageKnowledge(
        language_id="haskell", name="Haskell",
        teaching_style="Rigorous and mind-expanding — pure functional thinking.",
        greeting="Haskell! The purest of functional languages. Prepare to think in a completely new way.",
        core_concepts=["Pure Functions", "Type System (ADTs, type classes)", "Monads (IO, Maybe, Either)", "Lazy Evaluation", "Pattern Matching", "Higher-Order Functions", "Functors & Applicatives", "Type Classes", "Monad Transformers", "GHC Extensions"],
        common_mistakes=[{"mistake": "Space leaks from laziness", "fix": "Use strict annotations when needed"}, {"mistake": "Monad confusion", "fix": "Think of monads as computation contexts"}],
        best_practices=["Leverage the type system fully", "Use HLint for code style", "Write pure functions by default", "Use newtypes for type safety"],
        code_snippets={"hello": 'main = putStrLn "Hello, World!"', "maybe": "safeDivide :: Int -> Int -> Maybe Int\nsafeDivide _ 0 = Nothing\nsafeDivide x y = Just (x `div` y)"},
        difficulty_tips={"beginner": "Start with pure functions and pattern matching.", "intermediate": "Understand functors, applicatives, monads.", "advanced": "Master monad transformers and type-level programming.", "expert": "Contribute to GHC or write formal verification tools."},
        related_languages=["OCaml", "Elm", "PureScript"],
        ecosystem=["Cabal", "Stack", "Hackage", "HLint", "GHCi"],
        history_note="Designed by committee in 1990 as an open standard for functional programming."
    ),
    "scala": LanguageKnowledge(
        language_id="scala", name="Scala",
        teaching_style="Expressive and multi-paradigm — where OOP meets FP.",
        greeting="Scala! The best of both worlds — objects and functions, together at last.",
        core_concepts=["Case Classes", "Pattern Matching", "Traits", "Implicits/Givens", "For-Comprehensions", "Higher-Kinded Types", "Type Classes", "Opaque Types", "Macros", "Cats/ZIO"],
        common_mistakes=[{"mistake": "Overusing implicits", "fix": "Use given/using in Scala 3"}, {"mistake": "Complex type signatures", "fix": "Start simple, add complexity as needed"}],
        best_practices=["Use Scala 3 syntax", "Prefer immutability", "Use pattern matching", "Leverage the type system"],
        code_snippets={"hello": '@main def hello() = println("Hello, World!")', "case": "case class User(name: String, age: Int)"},
        difficulty_tips={"beginner": "Start with val, case classes, and collections.", "intermediate": "Master for-comprehensions and traits.", "advanced": "Learn ZIO or Cats for effect systems.", "expert": "Write Scala 3 macros and compiler plugins."},
        related_languages=["Kotlin", "Haskell", "Java"],
        ecosystem=["sbt", "Mill", "Metals", "Scalafmt", "Scalafix"],
        history_note="Created by Martin Odersky, first released in 2004."
    ),
    "elixir": LanguageKnowledge(
        language_id="elixir", name="Elixir",
        teaching_style="Joyful concurrency — built for distributed systems.",
        greeting="Elixir! Built on Erlang's rock-solid foundation. Let's build something that never goes down.",
        core_concepts=["Pattern Matching", "Processes", "GenServer", "Supervision Trees", "Pipe Operator", "OTP", "Phoenix Framework", "LiveView", "Ecto", "Distributed Computing"],
        common_mistakes=[{"mistake": "Not using pattern matching", "fix": "Pattern match everywhere"}, {"mistake": "Ignoring supervision", "fix": "Let it crash, supervisors restart"}],
        best_practices=["Use the pipe operator |>", "Leverage pattern matching", "Design supervisor trees", "Use LiveView for real-time UIs"],
        code_snippets={"hello": 'IO.puts("Hello, World!")', "pipe": '"hello" |> String.upcase() |> String.reverse()'},
        difficulty_tips={"beginner": "Start with IEx and pattern matching.", "intermediate": "Master GenServer and OTP patterns.", "advanced": "Build with Phoenix LiveView.", "expert": "Design distributed systems with clustering."},
        related_languages=["Erlang", "Ruby", "Clojure"],
        ecosystem=["Mix", "Hex", "Phoenix", "Ecto", "ExUnit"],
        history_note="Created by Jose Valim in 2011, inspired by Ruby and Erlang."
    ),
    "sql": LanguageKnowledge(
        language_id="sql", name="SQL",
        teaching_style="Logical and declarative — tell the database what you want.",
        greeting="SQL! The universal language of data. Every developer needs this skill.",
        core_concepts=["SELECT & Filtering", "JOINs (INNER, LEFT, RIGHT, FULL)", "Aggregation (GROUP BY, HAVING)", "Subqueries & CTEs", "Window Functions", "Indexes", "Transactions & ACID", "Stored Procedures", "Query Optimization", "Database Design & Normalization"],
        common_mistakes=[{"mistake": "SELECT * everywhere", "fix": "Select only needed columns"}, {"mistake": "No indexes", "fix": "Add indexes for WHERE and JOIN columns"}],
        best_practices=["Use CTEs for readability", "Always use parameterized queries", "Normalize to 3NF by default", "Use EXPLAIN ANALYZE"],
        code_snippets={"select": "SELECT u.name, COUNT(o.id) as order_count\nFROM users u\nLEFT JOIN orders o ON u.id = o.user_id\nGROUP BY u.name\nHAVING COUNT(o.id) > 5;"},
        difficulty_tips={"beginner": "Start with SELECT, WHERE, and ORDER BY.", "intermediate": "Master JOINs and GROUP BY.", "advanced": "Learn window functions and CTEs.", "expert": "Optimize query plans and design schemas."},
        related_languages=["GraphQL", "NoSQL query languages"],
        ecosystem=["PostgreSQL", "MySQL", "SQLite", "DBeaver", "pgAdmin"],
        history_note="Developed at IBM in the 1970s, standardized in 1986."
    ),
    "solidity": LanguageKnowledge(
        language_id="solidity", name="Solidity",
        teaching_style="Security-first — every line of code handles real money.",
        greeting="Solidity! Where code is law and bugs cost millions. Let's write bulletproof smart contracts.",
        core_concepts=["Smart Contracts", "Data Types (address, uint, mapping)", "Modifiers", "Events & Logs", "Gas Optimization", "Inheritance", "Interfaces", "Libraries", "Proxy Patterns", "Security (reentrancy, overflow)"],
        common_mistakes=[{"mistake": "Reentrancy attacks", "fix": "Use checks-effects-interactions pattern"}, {"mistake": "Floating pragma", "fix": "Lock to specific compiler version"}],
        best_practices=["Use OpenZeppelin contracts", "Always audit before deployment", "Minimize on-chain storage", "Use events for off-chain indexing"],
        code_snippets={"hello": '// SPDX-License-Identifier: MIT\npragma solidity ^0.8.0;\ncontract Hello {\n    function greet() public pure returns (string memory) {\n        return "Hello, World!";\n    }\n}'},
        difficulty_tips={"beginner": "Start with simple storage contracts.", "intermediate": "Master ERC-20 and ERC-721 standards.", "advanced": "Implement DeFi protocols.", "expert": "Audit contracts and find vulnerabilities."},
        related_languages=["JavaScript", "Vyper", "Rust (Solana)"],
        ecosystem=["Hardhat", "Foundry", "OpenZeppelin", "Etherscan", "Remix"],
        history_note="Created by Gavin Wood, first released in 2015 for Ethereum."
    ),
}

# Add compact entries for remaining languages
for lang_id, lang_data in [
    ("dart", ("Dart", "Flutter's language of choice.", "Let's build beautiful cross-platform apps!")),
    ("lua", ("Lua", "Lightweight and embeddable — the game scripting king.", "Lua powers Roblox and WoW addons!")),
    ("r", ("R", "Statistical computing and visualization.", "Let's analyze some data!")),
    ("julia", ("Julia", "High-performance scientific computing.", "Speed of C, ease of Python!")),
    ("perl", ("Perl", "Text processing and practical extraction.", "The Swiss Army chainsaw of programming!")),
    ("matlab", ("MATLAB", "Numerical computation and engineering.", "Let's crunch some numbers!")),
    ("fortran", ("Fortran", "High-performance computing pioneer.", "Still powering supercomputers!")),
    ("cobol", ("COBOL", "Business computing backbone.", "Billions of transactions daily depend on COBOL!")),
    ("assembly", ("Assembly", "As close to the metal as it gets.", "Raw CPU instructions — no abstraction!")),
    ("ocaml", ("OCaml", "Practical functional programming.", "Type inference and pattern matching excellence!")),
    ("clojure", ("Clojure", "Modern Lisp on the JVM.", "Immutable data and powerful macros!")),
    ("fsharp", ("F#", "Functional-first on .NET.", "Computation expressions and type providers!")),
    ("erlang", ("Erlang", "Concurrent and fault-tolerant.", "Built for telecom, perfect for distributed systems!")),
    ("prolog", ("Prolog", "Logic programming pioneer.", "Declare what you want, not how to compute it!")),
    ("lisp", ("Common Lisp", "The programmable programming language.", "Macros that write code — ultimate metaprogramming!")),
    ("zig", ("Zig", "Better C with comptime.", "Zero hidden control flow, explicit allocators!")),
    ("nim", ("Nim", "Efficient, expressive, elegant.", "Python-like syntax, C-like performance!")),
    ("crystal", ("Crystal", "Ruby-like speed demon.", "Ruby syntax with C performance!")),
    ("v", ("V", "Simple, fast, safe.", "Compiles in milliseconds!")),
    ("d", ("D", "Better C++ without the baggage.", "Templates, ranges, and CTFE!")),
    ("ada", ("Ada", "Safety-critical systems.", "Trusted for aerospace and defense!")),
    ("groovy", ("Groovy", "Java's dynamic companion.", "Perfect for Gradle build scripts!")),
    ("powershell", ("PowerShell", "Windows automation powerhouse.", "Objects in the pipeline!")),
    ("bash", ("Bash", "Unix shell scripting.", "The glue that holds Linux together!")),
    ("graphql", ("GraphQL", "API query language.", "Ask for exactly what you need!")),
    ("html", ("HTML", "Web markup foundation.", "Every website starts here!")),
    ("css", ("CSS", "Web styling language.", "Making the web beautiful since 1996!")),
]:
    if lang_id not in JEEVES_LANGUAGE_KB:
        JEEVES_LANGUAGE_KB[lang_id] = LanguageKnowledge(
            language_id=lang_id,
            name=lang_data[0],
            teaching_style=lang_data[1],
            greeting=lang_data[2],
            core_concepts=[f"{lang_data[0]} Fundamentals", f"{lang_data[0]} Intermediate", f"{lang_data[0]} Advanced", f"{lang_data[0]} Expert Patterns"],
            common_mistakes=[{"mistake": "Not reading the docs", "fix": f"Read the official {lang_data[0]} documentation"}],
            best_practices=[f"Follow {lang_data[0]} community conventions", "Write tests", "Use linters"],
            code_snippets={"hello": f"// Hello World in {lang_data[0]}"},
            difficulty_tips={"beginner": "Start with the basics.", "intermediate": "Build real projects.", "advanced": "Contribute to the ecosystem.", "expert": f"Become a {lang_data[0]} core contributor."},
            related_languages=[],
            ecosystem=[],
            history_note=f"{lang_data[0]} — a valued member of the programming language family."
        )


# =============================================================================
# API ROUTES
# =============================================================================

@router.get("/overview")
async def get_jeeves_language_overview():
    """Get overview of Jeeves' language knowledge"""
    return {
        "total_languages": len(JEEVES_LANGUAGE_KB),
        "languages": [
            {
                "id": kb.language_id,
                "name": kb.name,
                "teaching_style": kb.teaching_style,
                "concepts_count": len(kb.core_concepts)
            }
            for kb in JEEVES_LANGUAGE_KB.values()
        ],
        "jeeves_message": "I am well-versed in all these languages, sir. Shall we begin a lesson?"
    }


@router.get("/language/{language_id}")
async def get_language_knowledge(language_id: str):
    """Get Jeeves' complete knowledge for a specific language"""
    if language_id not in JEEVES_LANGUAGE_KB:
        raise HTTPException(status_code=404, detail=f"I'm afraid I don't yet have deep knowledge of '{language_id}', sir.")
    
    kb = JEEVES_LANGUAGE_KB[language_id]
    return {
        "knowledge": kb.dict(),
        "jeeves_greeting": kb.greeting,
        "teaching_approach": kb.teaching_style
    }


@router.get("/language/{language_id}/teach")
async def teach_language(language_id: str, level: str = "beginner"):
    """Get a teaching session from Jeeves for a language at a specific level"""
    if language_id not in JEEVES_LANGUAGE_KB:
        raise HTTPException(status_code=404, detail=f"Language '{language_id}' not found in my knowledge base.")
    
    kb = JEEVES_LANGUAGE_KB[language_id]
    tip = kb.difficulty_tips.get(level, kb.difficulty_tips.get("beginner", ""))
    
    return {
        "language": kb.name,
        "level": level,
        "greeting": kb.greeting,
        "tip": tip,
        "concepts_to_learn": kb.core_concepts,
        "common_pitfalls": kb.common_mistakes,
        "best_practices": kb.best_practices,
        "code_examples": kb.code_snippets,
        "related_languages": kb.related_languages,
        "ecosystem": kb.ecosystem,
        "jeeves_advice": f"For {level} level in {kb.name}: {tip}"
    }


@router.get("/language/{language_id}/quiz")
async def get_language_quiz(language_id: str, level: str = "beginner"):
    """Get a quick quiz from Jeeves for a language"""
    if language_id not in JEEVES_LANGUAGE_KB:
        raise HTTPException(status_code=404, detail=f"Language '{language_id}' not found.")
    
    kb = JEEVES_LANGUAGE_KB[language_id]
    
    # Generate contextual quiz questions based on knowledge base
    questions = [
        {
            "id": f"{language_id}_q1",
            "question": f"What is a core concept in {kb.name}?",
            "options": kb.core_concepts[:4] if len(kb.core_concepts) >= 4 else kb.core_concepts,
            "correct": 0,
            "explanation": f"All of these are core concepts, but '{kb.core_concepts[0]}' is foundational."
        },
        {
            "id": f"{language_id}_q2",
            "question": f"What is a common mistake in {kb.name}?",
            "options": [m["mistake"] for m in kb.common_mistakes[:4]],
            "correct": 0,
            "explanation": kb.common_mistakes[0]["fix"] if kb.common_mistakes else "Check the documentation."
        },
        {
            "id": f"{language_id}_q3",
            "question": f"Which of these is a best practice in {kb.name}?",
            "options": kb.best_practices[:4] if len(kb.best_practices) >= 4 else kb.best_practices,
            "correct": 0,
            "explanation": f"'{kb.best_practices[0]}' is an essential practice."
        }
    ]
    
    return {
        "language": kb.name,
        "level": level,
        "questions": questions,
        "jeeves_note": f"A small test of your {kb.name} knowledge, if you please."
    }


@router.get("/compare")
async def compare_languages(lang1: str, lang2: str):
    """Get Jeeves' comparison of two languages"""
    if lang1 not in JEEVES_LANGUAGE_KB:
        raise HTTPException(status_code=404, detail=f"Language '{lang1}' not found.")
    if lang2 not in JEEVES_LANGUAGE_KB:
        raise HTTPException(status_code=404, detail=f"Language '{lang2}' not found.")
    
    kb1 = JEEVES_LANGUAGE_KB[lang1]
    kb2 = JEEVES_LANGUAGE_KB[lang2]
    
    return {
        "comparison": {
            "languages": [kb1.name, kb2.name],
            "teaching_styles": [kb1.teaching_style, kb2.teaching_style],
            "concepts_count": [len(kb1.core_concepts), len(kb2.core_concepts)],
            "ecosystems": [kb1.ecosystem, kb2.ecosystem],
            "related_overlap": list(set(kb1.related_languages) & set(kb2.related_languages)),
            "history": [kb1.history_note, kb2.history_note]
        },
        "jeeves_verdict": f"Both {kb1.name} and {kb2.name} are excellent choices. {kb1.name} excels at being {kb1.teaching_style.split('—')[0].strip()}, while {kb2.name} shines at being {kb2.teaching_style.split('—')[0].strip()}."
    }


@router.get("/recommend")
async def recommend_language(goal: str = "web"):
    """Get Jeeves' language recommendation based on a goal"""
    goal_map = {
        "web": ["javascript", "typescript", "python", "php", "ruby"],
        "mobile": ["kotlin", "swift", "dart", "javascript", "csharp"],
        "game": ["cpp", "csharp", "lua", "rust", "python"],
        "data": ["python", "r", "julia", "sql", "scala"],
        "systems": ["rust", "c", "cpp", "go", "zig"],
        "ai": ["python", "julia", "r", "cpp", "java"],
        "blockchain": ["solidity", "rust", "go", "javascript", "python"],
        "devops": ["bash", "python", "go", "powershell", "ruby"],
        "embedded": ["c", "cpp", "rust", "assembly", "zig"],
        "functional": ["haskell", "elixir", "scala", "ocaml", "clojure"],
        "enterprise": ["java", "csharp", "kotlin", "go", "typescript"],
        "beginner": ["python", "javascript", "ruby", "lua", "html"],
    }
    
    recommended_ids = goal_map.get(goal.lower(), goal_map["web"])
    recommendations = []
    for lid in recommended_ids:
        if lid in JEEVES_LANGUAGE_KB:
            kb = JEEVES_LANGUAGE_KB[lid]
            recommendations.append({
                "id": lid,
                "name": kb.name,
                "reason": kb.teaching_style,
                "greeting": kb.greeting
            })
    
    return {
        "goal": goal,
        "recommendations": recommendations,
        "jeeves_advice": f"For {goal}, I'd recommend starting with {recommendations[0]['name'] if recommendations else 'Python'}. An excellent foundation, if I may say so."
    }
