"""
Academy Curriculum Seed Data Generator v1.0
Generates FULL curriculum for ALL tracks, bibles, exercises, projects, assessments.
Pre-seeded into MongoDB for instant loading.
"""

# ═══════════════════════════════════════════════════════════════════════════
# TRACK DEFINITIONS — Every track in the platform
# ═══════════════════════════════════════════════════════════════════════════

def _lesson(lid, title, desc, mins, diff, topics, content, code_example="", exercise=None, prereqs=None):
    """Helper to build a lesson dict."""
    l = {
        "id": lid, "title": title, "description": desc,
        "duration_minutes": mins, "difficulty": diff,
        "topics": topics, "prerequisites": prereqs or [],
        "content": content, "code_example": code_example,
    }
    if exercise:
        l["exercise"] = exercise
    return l


def _exercise(eid, title, desc, starter, solution, test_cases, hints=None):
    return {
        "id": eid, "title": title, "description": desc,
        "starter_code": starter, "solution": solution,
        "test_cases": test_cases, "hints": hints or [],
    }


def _project(pid, title, desc, difficulty, hours, requirements, starter="", tags=None):
    return {
        "id": pid, "title": title, "description": desc,
        "difficulty": difficulty, "estimated_hours": hours,
        "requirements": requirements, "starter_code": starter,
        "tags": tags or [],
    }


def _assessment(aid, title, questions, passing_score=70):
    return {
        "id": aid, "title": title, "questions": questions,
        "passing_score": passing_score, "total_points": sum(q.get("points", 10) for q in questions),
    }


def _question(qid, text, options, correct, points=10, explanation=""):
    return {
        "id": qid, "text": text, "options": options,
        "correct": correct, "points": points, "explanation": explanation,
    }


def _module(mid, name, desc, hours, lessons, project=None, assessment=None):
    m = {"id": mid, "name": name, "description": desc, "total_hours": hours, "lessons": lessons}
    if project:
        m["project"] = project
    if assessment:
        m["assessment"] = assessment
    return m


# ═══════════════════════════════════════════════════════════════════════════
# PYTHON TRACK — 200hrs
# ═══════════════════════════════════════════════════════════════════════════
def _python_track():
    return {
        "id": "python", "name": "Python Mastery", "icon": "logo-python",
        "color": "#3776AB", "total_hours": 2700, "category": "language",
        "description": "Complete Python from beginner to expert. Covers fundamentals, OOP, data structures, algorithms, web dev, data science, automation, and advanced patterns.",
        "prerequisites": [], "certificate": "Python Professional Developer",
        "modules": [
            _module("py_fundamentals", "Python Fundamentals", "Core syntax, types, control flow", 20, [
                _lesson("py_f1", "Variables & Data Types", "Integers, floats, strings, booleans, type conversion", 45, "beginner", ["variables", "types"],
                    "# Python Variables & Data Types\n\nPython is dynamically typed — you don't declare types explicitly.\n\n## Numeric Types\n```python\nage = 25          # int\npi = 3.14159      # float\ncomplex_num = 3+4j # complex\n```\n\n## Strings\n```python\nname = 'Alice'\ngreeting = f'Hello, {name}!'\nmultiline = '''This is\na multiline string'''\n```\n\n## Type Conversion\n```python\nx = int('42')       # str -> int\ny = float('3.14')   # str -> float\nz = str(100)        # int -> str\n```\n\n## Type Checking\n```python\ntype(42)          # <class 'int'>\nisinstance(42, int) # True\n```",
                    "# Try it: Variable declaration\nname = 'World'\nage = 25\npi = 3.14159\nis_student = True\nprint(f'{name} is {age} years old')\nprint(f'Pi is approximately {pi}')\nprint(f'Student: {is_student}')",
                    _exercise("py_ex1", "Variable Swap", "Swap two variables without a temp variable",
                        "a = 10\nb = 20\n# Swap a and b here\n\nprint(a, b)  # Should print: 20 10",
                        "a = 10\nb = 20\na, b = b, a\nprint(a, b)",
                        [{"input": "", "expected": "20 10"}],
                        ["Python supports tuple unpacking"])),
                _lesson("py_f2", "Control Flow", "if/elif/else, for/while loops, break/continue", 60, "beginner", ["control-flow", "loops"],
                    "# Control Flow in Python\n\n## Conditional Statements\n```python\ntemp = 72\nif temp > 80:\n    print('Hot!')\nelif temp > 60:\n    print('Nice!')\nelse:\n    print('Cold!')\n```\n\n## Ternary Operator\n```python\nstatus = 'adult' if age >= 18 else 'minor'\n```\n\n## For Loops\n```python\nfor i in range(5):\n    print(i)  # 0, 1, 2, 3, 4\n\nfor char in 'hello':\n    print(char)\n\nfor i, val in enumerate(['a','b','c']):\n    print(f'{i}: {val}')\n```\n\n## While Loops\n```python\ncount = 0\nwhile count < 5:\n    print(count)\n    count += 1\n```\n\n## Break & Continue\n```python\nfor i in range(10):\n    if i == 3: continue  # skip 3\n    if i == 7: break     # stop at 7\n    print(i)\n```",
                    "# Control flow demo\nfor i in range(1, 11):\n    if i % 2 == 0:\n        print(f'{i} is even')\n    else:\n        print(f'{i} is odd')",
                    _exercise("py_ex2", "FizzBuzz", "Print FizzBuzz for 1-100",
                        "# Print numbers 1-100. For multiples of 3 print 'Fizz',\n# multiples of 5 print 'Buzz', both print 'FizzBuzz'\nfor i in range(1, 101):\n    pass  # Your code here",
                        "for i in range(1, 101):\n    if i % 15 == 0:\n        print('FizzBuzz')\n    elif i % 3 == 0:\n        print('Fizz')\n    elif i % 5 == 0:\n        print('Buzz')\n    else:\n        print(i)",
                        [{"input": "", "expected_contains": "FizzBuzz"}],
                        ["Check divisibility by 15 first (both 3 and 5)"])),
                _lesson("py_f3", "Functions", "def, args, kwargs, return values, decorators intro", 60, "beginner", ["functions", "decorators"],
                    "# Python Functions\n\n## Basic Function\n```python\ndef greet(name):\n    return f'Hello, {name}!'\n\nprint(greet('Alice'))  # Hello, Alice!\n```\n\n## Default Arguments\n```python\ndef power(base, exp=2):\n    return base ** exp\n\npower(3)     # 9\npower(3, 3)  # 27\n```\n\n## *args and **kwargs\n```python\ndef total(*args):\n    return sum(args)\n\ntotal(1, 2, 3, 4)  # 10\n\ndef info(**kwargs):\n    for k, v in kwargs.items():\n        print(f'{k}: {v}')\n\ninfo(name='Alice', age=30)\n```\n\n## Lambda Functions\n```python\nsquare = lambda x: x ** 2\nsorted_names = sorted(names, key=lambda n: len(n))\n```\n\n## Decorators Preview\n```python\ndef timer(func):\n    import time\n    def wrapper(*args, **kwargs):\n        start = time.time()\n        result = func(*args, **kwargs)\n        print(f'{func.__name__} took {time.time()-start:.2f}s')\n        return result\n    return wrapper\n\n@timer\ndef slow():\n    import time; time.sleep(1)\n```",
                    "def factorial(n):\n    if n <= 1: return 1\n    return n * factorial(n - 1)\n\nfor i in range(10):\n    print(f'{i}! = {factorial(i)}')",
                    _exercise("py_ex3", "Palindrome Checker", "Write a function to check if a string is a palindrome",
                        "def is_palindrome(s):\n    # Return True if s is a palindrome (ignore case and spaces)\n    pass\n\nprint(is_palindrome('racecar'))  # True\nprint(is_palindrome('hello'))    # False\nprint(is_palindrome('A man a plan a canal Panama'))  # True",
                        "def is_palindrome(s):\n    cleaned = s.lower().replace(' ', '')\n    return cleaned == cleaned[::-1]\n\nprint(is_palindrome('racecar'))\nprint(is_palindrome('hello'))\nprint(is_palindrome('A man a plan a canal Panama'))",
                        [{"input": "", "expected_contains": "True"}])),
                _lesson("py_f4", "Data Structures", "Lists, tuples, dicts, sets, comprehensions", 75, "beginner", ["lists", "dicts", "sets"],
                    "# Python Data Structures\n\n## Lists (Mutable, Ordered)\n```python\nfruits = ['apple', 'banana', 'cherry']\nfruits.append('date')\nfruits.insert(1, 'blueberry')\nfruits.pop()  # removes last\nsliced = fruits[1:3]  # ['blueberry', 'banana']\n```\n\n## List Comprehensions\n```python\nsquares = [x**2 for x in range(10)]\nevens = [x for x in range(20) if x % 2 == 0]\nmatrix = [[i*j for j in range(5)] for i in range(5)]\n```\n\n## Tuples (Immutable)\n```python\npoint = (3, 4)\nx, y = point  # unpacking\ncolors = ('red', 'green', 'blue')\n```\n\n## Dictionaries\n```python\nuser = {'name': 'Alice', 'age': 30, 'role': 'dev'}\nuser['email'] = 'alice@example.com'\nfor key, val in user.items():\n    print(f'{key}: {val}')\n\n# Dict comprehension\nsquare_dict = {x: x**2 for x in range(10)}\n```\n\n## Sets\n```python\na = {1, 2, 3}\nb = {3, 4, 5}\na | b  # union: {1,2,3,4,5}\na & b  # intersection: {3}\na - b  # difference: {1,2}\n```",
                    "# Data structure operations\nnums = [3, 1, 4, 1, 5, 9, 2, 6, 5, 3, 5]\nprint(f'Sorted: {sorted(nums)}')\nprint(f'Unique: {sorted(set(nums))}')\nprint(f'Count of 5: {nums.count(5)}')\nprint(f'Sum: {sum(nums)}')\nfreq = {x: nums.count(x) for x in set(nums)}\nprint(f'Frequency: {freq}')",
                    _exercise("py_ex4", "Word Frequency Counter", "Count word occurrences in a sentence",
                        "def word_freq(text):\n    # Return a dict of word -> count\n    pass\n\nresult = word_freq('the cat sat on the mat the cat')\nprint(result)  # {'the': 3, 'cat': 2, 'sat': 1, 'on': 1, 'mat': 1}",
                        "def word_freq(text):\n    words = text.lower().split()\n    freq = {}\n    for w in words:\n        freq[w] = freq.get(w, 0) + 1\n    return freq\n\nresult = word_freq('the cat sat on the mat the cat')\nprint(result)",
                        [{"input": "", "expected_contains": "the"}])),
                _lesson("py_f5", "String Manipulation", "Formatting, regex, slicing, methods", 45, "beginner", ["strings", "regex"],
                    "# String Manipulation\n\n## F-strings (Python 3.6+)\n```python\nname = 'Alice'\nage = 30\nprint(f'{name} is {age} years old')  \nprint(f'{3.14159:.2f}')  # 3.14\nprint(f'{1000000:,}')    # 1,000,000\n```\n\n## String Methods\n```python\ns = '  Hello, World!  '\ns.strip()      # 'Hello, World!'\ns.lower()      # '  hello, world!  '\ns.upper()      # '  HELLO, WORLD!  '\ns.replace('World', 'Python')\ns.split(',')   # ['  Hello', ' World!  ']\n'-'.join(['a','b','c'])  # 'a-b-c'\n```\n\n## Regular Expressions\n```python\nimport re\npattern = r'\\b[A-Z][a-z]+\\b'\nmatches = re.findall(pattern, 'Hello World Foo bar Baz')\n# ['Hello', 'World', 'Foo', 'Baz']\n\nemail = re.search(r'[\\w.]+@[\\w.]+', 'contact: user@email.com')\nprint(email.group())  # user@email.com\n```",
                    "import re\ntext = 'Call me at 555-1234 or 555-5678'\nphones = re.findall(r'\\d{3}-\\d{4}', text)\nprint(f'Found {len(phones)} phone numbers: {phones}')",
                ),
            ],
                _project("py_proj1", "Contact Book CLI", "Build a CLI contact book with CRUD operations",
                    "beginner", 4, ["Store contacts in a dict", "Add/edit/delete/search contacts", "Save to JSON file", "Pretty print with formatting"],
                    "import json\n\ndef main():\n    contacts = {}\n    # Build your contact book here\n    pass\n\nif __name__ == '__main__':\n    main()",
                    ["python", "cli", "json"]),
                _assessment("py_assess1", "Python Fundamentals Assessment", [
                    _question("pq1", "What does `type(42)` return?", ["str", "int", "float", "number"], "int", 10, "42 is an integer literal"),
                    _question("pq2", "Which is immutable?", ["list", "dict", "tuple", "set"], "tuple", 10, "Tuples cannot be modified after creation"),
                    _question("pq3", "What does `[x**2 for x in range(5)]` produce?", ["[0,1,4,9,16]", "[1,4,9,16,25]", "[0,2,4,6,8]", "Error"], "[0,1,4,9,16]", 10),
                    _question("pq4", "What is the output of `'hello'[::-1]`?", ["'hello'", "'olleh'", "'h'", "Error"], "'olleh'", 10, "[::-1] reverses the string"),
                    _question("pq5", "Which keyword defines a function?", ["func", "function", "def", "fn"], "def", 10),
                ], 70),
            ),
            _module("py_oop", "Object-Oriented Python", "Classes, inheritance, polymorphism, magic methods", 30, [
                _lesson("py_o1", "Classes & Objects", "Defining classes, __init__, instance methods", 60, "intermediate", ["oop", "classes"],
                    "# Classes & Objects\n\n## Defining a Class\n```python\nclass Player:\n    def __init__(self, name, health=100):\n        self.name = name\n        self.health = health\n        self.inventory = []\n    \n    def take_damage(self, amount):\n        self.health = max(0, self.health - amount)\n        if self.health == 0:\n            print(f'{self.name} has been defeated!')\n    \n    def heal(self, amount):\n        self.health = min(100, self.health + amount)\n    \n    def pick_up(self, item):\n        self.inventory.append(item)\n        print(f'{self.name} picked up {item}')\n    \n    def __str__(self):\n        return f'Player({self.name}, HP:{self.health})'\n\n# Usage\nhero = Player('Aragorn')\nhero.take_damage(30)\nhero.pick_up('sword')\nprint(hero)  # Player(Aragorn, HP:70)\n```",
                    "class Player:\n    def __init__(self, name, health=100):\n        self.name = name\n        self.health = health\n    \n    def take_damage(self, amount):\n        self.health = max(0, self.health - amount)\n    \n    def __repr__(self):\n        return f'Player({self.name}, HP:{self.health})'\n\np = Player('Hero')\np.take_damage(25)\nprint(p)"),
                _lesson("py_o2", "Inheritance & Polymorphism", "Single/multiple inheritance, super(), ABC", 75, "intermediate", ["inheritance", "polymorphism"],
                    "# Inheritance\n\n```python\nclass Enemy:\n    def __init__(self, name, damage):\n        self.name = name\n        self.damage = damage\n    \n    def attack(self):\n        return f'{self.name} attacks for {self.damage} damage!'\n\nclass Dragon(Enemy):\n    def __init__(self, name):\n        super().__init__(name, damage=50)\n        self.can_fly = True\n    \n    def breathe_fire(self):\n        return f'{self.name} breathes fire for {self.damage * 2} damage!'\n\nclass Skeleton(Enemy):\n    def __init__(self):\n        super().__init__('Skeleton', damage=10)\n\n# Polymorphism\nenemies = [Dragon('Smaug'), Skeleton(), Dragon('Bahamut')]\nfor e in enemies:\n    print(e.attack())  # Same interface, different behavior\n```\n\n## Abstract Base Classes\n```python\nfrom abc import ABC, abstractmethod\n\nclass Shape(ABC):\n    @abstractmethod\n    def area(self):\n        pass\n    \n    @abstractmethod\n    def perimeter(self):\n        pass\n\nclass Circle(Shape):\n    def __init__(self, radius):\n        self.radius = radius\n    \n    def area(self):\n        return 3.14159 * self.radius ** 2\n    \n    def perimeter(self):\n        return 2 * 3.14159 * self.radius\n```",
                    "from abc import ABC, abstractmethod\n\nclass Shape(ABC):\n    @abstractmethod\n    def area(self): pass\n\nclass Rect(Shape):\n    def __init__(self, w, h): self.w, self.h = w, h\n    def area(self): return self.w * self.h\n\nclass Circle(Shape):\n    def __init__(self, r): self.r = r\n    def area(self): return 3.14159 * self.r**2\n\nshapes = [Rect(5,3), Circle(7)]\nfor s in shapes:\n    print(f'{s.__class__.__name__}: area = {s.area():.2f}')"),
                _lesson("py_o3", "Magic Methods", "__str__, __repr__, __eq__, __lt__, __add__, __len__", 60, "intermediate", ["dunder", "magic-methods"],
                    "# Magic (Dunder) Methods\n\n```python\nclass Vector:\n    def __init__(self, x, y):\n        self.x = x\n        self.y = y\n    \n    def __add__(self, other):\n        return Vector(self.x + other.x, self.y + other.y)\n    \n    def __sub__(self, other):\n        return Vector(self.x - other.x, self.y - other.y)\n    \n    def __mul__(self, scalar):\n        return Vector(self.x * scalar, self.y * scalar)\n    \n    def __abs__(self):\n        return (self.x**2 + self.y**2) ** 0.5\n    \n    def __eq__(self, other):\n        return self.x == other.x and self.y == other.y\n    \n    def __repr__(self):\n        return f'Vector({self.x}, {self.y})'\n\nv1 = Vector(3, 4)\nv2 = Vector(1, 2)\nprint(v1 + v2)    # Vector(4, 6)\nprint(abs(v1))     # 5.0\nprint(v1 * 3)      # Vector(9, 12)\n```",
                    "class Vector:\n    def __init__(self, x, y): self.x, self.y = x, y\n    def __add__(self, o): return Vector(self.x+o.x, self.y+o.y)\n    def __abs__(self): return (self.x**2+self.y**2)**0.5\n    def __repr__(self): return f'V({self.x},{self.y})'\n\nv = Vector(3,4) + Vector(1,2)\nprint(v, abs(v))"),
                _lesson("py_o4", "Properties & Descriptors", "@property, setters, data validation", 45, "intermediate", ["property", "descriptors"],
                    "# Properties\n\n```python\nclass Temperature:\n    def __init__(self, celsius=0):\n        self._celsius = celsius\n    \n    @property\n    def celsius(self):\n        return self._celsius\n    \n    @celsius.setter\n    def celsius(self, value):\n        if value < -273.15:\n            raise ValueError('Below absolute zero!')\n        self._celsius = value\n    \n    @property\n    def fahrenheit(self):\n        return self._celsius * 9/5 + 32\n    \n    @fahrenheit.setter\n    def fahrenheit(self, value):\n        self.celsius = (value - 32) * 5/9\n\nt = Temperature(100)\nprint(t.fahrenheit)  # 212.0\nt.fahrenheit = 32\nprint(t.celsius)     # 0.0\n```",
                    "class BankAccount:\n    def __init__(self, balance=0):\n        self._balance = balance\n    @property\n    def balance(self):\n        return self._balance\n    def deposit(self, amt):\n        if amt <= 0: raise ValueError('Positive only')\n        self._balance += amt\n    def withdraw(self, amt):\n        if amt > self._balance: raise ValueError('Insufficient')\n        self._balance -= amt\n\nacc = BankAccount(100)\nacc.deposit(50)\nacc.withdraw(30)\nprint(f'Balance: ${acc.balance}')"),
            ],
                _project("py_proj2", "RPG Battle System", "Build a text-based RPG with classes, inheritance, and combat",
                    "intermediate", 8, ["Player, Enemy, Spell base classes", "At least 3 enemy types", "Turn-based combat", "Inventory system", "Save/load with pickle"],
                    tags=["python", "oop", "game"]),
                _assessment("py_assess2", "OOP Assessment", [
                    _question("poq1", "What does `super().__init__()` do?", ["Creates a new object", "Calls parent constructor", "Overrides parent", "Returns None"], "Calls parent constructor", 10),
                    _question("poq2", "Which decorator makes a method a property?", ["@static", "@classmethod", "@property", "@abstract"], "@property", 10),
                    _question("poq3", "What is `__repr__` used for?", ["String for end users", "Debug representation", "Hashing", "Comparison"], "Debug representation", 10),
                ], 70),
            ),
            _module("py_advanced", "Advanced Python", "Generators, context managers, metaclasses, async", 35, [
                _lesson("py_a1", "Generators & Iterators", "yield, generator expressions, itertools", 75, "advanced", ["generators", "itertools"],
                    "# Generators\n\n## Basic Generator\n```python\ndef fibonacci():\n    a, b = 0, 1\n    while True:\n        yield a\n        a, b = b, a + b\n\n# Lazy evaluation — generates values on demand\nfib = fibonacci()\nfor _ in range(10):\n    print(next(fib), end=' ')  # 0 1 1 2 3 5 8 13 21 34\n```\n\n## Generator Expressions\n```python\nsquares = (x**2 for x in range(1000000))  # No memory allocation!\nprint(sum(squares))  # Computed lazily\n```\n\n## itertools — Infinite Iterators\n```python\nfrom itertools import count, cycle, repeat, chain, product, permutations\n\n# count(10, 2) -> 10, 12, 14, 16, ...\n# cycle('ABC') -> A, B, C, A, B, C, ...\n# chain([1,2], [3,4]) -> 1, 2, 3, 4\n# product('AB', '12') -> A1, A2, B1, B2\n# permutations('ABC', 2) -> AB, AC, BA, BC, CA, CB\n```\n\n## Pipeline with Generators\n```python\ndef read_lines(path):\n    with open(path) as f:\n        for line in f:\n            yield line.strip()\n\ndef filter_comments(lines):\n    for line in lines:\n        if not line.startswith('#'):\n            yield line\n\ndef parse_ints(lines):\n    for line in lines:\n        try: yield int(line)\n        except: pass\n\n# Memory-efficient pipeline\nnums = parse_ints(filter_comments(read_lines('data.txt')))\nprint(sum(nums))\n```",
                    "def fibonacci(n):\n    a, b = 0, 1\n    for _ in range(n):\n        yield a\n        a, b = b, a + b\n\nprint(list(fibonacci(15)))\nprint(f'Sum of first 100 fibs: {sum(fibonacci(100))}')"),
                _lesson("py_a2", "Decorators Deep Dive", "Closures, functools.wraps, parametrized decorators, class decorators", 60, "advanced", ["decorators", "closures"],
                    "# Advanced Decorators\n\n## Parametrized Decorator\n```python\nimport functools, time\n\ndef retry(max_attempts=3, delay=1):\n    def decorator(func):\n        @functools.wraps(func)\n        def wrapper(*args, **kwargs):\n            for attempt in range(1, max_attempts + 1):\n                try:\n                    return func(*args, **kwargs)\n                except Exception as e:\n                    if attempt == max_attempts:\n                        raise\n                    print(f'Attempt {attempt} failed: {e}. Retrying...')\n                    time.sleep(delay)\n        return wrapper\n    return decorator\n\n@retry(max_attempts=5, delay=0.5)\ndef fetch_data(url):\n    import random\n    if random.random() < 0.7:\n        raise ConnectionError('Network timeout')\n    return {'data': 'success'}\n```\n\n## Stacking Decorators\n```python\ndef log(func):\n    @functools.wraps(func)\n    def wrapper(*args, **kwargs):\n        print(f'Calling {func.__name__}')\n        result = func(*args, **kwargs)\n        print(f'{func.__name__} returned {result}')\n        return result\n    return wrapper\n\ndef timer(func):\n    @functools.wraps(func)\n    def wrapper(*args, **kwargs):\n        start = time.time()\n        result = func(*args, **kwargs)\n        print(f'{func.__name__} took {time.time()-start:.4f}s')\n        return result\n    return wrapper\n\n@log\n@timer  # timer runs first, then log\ndef compute(n):\n    return sum(range(n))\n```",
                    "import functools\n\ndef memoize(func):\n    cache = {}\n    @functools.wraps(func)\n    def wrapper(*args):\n        if args not in cache:\n            cache[args] = func(*args)\n        return cache[args]\n    return wrapper\n\n@memoize\ndef fib(n):\n    if n < 2: return n\n    return fib(n-1) + fib(n-2)\n\nprint(fib(50))  # Instant with memoization!"),
                _lesson("py_a3", "Async/Await", "asyncio, coroutines, event loop, aiohttp", 90, "advanced", ["async", "asyncio", "coroutines"],
                    "# Async Python\n\n## Basic Coroutine\n```python\nimport asyncio\n\nasync def fetch_data(url, delay):\n    print(f'Fetching {url}...')\n    await asyncio.sleep(delay)  # Simulates I/O\n    return f'Data from {url}'\n\nasync def main():\n    # Run concurrently\n    results = await asyncio.gather(\n        fetch_data('api.com/users', 2),\n        fetch_data('api.com/posts', 1),\n        fetch_data('api.com/comments', 3),\n    )\n    for r in results:\n        print(r)\n\nasyncio.run(main())\n```\n\n## Async Generators\n```python\nasync def async_range(n):\n    for i in range(n):\n        await asyncio.sleep(0.1)\n        yield i\n\nasync def main():\n    async for num in async_range(10):\n        print(num)\n```\n\n## Semaphore for Rate Limiting\n```python\nsem = asyncio.Semaphore(5)  # Max 5 concurrent\n\nasync def rate_limited_fetch(url):\n    async with sem:\n        return await fetch_data(url, 1)\n```",
                    "import asyncio\n\nasync def task(name, delay):\n    print(f'Task {name} starting')\n    await asyncio.sleep(delay)\n    print(f'Task {name} done after {delay}s')\n    return name\n\nasync def main():\n    results = await asyncio.gather(\n        task('A', 0.3), task('B', 0.1), task('C', 0.2)\n    )\n    print(f'Completed: {results}')\n\nasyncio.run(main())"),
                _lesson("py_a4", "Context Managers", "with statement, __enter__/__exit__, contextlib", 45, "advanced", ["context-managers"],
                    "# Context Managers\n\n## Custom Context Manager\n```python\nclass Timer:\n    def __enter__(self):\n        import time\n        self.start = time.time()\n        return self\n    \n    def __exit__(self, exc_type, exc_val, exc_tb):\n        import time\n        self.elapsed = time.time() - self.start\n        print(f'Elapsed: {self.elapsed:.4f}s')\n        return False  # Don't suppress exceptions\n\nwith Timer() as t:\n    sum(range(1000000))\nprint(f'Total: {t.elapsed:.4f}s')\n```\n\n## contextlib.contextmanager\n```python\nfrom contextlib import contextmanager\n\n@contextmanager\ndef managed_resource(name):\n    print(f'Acquiring {name}')\n    try:\n        yield name\n    finally:\n        print(f'Releasing {name}')\n\nwith managed_resource('database') as db:\n    print(f'Using {db}')\n```",
                    "from contextlib import contextmanager\nimport time\n\n@contextmanager\ndef timer(label):\n    start = time.time()\n    yield\n    print(f'{label}: {time.time()-start:.4f}s')\n\nwith timer('Sum 10M'):\n    total = sum(range(10_000_000))\nprint(f'Result: {total:,}')"),
                _lesson("py_a5", "Metaclasses & Descriptors", "type(), __new__, __init_subclass__, descriptors protocol", 60, "expert", ["metaclasses", "descriptors"],
                    "# Metaclasses\n\n## Everything is an Object\n```python\n# Classes are instances of 'type'\nclass MyClass:\n    pass\n\nprint(type(MyClass))  # <class 'type'>\nprint(type(42))       # <class 'int'>\n```\n\n## Custom Metaclass\n```python\nclass SingletonMeta(type):\n    _instances = {}\n    \n    def __call__(cls, *args, **kwargs):\n        if cls not in cls._instances:\n            cls._instances[cls] = super().__call__(*args, **kwargs)\n        return cls._instances[cls]\n\nclass Database(metaclass=SingletonMeta):\n    def __init__(self):\n        self.connected = True\n\ndb1 = Database()\ndb2 = Database()\nassert db1 is db2  # Same instance!\n```\n\n## __init_subclass__\n```python\nclass Plugin:\n    _registry = {}\n    \n    def __init_subclass__(cls, name=None, **kwargs):\n        super().__init_subclass__(**kwargs)\n        cls._registry[name or cls.__name__] = cls\n\nclass AudioPlugin(Plugin, name='audio'):\n    pass\n\nclass VideoPlugin(Plugin, name='video'):\n    pass\n\nprint(Plugin._registry)  # {'audio': AudioPlugin, 'video': VideoPlugin}\n```",
                    "class SingletonMeta(type):\n    _instances = {}\n    def __call__(cls, *a, **kw):\n        if cls not in cls._instances:\n            cls._instances[cls] = super().__call__(*a, **kw)\n        return cls._instances[cls]\n\nclass Config(metaclass=SingletonMeta):\n    def __init__(self):\n        self.debug = True\n\nc1, c2 = Config(), Config()\nprint(f'Same object: {c1 is c2}')  # True"),
            ],
                _project("py_proj3", "Async Web Scraper", "Build a concurrent web scraper using asyncio and aiohttp",
                    "advanced", 10, ["Async HTTP requests with aiohttp", "Rate limiting with semaphores", "Parse HTML with BeautifulSoup", "Save results to JSON", "Progress bar with tqdm"],
                    tags=["python", "async", "web-scraping"]),
            ),
            _module("py_data_science", "Data Science & ML", "NumPy, Pandas, Matplotlib, scikit-learn", 40, [
                _lesson("py_ds1", "NumPy Essentials", "Arrays, broadcasting, vectorization, linear algebra", 90, "intermediate", ["numpy", "arrays"],
                    "# NumPy\n\n```python\nimport numpy as np\n\n# Array Creation\na = np.array([1, 2, 3, 4, 5])\nb = np.zeros((3, 4))\nc = np.random.randn(1000)\nd = np.linspace(0, 2*np.pi, 100)\n\n# Broadcasting\nmatrix = np.arange(12).reshape(3, 4)\nprint(matrix + 10)      # Add 10 to every element\nprint(matrix * [1,2,3,4]) # Multiply each column\n\n# Vectorized Operations\nx = np.linspace(0, 10, 1000)\ny = np.sin(x) * np.exp(-x/5)  # No loops needed!\n\n# Linear Algebra\nA = np.array([[1,2],[3,4]])\nprint(np.linalg.det(A))      # Determinant\nprint(np.linalg.inv(A))      # Inverse\neigenvalues, eigenvectors = np.linalg.eig(A)\n```",
                    "import numpy as np\na = np.random.randn(1000)\nprint(f'Mean: {a.mean():.4f}')\nprint(f'Std:  {a.std():.4f}')\nprint(f'Min:  {a.min():.4f}')\nprint(f'Max:  {a.max():.4f}')"),
                _lesson("py_ds2", "Pandas Data Analysis", "DataFrames, groupby, merge, pivot tables", 90, "intermediate", ["pandas", "dataframes"],
                    "# Pandas\n\n```python\nimport pandas as pd\n\n# Create DataFrame\ndf = pd.DataFrame({\n    'name': ['Alice', 'Bob', 'Charlie', 'Diana'],\n    'age': [25, 30, 35, 28],\n    'salary': [50000, 60000, 75000, 55000],\n    'dept': ['Engineering', 'Marketing', 'Engineering', 'Marketing']\n})\n\n# Filtering\neng = df[df['dept'] == 'Engineering']\nhigh_salary = df[df['salary'] > 55000]\n\n# GroupBy\nby_dept = df.groupby('dept').agg({\n    'salary': ['mean', 'max'],\n    'age': 'mean'\n})\n\n# Apply custom functions\ndf['tax'] = df['salary'].apply(lambda s: s * 0.3)\n\n# Pivot Tables\npivot = df.pivot_table(values='salary', index='dept', aggfunc=['mean', 'count'])\n```",
                    "import pandas as pd\ndata = {'product': ['A','B','A','B','A','B'], 'month': [1,1,2,2,3,3], 'sales': [100,150,120,180,90,200]}\ndf = pd.DataFrame(data)\nprint(df.groupby('product')['sales'].agg(['sum','mean','max']))"),
            ],
                _project("py_proj4", "Data Dashboard", "Build a data analysis pipeline with visualization",
                    "intermediate", 12, ["Load CSV data with Pandas", "Clean and transform data", "Statistical analysis", "Generate matplotlib/seaborn charts", "Export report as HTML"],
                    tags=["python", "data-science", "pandas"]),
            ),
            _module("py_web", "Web Development", "Flask, FastAPI, REST APIs, databases", 35, [
                _lesson("py_w1", "FastAPI Fundamentals", "Routing, models, async endpoints, validation", 90, "intermediate", ["fastapi", "rest-api"],
                    "# FastAPI\n\n```python\nfrom fastapi import FastAPI, HTTPException\nfrom pydantic import BaseModel\nfrom typing import Optional\n\napp = FastAPI()\n\nclass Item(BaseModel):\n    name: str\n    price: float\n    description: Optional[str] = None\n\nitems_db = {}\n\n@app.get('/items')\nasync def list_items():\n    return list(items_db.values())\n\n@app.post('/items')\nasync def create_item(item: Item):\n    item_id = len(items_db) + 1\n    items_db[item_id] = item.dict()\n    return {'id': item_id, **item.dict()}\n\n@app.get('/items/{item_id}')\nasync def get_item(item_id: int):\n    if item_id not in items_db:\n        raise HTTPException(404, 'Item not found')\n    return items_db[item_id]\n\n@app.put('/items/{item_id}')\nasync def update_item(item_id: int, item: Item):\n    if item_id not in items_db:\n        raise HTTPException(404, 'Item not found')\n    items_db[item_id] = item.dict()\n    return items_db[item_id]\n\n@app.delete('/items/{item_id}')\nasync def delete_item(item_id: int):\n    if item_id not in items_db:\n        raise HTTPException(404, 'Item not found')\n    del items_db[item_id]\n    return {'deleted': True}\n```",
                    "from fastapi import FastAPI\napp = FastAPI()\n\n@app.get('/hello/{name}')\nasync def hello(name: str):\n    return {'message': f'Hello, {name}!'}"),
                _lesson("py_w2", "Database Integration", "SQLAlchemy, MongoDB with Motor, migrations", 75, "intermediate", ["database", "sqlalchemy", "mongodb"],
                    "# Database Integration\n\n## SQLAlchemy ORM\n```python\nfrom sqlalchemy import create_engine, Column, Integer, String\nfrom sqlalchemy.orm import declarative_base, Session\n\nBase = declarative_base()\n\nclass User(Base):\n    __tablename__ = 'users'\n    id = Column(Integer, primary_key=True)\n    name = Column(String(50))\n    email = Column(String(100), unique=True)\n\nengine = create_engine('sqlite:///app.db')\nBase.metadata.create_all(engine)\n\nwith Session(engine) as session:\n    user = User(name='Alice', email='alice@example.com')\n    session.add(user)\n    session.commit()\n    \n    users = session.query(User).all()\n```\n\n## MongoDB with Motor (async)\n```python\nimport motor.motor_asyncio\n\nclient = motor.motor_asyncio.AsyncIOMotorClient('mongodb://localhost:27017')\ndb = client.myapp\n\nasync def create_user(name, email):\n    result = await db.users.insert_one({'name': name, 'email': email})\n    return str(result.inserted_id)\n\nasync def find_users():\n    cursor = db.users.find({})\n    return await cursor.to_list(length=100)\n```",
                    "# MongoDB example\nfrom pymongo import MongoClient\nclient = MongoClient('mongodb://localhost:27017')\ndb = client.test_db\ndb.users.insert_one({'name': 'Alice', 'age': 30})\nfor user in db.users.find():\n    print(user)"),
            ],
                _project("py_proj5", "REST API with Auth", "Build a full REST API with JWT authentication",
                    "intermediate", 15, ["FastAPI with Pydantic models", "JWT authentication", "MongoDB storage", "CRUD for resources", "Rate limiting", "API documentation"],
                    tags=["python", "fastapi", "jwt", "mongodb"]),
            ),
            _module("py_testing", "Testing & Quality", "pytest, unittest, mocking, TDD, CI", 20, [
                _lesson("py_t1", "pytest Fundamentals", "Test functions, fixtures, parametrize, markers", 60, "intermediate", ["testing", "pytest"],
                    "# pytest\n\n```python\n# test_calculator.py\nimport pytest\n\ndef add(a, b):\n    return a + b\n\ndef divide(a, b):\n    if b == 0: raise ValueError('Division by zero')\n    return a / b\n\n# Basic tests\ndef test_add():\n    assert add(2, 3) == 5\n    assert add(-1, 1) == 0\n\ndef test_divide():\n    assert divide(10, 2) == 5.0\n\ndef test_divide_by_zero():\n    with pytest.raises(ValueError):\n        divide(10, 0)\n\n# Parametrized tests\n@pytest.mark.parametrize('a,b,expected', [\n    (2, 3, 5), (0, 0, 0), (-1, -1, -2), (100, 200, 300)\n])\ndef test_add_parametrized(a, b, expected):\n    assert add(a, b) == expected\n\n# Fixtures\n@pytest.fixture\ndef sample_data():\n    return [1, 2, 3, 4, 5]\n\ndef test_sum(sample_data):\n    assert sum(sample_data) == 15\n```\n\nRun: `pytest -v test_calculator.py`",
                    "# Simple test\ndef add(a, b): return a + b\n\nassert add(2,3) == 5\nassert add(-1,1) == 0\nassert add(0,0) == 0\nprint('All tests passed!')"),
            ],
                _project("py_proj6", "TDD Project", "Build a library using test-driven development",
                    "advanced", 8, ["Write tests first", "100% code coverage", "Mocking external services", "CI pipeline with GitHub Actions"],
                    tags=["python", "tdd", "pytest"]),
            ),
            _module("py_automation", "Automation & Scripting", "File handling, web scraping, system automation", 20, [
                _lesson("py_auto1", "File & Directory Operations", "os, pathlib, shutil, glob, watchdog", 60, "beginner", ["files", "automation"],
                    "# File Operations\n\n```python\nfrom pathlib import Path\nimport shutil, json\n\n# pathlib — Modern File Handling\np = Path('data/output')\np.mkdir(parents=True, exist_ok=True)\n\n# Write file\n(p / 'results.json').write_text(json.dumps({'score': 95}))\n\n# Read file\ndata = json.loads((p / 'results.json').read_text())\n\n# Glob — Find files\nfor py_file in Path('.').rglob('*.py'):\n    print(f'{py_file}: {py_file.stat().st_size} bytes')\n\n# Copy, Move, Delete\nshutil.copy('source.txt', 'backup.txt')\nshutil.move('old/', 'new/')\nshutil.rmtree('temp/')  # Delete directory tree\n\n# CSV Processing\nimport csv\nwith open('data.csv', 'w', newline='') as f:\n    writer = csv.DictWriter(f, fieldnames=['name', 'score'])\n    writer.writeheader()\n    writer.writerows([{'name': 'Alice', 'score': 95}])\n```",
                    "from pathlib import Path\n\n# Count files by extension\nfor ext in ['.py', '.js', '.ts', '.json']:\n    count = len(list(Path('.').rglob(f'*{ext}')))\n    if count: print(f'{ext}: {count} files')"),
            ]),
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════
# JAVASCRIPT TRACK — 250hrs
# ═══════════════════════════════════════════════════════════════════════════
def _javascript_track():
    return {
        "id": "javascript", "name": "JavaScript Mastery", "icon": "logo-javascript",
        "color": "#F7DF1E", "total_hours": 2700, "category": "language",
        "description": "Complete JavaScript from ES6+ to Node.js, React, and full-stack development.",
        "prerequisites": [], "certificate": "JavaScript Full-Stack Developer",
        "modules": [
            _module("js_fundamentals", "JS Fundamentals", "Variables, types, functions, DOM", 25, [
                _lesson("js_f1", "Variables & Modern JS", "let, const, template literals, destructuring", 60, "beginner", ["es6", "variables"],
                    "# Modern JavaScript\n\n## let vs const vs var\n```javascript\nlet count = 0;       // Block-scoped, reassignable\nconst PI = 3.14159;  // Block-scoped, not reassignable\nvar old = 'avoid';   // Function-scoped (legacy)\n\n// const with objects — properties CAN change\nconst user = { name: 'Alice' };\nuser.name = 'Bob';  // OK!\n// user = {};        // Error!\n```\n\n## Template Literals\n```javascript\nconst name = 'World';\nconst greeting = `Hello, ${name}!`;\nconst multiline = `\n  This is a\n  multiline string\n`;\n```\n\n## Destructuring\n```javascript\n// Array\nconst [a, b, ...rest] = [1, 2, 3, 4, 5];\n// a=1, b=2, rest=[3,4,5]\n\n// Object\nconst { name: userName, age = 25 } = { name: 'Alice', age: 30 };\n\n// Function params\nfunction greet({ name, role = 'user' }) {\n  return `${name} (${role})`;\n}\n```\n\n## Spread Operator\n```javascript\nconst arr1 = [1, 2, 3];\nconst arr2 = [...arr1, 4, 5]; // [1,2,3,4,5]\nconst obj1 = { a: 1, b: 2 };\nconst obj2 = { ...obj1, c: 3 }; // {a:1, b:2, c:3}\n```",
                    "const nums = [3, 1, 4, 1, 5, 9, 2, 6];\nconst [first, second, ...rest] = nums;\nconsole.log(`First: ${first}, Second: ${second}`);\nconsole.log(`Rest: ${rest}`);\nconsole.log(`Sum: ${nums.reduce((a,b) => a+b, 0)}`);",
                    _exercise("js_ex1", "Array Flatten", "Flatten a nested array",
                        "function flatten(arr) {\n  // Flatten nested arrays: [1,[2,[3]]] -> [1,2,3]\n}\n\nconsole.log(flatten([1, [2, [3, [4]], 5]]));",
                        "function flatten(arr) {\n  return arr.reduce((acc, val) =>\n    Array.isArray(val) ? acc.concat(flatten(val)) : acc.concat(val)\n  , []);\n}\nconsole.log(flatten([1, [2, [3, [4]], 5]]));",
                        [{"input": "", "expected": "[1,2,3,4,5]"}])),
                _lesson("js_f2", "Functions & Closures", "Arrow functions, closures, IIFE, higher-order functions", 75, "beginner", ["functions", "closures"],
                    "# Functions & Closures\n\n## Arrow Functions\n```javascript\nconst add = (a, b) => a + b;\nconst square = x => x * x;\nconst greet = () => 'Hello!';\n\n// Implicit return with objects\nconst makeUser = (name, age) => ({ name, age });\n```\n\n## Closures\n```javascript\nfunction counter() {\n  let count = 0;\n  return {\n    increment: () => ++count,\n    decrement: () => --count,\n    getCount: () => count,\n  };\n}\n\nconst c = counter();\nc.increment(); // 1\nc.increment(); // 2\nc.decrement(); // 1\n```\n\n## Higher-Order Functions\n```javascript\nconst nums = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];\n\nconst evens = nums.filter(n => n % 2 === 0);\nconst doubled = nums.map(n => n * 2);\nconst sum = nums.reduce((acc, n) => acc + n, 0);\nconst first = nums.find(n => n > 5);\nconst allPositive = nums.every(n => n > 0);\n```",
                    "// Closure: private counter\nfunction makeCounter(initial = 0) {\n  let count = initial;\n  return {\n    inc: () => ++count,\n    dec: () => --count,\n    val: () => count,\n  };\n}\nconst c = makeCounter(10);\nconsole.log(c.inc(), c.inc(), c.dec(), c.val());"),
                _lesson("js_f3", "Async JavaScript", "Promises, async/await, fetch, error handling", 90, "intermediate", ["async", "promises"],
                    "# Async JavaScript\n\n## Promises\n```javascript\nfunction fetchUser(id) {\n  return new Promise((resolve, reject) => {\n    setTimeout(() => {\n      if (id > 0) resolve({ id, name: 'Alice' });\n      else reject(new Error('Invalid ID'));\n    }, 1000);\n  });\n}\n\nfetchUser(1)\n  .then(user => console.log(user))\n  .catch(err => console.error(err));\n```\n\n## Async/Await\n```javascript\nasync function getUser(id) {\n  try {\n    const response = await fetch(`/api/users/${id}`);\n    if (!response.ok) throw new Error('Not found');\n    const user = await response.json();\n    return user;\n  } catch (error) {\n    console.error('Failed:', error.message);\n    return null;\n  }\n}\n```\n\n## Promise.all & Promise.race\n```javascript\nconst [users, posts, comments] = await Promise.all([\n  fetch('/api/users').then(r => r.json()),\n  fetch('/api/posts').then(r => r.json()),\n  fetch('/api/comments').then(r => r.json()),\n]);\n\n// First to resolve wins\nconst fastest = await Promise.race([\n  fetch('server1.com/data'),\n  fetch('server2.com/data'),\n]);\n```",
                    "async function delay(ms) {\n  return new Promise(r => setTimeout(r, ms));\n}\n\nasync function main() {\n  console.log('Start');\n  await delay(100);\n  console.log('After 100ms');\n  const results = await Promise.all([delay(50), delay(100), delay(75)]);\n  console.log('All done!');\n}\nmain();"),
            ],
                _project("js_proj1", "Task Manager App", "Build a full task manager with local storage",
                    "beginner", 6, ["CRUD operations", "Local storage persistence", "Filter & sort", "Keyboard shortcuts"],
                    tags=["javascript", "dom", "storage"]),
                _assessment("js_assess1", "JS Fundamentals Assessment", [
                    _question("jq1", "What does `const` prevent?", ["Changing properties", "Reassignment of variable", "Both", "Neither"], "Reassignment of variable", 10),
                    _question("jq2", "What does `[...arr]` do?", ["Reference copy", "Shallow copy", "Deep copy", "Error"], "Shallow copy", 10),
                    _question("jq3", "Arrow functions...", ["Have their own 'this'", "Inherit 'this' from parent", "Don't have 'this'", "Create new scope"], "Inherit 'this' from parent", 10),
                ], 70),
            ),
            _module("js_node", "Node.js & Backend", "Express, middleware, REST APIs, databases", 35, [
                _lesson("js_n1", "Node.js & Express", "Server setup, routing, middleware, error handling", 90, "intermediate", ["nodejs", "express"],
                    "# Node.js & Express\n\n```javascript\nconst express = require('express');\nconst app = express();\n\n// Middleware\napp.use(express.json());\napp.use((req, res, next) => {\n  console.log(`${req.method} ${req.path}`);\n  next();\n});\n\n// Routes\nlet todos = [];\n\napp.get('/api/todos', (req, res) => {\n  res.json(todos);\n});\n\napp.post('/api/todos', (req, res) => {\n  const todo = { id: Date.now(), ...req.body, done: false };\n  todos.push(todo);\n  res.status(201).json(todo);\n});\n\napp.put('/api/todos/:id', (req, res) => {\n  const todo = todos.find(t => t.id === parseInt(req.params.id));\n  if (!todo) return res.status(404).json({ error: 'Not found' });\n  Object.assign(todo, req.body);\n  res.json(todo);\n});\n\napp.delete('/api/todos/:id', (req, res) => {\n  todos = todos.filter(t => t.id !== parseInt(req.params.id));\n  res.json({ deleted: true });\n});\n\n// Error handler\napp.use((err, req, res, next) => {\n  console.error(err.stack);\n  res.status(500).json({ error: 'Something broke!' });\n});\n\napp.listen(3000, () => console.log('Server on :3000'));\n```",
                    "const http = require('http');\nconst server = http.createServer((req, res) => {\n  res.writeHead(200, {'Content-Type': 'application/json'});\n  res.end(JSON.stringify({message: 'Hello Node.js!', time: new Date()}));\n});\nserver.listen(3000);\nconsole.log('Server running on port 3000');"),
            ],
                _project("js_proj2", "REST API Server", "Build a production-ready REST API with Express",
                    "intermediate", 12, ["Express with TypeScript", "MongoDB with Mongoose", "JWT authentication", "Input validation", "Rate limiting", "API documentation with Swagger"],
                    tags=["nodejs", "express", "mongodb"]),
            ),
            _module("js_react", "React & Frontend", "Components, hooks, state management, routing", 40, [
                _lesson("js_r1", "React Fundamentals", "JSX, components, props, state, hooks", 90, "intermediate", ["react", "hooks"],
                    "# React Fundamentals\n\n```jsx\nimport React, { useState, useEffect } from 'react';\n\nfunction Counter() {\n  const [count, setCount] = useState(0);\n\n  useEffect(() => {\n    document.title = `Count: ${count}`;\n  }, [count]);\n\n  return (\n    <div>\n      <h1>{count}</h1>\n      <button onClick={() => setCount(c => c + 1)}>+</button>\n      <button onClick={() => setCount(c => c - 1)}>-</button>\n      <button onClick={() => setCount(0)}>Reset</button>\n    </div>\n  );\n}\n\n// Custom Hook\nfunction useLocalStorage(key, initial) {\n  const [value, setValue] = useState(() => {\n    const stored = localStorage.getItem(key);\n    return stored ? JSON.parse(stored) : initial;\n  });\n\n  useEffect(() => {\n    localStorage.setItem(key, JSON.stringify(value));\n  }, [key, value]);\n\n  return [value, setValue];\n}\n```",
                    "// Simple component\nfunction Greeting({ name }) {\n  return <h1>Hello, {name}!</h1>;\n}\n\nfunction App() {\n  const [name, setName] = useState('World');\n  return (\n    <div>\n      <Greeting name={name} />\n      <input value={name} onChange={e => setName(e.target.value)} />\n    </div>\n  );\n}"),
            ],
                _project("js_proj3", "Social Media Dashboard", "Build a React dashboard with data visualization",
                    "intermediate", 15, ["React with hooks", "Chart.js or Recharts", "REST API integration", "Responsive design", "Dark mode"],
                    tags=["react", "dashboard", "charts"]),
            ),
        ],
    }


# ═══════════════════════════════════════════════════════════════════════════
# ALL TRACK GENERATORS (compact definitions for remaining tracks)
# ═══════════════════════════════════════════════════════════════════════════

def _make_lang_track(tid, name, icon, color, hours, desc, cert, modules_data):
    """Generate a language track from compact module definitions."""
    modules = []
    for m in modules_data:
        lessons = []
        for i, l in enumerate(m["lessons"]):
            lessons.append(_lesson(
                f"{tid}_{m['id']}_{i+1}", l["title"], l["desc"],
                l.get("mins", 60), l.get("diff", "intermediate"),
                l.get("topics", []), l["content"],
                l.get("code", ""), l.get("exercise")
            ))
        modules.append(_module(
            f"{tid}_{m['id']}", m["name"], m["desc"], m.get("hours", 20),
            lessons, m.get("project"), m.get("assessment")
        ))
    return {
        "id": tid, "name": name, "icon": icon, "color": color,
        "total_hours": hours, "category": "language",
        "description": desc, "prerequisites": [],
        "certificate": cert, "modules": modules,
    }


def _typescript_track():
    return _make_lang_track("typescript", "TypeScript Mastery", "code-slash", "#3178C6", 180,
        "Complete TypeScript from basics to advanced generics, decorators, and full-stack typing.",
        "TypeScript Professional", [
        {"id": "ts_basics", "name": "TypeScript Basics", "desc": "Types, interfaces, enums, type guards", "hours": 25, "lessons": [
            {"title": "Type System Fundamentals", "desc": "Primitive types, type inference, annotations", "content": "# TypeScript Type System\n\n```typescript\n// Basic Types\nlet name: string = 'Alice';\nlet age: number = 30;\nlet active: boolean = true;\nlet items: string[] = ['a', 'b', 'c'];\nlet tuple: [string, number] = ['hello', 42];\n\n// Type Inference\nlet inferred = 42; // TypeScript infers 'number'\n\n// Union Types\nlet id: string | number = 'abc';\nid = 123; // OK\n\n// Literal Types\ntype Direction = 'north' | 'south' | 'east' | 'west';\nlet dir: Direction = 'north';\n\n// Enums\nenum Color { Red, Green, Blue }\nlet c: Color = Color.Green;\n```", "code": "type Status = 'active' | 'inactive' | 'pending';\ninterface User { name: string; status: Status; age?: number; }\nconst user: User = { name: 'Alice', status: 'active' };\nconsole.log(user);", "topics": ["types", "inference"]},
            {"title": "Interfaces & Types", "desc": "Interface declaration, extension, intersection types", "content": "# Interfaces\n\n```typescript\ninterface Animal {\n  name: string;\n  sound(): string;\n}\n\ninterface Pet extends Animal {\n  owner: string;\n}\n\nclass Dog implements Pet {\n  constructor(public name: string, public owner: string) {}\n  sound() { return 'Woof!'; }\n}\n\n// Intersection Types\ntype Timestamped = { createdAt: Date; updatedAt: Date };\ntype UserRecord = User & Timestamped;\n\n// Generics with Interfaces\ninterface Repository<T> {\n  find(id: string): T | null;\n  save(item: T): void;\n  delete(id: string): boolean;\n}\n```", "topics": ["interfaces", "generics"]},
            {"title": "Generics Deep Dive", "desc": "Generic functions, constraints, conditional types", "content": "# Generics\n\n```typescript\n// Generic Function\nfunction firstElement<T>(arr: T[]): T | undefined {\n  return arr[0];\n}\n\n// Constrained Generics\nfunction longest<T extends { length: number }>(a: T, b: T): T {\n  return a.length >= b.length ? a : b;\n}\n\n// Conditional Types\ntype IsString<T> = T extends string ? true : false;\ntype A = IsString<'hello'>; // true\ntype B = IsString<42>;      // false\n\n// Mapped Types\ntype Readonly<T> = { readonly [K in keyof T]: T[K] };\ntype Partial<T> = { [K in keyof T]?: T[K] };\ntype Required<T> = { [K in keyof T]-?: T[K] };\n\n// Utility Types\ntype Pick<T, K extends keyof T> = { [P in K]: T[P] };\ntype Omit<T, K extends keyof T> = Pick<T, Exclude<keyof T, K>>;\n```", "diff": "advanced", "topics": ["generics", "conditional-types"]},
        ],
            "project": _project("ts_proj1", "Type-Safe API Client", "Build a fully typed REST API client",
                "intermediate", 8, ["Generic request/response types", "Interceptors", "Error handling", "Auto-generated types from OpenAPI spec"],
                tags=["typescript", "api", "generics"]),
        },
        {"id": "ts_advanced", "name": "Advanced TypeScript", "desc": "Decorators, module system, declaration files", "hours": 30, "lessons": [
            {"title": "Decorators", "desc": "Class, method, property, parameter decorators", "content": "# Decorators\n\n```typescript\nfunction log(target: any, key: string, desc: PropertyDescriptor) {\n  const original = desc.value;\n  desc.value = function(...args: any[]) {\n    console.log(`Calling ${key} with`, args);\n    return original.apply(this, args);\n  };\n}\n\nclass Calculator {\n  @log\n  add(a: number, b: number) { return a + b; }\n}\n```", "topics": ["decorators"]},
            {"title": "Type-Level Programming", "desc": "Template literal types, recursive types, type gymnastics", "content": "# Type-Level Programming\n\n```typescript\n// Template Literal Types\ntype EventName = `on${Capitalize<string>}`;\n\n// Recursive Types\ntype DeepPartial<T> = {\n  [K in keyof T]?: T[K] extends object ? DeepPartial<T[K]> : T[K];\n};\n\n// Infer keyword\ntype ReturnType<T> = T extends (...args: any[]) => infer R ? R : never;\ntype Flatten<T> = T extends Array<infer U> ? U : T;\n```", "diff": "expert", "topics": ["type-programming"]},
        ]},
    ])


def _rust_track():
    return _make_lang_track("rust", "Rust Systems Programming", "construct", "#CE422B", 180,
        "Master Rust ownership, borrowing, lifetimes, async, and systems programming.",
        "Rust Systems Developer", [
        {"id": "rs_ownership", "name": "Ownership & Borrowing", "desc": "The core of Rust's memory safety", "hours": 30, "lessons": [
            {"title": "Ownership Rules", "desc": "Move semantics, Copy trait, ownership transfer", "content": "# Rust Ownership\n\n```rust\nfn main() {\n    // Rule 1: Each value has exactly one owner\n    let s1 = String::from(\"hello\");\n    let s2 = s1; // s1 is MOVED to s2, s1 is invalid\n    // println!(\"{}\", s1); // ERROR: value moved\n    println!(\"{}\", s2); // OK\n\n    // Rule 2: Copy types (stack-only) are copied\n    let x = 42;\n    let y = x; // Copy, both valid\n    println!(\"{} {}\", x, y);\n\n    // Rule 3: Value is dropped when owner goes out of scope\n    {\n        let s = String::from(\"temporary\");\n    } // s is dropped here\n}\n```", "topics": ["ownership", "move"]},
            {"title": "Borrowing & References", "desc": "Immutable and mutable references, borrowing rules", "content": "# Borrowing\n\n```rust\nfn calculate_length(s: &String) -> usize {\n    s.len() // Borrow, don't take ownership\n}\n\nfn change(s: &mut String) {\n    s.push_str(\", world\");\n}\n\nfn main() {\n    let mut s = String::from(\"hello\");\n    let len = calculate_length(&s); // Immutable borrow\n    change(&mut s); // Mutable borrow\n    \n    // Rules:\n    // - Any number of immutable references OR\n    // - Exactly ONE mutable reference\n    // - Never both at the same time\n}\n```", "topics": ["borrowing", "references"]},
            {"title": "Lifetimes", "desc": "Lifetime annotations, elision rules, static lifetime", "content": "# Lifetimes\n\n```rust\n// Lifetime annotation: returned ref lives as long as inputs\nfn longest<'a>(x: &'a str, y: &'a str) -> &'a str {\n    if x.len() > y.len() { x } else { y }\n}\n\n// Struct with lifetime\nstruct Excerpt<'a> {\n    part: &'a str,\n}\n\nimpl<'a> Excerpt<'a> {\n    fn level(&self) -> i32 { 3 }\n    fn announce(&self, msg: &str) -> &str {\n        println!(\"Attention: {}\", msg);\n        self.part\n    }\n}\n```", "diff": "advanced", "topics": ["lifetimes"]},
        ]},
        {"id": "rs_patterns", "name": "Enums, Pattern Matching & Traits", "desc": "Algebraic types and polymorphism", "hours": 25, "lessons": [
            {"title": "Enums & Pattern Matching", "desc": "Option, Result, match, if let", "content": "# Enums & Matching\n\n```rust\nenum Shape {\n    Circle(f64),\n    Rectangle(f64, f64),\n    Triangle(f64, f64, f64),\n}\n\nimpl Shape {\n    fn area(&self) -> f64 {\n        match self {\n            Shape::Circle(r) => std::f64::consts::PI * r * r,\n            Shape::Rectangle(w, h) => w * h,\n            Shape::Triangle(a, b, c) => {\n                let s = (a + b + c) / 2.0;\n                (s * (s-a) * (s-b) * (s-c)).sqrt()\n            }\n        }\n    }\n}\n\n// Option & Result\nfn divide(a: f64, b: f64) -> Result<f64, String> {\n    if b == 0.0 {\n        Err(\"Division by zero\".to_string())\n    } else {\n        Ok(a / b)\n    }\n}\n```", "topics": ["enums", "pattern-matching"]},
            {"title": "Traits & Generics", "desc": "Trait definitions, implementations, bounds, associated types", "content": "# Traits\n\n```rust\ntrait Summary {\n    fn summarize(&self) -> String;\n    fn preview(&self) -> String {\n        format!(\"Read more: {}...\", &self.summarize()[..20])\n    }\n}\n\nstruct Article { title: String, content: String }\nstruct Tweet { username: String, text: String }\n\nimpl Summary for Article {\n    fn summarize(&self) -> String {\n        format!(\"{}: {}\", self.title, &self.content[..50])\n    }\n}\n\nimpl Summary for Tweet {\n    fn summarize(&self) -> String {\n        format!(\"@{}: {}\", self.username, self.text)\n    }\n}\n\n// Generic with trait bound\nfn notify(item: &impl Summary) {\n    println!(\"Breaking: {}\", item.summarize());\n}\n```", "topics": ["traits", "generics"]},
        ]},
        {"id": "rs_async", "name": "Async Rust", "desc": "tokio, futures, channels, async patterns", "hours": 30, "lessons": [
            {"title": "Async/Await with Tokio", "desc": "Runtime, spawning tasks, async I/O", "content": "# Async Rust\n\n```rust\nuse tokio;\n\n#[tokio::main]\nasync fn main() {\n    let handle = tokio::spawn(async {\n        // Runs concurrently\n        tokio::time::sleep(std::time::Duration::from_secs(1)).await;\n        \"done\"\n    });\n\n    let result = handle.await.unwrap();\n    println!(\"Task result: {}\", result);\n}\n\n// Channels\nuse tokio::sync::mpsc;\n\nasync fn producer_consumer() {\n    let (tx, mut rx) = mpsc::channel(32);\n    \n    tokio::spawn(async move {\n        for i in 0..10 {\n            tx.send(i).await.unwrap();\n        }\n    });\n\n    while let Some(msg) = rx.recv().await {\n        println!(\"Got: {}\", msg);\n    }\n}\n```", "topics": ["async", "tokio"]},
        ]},
    ])


def _go_track():
    return _make_lang_track("go", "Go Programming", "rocket", "#00ADD8", 150,
        "Master Go for cloud-native development, concurrency, and microservices.",
        "Go Cloud Developer", [
        {"id": "go_basics", "name": "Go Fundamentals", "desc": "Syntax, types, functions, error handling", "hours": 25, "lessons": [
            {"title": "Go Basics", "desc": "Variables, functions, control flow", "content": "# Go Basics\n\n```go\npackage main\n\nimport \"fmt\"\n\nfunc main() {\n    // Variables\n    var name string = \"Go\"\n    age := 14 // Short declaration\n    \n    // Functions with multiple returns\n    sum, product := calc(3, 4)\n    fmt.Printf(\"%s is %d years old\\n\", name, age)\n    fmt.Printf(\"Sum: %d, Product: %d\\n\", sum, product)\n}\n\nfunc calc(a, b int) (int, int) {\n    return a + b, a * b\n}\n```", "topics": ["basics"]},
            {"title": "Structs & Interfaces", "desc": "Composition over inheritance", "content": "# Structs & Interfaces\n\n```go\ntype Shape interface {\n    Area() float64\n    Perimeter() float64\n}\n\ntype Circle struct { Radius float64 }\ntype Rectangle struct { Width, Height float64 }\n\nfunc (c Circle) Area() float64 {\n    return math.Pi * c.Radius * c.Radius\n}\nfunc (c Circle) Perimeter() float64 {\n    return 2 * math.Pi * c.Radius\n}\n\nfunc (r Rectangle) Area() float64 {\n    return r.Width * r.Height\n}\n\nfunc printShape(s Shape) {\n    fmt.Printf(\"Area: %.2f\\n\", s.Area())\n}\n```", "topics": ["structs", "interfaces"]},
        ]},
        {"id": "go_concurrency", "name": "Concurrency", "desc": "Goroutines, channels, select, sync", "hours": 30, "lessons": [
            {"title": "Goroutines & Channels", "desc": "Lightweight threads and communication", "content": "# Go Concurrency\n\n```go\nfunc main() {\n    ch := make(chan string, 10)\n    \n    // Launch goroutines\n    for i := 0; i < 5; i++ {\n        go func(id int) {\n            time.Sleep(time.Duration(rand.Intn(1000)) * time.Millisecond)\n            ch <- fmt.Sprintf(\"Worker %d done\", id)\n        }(i)\n    }\n    \n    // Collect results\n    for i := 0; i < 5; i++ {\n        fmt.Println(<-ch)\n    }\n}\n```\n\n## Select Statement\n```go\nselect {\ncase msg := <-ch1:\n    fmt.Println(\"From ch1:\", msg)\ncase msg := <-ch2:\n    fmt.Println(\"From ch2:\", msg)\ncase <-time.After(5 * time.Second):\n    fmt.Println(\"Timeout!\")\n}\n```", "topics": ["goroutines", "channels"]},
        ]},
    ])


def _cpp_track():
    return _make_lang_track("cpp", "C++ Mastery", "code", "#00599C", 300,
        "Master C++ for game engines, systems programming, and high-performance computing.",
        "C++ Systems Engineer", [
        {"id": "cpp_modern", "name": "Modern C++ (C++17/20)", "desc": "Smart pointers, move semantics, concepts", "hours": 40, "lessons": [
            {"title": "Smart Pointers & RAII", "desc": "unique_ptr, shared_ptr, weak_ptr, custom deleters", "content": "# Smart Pointers\n\n```cpp\n#include <memory>\n#include <iostream>\n\nclass Player {\npublic:\n    std::string name;\n    Player(std::string n) : name(n) { std::cout << name << \" created\\n\"; }\n    ~Player() { std::cout << name << \" destroyed\\n\"; }\n};\n\nint main() {\n    // unique_ptr — sole ownership\n    auto p1 = std::make_unique<Player>(\"Hero\");\n    // auto p2 = p1; // ERROR: can't copy\n    auto p2 = std::move(p1); // OK: transfer ownership\n    \n    // shared_ptr — shared ownership\n    auto p3 = std::make_shared<Player>(\"Ally\");\n    auto p4 = p3; // Both own it, ref count = 2\n    std::cout << \"Refs: \" << p3.use_count() << \"\\n\";\n    \n    // weak_ptr — non-owning observer\n    std::weak_ptr<Player> wp = p3;\n    if (auto sp = wp.lock()) {\n        std::cout << sp->name << \" still alive\\n\";\n    }\n}\n```", "topics": ["smart-pointers", "raii"]},
            {"title": "Move Semantics", "desc": "Rvalue references, std::move, perfect forwarding", "content": "# Move Semantics\n\n```cpp\nclass Buffer {\n    int* data;\n    size_t size;\npublic:\n    Buffer(size_t n) : data(new int[n]), size(n) {}\n    ~Buffer() { delete[] data; }\n    \n    // Copy constructor\n    Buffer(const Buffer& other) : data(new int[other.size]), size(other.size) {\n        std::copy(other.data, other.data + size, data);\n    }\n    \n    // Move constructor — steal resources\n    Buffer(Buffer&& other) noexcept : data(other.data), size(other.size) {\n        other.data = nullptr;\n        other.size = 0;\n    }\n    \n    // Move assignment\n    Buffer& operator=(Buffer&& other) noexcept {\n        if (this != &other) {\n            delete[] data;\n            data = other.data;\n            size = other.size;\n            other.data = nullptr;\n            other.size = 0;\n        }\n        return *this;\n    }\n};\n```", "diff": "advanced", "topics": ["move-semantics"]},
        ]},
        {"id": "cpp_templates", "name": "Templates & Metaprogramming", "desc": "Function/class templates, SFINAE, concepts", "hours": 35, "lessons": [
            {"title": "Template Fundamentals", "desc": "Function templates, class templates, specialization", "content": "# Templates\n\n```cpp\n// Function template\ntemplate<typename T>\nT max_val(T a, T b) {\n    return (a > b) ? a : b;\n}\n\n// Class template\ntemplate<typename T, size_t N>\nclass Array {\n    T data[N];\npublic:\n    T& operator[](size_t i) { return data[i]; }\n    constexpr size_t size() const { return N; }\n};\n\n// C++20 Concepts\ntemplate<typename T>\nconcept Numeric = std::integral<T> || std::floating_point<T>;\n\ntemplate<Numeric T>\nT sum(const std::vector<T>& v) {\n    return std::accumulate(v.begin(), v.end(), T{});\n}\n```", "topics": ["templates", "concepts"]},
        ]},
    ])


# ═══════════════════════════════════════════════════════════════════════════
# COMPACT TRACK DEFINITIONS (remaining languages)
# ═══════════════════════════════════════════════════════════════════════════

def _c_track():
    return _make_lang_track("c", "C Systems Programming", "terminal", "#A8B9CC", 200,
        "Master C for embedded systems, OS development, and low-level programming.", "C Systems Programmer", [
        {"id": "c_mem", "name": "Memory Management", "desc": "malloc, free, pointers, stack vs heap", "hours": 30, "lessons": [
            {"title": "Pointers & Memory", "desc": "Pointer arithmetic, arrays, dynamic allocation", "content": "# C Pointers\n\n```c\n#include <stdio.h>\n#include <stdlib.h>\n\nint main() {\n    // Stack allocation\n    int x = 42;\n    int *p = &x;\n    printf(\"Value: %d, Address: %p\\n\", *p, (void*)p);\n    \n    // Heap allocation\n    int *arr = (int*)malloc(10 * sizeof(int));\n    for (int i = 0; i < 10; i++) arr[i] = i * i;\n    \n    // Pointer arithmetic\n    for (int *ptr = arr; ptr < arr + 10; ptr++) {\n        printf(\"%d \", *ptr);\n    }\n    \n    free(arr);\n    return 0;\n}\n```", "topics": ["pointers", "memory"]},
        ]},
    ])

def _java_track():
    return _make_lang_track("java", "Java Enterprise", "cafe", "#ED8B00", 280,
        "Master Java for enterprise applications, Spring Boot, and JVM internals.", "Java Enterprise Developer", [
        {"id": "java_core", "name": "Core Java", "desc": "OOP, generics, collections, streams", "hours": 40, "lessons": [
            {"title": "Java OOP & Generics", "desc": "Classes, interfaces, generics, collections", "content": "# Java Core\n\n```java\nimport java.util.*;\nimport java.util.stream.*;\n\npublic class Main {\n    // Generic method\n    static <T extends Comparable<T>> T max(T a, T b) {\n        return a.compareTo(b) > 0 ? a : b;\n    }\n    \n    public static void main(String[] args) {\n        // Streams\n        List<String> names = List.of(\"Alice\", \"Bob\", \"Charlie\", \"Diana\");\n        \n        List<String> filtered = names.stream()\n            .filter(n -> n.length() > 3)\n            .map(String::toUpperCase)\n            .sorted()\n            .collect(Collectors.toList());\n        \n        System.out.println(filtered); // [ALICE, CHARLIE, DIANA]\n        \n        // Optional\n        Optional<String> first = names.stream()\n            .filter(n -> n.startsWith(\"Z\"))\n            .findFirst();\n        \n        String result = first.orElse(\"Not found\");\n    }\n}\n```", "topics": ["java", "generics", "streams"]},
        ]},
    ])

def _kotlin_track():
    return _make_lang_track("kotlin", "Kotlin Development", "phone-portrait", "#7F52FF", 150,
        "Master Kotlin for Android, server-side, and multiplatform development.", "Kotlin Developer", [
        {"id": "kt_core", "name": "Kotlin Fundamentals", "desc": "Null safety, extensions, coroutines", "hours": 25, "lessons": [
            {"title": "Kotlin Essentials", "desc": "Null safety, data classes, sealed classes, extensions", "content": "# Kotlin\n\n```kotlin\n// Data classes\ndata class User(val name: String, val age: Int)\n\n// Null safety\nfun greet(name: String?): String {\n    return \"Hello, ${name ?: \"World\"}!\"\n}\n\n// Extension functions\nfun String.isPalindrome(): Boolean {\n    val cleaned = this.lowercase().filter { it.isLetter() }\n    return cleaned == cleaned.reversed()\n}\n\n// Sealed classes\nsealed class Result {\n    data class Success(val data: String) : Result()\n    data class Error(val message: String) : Result()\n    object Loading : Result()\n}\n\nfun handle(result: Result) = when(result) {\n    is Result.Success -> println(result.data)\n    is Result.Error -> println(\"Error: ${result.message}\")\n    Result.Loading -> println(\"Loading...\")\n}\n```", "topics": ["kotlin", "null-safety"]},
        ]},
    ])

def _swift_track():
    return _make_lang_track("swift", "Swift & iOS", "logo-apple", "#F05138", 170,
        "Master Swift for iOS, macOS, and SwiftUI development.", "Swift iOS Developer", [
        {"id": "sw_core", "name": "Swift Fundamentals", "desc": "Optionals, protocols, closures, SwiftUI", "hours": 30, "lessons": [
            {"title": "Swift Essentials", "desc": "Optionals, enums, protocols, error handling", "content": "# Swift\n\n```swift\n// Optionals\nvar name: String? = \"Alice\"\nlet greeting = \"Hello, \\(name ?? \"World\")!\"\n\n// Enums with associated values\nenum NetworkResult {\n    case success(Data)\n    case failure(Error)\n}\n\n// Protocols\nprotocol Drawable {\n    func draw()\n    var area: Double { get }\n}\n\nstruct Circle: Drawable {\n    let radius: Double\n    var area: Double { .pi * radius * radius }\n    func draw() { print(\"Drawing circle r=\\(radius)\") }\n}\n\n// Closures\nlet numbers = [3, 1, 4, 1, 5, 9]\nlet sorted = numbers.sorted { $0 > $1 }\nlet evens = numbers.filter { $0 % 2 == 0 }\n```", "topics": ["swift", "optionals", "protocols"]},
        ]},
    ])

def _csharp_track():
    return _make_lang_track("csharp", "C# & .NET", "game-controller", "#239120", 250,
        "Master C# for Unity game dev, .NET backend, and enterprise applications.", "C# .NET Developer", [
        {"id": "cs_core", "name": "C# Fundamentals", "desc": "LINQ, async, generics, Unity basics", "hours": 35, "lessons": [
            {"title": "C# Modern Features", "desc": "LINQ, pattern matching, records, async streams", "content": "# C# Modern Features\n\n```csharp\nusing System;\nusing System.Linq;\nusing System.Collections.Generic;\n\n// Records (immutable data)\nrecord Player(string Name, int Health, int Level);\n\n// Pattern Matching\nstring Classify(object obj) => obj switch\n{\n    int n when n > 0 => \"Positive\",\n    int n when n < 0 => \"Negative\",\n    string s => $\"String: {s}\",\n    null => \"Null\",\n    _ => \"Unknown\"\n};\n\n// LINQ\nvar players = new List<Player>\n{\n    new(\"Alice\", 100, 25),\n    new(\"Bob\", 80, 30),\n    new(\"Charlie\", 95, 20)\n};\n\nvar highLevel = players\n    .Where(p => p.Level > 22)\n    .OrderByDescending(p => p.Health)\n    .Select(p => $\"{p.Name} (Lv.{p.Level})\");\n\n// Async Streams\nasync IAsyncEnumerable<int> GenerateAsync()\n{\n    for (int i = 0; i < 10; i++)\n    {\n        await Task.Delay(100);\n        yield return i;\n    }\n}\n```", "topics": ["csharp", "linq", "async"]},
        ]},
    ])

def _ruby_track():
    return _make_lang_track("ruby", "Ruby & Rails", "diamond", "#CC342D", 130,
        "Master Ruby metaprogramming and Rails full-stack development.", "Ruby Full-Stack Developer", [
        {"id": "rb_core", "name": "Ruby Fundamentals", "desc": "Blocks, procs, metaprogramming, Rails", "hours": 25, "lessons": [
            {"title": "Ruby Essentials", "desc": "Blocks, procs, lambdas, metaprogramming", "content": "# Ruby\n\n```ruby\n# Blocks & Iterators\n[1,2,3,4,5].each { |n| puts n * 2 }\n\nsquares = (1..10).map { |n| n ** 2 }\nevens = (1..20).select(&:even?)\n\n# Procs & Lambdas\nmultiply = ->(a, b) { a * b }\nputs multiply.call(3, 4)  # 12\n\n# Metaprogramming\nclass Dog\n  attr_accessor :name, :breed\n  \n  def initialize(name, breed)\n    @name = name\n    @breed = breed\n  end\n  \n  def self.create_method(name)\n    define_method(name) { puts \"#{@name} is #{name}ing!\" }\n  end\n  \n  create_method :bark\n  create_method :sit\n  create_method :fetch\nend\n\ndog = Dog.new('Rex', 'Lab')\ndog.bark   # Rex is barking!\ndog.fetch  # Rex is fetching!\n```", "topics": ["ruby", "metaprogramming"]},
        ]},
    ])

def _php_track():
    return _make_lang_track("php", "Modern PHP", "globe", "#777BB4", 120,
        "Master modern PHP 8+ with Laravel, typed properties, and attributes.", "PHP Laravel Developer", [
        {"id": "php_core", "name": "PHP 8+ Features", "desc": "Types, attributes, fibers, Laravel", "hours": 25, "lessons": [
            {"title": "PHP 8 Modern Features", "desc": "Named arguments, match, enums, fibers", "content": "# PHP 8+\n\n```php\n<?php\n// Enums (PHP 8.1)\nenum Status: string {\n    case Active = 'active';\n    case Inactive = 'inactive';\n    case Pending = 'pending';\n}\n\n// Named Arguments\nfunction createUser(string $name, int $age, string $role = 'user'): array {\n    return compact('name', 'age', 'role');\n}\n$user = createUser(name: 'Alice', age: 30);\n\n// Match Expression\n$result = match($status) {\n    Status::Active => 'User is active',\n    Status::Inactive => 'User is inactive',\n    default => 'Unknown status',\n};\n\n// Readonly Properties (PHP 8.1)\nclass User {\n    public function __construct(\n        public readonly string $name,\n        public readonly string $email,\n        public int $age = 0,\n    ) {}\n}\n```", "topics": ["php8", "enums"]},
        ]},
    ])

def _sql_track():
    return _make_lang_track("sql", "SQL Mastery", "file-tray-stacked", "#336791", 100,
        "Master SQL from basics to advanced queries, optimization, and administration.", "SQL Database Expert", [
        {"id": "sql_core", "name": "SQL Fundamentals", "desc": "SELECT, JOIN, subqueries, aggregation", "hours": 20, "lessons": [
            {"title": "Queries & Joins", "desc": "SELECT, WHERE, JOIN, GROUP BY, HAVING, subqueries", "content": "# SQL Queries\n\n```sql\n-- Basic SELECT with filtering\nSELECT name, email, created_at\nFROM users\nWHERE status = 'active'\n  AND created_at > '2024-01-01'\nORDER BY created_at DESC\nLIMIT 10;\n\n-- JOINs\nSELECT u.name, COUNT(o.id) as order_count, SUM(o.total) as total_spent\nFROM users u\nLEFT JOIN orders o ON u.id = o.user_id\nGROUP BY u.id, u.name\nHAVING SUM(o.total) > 100\nORDER BY total_spent DESC;\n\n-- Window Functions\nSELECT name, salary,\n  RANK() OVER (PARTITION BY department ORDER BY salary DESC) as dept_rank,\n  AVG(salary) OVER (PARTITION BY department) as dept_avg\nFROM employees;\n\n-- CTE (Common Table Expression)\nWITH monthly_sales AS (\n  SELECT DATE_TRUNC('month', created_at) as month,\n         SUM(total) as revenue\n  FROM orders\n  GROUP BY 1\n)\nSELECT month, revenue,\n  LAG(revenue) OVER (ORDER BY month) as prev_month,\n  revenue - LAG(revenue) OVER (ORDER BY month) as growth\nFROM monthly_sales;\n```", "topics": ["sql", "joins", "window-functions"]},
        ]},
    ])

def _bash_track():
    return _make_lang_track("bash", "Bash & Shell Scripting", "terminal", "#4EAA25", 70,
        "Master Bash scripting for automation, DevOps, and system administration.", "Shell Scripting Expert", [
        {"id": "bash_core", "name": "Shell Scripting", "desc": "Variables, functions, pipes, automation", "hours": 20, "lessons": [
            {"title": "Bash Essentials", "desc": "Variables, conditionals, loops, functions, pipes", "content": "# Bash Scripting\n\n```bash\n#!/bin/bash\n\n# Variables\nNAME=\"World\"\necho \"Hello, $NAME!\"\n\n# Functions\ngreet() {\n    local name=\"$1\"\n    echo \"Welcome, $name!\"\n}\ngreet \"Alice\"\n\n# Conditionals\nif [ -f \"config.json\" ]; then\n    echo \"Config found\"\nelse\n    echo \"Config missing\"\nfi\n\n# Loops\nfor file in *.py; do\n    echo \"Processing $file\"\n    wc -l \"$file\"\ndone\n\n# Pipes & Process Substitution\nfind . -name '*.log' -mtime +7 | xargs rm -f\nps aux | grep python | awk '{print $2, $11}'\ndu -sh */ | sort -rh | head -10\n\n# Error handling\nset -euo pipefail\ntrap 'echo \"Error on line $LINENO\"' ERR\n```", "topics": ["bash", "shell"]},
        ]},
    ])


# ═══════════════════════════════════════════════════════════════════════════
# REMAINING QUICK TRACKS
# ═══════════════════════════════════════════════════════════════════════════

def _remaining_lang_tracks():
    """Generate remaining language tracks with essential content."""
    tracks = []
    defs = [
        ("dart", "Dart & Flutter", "apps", "#0175C2", 140, "Master Dart for cross-platform Flutter development.", "Dart Flutter Developer",
         [{"id": "dt_core", "name": "Dart Fundamentals", "desc": "Null safety, async, Flutter widgets", "hours": 25, "lessons": [
             {"title": "Dart Essentials", "desc": "Null safety, async/await, collections, classes", "content": "# Dart\n\n```dart\n// Null Safety\nString? nullableName;\nString name = nullableName ?? 'Default';\n\n// Classes\nclass Player {\n  final String name;\n  int health;\n  Player(this.name, {this.health = 100});\n  void takeDamage(int amount) => health = (health - amount).clamp(0, 100);\n}\n\n// Async\nFuture<String> fetchData() async {\n  await Future.delayed(Duration(seconds: 1));\n  return 'Data loaded';\n}\n\n// Collections\nvar scores = [95, 87, 92, 78, 88];\nvar average = scores.reduce((a, b) => a + b) / scores.length;\nvar high = scores.where((s) => s > 85).toList();\n```", "topics": ["dart", "null-safety"]}]}]),
        ("scala", "Scala FP+OOP", "layers", "#DC322F", 160, "Master Scala for functional programming and big data with Spark.", "Scala Developer",
         [{"id": "sc_core", "name": "Scala Fundamentals", "desc": "Pattern matching, implicits, futures", "hours": 25, "lessons": [
             {"title": "Scala Essentials", "desc": "Case classes, pattern matching, for-comprehensions", "content": "# Scala\n\n```scala\n// Case Classes\ncase class Player(name: String, health: Int = 100)\nval hero = Player(\"Aragorn\")\nval damaged = hero.copy(health = 70)\n\n// Pattern Matching\ndef describe(x: Any): String = x match {\n  case i: Int if i > 0 => s\"Positive: $i\"\n  case s: String => s\"String: $s\"\n  case Player(name, hp) => s\"$name (HP: $hp)\"\n  case _ => \"Unknown\"\n}\n\n// For-Comprehension\nval pairs = for {\n  x <- 1 to 5\n  y <- 1 to 5\n  if x + y > 6\n} yield (x, y)\n```", "topics": ["scala", "pattern-matching"]}]}]),
        ("haskell", "Haskell Pure FP", "infinite", "#5D4F85", 200, "Master Haskell for pure functional programming, monads, and type theory.", "Haskell FP Expert",
         [{"id": "hs_core", "name": "Haskell Fundamentals", "desc": "Types, typeclasses, monads, IO", "hours": 30, "lessons": [
             {"title": "Haskell Essentials", "desc": "Pattern matching, higher-order functions, monads", "content": "# Haskell\n\n```haskell\n-- Pattern Matching\nfactorial :: Integer -> Integer\nfactorial 0 = 1\nfactorial n = n * factorial (n - 1)\n\n-- List comprehension\npythTriples = [(a,b,c) | c <- [1..], b <- [1..c], a <- [1..b], a^2 + b^2 == c^2]\n\n-- Higher-order functions\nmap (*2) [1..10]        -- [2,4,6,8,10,12,14,16,18,20]\nfilter even [1..20]     -- [2,4,6,8,10,12,14,16,18,20]\nfoldr (+) 0 [1..100]    -- 5050\n\n-- Maybe Monad\nsafeDivide :: Double -> Double -> Maybe Double\nsafeDivide _ 0 = Nothing\nsafeDivide a b = Just (a / b)\n\n-- IO Monad\nmain :: IO ()\nmain = do\n  putStrLn \"What's your name?\"\n  name <- getLine\n  putStrLn (\"Hello, \" ++ name ++ \"!\")\n```", "topics": ["haskell", "monads"]}]}]),
        ("elixir", "Elixir & Phoenix", "flask", "#6E4A7E", 130, "Master Elixir for fault-tolerant, distributed systems with Phoenix.", "Elixir Developer",
         [{"id": "ex_core", "name": "Elixir Fundamentals", "desc": "Pattern matching, processes, GenServer", "hours": 25, "lessons": [
             {"title": "Elixir Essentials", "desc": "Pipes, pattern matching, processes, OTP", "content": "# Elixir\n\n```elixir\n# Pipe Operator\nresult = \"hello world\"\n  |> String.split()\n  |> Enum.map(&String.capitalize/1)\n  |> Enum.join(\" \")\n# \"Hello World\"\n\n# Pattern Matching\ndefmodule Math do\n  def factorial(0), do: 1\n  def factorial(n) when n > 0, do: n * factorial(n - 1)\nend\n\n# GenServer\ndefmodule Counter do\n  use GenServer\n  def start_link(initial), do: GenServer.start_link(__MODULE__, initial)\n  def increment(pid), do: GenServer.call(pid, :increment)\n  def handle_call(:increment, _from, state), do: {:reply, state + 1, state + 1}\nend\n```", "topics": ["elixir", "otp"]}]}]),
        ("solidity", "Solidity & Web3", "link", "#363636", 120, "Master Solidity for smart contracts, DeFi, and blockchain development.", "Blockchain Developer",
         [{"id": "sol_core", "name": "Smart Contracts", "desc": "Solidity basics, ERC standards, security", "hours": 25, "lessons": [
             {"title": "Solidity Essentials", "desc": "Contracts, mappings, events, modifiers", "content": "# Solidity\n\n```solidity\n// SPDX-License-Identifier: MIT\npragma solidity ^0.8.19;\n\ncontract Token {\n    string public name;\n    mapping(address => uint256) public balances;\n    event Transfer(address indexed from, address indexed to, uint256 amount);\n    \n    constructor(string memory _name, uint256 initialSupply) {\n        name = _name;\n        balances[msg.sender] = initialSupply;\n    }\n    \n    modifier onlyPositive(uint256 amount) {\n        require(amount > 0, \"Amount must be positive\");\n        _;\n    }\n    \n    function transfer(address to, uint256 amount) external onlyPositive(amount) {\n        require(balances[msg.sender] >= amount, \"Insufficient balance\");\n        balances[msg.sender] -= amount;\n        balances[to] += amount;\n        emit Transfer(msg.sender, to, amount);\n    }\n}\n```", "topics": ["solidity", "smart-contracts"]}]}]),
        ("lua", "Lua Scripting", "game-controller", "#000080", 80, "Master Lua for game scripting, embedding, and rapid prototyping.", "Lua Game Scripter",
         [{"id": "lua_core", "name": "Lua Fundamentals", "desc": "Tables, metatables, coroutines", "hours": 20, "lessons": [
             {"title": "Lua Essentials", "desc": "Tables as everything, metatables, coroutines", "content": "# Lua\n\n```lua\n-- Tables (the only data structure)\nlocal player = {\n    name = \"Hero\",\n    health = 100,\n    inventory = {\"sword\", \"shield\", \"potion\"}\n}\n\n-- Methods\nfunction player:takeDamage(amount)\n    self.health = math.max(0, self.health - amount)\nend\n\n-- Metatables (OOP)\nlocal Enemy = {}\nEnemy.__index = Enemy\n\nfunction Enemy.new(name, hp)\n    return setmetatable({name=name, hp=hp}, Enemy)\nend\n\nfunction Enemy:attack()\n    print(self.name .. \" attacks!\")\nend\n\nlocal goblin = Enemy.new(\"Goblin\", 30)\ngoblin:attack()\n\n-- Coroutines\nlocal co = coroutine.create(function()\n    for i = 1, 5 do\n        print(\"Step \" .. i)\n        coroutine.yield()\n    end\nend)\n```", "topics": ["lua", "metatables"]}]}]),
        ("r", "R Data Science", "analytics", "#276DC3", 140, "Master R for statistical computing, data visualization, and machine learning.", "R Data Scientist",
         [{"id": "r_core", "name": "R Fundamentals", "desc": "Vectors, data frames, ggplot2, tidyverse", "hours": 25, "lessons": [
             {"title": "R Essentials", "desc": "Vectors, data frames, tidyverse, ggplot2", "content": "# R\n\n```r\n# Vectors\nnums <- c(1, 2, 3, 4, 5)\nmean(nums)  # 3\nsd(nums)    # 1.581139\n\n# Data Frames\ndf <- data.frame(\n  name = c(\"Alice\", \"Bob\", \"Charlie\"),\n  age = c(25, 30, 35),\n  score = c(95, 87, 92)\n)\n\n# Tidyverse\nlibrary(tidyverse)\ndf %>%\n  filter(age > 25) %>%\n  mutate(grade = ifelse(score > 90, \"A\", \"B\")) %>%\n  arrange(desc(score))\n\n# ggplot2\nggplot(df, aes(x=age, y=score, color=name)) +\n  geom_point(size=3) +\n  geom_smooth(method='lm') +\n  theme_minimal() +\n  labs(title='Score vs Age')\n```", "topics": ["r", "tidyverse", "ggplot2"]}]}]),
        ("assembly", "Assembly Language", "hardware-chip", "#6E4C13", 160, "Master x86 and ARM assembly for systems programming and reverse engineering.", "Assembly Programmer",
         [{"id": "asm_core", "name": "x86 Assembly", "desc": "Registers, instructions, memory, calling conventions", "hours": 30, "lessons": [
             {"title": "x86 Fundamentals", "desc": "Registers, MOV, arithmetic, stack, syscalls", "content": "# x86-64 Assembly\n\n```asm\n; Hello World (Linux x86-64)\nsection .data\n    msg db 'Hello, World!', 10  ; 10 = newline\n    len equ $ - msg\n\nsection .text\n    global _start\n\n_start:\n    ; write(1, msg, len)\n    mov rax, 1          ; syscall: write\n    mov rdi, 1          ; fd: stdout\n    mov rsi, msg        ; buffer\n    mov rdx, len        ; count\n    syscall\n    \n    ; exit(0)\n    mov rax, 60         ; syscall: exit\n    xor rdi, rdi        ; status: 0\n    syscall\n\n; Function: add two numbers\nadd_nums:\n    push rbp\n    mov rbp, rsp\n    mov rax, rdi        ; first arg\n    add rax, rsi        ; second arg\n    pop rbp\n    ret\n```", "topics": ["assembly", "x86"]}]}]),
    ]
    for tid, name, icon, color, hours, desc, cert, mods in defs:
        tracks.append(_make_lang_track(tid, name, icon, color, hours, desc, cert, mods))
    return tracks


# ═══════════════════════════════════════════════════════════════════════════
# SUBJECT ACADEMY TRACKS
# ═══════════════════════════════════════════════════════════════════════════

def _subject_academy_tracks():
    """Generate all subject academy tracks."""
    return [
        {"id": "math_academy", "name": "Mathematics Academy", "icon": "calculator", "color": "#E91E63", "total_hours": 4860, "category": "academy",
         "description": "Complete mathematics from algebra to multivariable calculus.", "certificate": "Mathematics Professional",
         "modules": [
             _module("algebra", "Algebra", "Equations, functions, polynomials", 40, [
                 _lesson("alg1", "Linear Equations", "Solving systems, graphing, word problems", 60, "beginner", ["algebra"],
                     "# Linear Equations\n\n## Slope-Intercept Form\n```\ny = mx + b\nm = slope, b = y-intercept\n```\n\n## Solving Systems\n```python\n# Substitution method\n# 2x + y = 10\n# x - y = 2\n# From eq 2: x = y + 2\n# Sub into eq 1: 2(y+2) + y = 10 → 3y = 6 → y = 2, x = 4\n\nimport numpy as np\nA = np.array([[2, 1], [1, -1]])\nb = np.array([10, 2])\nx = np.linalg.solve(A, b)\nprint(f'x = {x[0]}, y = {x[1]}')\n```"),
                 _lesson("alg2", "Polynomials & Factoring", "Quadratic formula, factoring techniques", 75, "beginner", ["polynomials"],
                     "# Polynomials\n\n## Quadratic Formula\n```\nax² + bx + c = 0\nx = (-b ± √(b²-4ac)) / 2a\n```\n\n## Factoring Patterns\n```\na² - b² = (a+b)(a-b)           # Difference of squares\na² + 2ab + b² = (a+b)²         # Perfect square\na³ + b³ = (a+b)(a²-ab+b²)      # Sum of cubes\n```\n\n```python\nimport numpy as np\n\n# Find roots of 2x² - 5x + 3 = 0\ncoeffs = [2, -5, 3]\nroots = np.roots(coeffs)\nprint(f'Roots: {roots}')  # [1.5, 1.0]\n```"),
             ]),
             _module("linear_algebra", "Linear Algebra", "Matrices, transformations, eigenvalues", 50, [
                 _lesson("la1", "Vectors & Matrices", "Operations, dot product, cross product", 90, "intermediate", ["vectors", "matrices"],
                     "# Linear Algebra\n\n## Vector Operations\n```python\nimport numpy as np\n\nv1 = np.array([1, 2, 3])\nv2 = np.array([4, 5, 6])\n\ndot = np.dot(v1, v2)           # 32\ncross = np.cross(v1, v2)       # [-3, 6, -3]\nmagnitude = np.linalg.norm(v1) # 3.742\nunit = v1 / magnitude          # normalized\n```\n\n## Matrix Operations\n```python\nA = np.array([[1, 2], [3, 4]])\nB = np.array([[5, 6], [7, 8]])\n\nC = A @ B                      # Matrix multiply\ndet = np.linalg.det(A)         # -2.0\ninv = np.linalg.inv(A)         # Inverse\nevals, evecs = np.linalg.eig(A)# Eigendecomposition\n\nprint(f'Determinant: {det}')\nprint(f'Eigenvalues: {evals}')\n```"),
                 _lesson("la2", "Transformations", "Rotation, scaling, projection, SVD", 75, "intermediate", ["transformations", "svd"],
                     "# Transformations\n\n## 2D Rotation Matrix\n```python\nimport numpy as np\n\ndef rotation_matrix(theta):\n    c, s = np.cos(theta), np.sin(theta)\n    return np.array([[c, -s], [s, c]])\n\n# Rotate point (1, 0) by 90 degrees\nR = rotation_matrix(np.pi/2)\npoint = np.array([1, 0])\nrotated = R @ point  # [0, 1]\n\n# SVD — Singular Value Decomposition\nA = np.random.randn(3, 2)\nU, S, Vt = np.linalg.svd(A, full_matrices=False)\nprint(f'Singular values: {S}')\n# Reconstruct: A ≈ U @ diag(S) @ Vt\n```"),
             ]),
             _module("calculus", "Calculus", "Limits, derivatives, integrals", 60, [
                 _lesson("calc1", "Limits & Derivatives", "Limit definition, differentiation rules, chain rule", 90, "intermediate", ["calculus", "derivatives"],
                     "# Calculus — Derivatives\n\n## Differentiation Rules\n```\nPower Rule:    d/dx[xⁿ] = nxⁿ⁻¹\nProduct Rule:  d/dx[fg] = f'g + fg'\nChain Rule:    d/dx[f(g(x))] = f'(g(x)) · g'(x)\nQuotient Rule: d/dx[f/g] = (f'g - fg') / g²\n```\n\n## Common Derivatives\n```\nd/dx[sin(x)] = cos(x)\nd/dx[cos(x)] = -sin(x)\nd/dx[eˣ] = eˣ\nd/dx[ln(x)] = 1/x\nd/dx[xⁿ] = nxⁿ⁻¹\n```\n\n## Numerical Differentiation\n```python\nimport numpy as np\n\ndef derivative(f, x, h=1e-8):\n    return (f(x + h) - f(x - h)) / (2 * h)\n\nf = lambda x: x**3 - 2*x + 1\nprint(derivative(f, 2))  # ≈ 10.0 (3x²-2 at x=2)\n```"),
                 _lesson("calc2", "Integration", "Antiderivatives, definite integrals, techniques", 90, "intermediate", ["integrals"],
                     "# Integration\n\n## Basic Integrals\n```\n∫xⁿ dx = xⁿ⁺¹/(n+1) + C\n∫sin(x) dx = -cos(x) + C\n∫cos(x) dx = sin(x) + C\n∫eˣ dx = eˣ + C\n∫1/x dx = ln|x| + C\n```\n\n## Numerical Integration\n```python\nimport numpy as np\nfrom scipy import integrate\n\n# Trapezoidal Rule\ndef trapezoidal(f, a, b, n=1000):\n    x = np.linspace(a, b, n)\n    y = f(x)\n    return np.trapz(y, x)\n\nf = lambda x: x**2\nresult = trapezoidal(f, 0, 3)  # ≈ 9.0\n\n# scipy quad (adaptive)\nresult, error = integrate.quad(lambda x: np.sin(x), 0, np.pi)\nprint(f'∫sin(x)dx from 0 to π = {result:.6f}')  # 2.0\n```"),
             ]),
         ]},
        {"id": "physics_academy", "name": "Physics Academy", "icon": "planet", "color": "#9C27B0", "total_hours": 2970, "category": "academy",
         "description": "Complete physics from classical mechanics to quantum computing.", "certificate": "Computational Physics",
         "modules": [
             _module("mechanics", "Classical Mechanics", "Newton's laws, energy, momentum, oscillations", 40, [
                 _lesson("phys1", "Newton's Laws & Kinematics", "Force, acceleration, projectile motion", 75, "beginner", ["mechanics", "kinematics"],
                     "# Classical Mechanics\n\n## Newton's Laws\n```\n1. An object at rest stays at rest (inertia)\n2. F = ma (force = mass × acceleration)\n3. Every action has an equal and opposite reaction\n```\n\n## Projectile Motion\n```python\nimport numpy as np\nimport matplotlib.pyplot as plt\n\ng = 9.81  # m/s²\nv0 = 50   # m/s\ntheta = 45  # degrees\n\ntheta_rad = np.radians(theta)\nt_flight = 2 * v0 * np.sin(theta_rad) / g\nt = np.linspace(0, t_flight, 100)\n\nx = v0 * np.cos(theta_rad) * t\ny = v0 * np.sin(theta_rad) * t - 0.5 * g * t**2\n\nrange_val = v0**2 * np.sin(2*theta_rad) / g\nmax_height = (v0 * np.sin(theta_rad))**2 / (2*g)\n\nprint(f'Range: {range_val:.1f}m')\nprint(f'Max Height: {max_height:.1f}m')\nprint(f'Flight Time: {t_flight:.2f}s')\n```"),
             ]),
         ]},
        {"id": "cs_academy", "name": "CS Academy", "icon": "code-slash", "color": "#2196F3", "total_hours": 3240, "category": "academy",
         "description": "Complete computer science from data structures to distributed systems.", "certificate": "Computer Science Professional",
         "modules": [
             _module("dsa", "Data Structures & Algorithms", "Arrays, trees, graphs, sorting, dynamic programming", 80, [
                 _lesson("dsa1", "Arrays & Hash Tables", "Operations, collision handling, applications", 75, "beginner", ["arrays", "hash-tables"],
                     "# Data Structures\n\n## Hash Table Implementation\n```python\nclass HashTable:\n    def __init__(self, size=1000):\n        self.size = size\n        self.table = [[] for _ in range(size)]\n    \n    def _hash(self, key):\n        return hash(key) % self.size\n    \n    def set(self, key, value):\n        idx = self._hash(key)\n        for i, (k, v) in enumerate(self.table[idx]):\n            if k == key:\n                self.table[idx][i] = (key, value)\n                return\n        self.table[idx].append((key, value))\n    \n    def get(self, key):\n        idx = self._hash(key)\n        for k, v in self.table[idx]:\n            if k == key:\n                return v\n        raise KeyError(key)\n    \n    def __contains__(self, key):\n        try:\n            self.get(key)\n            return True\n        except KeyError:\n            return False\n```\n\n## Time Complexities\n```\nArray:  Access O(1) | Search O(n) | Insert O(n) | Delete O(n)\nHash:   Access N/A  | Search O(1) | Insert O(1) | Delete O(1)\nTree:   Access O(log n) | Search O(log n) | Insert O(log n)\nHeap:   Find min O(1) | Insert O(log n) | Delete min O(log n)\n```"),
                 _lesson("dsa2", "Trees & Graphs", "BST, AVL, BFS, DFS, Dijkstra", 90, "intermediate", ["trees", "graphs"],
                     "# Trees & Graphs\n\n## Binary Search Tree\n```python\nclass Node:\n    def __init__(self, val):\n        self.val = val\n        self.left = None\n        self.right = None\n\nclass BST:\n    def __init__(self):\n        self.root = None\n    \n    def insert(self, val):\n        if not self.root:\n            self.root = Node(val)\n            return\n        self._insert(self.root, val)\n    \n    def _insert(self, node, val):\n        if val < node.val:\n            if node.left: self._insert(node.left, val)\n            else: node.left = Node(val)\n        else:\n            if node.right: self._insert(node.right, val)\n            else: node.right = Node(val)\n    \n    def inorder(self, node=None):\n        if node is None: node = self.root\n        if node:\n            yield from self.inorder(node.left)\n            yield node.val\n            yield from self.inorder(node.right)\n\ntree = BST()\nfor v in [5, 3, 7, 1, 4, 6, 8]:\n    tree.insert(v)\nprint(list(tree.inorder()))  # [1,3,4,5,6,7,8]\n```\n\n## Graph BFS/DFS\n```python\nfrom collections import deque\n\ndef bfs(graph, start):\n    visited = set()\n    queue = deque([start])\n    order = []\n    while queue:\n        node = queue.popleft()\n        if node not in visited:\n            visited.add(node)\n            order.append(node)\n            queue.extend(graph[node] - visited)\n    return order\n\ndef dfs(graph, start, visited=None):\n    if visited is None: visited = set()\n    visited.add(start)\n    print(start, end=' ')\n    for neighbor in graph[start] - visited:\n        dfs(graph, neighbor, visited)\n```"),
                 _lesson("dsa3", "Dynamic Programming", "Memoization, tabulation, classic problems", 90, "advanced", ["dynamic-programming"],
                     "# Dynamic Programming\n\n## Fibonacci (Top-Down vs Bottom-Up)\n```python\n# Top-Down (Memoization)\nfrom functools import lru_cache\n\n@lru_cache(maxsize=None)\ndef fib_memo(n):\n    if n < 2: return n\n    return fib_memo(n-1) + fib_memo(n-2)\n\n# Bottom-Up (Tabulation)\ndef fib_tab(n):\n    if n < 2: return n\n    dp = [0] * (n + 1)\n    dp[1] = 1\n    for i in range(2, n + 1):\n        dp[i] = dp[i-1] + dp[i-2]\n    return dp[n]\n```\n\n## Classic DP: Longest Common Subsequence\n```python\ndef lcs(s1, s2):\n    m, n = len(s1), len(s2)\n    dp = [[0] * (n+1) for _ in range(m+1)]\n    for i in range(1, m+1):\n        for j in range(1, n+1):\n            if s1[i-1] == s2[j-1]:\n                dp[i][j] = dp[i-1][j-1] + 1\n            else:\n                dp[i][j] = max(dp[i-1][j], dp[i][j-1])\n    return dp[m][n]\n\nprint(lcs('ABCBDAB', 'BDCAB'))  # 4 (BCAB)\n```\n\n## Knapsack Problem\n```python\ndef knapsack(weights, values, capacity):\n    n = len(weights)\n    dp = [[0] * (capacity+1) for _ in range(n+1)]\n    for i in range(1, n+1):\n        for w in range(capacity+1):\n            dp[i][w] = dp[i-1][w]  # Don't take item\n            if weights[i-1] <= w:\n                dp[i][w] = max(dp[i][w], dp[i-1][w-weights[i-1]] + values[i-1])\n    return dp[n][capacity]\n```"),
             ]),
         ]},
        {"id": "game_dev_academy", "name": "Game Dev Academy", "icon": "game-controller", "color": "#FF5722", "total_hours": 4320, "category": "academy",
         "description": "Complete game development from engine architecture to shipping.", "certificate": "Game Developer Professional",
         "modules": [
             _module("game_arch", "Game Architecture", "Game loops, ECS, state machines, scene management", 40, [
                 _lesson("gd1", "Game Loop & ECS", "Fixed timestep, entity-component-system, delta time", 90, "intermediate", ["game-loop", "ecs"],
                     "# Game Architecture\n\n## Fixed Timestep Game Loop\n```python\nimport time\n\nTICK_RATE = 60\nTIME_STEP = 1.0 / TICK_RATE\n\ndef game_loop():\n    previous = time.time()\n    accumulator = 0.0\n    \n    while running:\n        current = time.time()\n        delta = current - previous\n        previous = current\n        accumulator += delta\n        \n        while accumulator >= TIME_STEP:\n            update(TIME_STEP)   # Physics/logic\n            accumulator -= TIME_STEP\n        \n        alpha = accumulator / TIME_STEP\n        render(alpha)           # Interpolated render\n```\n\n## Entity-Component-System\n```python\nclass Entity:\n    _next_id = 0\n    def __init__(self):\n        Entity._next_id += 1\n        self.id = Entity._next_id\n        self.components = {}\n    \n    def add(self, component):\n        self.components[type(component).__name__] = component\n    \n    def get(self, comp_type):\n        return self.components.get(comp_type.__name__)\n\nclass Position:\n    def __init__(self, x=0, y=0): self.x, self.y = x, y\n\nclass Velocity:\n    def __init__(self, dx=0, dy=0): self.dx, self.dy = dx, dy\n\nclass MovementSystem:\n    def update(self, entities, dt):\n        for e in entities:\n            pos = e.get(Position)\n            vel = e.get(Velocity)\n            if pos and vel:\n                pos.x += vel.dx * dt\n                pos.y += vel.dy * dt\n```"),
             ]),
         ]},
        {"id": "web_dev_academy", "name": "Web Dev Academy", "icon": "globe", "color": "#4CAF50", "total_hours": 4050, "category": "academy",
         "description": "Full-stack web development from HTML/CSS to deployment.", "certificate": "Full-Stack Web Developer",
         "modules": [
             _module("web_fundamentals", "Web Fundamentals", "HTML5, CSS3, responsive design", 30, [
                 _lesson("web1", "HTML5 & Semantic Markup", "Modern HTML, accessibility, SEO", 60, "beginner", ["html5", "semantic"],
                     "# HTML5 Semantic Markup\n\n```html\n<!DOCTYPE html>\n<html lang=\"en\">\n<head>\n    <meta charset=\"UTF-8\">\n    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">\n    <title>Modern Web</title>\n</head>\n<body>\n    <header>\n        <nav aria-label=\"Main navigation\">\n            <ul>\n                <li><a href=\"/\">Home</a></li>\n                <li><a href=\"/about\">About</a></li>\n            </ul>\n        </nav>\n    </header>\n    \n    <main>\n        <article>\n            <h1>Article Title</h1>\n            <time datetime=\"2024-01-15\">Jan 15, 2024</time>\n            <p>Content here...</p>\n            <figure>\n                <img src=\"chart.png\" alt=\"Sales chart showing 30% growth\">\n                <figcaption>Q4 2024 Sales Growth</figcaption>\n            </figure>\n        </article>\n        \n        <aside>\n            <h2>Related Articles</h2>\n        </aside>\n    </main>\n    \n    <footer>\n        <p>&copy; 2024 Company</p>\n    </footer>\n</body>\n</html>\n```"),
             ]),
         ]},
        {"id": "cloud_academy", "name": "Cloud Academy", "icon": "cloud", "color": "#FF9800", "total_hours": 3780, "category": "academy",
         "description": "Master AWS, GCP, Azure, and cloud-native architecture.", "certificate": "Cloud Solutions Architect",
         "modules": [
             _module("cloud_fundamentals", "Cloud Fundamentals", "IaaS, PaaS, SaaS, regions, pricing", 25, [
                 _lesson("cld1", "Cloud Architecture", "Compute, storage, networking, serverless", 75, "beginner", ["cloud", "architecture"],
                     "# Cloud Architecture\n\n## Service Models\n```\nIaaS (Infrastructure) — VMs, Networks, Storage\n  AWS: EC2, VPC, S3\n  GCP: Compute Engine, Cloud Storage\n  Azure: Virtual Machines, Blob Storage\n\nPaaS (Platform) — Managed Services\n  AWS: Elastic Beanstalk, RDS, Lambda\n  GCP: App Engine, Cloud SQL, Cloud Functions\n  Azure: App Service, Azure SQL, Azure Functions\n\nSaaS (Software) — Ready-to-use\n  Gmail, Slack, Salesforce, GitHub\n```\n\n## Well-Architected Framework\n```\n1. Operational Excellence — Automate everything\n2. Security — Defense in depth\n3. Reliability — Design for failure\n4. Performance Efficiency — Right-size resources\n5. Cost Optimization — Pay only for what you use\n6. Sustainability — Minimize environmental impact\n```\n\n## Terraform Example\n```hcl\nresource \"aws_instance\" \"web\" {\n  ami           = \"ami-0c55b159cbfafe1f0\"\n  instance_type = \"t3.micro\"\n  \n  tags = {\n    Name = \"web-server\"\n    Env  = \"production\"\n  }\n}\n\nresource \"aws_s3_bucket\" \"data\" {\n  bucket = \"my-data-bucket\"\n  versioning { enabled = true }\n}\n```"),
             ]),
         ]},
        {"id": "blockchain_academy", "name": "Blockchain Academy", "icon": "link", "color": "#607D8B", "total_hours": 2160, "category": "academy",
         "description": "Master blockchain, DeFi, smart contracts, and Web3 development.", "certificate": "Blockchain Developer",
         "modules": [
             _module("blockchain_fundamentals", "Blockchain Fundamentals", "Consensus, cryptography, distributed ledgers", 25, [
                 _lesson("bc1", "Blockchain Core Concepts", "Hash functions, Merkle trees, consensus mechanisms", 75, "beginner", ["blockchain", "cryptography"],
                     "# Blockchain Fundamentals\n\n## Hash Functions\n```python\nimport hashlib\n\ndef sha256(data):\n    return hashlib.sha256(data.encode()).hexdigest()\n\n# Simple Block\nclass Block:\n    def __init__(self, index, data, prev_hash):\n        self.index = index\n        self.data = data\n        self.prev_hash = prev_hash\n        self.nonce = 0\n        self.hash = self.calculate_hash()\n    \n    def calculate_hash(self):\n        content = f'{self.index}{self.data}{self.prev_hash}{self.nonce}'\n        return sha256(content)\n    \n    def mine(self, difficulty=4):\n        target = '0' * difficulty\n        while not self.hash.startswith(target):\n            self.nonce += 1\n            self.hash = self.calculate_hash()\n        return self.hash\n\n# Simple Blockchain\ngenesis = Block(0, 'Genesis', '0')\ngenesis.mine()\nblock1 = Block(1, 'Transaction: Alice->Bob 5 BTC', genesis.hash)\nblock1.mine()\nprint(f'Genesis: {genesis.hash[:16]}...')\nprint(f'Block 1: {block1.hash[:16]}...')\n```"),
             ]),
         ]},
    ]


# ═══════════════════════════════════════════════════════════════════════════
# KNOWLEDGE BIBLES
# ═══════════════════════════════════════════════════════════════════════════

def _knowledge_bibles():
    """Generate all knowledge bible content."""
    return [
        {"id": "security_bible", "name": "Security Bible", "icon": "shield", "color": "#F44336", "total_hours": 2430, "category": "bible",
         "description": "Complete cybersecurity from fundamentals to advanced pentesting.",
         "sections": [
             {"id": "sec_fundamentals", "name": "Security Fundamentals", "articles": [
                 {"id": "sec1", "title": "CIA Triad", "content": "# CIA Triad\n\n## Confidentiality\nEnsure data is only accessible to authorized users.\n- Encryption (AES-256, RSA)\n- Access controls (RBAC, ABAC)\n- Authentication (MFA, biometrics)\n\n## Integrity\nEnsure data hasn't been tampered with.\n- Hash functions (SHA-256)\n- Digital signatures\n- Checksums\n\n## Availability\nEnsure systems are accessible when needed.\n- Redundancy\n- Load balancing\n- DDoS protection\n\n```python\nimport hashlib, secrets\n\n# Verify file integrity\ndef file_hash(path):\n    sha = hashlib.sha256()\n    with open(path, 'rb') as f:\n        for chunk in iter(lambda: f.read(8192), b''):\n            sha.update(chunk)\n    return sha.hexdigest()\n\n# Generate secure token\ntoken = secrets.token_urlsafe(32)\nprint(f'Secure token: {token}')\n```", "tags": ["cia", "fundamentals"]},
                 {"id": "sec2", "title": "OWASP Top 10", "content": "# OWASP Top 10 (2024)\n\n## 1. Broken Access Control\n```python\n# BAD: Direct object reference\n@app.get('/api/users/{user_id}/data')\nasync def get_data(user_id: int):\n    return db.find(user_id)  # No auth check!\n\n# GOOD: Check ownership\n@app.get('/api/users/{user_id}/data')\nasync def get_data(user_id: int, current_user = Depends(get_current_user)):\n    if current_user.id != user_id and not current_user.is_admin:\n        raise HTTPException(403)\n    return db.find(user_id)\n```\n\n## 2. Injection\n```python\n# BAD: SQL Injection\nquery = f\"SELECT * FROM users WHERE name = '{name}'\"  # NEVER!\n\n# GOOD: Parameterized\ncursor.execute(\"SELECT * FROM users WHERE name = %s\", (name,))\n```\n\n## 3. XSS (Cross-Site Scripting)\n```javascript\n// BAD\ndocument.innerHTML = userInput;  // NEVER!\n\n// GOOD\ndocument.textContent = userInput;  // Escaped\n```", "tags": ["owasp", "injection", "xss"]},
             ]},
         ]},
        {"id": "devops_bible", "name": "DevOps Bible", "icon": "cloud", "color": "#2196F3", "total_hours": 2700, "category": "bible",
         "description": "Complete DevOps from CI/CD to Kubernetes and infrastructure as code.",
         "sections": [
             {"id": "devops_cicd", "name": "CI/CD Pipelines", "articles": [
                 {"id": "do1", "title": "GitHub Actions", "content": "# GitHub Actions CI/CD\n\n```yaml\nname: CI/CD Pipeline\non:\n  push:\n    branches: [main]\n  pull_request:\n    branches: [main]\n\njobs:\n  test:\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-python@v5\n        with:\n          python-version: '3.12'\n      - run: pip install -r requirements.txt\n      - run: pytest --cov=app tests/\n      - uses: codecov/codecov-action@v4\n\n  build:\n    needs: test\n    runs-on: ubuntu-latest\n    steps:\n      - uses: actions/checkout@v4\n      - uses: docker/build-push-action@v5\n        with:\n          push: true\n          tags: myapp:${{ github.sha }}\n\n  deploy:\n    needs: build\n    runs-on: ubuntu-latest\n    if: github.ref == 'refs/heads/main'\n    steps:\n      - run: kubectl set image deployment/myapp myapp=myapp:${{ github.sha }}\n```", "tags": ["github-actions", "ci-cd"]},
                 {"id": "do2", "title": "Docker & Kubernetes", "content": "# Docker & Kubernetes\n\n## Dockerfile\n```dockerfile\nFROM python:3.12-slim\nWORKDIR /app\nCOPY requirements.txt .\nRUN pip install --no-cache-dir -r requirements.txt\nCOPY . .\nEXPOSE 8000\nCMD [\"uvicorn\", \"main:app\", \"--host\", \"0.0.0.0\", \"--port\", \"8000\"]\n```\n\n## Kubernetes Deployment\n```yaml\napiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: web-app\nspec:\n  replicas: 3\n  selector:\n    matchLabels:\n      app: web\n  template:\n    metadata:\n      labels:\n        app: web\n    spec:\n      containers:\n      - name: web\n        image: myapp:latest\n        ports:\n        - containerPort: 8000\n        resources:\n          limits:\n            memory: 256Mi\n            cpu: 500m\n        livenessProbe:\n          httpGet:\n            path: /health\n            port: 8000\n          initialDelaySeconds: 10\n```", "tags": ["docker", "kubernetes"]},
             ]},
         ]},
        {"id": "frontend_bible", "name": "Frontend Bible", "icon": "tablet-portrait", "color": "#E91E63", "total_hours": 3240, "category": "bible",
         "description": "Complete frontend development from HTML/CSS to React, Vue, and Angular.",
         "sections": [
             {"id": "fe_modern", "name": "Modern Frontend", "articles": [
                 {"id": "fe1", "title": "React Patterns", "content": "# React Patterns\n\n## Custom Hooks\n```jsx\nfunction useFetch(url) {\n  const [data, setData] = useState(null);\n  const [loading, setLoading] = useState(true);\n  const [error, setError] = useState(null);\n\n  useEffect(() => {\n    const controller = new AbortController();\n    setLoading(true);\n    \n    fetch(url, { signal: controller.signal })\n      .then(res => res.json())\n      .then(setData)\n      .catch(setError)\n      .finally(() => setLoading(false));\n    \n    return () => controller.abort();\n  }, [url]);\n\n  return { data, loading, error };\n}\n```\n\n## Compound Components\n```jsx\nconst Tabs = ({ children }) => {\n  const [active, setActive] = useState(0);\n  return (\n    <TabsContext.Provider value={{ active, setActive }}>\n      {children}\n    </TabsContext.Provider>\n  );\n};\nTabs.List = TabList;\nTabs.Panel = TabPanel;\n\n// Usage\n<Tabs>\n  <Tabs.List>\n    <Tabs.Tab>Profile</Tabs.Tab>\n    <Tabs.Tab>Settings</Tabs.Tab>\n  </Tabs.List>\n  <Tabs.Panel>Profile content</Tabs.Panel>\n  <Tabs.Panel>Settings content</Tabs.Panel>\n</Tabs>\n```", "tags": ["react", "patterns", "hooks"]},
             ]},
         ]},
        {"id": "backend_bible", "name": "Backend Bible", "icon": "server", "color": "#4CAF50", "total_hours": 3780, "category": "bible",
         "description": "Complete backend development from APIs to distributed systems.",
         "sections": [
             {"id": "be_apis", "name": "API Design", "articles": [
                 {"id": "be1", "title": "REST API Best Practices", "content": "# REST API Design\n\n## URL Structure\n```\nGET    /api/v1/users          # List users\nGET    /api/v1/users/123      # Get user\nPOST   /api/v1/users          # Create user\nPUT    /api/v1/users/123      # Update user\nDELETE /api/v1/users/123      # Delete user\nGET    /api/v1/users/123/posts # User's posts\n```\n\n## Response Format\n```json\n{\n  \"data\": { \"id\": 123, \"name\": \"Alice\" },\n  \"meta\": { \"total\": 50, \"page\": 1, \"per_page\": 20 },\n  \"links\": {\n    \"next\": \"/api/v1/users?page=2\",\n    \"prev\": null\n  }\n}\n```\n\n## Error Format\n```json\n{\n  \"error\": {\n    \"code\": \"VALIDATION_ERROR\",\n    \"message\": \"Invalid email format\",\n    \"details\": [\n      { \"field\": \"email\", \"message\": \"Must be a valid email\" }\n    ]\n  }\n}\n```\n\n## Rate Limiting Headers\n```\nX-RateLimit-Limit: 100\nX-RateLimit-Remaining: 95\nX-RateLimit-Reset: 1640995200\nRetry-After: 60\n```", "tags": ["rest", "api-design"]},
             ]},
         ]},
        {"id": "database_bible", "name": "Database Bible", "icon": "file-tray-stacked", "color": "#795548", "total_hours": 2430, "category": "bible",
         "description": "Complete database design, optimization, and administration.",
         "sections": [
             {"id": "db_design", "name": "Database Design", "articles": [
                 {"id": "db1", "title": "Schema Design Patterns", "content": "# Database Design\n\n## Normalization\n```\n1NF: No repeating groups, atomic values\n2NF: 1NF + no partial dependencies\n3NF: 2NF + no transitive dependencies\nBCNF: 3NF + every determinant is a candidate key\n```\n\n## Indexing Strategy\n```sql\n-- B-Tree (default, good for ranges)\nCREATE INDEX idx_users_email ON users(email);\n\n-- Composite index (leftmost prefix rule)\nCREATE INDEX idx_orders ON orders(user_id, created_at);\n\n-- Partial index (conditional)\nCREATE INDEX idx_active_users ON users(email)\n  WHERE status = 'active';\n\n-- EXPLAIN to analyze queries\nEXPLAIN ANALYZE\nSELECT * FROM orders\nWHERE user_id = 123\n  AND created_at > '2024-01-01'\nORDER BY created_at DESC\nLIMIT 10;\n```\n\n## MongoDB Schema Design\n```javascript\n// Embedded (1:few, read-heavy)\n{\n  _id: ObjectId(),\n  name: 'Alice',\n  addresses: [\n    { street: '123 Main', city: 'NYC' },\n    { street: '456 Oak', city: 'LA' }\n  ]\n}\n\n// Referenced (1:many, write-heavy)\n// users collection\n{ _id: ObjectId('user1'), name: 'Alice' }\n// orders collection\n{ _id: ObjectId(), user_id: ObjectId('user1'), total: 99.99 }\n```", "tags": ["schema", "indexing", "mongodb"]},
             ]},
         ]},
    ]


# ═══════════════════════════════════════════════════════════════════════════
# MASTER FUNCTION — Returns ALL content
# ═══════════════════════════════════════════════════════════════════════════

def get_all_tracks():
    """Return all language tracks."""
    tracks = [
        _python_track(),
        _javascript_track(),
        _typescript_track(),
        _rust_track(),
        _go_track(),
        _cpp_track(),
        _c_track(),
        _java_track(),
        _kotlin_track(),
        _swift_track(),
        _csharp_track(),
        _ruby_track(),
        _php_track(),
        _sql_track(),
        _bash_track(),
    ]
    tracks.extend(_remaining_lang_tracks())
    return tracks


def get_all_academies():
    """Return all subject academy tracks."""
    return _subject_academy_tracks()


def get_all_bibles():
    """Return all knowledge bibles."""
    return _knowledge_bibles()


def get_all_content():
    """Return everything."""
    return {
        "tracks": get_all_tracks(),
        "academies": get_all_academies(),
        "bibles": get_all_bibles(),
    }
