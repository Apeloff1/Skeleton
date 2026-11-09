"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    THE ULTIMATE COMPUTER SCIENCE BIBLE                        ║
║                     15-Year Comprehensive Curriculum                          ║
║                                                                               ║
║  From absolute beginner to world-class computer scientist                     ║
║  150+ courses • 15 years • 10,000+ hours of content                          ║
║  Multiple parallel tracks for simultaneous learning                           ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from typing import Dict, List, Any, Optional
from enum import Enum

# ============================================================================
# ENUMS FOR CURRICULUM STRUCTURE
# ============================================================================

class DifficultyLevel(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"
    MASTER = "master"
    PHD = "phd"

class TrackType(str, Enum):
    CORE = "core"
    SYSTEMS = "systems"
    THEORY = "theory"
    AI_ML = "ai_ml"
    SECURITY = "security"
    WEB_MOBILE = "web_mobile"
    DATA = "data"
    RESEARCH = "research"
    GRAPHICS = "graphics"
    COMPILERS = "compilers"

# ============================================================================
# THE COMPLETE 15-YEAR CS BIBLE CURRICULUM
# ============================================================================

CS_BIBLE = {
    "title": "The Ultimate Computer Science Bible",
    "subtitle": "15-Year Journey from Beginner to Master",
    "version": "10.0.0",
    "total_years": 15,
    "total_courses": 180,
    "total_hours": 12000,
    "parallel_tracks": 6,
    "certification_levels": [
        {"level": 1, "name": "Certificate", "years": "1-2", "title": "CS Fundamentals Certificate"},
        {"level": 2, "name": "Associate", "years": "3-4", "title": "Associate in Computer Science"},
        {"level": 3, "name": "Bachelor", "years": "5-8", "title": "Bachelor of Science in CS"},
        {"level": 4, "name": "Master", "years": "9-12", "title": "Master of Science in CS"},
        {"level": 5, "name": "PhD", "years": "13-15", "title": "Doctor of Philosophy in CS"}
    ],
    
    # ========================================================================
    # YEAR 1: FOUNDATION YEAR - Programming Fundamentals
    # ========================================================================
    "year_1": {
        "year": 1,
        "name": "Foundation Year",
        "theme": "Programming Fundamentals & Computational Thinking",
        "level": DifficultyLevel.BEGINNER,
        "total_hours": 720,
        "parallel_courses": 6,
        "description": "Build your foundation in programming, logic, and computational thinking. No prior experience required.",
        "tracks": {
            TrackType.CORE: [
                {
                    "id": "y1_cs101",
                    "code": "CS 101",
                    "title": "Introduction to Programming",
                    "subtitle": "Your First Lines of Code",
                    "credits": 4,
                    "hours": 60,
                    "weeks": 15,
                    "prerequisites": [],
                    "description": "Learn fundamental programming concepts using Python. Perfect for absolute beginners.",
                    "learning_objectives": [
                        "Write basic programs with variables, expressions, and statements",
                        "Implement control flow with conditionals and loops",
                        "Create and use functions for code organization",
                        "Work with fundamental data structures (lists, dictionaries)",
                        "Debug programs and handle errors gracefully",
                        "Apply computational thinking to solve real problems"
                    ],
                    "topics": [
                        {"week": 1, "topic": "Introduction to Computing", "subtopics": ["What is programming?", "Setting up your environment", "Your first program"]},
                        {"week": 2, "topic": "Variables and Data Types", "subtopics": ["Numbers, strings, booleans", "Type conversion", "Variable naming"]},
                        {"week": 3, "topic": "Operators and Expressions", "subtopics": ["Arithmetic operators", "Comparison operators", "Logical operators"]},
                        {"week": 4, "topic": "Conditional Statements", "subtopics": ["if/elif/else", "Nested conditions", "Boolean logic"]},
                        {"week": 5, "topic": "Loops - Part 1", "subtopics": ["while loops", "Loop control", "Infinite loops"]},
                        {"week": 6, "topic": "Loops - Part 2", "subtopics": ["for loops", "range()", "Nested loops"]},
                        {"week": 7, "topic": "Functions - Part 1", "subtopics": ["Defining functions", "Parameters and arguments", "Return values"]},
                        {"week": 8, "topic": "Functions - Part 2", "subtopics": ["Scope and lifetime", "Default parameters", "Lambda functions"]},
                        {"week": 9, "topic": "Lists", "subtopics": ["Creating lists", "Indexing and slicing", "List methods"]},
                        {"week": 10, "topic": "Dictionaries", "subtopics": ["Key-value pairs", "Dictionary operations", "Nested structures"]},
                        {"week": 11, "topic": "String Manipulation", "subtopics": ["String methods", "Formatting", "Regular expressions intro"]},
                        {"week": 12, "topic": "File I/O", "subtopics": ["Reading files", "Writing files", "Working with paths"]},
                        {"week": 13, "topic": "Error Handling", "subtopics": ["Exceptions", "try/except", "Custom exceptions"]},
                        {"week": 14, "topic": "Modules and Packages", "subtopics": ["Importing modules", "Standard library", "pip basics"]},
                        {"week": 15, "topic": "Capstone Project", "subtopics": ["Project planning", "Implementation", "Presentation"]}
                    ],
                    "projects": [
                        {"name": "Calculator Application", "description": "Build a multi-function calculator", "difficulty": "easy"},
                        {"name": "Text-based Adventure Game", "description": "Create an interactive story game", "difficulty": "medium"},
                        {"name": "Personal Budget Tracker", "description": "Track income and expenses", "difficulty": "medium"},
                        {"name": "Password Generator", "description": "Generate secure random passwords", "difficulty": "easy"}
                    ],
                    "languages": ["python"],
                    "tools": ["VS Code", "Python REPL", "pip"],
                    "assessment": {
                        "quizzes": 10,
                        "assignments": 8,
                        "midterm": True,
                        "final_project": True
                    },
                    "content": """
# Introduction to Programming

Welcome to your journey into the world of programming! This course will teach you
how to think like a programmer and write your first programs.

## What is Programming?

Programming is the art of giving instructions to a computer. Just like you might
follow a recipe to bake a cake, computers follow programs to perform tasks.

### The Programming Mindset

1. **Decomposition** - Break problems into smaller pieces
2. **Pattern Recognition** - Find similarities in problems
3. **Abstraction** - Focus on important details, ignore the rest
4. **Algorithm Design** - Create step-by-step solutions

## Your First Program

```python
# The classic first program
print("Hello, World!")

# Variables store data
name = "Student"
age = 20
gpa = 3.75

# Making decisions
if age >= 18:
    print(f"{name} is an adult")
    if gpa >= 3.5:
        print("And on the Dean's List!")
else:
    print(f"{name} is a minor")

# Loops repeat actions
print("\\nCounting to 5:")
for i in range(1, 6):
    print(f"  Count: {i}")

# Functions organize code
def greet(person, greeting="Hello"):
    \"\"\"Generate a greeting message.\"\"\"
    return f"{greeting}, {person}!"

print(greet("World"))
print(greet("Python", "Welcome to"))

# Working with lists
numbers = [1, 2, 3, 4, 5]
doubled = [n * 2 for n in numbers]
print(f"Original: {numbers}")
print(f"Doubled: {doubled}")

# Dictionaries for key-value data
student = {
    "name": "Alex",
    "age": 20,
    "courses": ["CS101", "MATH101", "ENG101"]
}
print(f"\\nStudent: {student['name']}")
print(f"Taking {len(student['courses'])} courses")
```

## Practice Makes Perfect

Programming is a skill learned by doing. Write code every day, even if it's just
for 15 minutes. Embrace mistakes - they're the best teachers!

### Tips for Success

- Type out examples yourself (don't just copy-paste)
- Experiment with variations of examples
- Break when stuck, then come back fresh
- Explain your code to others (or a rubber duck!)
- Build projects that interest you
"""
                },
                {
                    "id": "y1_cs102",
                    "code": "CS 102",
                    "title": "Programming in C",
                    "subtitle": "Understanding the Machine",
                    "credits": 4,
                    "hours": 60,
                    "weeks": 15,
                    "prerequisites": ["y1_cs101"],
                    "description": "Learn C programming to understand how computers really work at a lower level.",
                    "learning_objectives": [
                        "Understand memory management and pointers",
                        "Work with arrays, strings, and structures",
                        "Implement algorithms in a systems language",
                        "Debug programs using GDB",
                        "Understand the compilation process"
                    ],
                    "topics": [
                        {"week": 1, "topic": "C Language Overview", "subtopics": ["History", "Compilation", "Hello World in C"]},
                        {"week": 2, "topic": "Data Types and Variables", "subtopics": ["Primitive types", "sizeof", "Type modifiers"]},
                        {"week": 3, "topic": "Operators and Control Flow", "subtopics": ["All operators", "Precedence", "if/switch/loops"]},
                        {"week": 4, "topic": "Functions", "subtopics": ["Declaration vs definition", "Pass by value", "Recursion"]},
                        {"week": 5, "topic": "Arrays", "subtopics": ["1D arrays", "Multi-dimensional", "Array decay"]},
                        {"week": 6, "topic": "Pointers - Part 1", "subtopics": ["Address-of operator", "Dereferencing", "Pointer arithmetic"]},
                        {"week": 7, "topic": "Pointers - Part 2", "subtopics": ["Pointers and arrays", "Pointer to pointer", "void pointers"]},
                        {"week": 8, "topic": "Strings", "subtopics": ["C strings", "String functions", "String manipulation"]},
                        {"week": 9, "topic": "Structures and Unions", "subtopics": ["struct", "union", "typedef"]},
                        {"week": 10, "topic": "Dynamic Memory", "subtopics": ["malloc/calloc", "realloc", "free"]},
                        {"week": 11, "topic": "File I/O", "subtopics": ["fopen/fclose", "Reading/writing", "Binary files"]},
                        {"week": 12, "topic": "Preprocessor", "subtopics": ["Macros", "Conditional compilation", "Header files"]},
                        {"week": 13, "topic": "Advanced Topics", "subtopics": ["Function pointers", "Bit manipulation", "Variadic functions"]},
                        {"week": 14, "topic": "Debugging", "subtopics": ["GDB basics", "Valgrind", "Common bugs"]},
                        {"week": 15, "topic": "Systems Project", "subtopics": ["Implementation", "Testing", "Documentation"]}
                    ],
                    "projects": [
                        {"name": "Memory Allocator", "description": "Implement a simple malloc", "difficulty": "hard"},
                        {"name": "String Library", "description": "Implement standard string functions", "difficulty": "medium"},
                        {"name": "Simple Shell", "description": "Build a command-line shell", "difficulty": "hard"}
                    ],
                    "languages": ["c"],
                    "tools": ["GCC", "GDB", "Valgrind", "Make"],
                    "content": """
# Programming in C

C is the foundation of modern computing. Understanding C gives you insight into
how computers actually work at the hardware level.

## Why Learn C?

- **Direct memory access** - Control exactly how data is stored
- **High performance** - Code runs close to the metal
- **Systems programming** - Build operating systems, drivers, embedded systems
- **Foundation** - Many languages (C++, Java, Python internals) are built on C concepts

## Pointers - The Heart of C

```c
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main() {
    // Basic pointer usage
    int x = 42;
    int *ptr = &x;  // ptr holds address of x
    
    printf("Value of x: %d\\n", x);
    printf("Address of x: %p\\n", (void*)&x);
    printf("Value via pointer: %d\\n", *ptr);
    printf("Pointer address: %p\\n", (void*)ptr);
    
    // Pointer arithmetic with arrays
    int arr[] = {10, 20, 30, 40, 50};
    int *p = arr;  // arr decays to pointer
    
    printf("\\nArray via pointer arithmetic:\\n");
    for (int i = 0; i < 5; i++) {
        printf("  arr[%d] = %d (at %p)\\n", i, *(p + i), (void*)(p + i));
    }
    
    // Dynamic memory allocation
    printf("\\nDynamic memory:\\n");
    int *dynamic = malloc(5 * sizeof(int));
    if (dynamic == NULL) {
        fprintf(stderr, "Memory allocation failed!\\n");
        return 1;
    }
    
    for (int i = 0; i < 5; i++) {
        dynamic[i] = i * i;
        printf("  dynamic[%d] = %d\\n", i, dynamic[i]);
    }
    
    free(dynamic);  // ALWAYS free allocated memory
    printf("Memory freed successfully\\n");
    
    return 0;
}
```

## Structures and Memory Layout

```c
#include <stdio.h>
#include <string.h>

// Define a structure
typedef struct {
    int id;
    char name[50];
    float gpa;
} Student;

// Function to print student info
void print_student(const Student *s) {
    printf("ID: %d, Name: %s, GPA: %.2f\\n", s->id, s->name, s->gpa);
}

int main() {
    // Stack allocation
    Student s1 = {1, "Alice", 3.85};
    print_student(&s1);
    
    // Modify via pointer
    Student *ptr = &s1;
    ptr->gpa = 3.90;  // Arrow operator for pointer to struct
    print_student(&s1);
    
    printf("Size of Student struct: %zu bytes\\n", sizeof(Student));
    
    return 0;
}
```

## Memory Safety Tips

1. Always initialize pointers (or set to NULL)
2. Check malloc return values
3. Free memory exactly once
4. Don't access freed memory
5. Don't return pointers to local variables
6. Use Valgrind to detect memory leaks
"""
                }
            ],
            TrackType.THEORY: [
                {
                    "id": "y1_math101",
                    "code": "MATH 101",
                    "title": "Discrete Mathematics I",
                    "subtitle": "The Language of Computer Science",
                    "credits": 4,
                    "hours": 60,
                    "weeks": 15,
                    "prerequisites": [],
                    "description": "Essential mathematical foundations for computer science.",
                    "learning_objectives": [
                        "Apply propositional and predicate logic",
                        "Construct mathematical proofs",
                        "Work with sets, relations, and functions",
                        "Apply counting principles and probability",
                        "Understand mathematical induction"
                    ],
                    "topics": [
                        {"week": 1, "topic": "Propositional Logic", "subtopics": ["Propositions", "Truth tables", "Logical equivalence"]},
                        {"week": 2, "topic": "Propositional Logic II", "subtopics": ["Logical laws", "Normal forms", "Satisfiability"]},
                        {"week": 3, "topic": "Predicate Logic", "subtopics": ["Predicates", "Quantifiers", "Nested quantifiers"]},
                        {"week": 4, "topic": "Proof Techniques I", "subtopics": ["Direct proof", "Contrapositive", "Contradiction"]},
                        {"week": 5, "topic": "Proof Techniques II", "subtopics": ["Cases", "Existence", "Uniqueness"]},
                        {"week": 6, "topic": "Sets", "subtopics": ["Set notation", "Operations", "Power sets"]},
                        {"week": 7, "topic": "Set Theory", "subtopics": ["Venn diagrams", "Cardinality", "Cartesian product"]},
                        {"week": 8, "topic": "Relations", "subtopics": ["Binary relations", "Properties", "Equivalence relations"]},
                        {"week": 9, "topic": "Functions", "subtopics": ["Definition", "Injection/surjection/bijection", "Composition"]},
                        {"week": 10, "topic": "Mathematical Induction", "subtopics": ["Weak induction", "Strong induction", "Structural induction"]},
                        {"week": 11, "topic": "Counting I", "subtopics": ["Sum rule", "Product rule", "Inclusion-exclusion"]},
                        {"week": 12, "topic": "Counting II", "subtopics": ["Permutations", "Combinations", "Binomial theorem"]},
                        {"week": 13, "topic": "Recursion", "subtopics": ["Recursive definitions", "Recurrence relations", "Solving recurrences"]},
                        {"week": 14, "topic": "Probability Basics", "subtopics": ["Sample spaces", "Events", "Conditional probability"]},
                        {"week": 15, "topic": "Review and Applications", "subtopics": ["CS applications", "Problem solving", "Final exam prep"]}
                    ],
                    "projects": [
                        {"name": "Logic Gate Simulator", "description": "Implement logic gates in code", "difficulty": "medium"},
                        {"name": "Proof Checker", "description": "Verify mathematical proofs", "difficulty": "hard"}
                    ],
                    "languages": [],
                    "tools": ["LaTeX", "Proof assistants (optional)"],
                    "content": """
# Discrete Mathematics I

Mathematics is the language of computer science. This course builds the
foundation you'll use throughout your career.

## Propositional Logic

```
Propositions are statements that are either TRUE or FALSE.

Examples:
  p: "It is raining" 
  q: "I have an umbrella"
  r: "2 + 2 = 4" (always true)
  s: "2 + 2 = 5" (always false)

Logical Operators:
  ¬p     - NOT p (negation)
  p ∧ q  - p AND q (conjunction)
  p ∨ q  - p OR q (disjunction)
  p → q  - p IMPLIES q (implication)
  p ↔ q  - p IFF q (biconditional)

Truth Table for Implication (→):
  p | q | p → q
  T | T |   T
  T | F |   F
  F | T |   T
  F | F |   T

Key insight: False implies anything (vacuous truth)
```

## Sets and Set Operations

```
Set notation:
  A = {1, 2, 3, 4, 5}
  B = {4, 5, 6, 7, 8}
  C = {x ∈ ℤ | x > 0 and x < 6}  (set-builder notation)

Operations:
  A ∪ B = {1, 2, 3, 4, 5, 6, 7, 8}    (Union)
  A ∩ B = {4, 5}                       (Intersection)
  A - B = {1, 2, 3}                    (Difference)
  A × B = {(1,4), (1,5), ...}          (Cartesian Product)
  |A| = 5                               (Cardinality)
  P(A) = {∅, {1}, {2}, ..., A}         (Power set, |P(A)| = 2^n)

Important properties:
  A ∪ (B ∩ C) = (A ∪ B) ∩ (A ∪ C)     (Distributive)
  ¬(A ∪ B) = ¬A ∩ ¬B                   (De Morgan's)
```

## Mathematical Induction

```
To prove P(n) for all n ≥ n₀:

1. BASE CASE: Prove P(n₀) is true
2. INDUCTIVE STEP: 
   - Assume P(k) is true (Inductive Hypothesis)
   - Prove P(k+1) is true using this assumption

Example: Prove 1 + 2 + ... + n = n(n+1)/2

Base case (n=1): 
  LHS = 1
  RHS = 1(2)/2 = 1 ✓

Inductive step:
  Assume: 1 + 2 + ... + k = k(k+1)/2
  Prove:  1 + 2 + ... + k + (k+1) = (k+1)(k+2)/2
  
  LHS = k(k+1)/2 + (k+1)          (by IH)
      = (k+1)(k/2 + 1)
      = (k+1)(k+2)/2              ✓
```

## Counting Principles

```
Sum Rule: If task A can be done in m ways and task B in n ways,
          and they're mutually exclusive, total = m + n

Product Rule: If task A has m ways and task B has n ways,
              and they're independent, total = m × n

Permutations (order matters):
  P(n, r) = n! / (n-r)!
  
Combinations (order doesn't matter):
  C(n, r) = n! / (r!(n-r)!)

Binomial Theorem:
  (x + y)^n = Σ C(n,k) x^(n-k) y^k for k=0 to n
```
"""
                }
            ],
            TrackType.SYSTEMS: [
                {
                    "id": "y1_cs104",
                    "code": "CS 104",
                    "title": "Computer Systems Fundamentals",
                    "subtitle": "How Computers Work",
                    "credits": 4,
                    "hours": 60,
                    "weeks": 15,
                    "prerequisites": [],
                    "description": "Understand the fundamental architecture of computer systems.",
                    "learning_objectives": [
                        "Convert between number systems (binary, octal, hex)",
                        "Understand Boolean algebra and logic gates",
                        "Describe CPU architecture and instruction execution",
                        "Explain the memory hierarchy",
                        "Write basic assembly language programs"
                    ],
                    "topics": [
                        {"week": 1, "topic": "Number Systems", "subtopics": ["Binary", "Octal", "Hexadecimal"]},
                        {"week": 2, "topic": "Binary Arithmetic", "subtopics": ["Addition", "Subtraction", "Two's complement"]},
                        {"week": 3, "topic": "Boolean Algebra", "subtopics": ["Boolean expressions", "Laws", "Simplification"]},
                        {"week": 4, "topic": "Logic Gates", "subtopics": ["AND/OR/NOT", "NAND/NOR/XOR", "Universal gates"]},
                        {"week": 5, "topic": "Combinational Circuits", "subtopics": ["Multiplexers", "Decoders", "Adders"]},
                        {"week": 6, "topic": "Sequential Circuits", "subtopics": ["Flip-flops", "Registers", "Counters"]},
                        {"week": 7, "topic": "CPU Architecture", "subtopics": ["ALU", "Control unit", "Registers"]},
                        {"week": 8, "topic": "Instruction Set Architecture", "subtopics": ["RISC vs CISC", "Addressing modes", "Instruction formats"]},
                        {"week": 9, "topic": "Assembly Language I", "subtopics": ["x86 basics", "Registers", "Simple instructions"]},
                        {"week": 10, "topic": "Assembly Language II", "subtopics": ["Control flow", "Stack", "Function calls"]},
                        {"week": 11, "topic": "Memory Hierarchy", "subtopics": ["Registers", "Cache", "RAM", "Disk"]},
                        {"week": 12, "topic": "Cache Memory", "subtopics": ["Cache design", "Replacement policies", "Write policies"]},
                        {"week": 13, "topic": "I/O Systems", "subtopics": ["I/O devices", "Interrupts", "DMA"]},
                        {"week": 14, "topic": "Operating System Overview", "subtopics": ["OS functions", "Process concept", "Memory management"]},
                        {"week": 15, "topic": "Modern Architectures", "subtopics": ["Pipelining", "Multi-core", "GPU basics"]}
                    ],
                    "projects": [
                        {"name": "Binary Calculator", "description": "Implement arithmetic in binary", "difficulty": "easy"},
                        {"name": "Logic Circuit Simulator", "description": "Build a digital circuit simulator", "difficulty": "medium"},
                        {"name": "Assembly Programs", "description": "Write utility programs in assembly", "difficulty": "hard"}
                    ],
                    "languages": ["assembly_x86"],
                    "tools": ["NASM", "Logisim", "Digital circuit simulators"],
                    "content": """
# Computer Systems Fundamentals

Understanding how computers work at the hardware level is essential for
writing efficient software.

## Binary Number System

```
Decimal  Binary    Hex    Octal
0        0000      0x0    0o0
1        0001      0x1    0o1
5        0101      0x5    0o5
10       1010      0xA    0o12
15       1111      0xF    0o17
255      11111111  0xFF   0o377

Binary Addition:
    1011  (11 in decimal)
  + 0110  ( 6 in decimal)
  ------
   10001  (17 in decimal)

Two's Complement (for negative numbers):
  To negate: flip bits, add 1
  -5 in 8-bit: ~00000101 + 1 = 11111010 + 1 = 11111011
```

## CPU Architecture

```
┌─────────────────────────────────────────────────────────┐
│                         CPU                              │
│  ┌─────────────────┐  ┌───────────────────────────┐    │
│  │  Control Unit   │  │   Arithmetic Logic Unit    │    │
│  │  - Fetch        │  │   - ADD, SUB, MUL, DIV    │    │
│  │  - Decode       │  │   - AND, OR, NOT, XOR     │    │
│  │  - Execute      │  │   - Compare, Shift        │    │
│  └─────────────────┘  └───────────────────────────┘    │
│                                                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │                  Registers                        │   │
│  │  RAX RBX RCX RDX RSI RDI RBP RSP R8-R15         │   │
│  │  RIP (Instruction Pointer)  RFLAGS              │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
                          ↑↓
┌─────────────────────────────────────────────────────────┐
│                    Memory (RAM)                          │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐   │
│  │  Stack  │  │  Heap   │  │  Data   │  │  Text   │   │
│  └─────────┘  └─────────┘  └─────────┘  └─────────┘   │
└─────────────────────────────────────────────────────────┘
```

## Assembly Language Basics

```asm
; Hello World in x86-64 Linux Assembly
section .data
    msg db "Hello, World!", 10    ; string with newline
    len equ $ - msg               ; length of string

section .text
    global _start

_start:
    ; syscall: write(1, msg, len)
    mov rax, 1          ; syscall number for write
    mov rdi, 1          ; file descriptor (stdout)
    mov rsi, msg        ; pointer to string
    mov rdx, len        ; length of string
    syscall

    ; syscall: exit(0)
    mov rax, 60         ; syscall number for exit
    xor rdi, rdi        ; exit code 0
    syscall
```

## Memory Hierarchy

```
Speed/Cost Tradeoff:

Registers    ~1 cycle     ~KB      $$$$$
    ↓
L1 Cache     ~4 cycles    ~64KB    $$$$
    ↓
L2 Cache     ~10 cycles   ~256KB   $$$
    ↓
L3 Cache     ~40 cycles   ~8MB     $$
    ↓
Main Memory  ~100 cycles  ~16GB    $
    ↓
SSD          ~10⁵ cycles  ~TB      ¢
    ↓
HDD          ~10⁷ cycles  ~TB      ¢

Locality Principles:
- Temporal: Recently accessed → likely accessed again
- Spatial: Nearby addresses → likely accessed soon
```
"""
                }
            ],
            TrackType.WEB_MOBILE: [
                {
                    "id": "y1_cs106",
                    "code": "CS 106",
                    "title": "Web Development Fundamentals",
                    "subtitle": "Building for the Browser",
                    "credits": 4,
                    "hours": 60,
                    "weeks": 15,
                    "prerequisites": ["y1_cs101"],
                    "description": "Learn to build modern web applications from scratch.",
                    "learning_objectives": [
                        "Create semantic HTML5 documents",
                        "Style pages with CSS3 including Flexbox and Grid",
                        "Add interactivity with JavaScript",
                        "Understand HTTP and REST APIs",
                        "Use Git for version control"
                    ],
                    "topics": [
                        {"week": 1, "topic": "Introduction to the Web", "subtopics": ["How the web works", "HTML basics", "Your first webpage"]},
                        {"week": 2, "topic": "HTML5 Structure", "subtopics": ["Semantic elements", "Forms", "Tables"]},
                        {"week": 3, "topic": "CSS Fundamentals", "subtopics": ["Selectors", "Box model", "Colors and fonts"]},
                        {"week": 4, "topic": "CSS Layout - Flexbox", "subtopics": ["Flex container", "Flex items", "Alignment"]},
                        {"week": 5, "topic": "CSS Layout - Grid", "subtopics": ["Grid container", "Grid items", "Areas"]},
                        {"week": 6, "topic": "Responsive Design", "subtopics": ["Media queries", "Mobile-first", "Viewport"]},
                        {"week": 7, "topic": "JavaScript Basics", "subtopics": ["Variables", "Functions", "Control flow"]},
                        {"week": 8, "topic": "DOM Manipulation", "subtopics": ["Selecting elements", "Modifying content", "Events"]},
                        {"week": 9, "topic": "JavaScript Objects", "subtopics": ["Objects", "Arrays", "JSON"]},
                        {"week": 10, "topic": "Async JavaScript", "subtopics": ["Callbacks", "Promises", "async/await"]},
                        {"week": 11, "topic": "Fetch API", "subtopics": ["Making requests", "Handling responses", "Error handling"]},
                        {"week": 12, "topic": "HTTP and REST", "subtopics": ["HTTP methods", "Status codes", "REST principles"]},
                        {"week": 13, "topic": "Version Control", "subtopics": ["Git basics", "Branching", "GitHub"]},
                        {"week": 14, "topic": "Web Security Basics", "subtopics": ["XSS", "CSRF", "HTTPS"]},
                        {"week": 15, "topic": "Final Project", "subtopics": ["Full web application", "Deployment", "Presentation"]}
                    ],
                    "projects": [
                        {"name": "Personal Portfolio", "description": "Build your developer portfolio", "difficulty": "easy"},
                        {"name": "Interactive Quiz App", "description": "Quiz game with scoring", "difficulty": "medium"},
                        {"name": "Weather Dashboard", "description": "Fetch and display weather data", "difficulty": "medium"}
                    ],
                    "languages": ["html", "css", "javascript"],
                    "tools": ["VS Code", "Chrome DevTools", "Git", "GitHub"],
                    "content": """
# Web Development Fundamentals

The web is the most ubiquitous platform. Learn to build for it.

## The Web Stack

```
┌─────────────────────────────────────────┐
│       JavaScript (Behavior)              │
│  - Interactivity                         │
│  - Dynamic content                       │
│  - API communication                     │
├─────────────────────────────────────────┤
│       CSS (Presentation)                 │
│  - Visual styling                        │
│  - Layout                                │
│  - Animations                            │
├─────────────────────────────────────────┤
│       HTML (Structure)                   │
│  - Content                               │
│  - Semantic meaning                      │
│  - Accessibility                         │
└─────────────────────────────────────────┘
```

## Modern HTML5

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Modern Web Page</title>
    <link rel="stylesheet" href="styles.css">
</head>
<body>
    <header>
        <nav>
            <a href="/">Home</a>
            <a href="/about">About</a>
            <a href="/contact">Contact</a>
        </nav>
    </header>
    
    <main>
        <article>
            <h1>Welcome to Web Development</h1>
            <p>Learn to build amazing websites!</p>
            
            <section>
                <h2>Why Web Dev?</h2>
                <ul>
                    <li>Reach billions of users</li>
                    <li>Cross-platform by default</li>
                    <li>Constantly evolving</li>
                </ul>
            </section>
        </article>
        
        <aside>
            <h3>Quick Links</h3>
            <a href="/resources">Resources</a>
        </aside>
    </main>
    
    <footer>
        <p>&copy; 2025 My Website</p>
    </footer>
</body>
</html>
```

## CSS Grid and Flexbox

```css
/* CSS Custom Properties */
:root {
    --primary: #3498db;
    --secondary: #2ecc71;
    --text: #333;
    --background: #f9f9f9;
}

/* Flexbox Navigation */
nav {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem 2rem;
    background: var(--primary);
}

/* CSS Grid Layout */
.grid-container {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
    gap: 2rem;
    padding: 2rem;
}

/* Responsive Design */
@media (max-width: 768px) {
    nav {
        flex-direction: column;
    }
    
    .grid-container {
        grid-template-columns: 1fr;
    }
}
```

## Modern JavaScript

```javascript
// Modern ES6+ JavaScript

// Fetch data from API
async function fetchUsers() {
    try {
        const response = await fetch('https://api.example.com/users');
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const users = await response.json();
        return users;
    } catch (error) {
        console.error('Failed to fetch users:', error);
        return [];
    }
}

// DOM manipulation
document.addEventListener('DOMContentLoaded', async () => {
    const container = document.getElementById('users');
    const users = await fetchUsers();
    
    users.forEach(user => {
        const card = document.createElement('div');
        card.className = 'user-card';
        card.innerHTML = `
            <h3>${user.name}</h3>
            <p>${user.email}</p>
        `;
        container.appendChild(card);
    });
});
```
"""
                }
            ],
            TrackType.DATA: [
                {
                    "id": "y1_cs107",
                    "code": "CS 107",
                    "title": "Introduction to Databases",
                    "subtitle": "Storing and Retrieving Data",
                    "credits": 4,
                    "hours": 60,
                    "weeks": 15,
                    "prerequisites": ["y1_cs101"],
                    "description": "Learn to design and query relational databases.",
                    "learning_objectives": [
                        "Design normalized database schemas",
                        "Write complex SQL queries",
                        "Understand ACID properties",
                        "Use indexes for performance",
                        "Work with transactions"
                    ],
                    "topics": [
                        {"week": 1, "topic": "Introduction to Databases", "subtopics": ["Why databases?", "Types of databases", "DBMS overview"]},
                        {"week": 2, "topic": "Relational Model", "subtopics": ["Tables", "Keys", "Relationships"]},
                        {"week": 3, "topic": "SQL Basics", "subtopics": ["SELECT", "INSERT", "UPDATE", "DELETE"]},
                        {"week": 4, "topic": "Filtering and Sorting", "subtopics": ["WHERE", "ORDER BY", "LIMIT"]},
                        {"week": 5, "topic": "Joins", "subtopics": ["INNER JOIN", "LEFT/RIGHT JOIN", "Self joins"]},
                        {"week": 6, "topic": "Aggregation", "subtopics": ["GROUP BY", "HAVING", "Aggregate functions"]},
                        {"week": 7, "topic": "Subqueries", "subtopics": ["Scalar subqueries", "Table subqueries", "Correlated subqueries"]},
                        {"week": 8, "topic": "Database Design", "subtopics": ["ER diagrams", "Entity relationships", "Cardinality"]},
                        {"week": 9, "topic": "Normalization", "subtopics": ["1NF", "2NF", "3NF", "BCNF"]},
                        {"week": 10, "topic": "Indexes", "subtopics": ["B-tree indexes", "Hash indexes", "Query optimization"]},
                        {"week": 11, "topic": "Transactions", "subtopics": ["ACID properties", "Isolation levels", "Deadlocks"]},
                        {"week": 12, "topic": "Advanced SQL", "subtopics": ["Window functions", "CTEs", "Recursive queries"]},
                        {"week": 13, "topic": "Stored Procedures", "subtopics": ["Functions", "Procedures", "Triggers"]},
                        {"week": 14, "topic": "Database Security", "subtopics": ["Users and roles", "Permissions", "SQL injection"]},
                        {"week": 15, "topic": "Final Project", "subtopics": ["Design database", "Implement", "Query optimization"]}
                    ],
                    "projects": [
                        {"name": "Student Records System", "description": "Full database for a school", "difficulty": "medium"},
                        {"name": "E-commerce Database", "description": "Products, orders, customers", "difficulty": "medium"},
                        {"name": "Social Media Schema", "description": "Users, posts, relationships", "difficulty": "hard"}
                    ],
                    "languages": ["sql"],
                    "tools": ["PostgreSQL", "MySQL", "SQLite", "DBeaver"],
                    "content": """
# Introduction to Databases

Databases are the backbone of modern applications. Learn to store,
organize, and retrieve data efficiently.

## SQL Fundamentals

```sql
-- Create tables with proper constraints
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) NOT NULL,
    password_hash CHAR(60) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE posts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(200) NOT NULL,
    content TEXT,
    published_at TIMESTAMP,
    view_count INTEGER DEFAULT 0
);

-- Insert data
INSERT INTO users (username, email, password_hash)
VALUES 
    ('alice', 'alice@example.com', '$2b$12$...'),
    ('bob', 'bob@example.com', '$2b$12$...');

-- Query with joins
SELECT 
    u.username,
    COUNT(p.id) as post_count,
    MAX(p.published_at) as last_post
FROM users u
LEFT JOIN posts p ON u.id = p.user_id
WHERE u.is_active = TRUE
GROUP BY u.id, u.username
HAVING COUNT(p.id) > 0
ORDER BY post_count DESC;
```

## Advanced Queries

```sql
-- Window functions
SELECT 
    username,
    post_count,
    RANK() OVER (ORDER BY post_count DESC) as ranking,
    post_count * 100.0 / SUM(post_count) OVER () as percentage
FROM user_stats;

-- Common Table Expressions (CTE)
WITH active_users AS (
    SELECT id, username
    FROM users
    WHERE last_login > NOW() - INTERVAL '30 days'
),
user_posts AS (
    SELECT user_id, COUNT(*) as post_count
    FROM posts
    WHERE published_at > NOW() - INTERVAL '30 days'
    GROUP BY user_id
)
SELECT 
    au.username,
    COALESCE(up.post_count, 0) as recent_posts
FROM active_users au
LEFT JOIN user_posts up ON au.id = up.user_id
ORDER BY recent_posts DESC;

-- Recursive CTE (for hierarchical data)
WITH RECURSIVE category_tree AS (
    -- Base case: root categories
    SELECT id, name, parent_id, 0 as depth
    FROM categories
    WHERE parent_id IS NULL
    
    UNION ALL
    
    -- Recursive case: child categories
    SELECT c.id, c.name, c.parent_id, ct.depth + 1
    FROM categories c
    JOIN category_tree ct ON c.parent_id = ct.id
)
SELECT * FROM category_tree ORDER BY depth, name;
```

## Database Normalization

```
1NF (First Normal Form):
  - Eliminate repeating groups
  - Create separate table for each set of related data
  - Identify each set with a primary key

2NF (Second Normal Form):
  - Be in 1NF
  - Remove partial dependencies
  - All non-key attributes depend on the whole primary key

3NF (Third Normal Form):
  - Be in 2NF
  - Remove transitive dependencies
  - Non-key attributes depend only on the primary key

Example transformation:
  
BAD (unnormalized):
  Orders(order_id, customer_name, customer_email, item1, item2, item3)

GOOD (3NF):
  Customers(customer_id, name, email)
  Orders(order_id, customer_id, order_date)
  OrderItems(order_id, product_id, quantity, price)
  Products(product_id, name, description)
```
"""
                }
            ]
        },
        "capstone": {
            "id": "y1_capstone",
            "title": "Year 1 Capstone: Build Your First Application",
            "description": "Combine everything you've learned to build a complete application",
            "hours": 60,
            "deliverables": [
                "Working application with frontend and backend",
                "Database design document",
                "User documentation",
                "Technical presentation"
            ]
        }
    },
    
    # ========================================================================
    # YEAR 2: CORE YEAR - Data Structures & Algorithms
    # ========================================================================
    "year_2": {
        "year": 2,
        "name": "Core Year",
        "theme": "Data Structures & Algorithms",
        "level": DifficultyLevel.BEGINNER,
        "total_hours": 720,
        "parallel_courses": 6,
        "description": "Master fundamental data structures and algorithms - the core of CS.",
        "tracks": {
            TrackType.CORE: [
                {
                    "id": "y2_cs201",
                    "code": "CS 201",
                    "title": "Data Structures",
                    "subtitle": "Organizing Data Efficiently",
                    "credits": 4,
                    "hours": 60,
                    "weeks": 15,
                    "prerequisites": ["y1_cs101", "y1_cs102"],
                    "description": "Learn fundamental data structures and their implementations.",
                    "learning_objectives": [
                        "Implement arrays, linked lists, stacks, and queues",
                        "Build and traverse binary trees and BSTs",
                        "Understand hash tables and collision resolution",
                        "Implement heaps and priority queues",
                        "Work with graphs and graph representations"
                    ],
                    "topics": [
                        {"week": 1, "topic": "Arrays and Dynamic Arrays", "subtopics": ["Static arrays", "Dynamic arrays", "Amortized analysis"]},
                        {"week": 2, "topic": "Linked Lists", "subtopics": ["Singly linked", "Doubly linked", "Circular lists"]},
                        {"week": 3, "topic": "Stacks", "subtopics": ["Array implementation", "Linked list implementation", "Applications"]},
                        {"week": 4, "topic": "Queues", "subtopics": ["Queue variants", "Circular queue", "Deque"]},
                        {"week": 5, "topic": "Trees Introduction", "subtopics": ["Tree terminology", "Binary trees", "Tree traversals"]},
                        {"week": 6, "topic": "Binary Search Trees", "subtopics": ["BST operations", "Balancing issues", "AVL trees intro"]},
                        {"week": 7, "topic": "Balanced Trees", "subtopics": ["AVL trees", "Red-black trees", "2-3 trees"]},
                        {"week": 8, "topic": "Heaps", "subtopics": ["Binary heaps", "Heap operations", "Heapsort"]},
                        {"week": 9, "topic": "Priority Queues", "subtopics": ["PQ implementations", "Applications", "Fibonacci heaps intro"]},
                        {"week": 10, "topic": "Hash Tables", "subtopics": ["Hash functions", "Collision handling", "Load factor"]},
                        {"week": 11, "topic": "Advanced Hashing", "subtopics": ["Open addressing", "Chaining", "Perfect hashing"]},
                        {"week": 12, "topic": "Graphs Introduction", "subtopics": ["Graph terminology", "Representations", "Adjacency list/matrix"]},
                        {"week": 13, "topic": "Graph Traversals", "subtopics": ["BFS", "DFS", "Applications"]},
                        {"week": 14, "topic": "Advanced Data Structures", "subtopics": ["Tries", "Segment trees", "Union-Find"]},
                        {"week": 15, "topic": "Final Project", "subtopics": ["Implementation", "Analysis", "Presentation"]}
                    ],
                    "projects": [
                        {"name": "Text Editor Buffer", "description": "Rope data structure", "difficulty": "hard"},
                        {"name": "LRU Cache", "description": "Implement LRU cache", "difficulty": "medium"},
                        {"name": "Spell Checker", "description": "Trie-based spell checker", "difficulty": "medium"}
                    ],
                    "languages": ["python", "c", "java"],
                    "content": """
# Data Structures

Data structures are ways of organizing data for efficient access and modification.

## Core Data Structures

### Linked List Implementation

```python
class Node:
    def __init__(self, data):
        self.data = data
        self.next = None

class LinkedList:
    def __init__(self):
        self.head = None
        self.size = 0
    
    def append(self, data):
        new_node = Node(data)
        if not self.head:
            self.head = new_node
        else:
            current = self.head
            while current.next:
                current = current.next
            current.next = new_node
        self.size += 1
    
    def prepend(self, data):
        new_node = Node(data)
        new_node.next = self.head
        self.head = new_node
        self.size += 1
    
    def delete(self, data):
        if not self.head:
            return
        if self.head.data == data:
            self.head = self.head.next
            self.size -= 1
            return
        current = self.head
        while current.next:
            if current.next.data == data:
                current.next = current.next.next
                self.size -= 1
                return
            current = current.next
```

### Binary Search Tree

```python
class TreeNode:
    def __init__(self, val):
        self.val = val
        self.left = None
        self.right = None

class BST:
    def __init__(self):
        self.root = None
    
    def insert(self, val):
        if not self.root:
            self.root = TreeNode(val)
            return
        self._insert_recursive(self.root, val)
    
    def _insert_recursive(self, node, val):
        if val < node.val:
            if node.left:
                self._insert_recursive(node.left, val)
            else:
                node.left = TreeNode(val)
        else:
            if node.right:
                self._insert_recursive(node.right, val)
            else:
                node.right = TreeNode(val)
    
    def search(self, val):
        return self._search_recursive(self.root, val)
    
    def _search_recursive(self, node, val):
        if not node:
            return None
        if val == node.val:
            return node
        elif val < node.val:
            return self._search_recursive(node.left, val)
        else:
            return self._search_recursive(node.right, val)
    
    def inorder(self):
        result = []
        self._inorder_recursive(self.root, result)
        return result
    
    def _inorder_recursive(self, node, result):
        if node:
            self._inorder_recursive(node.left, result)
            result.append(node.val)
            self._inorder_recursive(node.right, result)
```

### Hash Table

```python
class HashTable:
    def __init__(self, size=16):
        self.size = size
        self.buckets = [[] for _ in range(size)]
        self.count = 0
    
    def _hash(self, key):
        return hash(key) % self.size
    
    def put(self, key, value):
        index = self._hash(key)
        bucket = self.buckets[index]
        
        for i, (k, v) in enumerate(bucket):
            if k == key:
                bucket[i] = (key, value)
                return
        
        bucket.append((key, value))
        self.count += 1
        
        if self.count / self.size > 0.75:
            self._resize()
    
    def get(self, key):
        index = self._hash(key)
        bucket = self.buckets[index]
        
        for k, v in bucket:
            if k == key:
                return v
        raise KeyError(key)
    
    def _resize(self):
        old_buckets = self.buckets
        self.size *= 2
        self.buckets = [[] for _ in range(self.size)]
        self.count = 0
        
        for bucket in old_buckets:
            for key, value in bucket:
                self.put(key, value)
```
"""
                },
                {
                    "id": "y2_cs202",
                    "code": "CS 202",
                    "title": "Algorithms",
                    "subtitle": "Solving Problems Efficiently",
                    "credits": 4,
                    "hours": 60,
                    "weeks": 15,
                    "prerequisites": ["y2_cs201", "y1_math101"],
                    "description": "Master fundamental algorithms and complexity analysis.",
                    "learning_objectives": [
                        "Analyze algorithm complexity using Big-O notation",
                        "Implement sorting and searching algorithms",
                        "Apply divide-and-conquer strategies",
                        "Use dynamic programming for optimization",
                        "Solve graph problems efficiently"
                    ],
                    "topics": [
                        {"week": 1, "topic": "Algorithm Analysis", "subtopics": ["Big-O", "Big-Omega", "Big-Theta"]},
                        {"week": 2, "topic": "Searching", "subtopics": ["Linear search", "Binary search", "Interpolation search"]},
                        {"week": 3, "topic": "Basic Sorting", "subtopics": ["Bubble sort", "Selection sort", "Insertion sort"]},
                        {"week": 4, "topic": "Efficient Sorting", "subtopics": ["Merge sort", "Quick sort", "Analysis"]},
                        {"week": 5, "topic": "Linear Time Sorting", "subtopics": ["Counting sort", "Radix sort", "Bucket sort"]},
                        {"week": 6, "topic": "Divide and Conquer", "subtopics": ["D&C paradigm", "Master theorem", "Applications"]},
                        {"week": 7, "topic": "Greedy Algorithms", "subtopics": ["Greedy paradigm", "Activity selection", "Huffman coding"]},
                        {"week": 8, "topic": "Dynamic Programming I", "subtopics": ["DP concepts", "Memoization", "Tabulation"]},
                        {"week": 9, "topic": "Dynamic Programming II", "subtopics": ["LCS", "Edit distance", "Knapsack"]},
                        {"week": 10, "topic": "Graph Algorithms I", "subtopics": ["Shortest paths", "Dijkstra", "Bellman-Ford"]},
                        {"week": 11, "topic": "Graph Algorithms II", "subtopics": ["All-pairs shortest paths", "Floyd-Warshall", "Johnson's"]},
                        {"week": 12, "topic": "Graph Algorithms III", "subtopics": ["MST", "Prim's", "Kruskal's"]},
                        {"week": 13, "topic": "Network Flow", "subtopics": ["Max flow", "Ford-Fulkerson", "Applications"]},
                        {"week": 14, "topic": "String Algorithms", "subtopics": ["Pattern matching", "KMP", "Rabin-Karp"]},
                        {"week": 15, "topic": "NP-Completeness Intro", "subtopics": ["P vs NP", "Reductions", "NP-hard problems"]}
                    ],
                    "projects": [
                        {"name": "Sorting Visualizer", "description": "Visualize sorting algorithms", "difficulty": "medium"},
                        {"name": "Path Finder", "description": "Visualize graph algorithms", "difficulty": "medium"},
                        {"name": "Algorithm Competition", "description": "Solve competitive programming problems", "difficulty": "hard"}
                    ],
                    "languages": ["python", "cpp"],
                    "content": """
# Algorithms

Algorithms are step-by-step procedures for solving problems efficiently.

## Complexity Analysis

```
Time Complexity Classes:

O(1)        Constant     Accessing array element
O(log n)    Logarithmic  Binary search
O(n)        Linear       Linear search
O(n log n)  Linearithmic Efficient sorting
O(n²)       Quadratic    Nested loops
O(2^n)      Exponential  Subset enumeration
O(n!)       Factorial    Permutation generation

Space Complexity:
- Auxiliary space (extra space used)
- Total space (input + auxiliary)
```

## Classic Algorithms

### Merge Sort

```python
def merge_sort(arr):
    if len(arr) <= 1:
        return arr
    
    mid = len(arr) // 2
    left = merge_sort(arr[:mid])
    right = merge_sort(arr[mid:])
    
    return merge(left, right)

def merge(left, right):
    result = []
    i = j = 0
    
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1
    
    result.extend(left[i:])
    result.extend(right[j:])
    return result
```

### Dynamic Programming - Fibonacci

```python
# Naive recursion: O(2^n)
def fib_naive(n):
    if n <= 1:
        return n
    return fib_naive(n-1) + fib_naive(n-2)

# Memoization (top-down): O(n)
def fib_memo(n, memo={}):
    if n in memo:
        return memo[n]
    if n <= 1:
        return n
    memo[n] = fib_memo(n-1, memo) + fib_memo(n-2, memo)
    return memo[n]

# Tabulation (bottom-up): O(n)
def fib_tab(n):
    if n <= 1:
        return n
    dp = [0] * (n + 1)
    dp[1] = 1
    for i in range(2, n + 1):
        dp[i] = dp[i-1] + dp[i-2]
    return dp[n]

# Space optimized: O(1)
def fib_optimal(n):
    if n <= 1:
        return n
    prev, curr = 0, 1
    for _ in range(2, n + 1):
        prev, curr = curr, prev + curr
    return curr
```

### Dijkstra's Shortest Path

```python
import heapq

def dijkstra(graph, start):
    distances = {node: float('infinity') for node in graph}
    distances[start] = 0
    pq = [(0, start)]
    visited = set()
    
    while pq:
        current_distance, current_node = heapq.heappop(pq)
        
        if current_node in visited:
            continue
        visited.add(current_node)
        
        for neighbor, weight in graph[current_node].items():
            distance = current_distance + weight
            
            if distance < distances[neighbor]:
                distances[neighbor] = distance
                heapq.heappush(pq, (distance, neighbor))
    
    return distances
```
"""
                }
            ],
            TrackType.THEORY: [
                {
                    "id": "y2_math201",
                    "code": "MATH 201",
                    "title": "Discrete Mathematics II",
                    "subtitle": "Advanced Discrete Structures",
                    "credits": 4,
                    "hours": 60,
                    "weeks": 15,
                    "prerequisites": ["y1_math101"],
                    "description": "Advanced discrete mathematics including graph theory and number theory.",
                    "topics": [
                        {"week": 1, "topic": "Advanced Counting", "subtopics": ["Generating functions", "Recurrence relations"]},
                        {"week": 2, "topic": "Graph Theory Basics", "subtopics": ["Graphs", "Paths", "Cycles"]},
                        {"week": 3, "topic": "Trees", "subtopics": ["Tree properties", "Spanning trees", "Counting trees"]},
                        {"week": 4, "topic": "Planar Graphs", "subtopics": ["Euler's formula", "Coloring", "Kuratowski's theorem"]},
                        {"week": 5, "topic": "Graph Algorithms", "subtopics": ["Connectivity", "Matching", "Network flow"]},
                        {"week": 6, "topic": "Number Theory I", "subtopics": ["Divisibility", "Primes", "GCD/LCM"]},
                        {"week": 7, "topic": "Number Theory II", "subtopics": ["Modular arithmetic", "Fermat's little theorem"]},
                        {"week": 8, "topic": "Number Theory III", "subtopics": ["RSA cryptography", "Chinese remainder theorem"]},
                        {"week": 9, "topic": "Algebraic Structures", "subtopics": ["Groups", "Rings", "Fields intro"]},
                        {"week": 10, "topic": "Boolean Algebra", "subtopics": ["Boolean functions", "Karnaugh maps", "Circuit design"]},
                        {"week": 11, "topic": "Combinatorics", "subtopics": ["Pigeonhole principle", "Ramsey theory"]},
                        {"week": 12, "topic": "Probability II", "subtopics": ["Random variables", "Expected value", "Variance"]},
                        {"week": 13, "topic": "Probabilistic Analysis", "subtopics": ["Randomized algorithms", "Analysis techniques"]},
                        {"week": 14, "topic": "Information Theory", "subtopics": ["Entropy", "Coding theory basics"]},
                        {"week": 15, "topic": "Applications", "subtopics": ["Cryptography", "Coding", "Algorithm design"]}
                    ],
                    "languages": [],
                    "content": """
# Discrete Mathematics II

Building on foundations to explore deeper mathematical structures.

## Graph Theory

```
Basic Definitions:
- Graph G = (V, E) where V is vertices, E is edges
- Degree of vertex: number of edges incident to it
- Path: sequence of vertices connected by edges
- Cycle: path that starts and ends at same vertex
- Connected: path exists between any two vertices

Important Theorems:
- Handshaking Lemma: Sum of degrees = 2|E|
- Euler's Formula (planar): V - E + F = 2
- Four Color Theorem: Any planar graph is 4-colorable
```

## Number Theory

```
Modular Arithmetic:
- a ≡ b (mod n) means n | (a - b)
- (a + b) mod n = ((a mod n) + (b mod n)) mod n
- (a × b) mod n = ((a mod n) × (b mod n)) mod n

Fermat's Little Theorem:
- If p is prime and gcd(a, p) = 1:
  a^(p-1) ≡ 1 (mod p)

RSA Key Generation:
1. Choose primes p, q
2. n = p × q
3. φ(n) = (p-1)(q-1)
4. Choose e such that gcd(e, φ(n)) = 1
5. d = e^(-1) mod φ(n)
6. Public key: (n, e), Private key: (n, d)
```
"""
                }
            ],
            TrackType.SYSTEMS: [
                {
                    "id": "y2_cs204",
                    "code": "CS 204",
                    "title": "Object-Oriented Programming",
                    "subtitle": "Designing with Objects",
                    "credits": 4,
                    "hours": 60,
                    "weeks": 15,
                    "prerequisites": ["y1_cs101", "y1_cs102"],
                    "description": "Master object-oriented design principles using Java and C++.",
                    "topics": [
                        {"week": 1, "topic": "OOP Fundamentals", "subtopics": ["Classes", "Objects", "Encapsulation"]},
                        {"week": 2, "topic": "Inheritance", "subtopics": ["Extending classes", "Method overriding", "super keyword"]},
                        {"week": 3, "topic": "Polymorphism", "subtopics": ["Runtime polymorphism", "Virtual functions", "Dynamic binding"]},
                        {"week": 4, "topic": "Abstract Classes", "subtopics": ["Abstract methods", "Interfaces", "Multiple inheritance"]},
                        {"week": 5, "topic": "Java Collections", "subtopics": ["List", "Set", "Map", "Iterators"]},
                        {"week": 6, "topic": "Generics", "subtopics": ["Generic classes", "Generic methods", "Type bounds"]},
                        {"week": 7, "topic": "Exception Handling", "subtopics": ["Try-catch", "Custom exceptions", "Best practices"]},
                        {"week": 8, "topic": "SOLID Principles", "subtopics": ["SRP", "OCP", "LSP", "ISP", "DIP"]},
                        {"week": 9, "topic": "Design Patterns I", "subtopics": ["Singleton", "Factory", "Builder"]},
                        {"week": 10, "topic": "Design Patterns II", "subtopics": ["Observer", "Strategy", "Decorator"]},
                        {"week": 11, "topic": "Design Patterns III", "subtopics": ["Adapter", "Facade", "Composite"]},
                        {"week": 12, "topic": "Unit Testing", "subtopics": ["JUnit", "Test-driven development", "Mocking"]},
                        {"week": 13, "topic": "Refactoring", "subtopics": ["Code smells", "Refactoring techniques"]},
                        {"week": 14, "topic": "UML", "subtopics": ["Class diagrams", "Sequence diagrams", "Use cases"]},
                        {"week": 15, "topic": "Final Project", "subtopics": ["Design", "Implementation", "Testing"]}
                    ],
                    "projects": [
                        {"name": "Library Management System", "description": "Full OOP system", "difficulty": "medium"},
                        {"name": "Game Framework", "description": "Build a game engine", "difficulty": "hard"}
                    ],
                    "languages": ["java", "cpp"],
                    "content": """
# Object-Oriented Programming

OOP is a paradigm based on "objects" containing data and code.

## The Four Pillars

### Encapsulation
```java
public class BankAccount {
    private double balance;  // Hidden from outside
    private String accountId;
    
    public BankAccount(String id, double initialBalance) {
        this.accountId = id;
        this.balance = initialBalance;
    }
    
    public void deposit(double amount) {
        if (amount > 0) {
            balance += amount;
        }
    }
    
    public boolean withdraw(double amount) {
        if (amount > 0 && amount <= balance) {
            balance -= amount;
            return true;
        }
        return false;
    }
    
    public double getBalance() {
        return balance;
    }
}
```

### Inheritance & Polymorphism
```java
public abstract class Shape {
    protected String color;
    
    public Shape(String color) {
        this.color = color;
    }
    
    public abstract double area();
    public abstract double perimeter();
}

public class Circle extends Shape {
    private double radius;
    
    public Circle(String color, double radius) {
        super(color);
        this.radius = radius;
    }
    
    @Override
    public double area() {
        return Math.PI * radius * radius;
    }
    
    @Override
    public double perimeter() {
        return 2 * Math.PI * radius;
    }
}

public class Rectangle extends Shape {
    private double width, height;
    
    public Rectangle(String color, double w, double h) {
        super(color);
        this.width = w;
        this.height = h;
    }
    
    @Override
    public double area() {
        return width * height;
    }
    
    @Override
    public double perimeter() {
        return 2 * (width + height);
    }
}
```

## SOLID Principles

```
S - Single Responsibility: A class should have one reason to change
O - Open/Closed: Open for extension, closed for modification  
L - Liskov Substitution: Subtypes must be substitutable for base types
I - Interface Segregation: Many specific interfaces > one general interface
D - Dependency Inversion: Depend on abstractions, not concretions
```
"""
                }
            ]
        }
    },
    
    # ========================================================================
    # YEARS 3-15 CONDENSED (Due to space, providing structure and key courses)
    # ========================================================================
    
    "year_3": {
        "year": 3,
        "name": "Systems Year",
        "theme": "Computer Architecture & Operating Systems",
        "level": DifficultyLevel.INTERMEDIATE,
        "total_hours": 720,
        "description": "Deep dive into how computers and operating systems work.",
        "key_courses": [
            {"id": "y3_cs301", "code": "CS 301", "title": "Computer Architecture", "hours": 60},
            {"id": "y3_cs302", "code": "CS 302", "title": "Operating Systems", "hours": 60},
            {"id": "y3_cs303", "code": "CS 303", "title": "Systems Programming", "hours": 60},
            {"id": "y3_cs304", "code": "CS 304", "title": "Computer Networks", "hours": 60},
            {"id": "y3_cs305", "code": "CS 305", "title": "Parallel Computing", "hours": 60},
            {"id": "y3_cs306", "code": "CS 306", "title": "Embedded Systems", "hours": 60}
        ]
    },
    
    "year_4": {
        "year": 4,
        "name": "Theory Year",
        "theme": "Theory of Computation & Formal Methods",
        "level": DifficultyLevel.INTERMEDIATE,
        "total_hours": 720,
        "description": "Understand the theoretical foundations of computing.",
        "key_courses": [
            {"id": "y4_cs401", "code": "CS 401", "title": "Theory of Computation", "hours": 60},
            {"id": "y4_cs402", "code": "CS 402", "title": "Programming Languages", "hours": 60},
            {"id": "y4_cs403", "code": "CS 403", "title": "Formal Methods", "hours": 60},
            {"id": "y4_cs404", "code": "CS 404", "title": "Logic in CS", "hours": 60},
            {"id": "y4_math401", "code": "MATH 401", "title": "Linear Algebra for CS", "hours": 60},
            {"id": "y4_math402", "code": "MATH 402", "title": "Probability & Statistics", "hours": 60}
        ]
    },
    
    "year_5": {
        "year": 5,
        "name": "Software Engineering Year",
        "theme": "Professional Software Development",
        "level": DifficultyLevel.INTERMEDIATE,
        "total_hours": 720,
        "description": "Build production-quality software systems.",
        "key_courses": [
            {"id": "y5_cs501", "code": "CS 501", "title": "Software Engineering", "hours": 60},
            {"id": "y5_cs502", "code": "CS 502", "title": "Software Architecture", "hours": 60},
            {"id": "y5_cs503", "code": "CS 503", "title": "DevOps & Cloud Computing", "hours": 60},
            {"id": "y5_cs504", "code": "CS 504", "title": "Mobile Development", "hours": 60},
            {"id": "y5_cs505", "code": "CS 505", "title": "Full-Stack Development", "hours": 60},
            {"id": "y5_cs506", "code": "CS 506", "title": "Software Testing & QA", "hours": 60}
        ]
    },
    
    "year_6": {
        "year": 6,
        "name": "Database Year",
        "theme": "Data Management & Distributed Systems",
        "level": DifficultyLevel.INTERMEDIATE,
        "total_hours": 720,
        "description": "Master data storage, retrieval, and distributed systems.",
        "key_courses": [
            {"id": "y6_cs601", "code": "CS 601", "title": "Advanced Databases", "hours": 60},
            {"id": "y6_cs602", "code": "CS 602", "title": "Distributed Systems", "hours": 60},
            {"id": "y6_cs603", "code": "CS 603", "title": "Big Data Systems", "hours": 60},
            {"id": "y6_cs604", "code": "CS 604", "title": "NoSQL Databases", "hours": 60},
            {"id": "y6_cs605", "code": "CS 605", "title": "Data Warehousing", "hours": 60},
            {"id": "y6_cs606", "code": "CS 606", "title": "Stream Processing", "hours": 60}
        ]
    },
    
    "year_7": {
        "year": 7,
        "name": "Networks & Security Year",
        "theme": "Networking, Security & Cryptography",
        "level": DifficultyLevel.ADVANCED,
        "total_hours": 720,
        "description": "Secure systems and network infrastructure.",
        "key_courses": [
            {"id": "y7_cs701", "code": "CS 701", "title": "Advanced Networking", "hours": 60},
            {"id": "y7_cs702", "code": "CS 702", "title": "Computer Security", "hours": 60},
            {"id": "y7_cs703", "code": "CS 703", "title": "Cryptography", "hours": 60},
            {"id": "y7_cs704", "code": "CS 704", "title": "Network Security", "hours": 60},
            {"id": "y7_cs705", "code": "CS 705", "title": "Ethical Hacking", "hours": 60},
            {"id": "y7_cs706", "code": "CS 706", "title": "Blockchain Technology", "hours": 60}
        ]
    },
    
    "year_8": {
        "year": 8,
        "name": "AI Foundations Year",
        "theme": "Machine Learning & Artificial Intelligence",
        "level": DifficultyLevel.ADVANCED,
        "total_hours": 720,
        "description": "Enter the world of intelligent systems.",
        "key_courses": [
            {"id": "y8_cs801", "code": "CS 801", "title": "Machine Learning", "hours": 60},
            {"id": "y8_cs802", "code": "CS 802", "title": "Deep Learning", "hours": 60},
            {"id": "y8_cs803", "code": "CS 803", "title": "Natural Language Processing", "hours": 60},
            {"id": "y8_cs804", "code": "CS 804", "title": "Computer Vision", "hours": 60},
            {"id": "y8_cs805", "code": "CS 805", "title": "Reinforcement Learning", "hours": 60},
            {"id": "y8_cs806", "code": "CS 806", "title": "AI Ethics & Safety", "hours": 60}
        ]
    },
    
    "year_9": {
        "year": 9,
        "name": "Compilers Year",
        "theme": "Language Implementation & Compiler Construction",
        "level": DifficultyLevel.ADVANCED,
        "total_hours": 720,
        "description": "Build programming languages and compilers.",
        "key_courses": [
            {"id": "y9_cs901", "code": "CS 901", "title": "Compiler Construction", "hours": 60},
            {"id": "y9_cs902", "code": "CS 902", "title": "Language Design", "hours": 60},
            {"id": "y9_cs903", "code": "CS 903", "title": "Runtime Systems", "hours": 60},
            {"id": "y9_cs904", "code": "CS 904", "title": "Static Analysis", "hours": 60},
            {"id": "y9_cs905", "code": "CS 905", "title": "JIT Compilation", "hours": 60},
            {"id": "y9_cs906", "code": "CS 906", "title": "Program Optimization", "hours": 60}
        ]
    },
    
    "year_10": {
        "year": 10,
        "name": "Graphics Year",
        "theme": "Computer Graphics & Visualization",
        "level": DifficultyLevel.ADVANCED,
        "total_hours": 720,
        "description": "Create stunning visual experiences.",
        "key_courses": [
            {"id": "y10_cs1001", "code": "CS 1001", "title": "Computer Graphics", "hours": 60},
            {"id": "y10_cs1002", "code": "CS 1002", "title": "3D Rendering", "hours": 60},
            {"id": "y10_cs1003", "code": "CS 1003", "title": "Game Engine Development", "hours": 60},
            {"id": "y10_cs1004", "code": "CS 1004", "title": "Virtual Reality", "hours": 60},
            {"id": "y10_cs1005", "code": "CS 1005", "title": "Scientific Visualization", "hours": 60},
            {"id": "y10_cs1006", "code": "CS 1006", "title": "GPU Programming", "hours": 60}
        ]
    },
    
    "year_11": {
        "year": 11,
        "name": "Research Year I",
        "theme": "Advanced Algorithms & Complexity Theory",
        "level": DifficultyLevel.EXPERT,
        "total_hours": 720,
        "description": "Push the boundaries of algorithmic knowledge.",
        "key_courses": [
            {"id": "y11_cs1101", "code": "CS 1101", "title": "Advanced Algorithms", "hours": 60},
            {"id": "y11_cs1102", "code": "CS 1102", "title": "Computational Complexity", "hours": 60},
            {"id": "y11_cs1103", "code": "CS 1103", "title": "Approximation Algorithms", "hours": 60},
            {"id": "y11_cs1104", "code": "CS 1104", "title": "Randomized Algorithms", "hours": 60},
            {"id": "y11_cs1105", "code": "CS 1105", "title": "Online Algorithms", "hours": 60},
            {"id": "y11_cs1106", "code": "CS 1106", "title": "Quantum Computing", "hours": 60}
        ]
    },
    
    "year_12": {
        "year": 12,
        "name": "Research Year II",
        "theme": "Distributed Computing & Advanced Systems",
        "level": DifficultyLevel.EXPERT,
        "total_hours": 720,
        "description": "Design and analyze large-scale distributed systems.",
        "key_courses": [
            {"id": "y12_cs1201", "code": "CS 1201", "title": "Advanced Distributed Systems", "hours": 60},
            {"id": "y12_cs1202", "code": "CS 1202", "title": "Consensus Protocols", "hours": 60},
            {"id": "y12_cs1203", "code": "CS 1203", "title": "Distributed Databases", "hours": 60},
            {"id": "y12_cs1204", "code": "CS 1204", "title": "Cloud Infrastructure", "hours": 60},
            {"id": "y12_cs1205", "code": "CS 1205", "title": "Fault Tolerance", "hours": 60},
            {"id": "y12_cs1206", "code": "CS 1206", "title": "Performance Engineering", "hours": 60}
        ]
    },
    
    "year_13": {
        "year": 13,
        "name": "Specialization Year",
        "theme": "Domain Expertise & Research Methodology",
        "level": DifficultyLevel.MASTER,
        "total_hours": 720,
        "description": "Deep specialization in chosen research area.",
        "tracks": {
            "systems_track": [
                {"id": "y13_sys1", "title": "Advanced OS Research", "hours": 120},
                {"id": "y13_sys2", "title": "Systems Security Research", "hours": 120}
            ],
            "ai_track": [
                {"id": "y13_ai1", "title": "Advanced Deep Learning", "hours": 120},
                {"id": "y13_ai2", "title": "AI Safety Research", "hours": 120}
            ],
            "theory_track": [
                {"id": "y13_th1", "title": "Computational Complexity Research", "hours": 120},
                {"id": "y13_th2", "title": "Algorithmic Game Theory", "hours": 120}
            ]
        }
    },
    
    "year_14": {
        "year": 14,
        "name": "Innovation Year",
        "theme": "Original Research & Publication",
        "level": DifficultyLevel.MASTER,
        "total_hours": 720,
        "description": "Conduct original research and publish findings.",
        "components": [
            {"title": "Research Proposal Development", "hours": 120},
            {"title": "Literature Review & State of the Art", "hours": 120},
            {"title": "Research Implementation", "hours": 240},
            {"title": "Paper Writing & Publication", "hours": 120},
            {"title": "Conference Presentation", "hours": 60},
            {"title": "Peer Review Participation", "hours": 60}
        ]
    },
    
    "year_15": {
        "year": 15,
        "name": "Mastery Year",
        "theme": "Teaching, Leadership & Dissertation",
        "level": DifficultyLevel.PHD,
        "total_hours": 720,
        "description": "Complete your journey to computer science mastery.",
        "components": [
            {"title": "Dissertation Writing", "hours": 300},
            {"title": "Dissertation Defense Preparation", "hours": 60},
            {"title": "Teaching Practicum", "hours": 120},
            {"title": "Research Mentorship", "hours": 60},
            {"title": "Industry Collaboration", "hours": 120},
            {"title": "Career Development", "hours": 60}
        ],
        "milestones": [
            "Complete and defend doctoral dissertation",
            "Publish at least 3 peer-reviewed papers",
            "Present at international conferences",
            "Mentor junior researchers",
            "Develop course curriculum",
            "Establish research collaboration network"
        ]
    },
    
    # ========================================================================
    # METADATA AND SUMMARY
    # ========================================================================
    
    "summary": {
        "total_years": 15,
        "total_courses": 180,
        "total_hours": 12000,
        "certification_path": [
            {"years": "1-2", "certification": "CS Fundamentals Certificate", "hours": 1440},
            {"years": "3-4", "certification": "Associate in Computer Science", "hours": 2880},
            {"years": "5-8", "certification": "Bachelor of Science in CS", "hours": 5760},
            {"years": "9-12", "certification": "Master of Science in CS", "hours": 8640},
            {"years": "13-15", "certification": "Doctor of Philosophy in CS", "hours": 10800}
        ],
        "tracks": [
            {"name": "Systems Track", "focus": "Operating Systems, Architecture, Embedded"},
            {"name": "Theory Track", "focus": "Algorithms, Complexity, Formal Methods"},
            {"name": "AI/ML Track", "focus": "Machine Learning, Deep Learning, NLP"},
            {"name": "Security Track", "focus": "Cryptography, Network Security, Ethical Hacking"},
            {"name": "Web/Mobile Track", "focus": "Full-Stack, Mobile, Cloud"},
            {"name": "Data Track", "focus": "Databases, Big Data, Analytics"},
            {"name": "Graphics Track", "focus": "Computer Graphics, VR/AR, Game Dev"},
            {"name": "Compilers Track", "focus": "Language Design, Compiler Construction"}
        ]
    }
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_year_info(year: int) -> dict:
    """Get information about a specific year in the curriculum."""
    year_key = f"year_{year}"
    if year_key in CS_BIBLE:
        return CS_BIBLE[year_key]
    return None

def get_course(course_id: str) -> dict:
    """Get information about a specific course."""
    for year_num in range(1, 16):
        year_key = f"year_{year_num}"
        if year_key in CS_BIBLE:
            year_data = CS_BIBLE[year_key]
            if "tracks" in year_data:
                for track_name, courses in year_data["tracks"].items():
                    if isinstance(courses, list):
                        for course in courses:
                            if course.get("id") == course_id:
                                return course
            if "key_courses" in year_data:
                for course in year_data["key_courses"]:
                    if course.get("id") == course_id:
                        return course
    return None

def get_all_courses() -> list:
    """Get a list of all courses in the curriculum."""
    courses = []
    for year_num in range(1, 16):
        year_key = f"year_{year_num}"
        if year_key in CS_BIBLE:
            year_data = CS_BIBLE[year_key]
            if "tracks" in year_data:
                for track_name, track_courses in year_data["tracks"].items():
                    if isinstance(track_courses, list):
                        for course in track_courses:
                            courses.append({
                                "year": year_num,
                                "track": track_name,
                                **course
                            })
            if "key_courses" in year_data:
                for course in year_data["key_courses"]:
                    courses.append({
                        "year": year_num,
                        "track": "core",
                        **course
                    })
    return courses

def get_curriculum_stats() -> dict:
    """Get statistics about the curriculum."""
    return {
        "title": CS_BIBLE["title"],
        "subtitle": CS_BIBLE["subtitle"],
        "total_years": CS_BIBLE["total_years"],
        "total_courses": CS_BIBLE["total_courses"],
        "total_hours": CS_BIBLE["total_hours"],
        "parallel_tracks": CS_BIBLE["parallel_tracks"],
        "certification_levels": CS_BIBLE["certification_levels"],
        "tracks": CS_BIBLE["summary"]["tracks"]
    }
