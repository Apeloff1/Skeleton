// ============================================================================
// CODEDOCK QUANTUM NEXUS - THE COMPLETE CODING BIBLE
// A Year-Long Journey from Zero to Mastery
// 52 Weeks • 12 Months • Infinite Possibilities
// ============================================================================

import { BibleChapter } from '../../types';

export const CODING_BIBLE: BibleChapter[] = [
  // ═══════════════════════════════════════════════════════════════════════════
  // MONTH 1-2: AWAKENING (Weeks 1-8)
  // ═══════════════════════════════════════════════════════════════════════════
  {
    id: 'week1', day: 1, tier: 'beginner', title: 'The Awakening', subtitle: 'Your First Line of Code',
    icon: 'sunny', color: '#22C55E', unlocked: true, estimatedTime: '45 min',
    sections: [
      { title: 'Welcome to Your Journey', content: `Welcome, future developer. Today marks the beginning of something extraordinary.\n\nProgramming is not about memorizing syntax. It is about learning to think in new ways, to break down problems into smaller pieces, and to express solutions with precision and elegance.\n\nTake a deep breath. You belong here.`, tips: ['Every expert was once a beginner', 'Progress over perfection', 'Embrace confusion - it means learning'] },
      { title: 'What is Programming?', content: `At its core, programming is communication. You are learning to speak to computers.\n\nComputers are incredibly powerful but literal. They do exactly what you tell them - nothing more, nothing less.`, code: `# Your first program\nprint("Hello, World!")\n\n# Congratulations! You just gave a computer an instruction.`, language: 'python' },
      { title: 'Variables', content: `Variables are containers for information. Think of them as labeled boxes where you store data.`, code: `name = "Ada"\nage = 28\nis_programmer = True\n\nprint(name)\nprint(age)`, language: 'python' },
      { title: 'Data Types', content: `Data comes in different types:\n\n• Strings (str): Text in quotes\n• Integers (int): Whole numbers\n• Floats (float): Decimal numbers\n• Booleans (bool): True or False`, code: `greeting = "Hello"\ncount = 42\npi = 3.14159\nis_active = True\n\nprint(type(greeting))  # <class 'str'>`, language: 'python' }
    ]
  },
  {
    id: 'week2', day: 8, tier: 'beginner', title: 'The Conversation', subtitle: 'Input, Output & Math',
    icon: 'chatbubbles', color: '#3B82F6', unlocked: true, estimatedTime: '50 min',
    sections: [
      { title: 'Getting User Input', content: `Programs become interactive when they receive input from users.`, code: `name = input("What is your name? ")\nprint("Hello, " + name + "!")\n\n# input() always returns a string\nage = int(input("How old are you? "))\nprint("Next year you will be", age + 1)`, language: 'python' },
      { title: 'Arithmetic Operations', content: `Python is a powerful calculator.\n\n+ Addition\n- Subtraction\n* Multiplication\n/ Division\n// Floor division\n% Modulo (remainder)\n** Exponentiation`, code: `print(10 + 3)   # 13\nprint(10 - 3)   # 7\nprint(10 * 3)   # 30\nprint(10 / 3)   # 3.333...\nprint(10 // 3)  # 3\nprint(10 % 3)   # 1\nprint(10 ** 3)  # 1000`, language: 'python' },
      { title: 'String Formatting', content: `f-strings are the modern way to format strings in Python.`, code: `name = "Alice"\nage = 30\n\nmessage = f"My name is {name} and I am {age}"\nprint(message)\n\nprint(f"In 5 years: {age + 5}")`, language: 'python' }
    ]
  },
  {
    id: 'week3', day: 15, tier: 'beginner', title: 'The Crossroads', subtitle: 'Making Decisions',
    icon: 'git-branch', color: '#8B5CF6', unlocked: true, estimatedTime: '55 min',
    sections: [
      { title: 'If Statements', content: `The if statement lets your program make decisions based on conditions.`, code: `temperature = 35\n\nif temperature > 30:\n    print("It is hot outside!")\n    print("Stay hydrated!")`, language: 'python' },
      { title: 'If-Else', content: `Use else to handle the alternative case.`, code: `age = 16\n\nif age >= 18:\n    print("You are an adult")\nelse:\n    print("You are a minor")`, language: 'python' },
      { title: 'Elif (Multiple Conditions)', content: `Use elif to check multiple conditions in sequence.`, code: `score = 78\n\nif score >= 90:\n    grade = "A"\nelif score >= 80:\n    grade = "B"\nelif score >= 70:\n    grade = "C"\nelse:\n    grade = "F"\n\nprint(f"Grade: {grade}")`, language: 'python' },
      { title: 'Comparison Operators', content: `== Equal to\n!= Not equal to\n> Greater than\n< Less than\n>= Greater than or equal\n<= Less than or equal`, code: `x = 10\ny = 5\n\nprint(x == y)   # False\nprint(x != y)   # True\nprint(x > y)    # True\nprint(x >= 10)  # True`, language: 'python', warning: 'Do not confuse = (assignment) with == (comparison)!' }
    ]
  },
  {
    id: 'week4', day: 22, tier: 'beginner', title: 'The Logic', subtitle: 'Combining Conditions',
    icon: 'git-merge', color: '#EC4899', unlocked: true, estimatedTime: '45 min',
    sections: [
      { title: 'Logical Operators', content: `and - Both must be True\nor - At least one must be True\nnot - Reverses the boolean`, code: `age = 25\nhas_license = True\n\nif age >= 18 and has_license:\n    print("You can drive")\n\nif age < 18 or not has_license:\n    print("You cannot drive")`, language: 'python' },
      { title: 'Nested Conditions', content: `You can put if statements inside other if statements.`, code: `user_type = "member"\nyears = 3\n\nif user_type == "member":\n    if years >= 5:\n        discount = 20\n    elif years >= 2:\n        discount = 10\n    else:\n        discount = 5\n    print(f"Discount: {discount}%")`, language: 'python' },
      { title: 'Truthiness', content: `In Python, values can be "truthy" or "falsy".\n\nFalsy: False, None, 0, "", [], {}\nEverything else is truthy.`, code: `name = input("Enter name: ")\n\nif name:  # True if not empty\n    print(f"Hello, {name}!")\nelse:\n    print("You did not enter a name.")`, language: 'python' }
    ]
  },
  {
    id: 'week5', day: 29, tier: 'beginner', title: 'The Repetition', subtitle: 'Loops',
    icon: 'repeat', color: '#F59E0B', unlocked: true, estimatedTime: '60 min',
    sections: [
      { title: 'Why Loops?', content: `Loops let you repeat actions automatically instead of writing repetitive code.`, code: `# Without loops (painful!)\nprint(1)\nprint(2)\nprint(3)\n\n# With a loop (elegant!)\nfor i in range(1, 4):\n    print(i)`, language: 'python' },
      { title: 'For Loops', content: `Use for loops when you know how many times to repeat.`, code: `for num in range(5):\n    print(num)  # 0, 1, 2, 3, 4\n\nfruits = ["apple", "banana", "cherry"]\nfor fruit in fruits:\n    print(f"I love {fruit}!")`, language: 'python' },
      { title: 'While Loops', content: `Use while loops when you do not know how many iterations.`, code: `count = 0\nwhile count < 5:\n    print(count)\n    count += 1  # Critical!\n\nprint("Done!")`, language: 'python', warning: 'Always ensure your while loop can end!' },
      { title: 'Break and Continue', content: `break exits the loop. continue skips to the next iteration.`, code: `for i in range(10):\n    if i == 5:\n        break  # Exit at 5\n    print(i)\n\nfor i in range(10):\n    if i % 2 == 0:\n        continue  # Skip evens\n    print(i)`, language: 'python' }
    ]
  },
  {
    id: 'week6', day: 36, tier: 'beginner', title: 'The Collection', subtitle: 'Lists',
    icon: 'list', color: '#3B82F6', unlocked: true, estimatedTime: '55 min',
    sections: [
      { title: 'Understanding Lists', content: `A list is an ordered collection of items. Lists are mutable and can hold any data type.`, code: `numbers = [1, 2, 3, 4, 5]\nfruits = ["apple", "banana", "cherry"]\n\nprint(fruits[0])   # "apple"\nprint(fruits[-1])  # "cherry"\nprint(len(fruits)) # 3`, language: 'python' },
      { title: 'Modifying Lists', content: `Lists can be changed after creation.`, code: `fruits = ["apple", "banana"]\n\nfruits.append("cherry")  # Add to end\nfruits.insert(0, "apricot")  # Insert at index\nfruits.remove("banana")  # Remove by value\ndel fruits[0]  # Delete by index\nlast = fruits.pop()  # Remove and return last`, language: 'python' },
      { title: 'List Slicing', content: `Extract portions of a list with slicing.`, code: `nums = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]\n\nprint(nums[2:5])   # [2, 3, 4]\nprint(nums[:4])    # [0, 1, 2, 3]\nprint(nums[6:])    # [6, 7, 8, 9]\nprint(nums[::2])   # [0, 2, 4, 6, 8]\nprint(nums[::-1])  # Reversed!`, language: 'python' },
      { title: 'List Comprehensions', content: `A powerful, Pythonic way to create lists.`, code: `squares = [x**2 for x in range(10)]\nprint(squares)  # [0, 1, 4, 9, 16, 25, 36, 49, 64, 81]\n\nevens = [x for x in range(20) if x % 2 == 0]\nprint(evens)  # [0, 2, 4, 6, 8, 10, 12, 14, 16, 18]`, language: 'python' }
    ]
  },
  {
    id: 'week7', day: 43, tier: 'beginner', title: 'The Dictionary', subtitle: 'Key-Value Pairs',
    icon: 'book', color: '#6366F1', unlocked: true, estimatedTime: '50 min',
    sections: [
      { title: 'Understanding Dictionaries', content: `Dictionaries store data as key-value pairs. Think word -> definition.`, code: `person = {\n    "name": "Alice",\n    "age": 30,\n    "city": "NYC"\n}\n\nprint(person["name"])  # Alice\nprint(person.get("age"))  # 30\nprint(person.get("job", "Unknown"))  # Unknown`, language: 'python' },
      { title: 'Modifying Dictionaries', content: `Add, update, and remove key-value pairs.`, code: `person = {"name": "Alice", "age": 30}\n\nperson["email"] = "alice@example.com"  # Add\nperson["age"] = 31  # Update\ndel person["email"]  # Delete\n\nfor key, value in person.items():\n    print(f"{key}: {value}")`, language: 'python' },
      { title: 'Nested Structures', content: `Real-world data is often complex and nested.`, code: `users = [\n    {"name": "Alice", "age": 30},\n    {"name": "Bob", "age": 25}\n]\n\nfor user in users:\n    print(f"{user['name']} is {user['age']}")`, language: 'python' }
    ]
  },
  {
    id: 'week8', day: 50, tier: 'beginner', title: 'The Function', subtitle: 'Reusable Code',
    icon: 'cube', color: '#F97316', unlocked: true, estimatedTime: '65 min',
    sections: [
      { title: 'Why Functions?', content: `Functions are named blocks of reusable code. Write once, use many times.`, code: `def greet(name):\n    print(f"Hello, {name}!")\n\ngreet("Alice")\ngreet("Bob")`, language: 'python' },
      { title: 'Parameters and Return', content: `Functions can take inputs and return outputs.`, code: `def add(a, b):\n    return a + b\n\nresult = add(5, 3)\nprint(result)  # 8\n\ndef greet(name, greeting="Hello"):\n    return f"{greeting}, {name}!"\n\nprint(greet("Alice"))  # Hello, Alice!\nprint(greet("Bob", "Hi"))  # Hi, Bob!`, language: 'python' },
      { title: 'Multiple Return Values', content: `Functions can return multiple values as tuples.`, code: `def get_stats(numbers):\n    return min(numbers), max(numbers), sum(numbers)\n\nlow, high, total = get_stats([1, 2, 3, 4, 5])\nprint(f"Min: {low}, Max: {high}, Sum: {total}")`, language: 'python' }
    ]
  },
  // ═══════════════════════════════════════════════════════════════════════════
  // MONTH 3-4: FOUNDATION (Weeks 9-16)
  // ═══════════════════════════════════════════════════════════════════════════
  {
    id: 'week9', day: 57, tier: 'foundation', title: 'The Scope', subtitle: 'Variable Visibility',
    icon: 'eye', color: '#2563EB', unlocked: true, estimatedTime: '45 min',
    sections: [
      { title: 'Local vs Global', content: `Where you define a variable determines where you can use it.`, code: `message = "Hello, Global!"\n\ndef my_func():\n    local_msg = "Hello, Local!"\n    print(message)  # Can access global\n    print(local_msg)  # Can access local\n\nmy_func()\nprint(message)  # Works\n# print(local_msg)  # ERROR!`, language: 'python' },
      { title: 'The Global Keyword', content: `Use global to modify global variables from inside functions (use sparingly).`, code: `counter = 0\n\ndef increment():\n    global counter\n    counter += 1\n\nincrement()\nincrement()\nprint(counter)  # 2`, language: 'python', tips: ['Avoid global variables when possible', 'Pass values as parameters instead'] }
    ]
  },
  {
    id: 'week10', day: 64, tier: 'foundation', title: 'The Error', subtitle: 'Exception Handling',
    icon: 'bug', color: '#EF4444', unlocked: true, estimatedTime: '55 min',
    sections: [
      { title: 'Why Handle Errors?', content: `Programs encounter errors. With exception handling, they recover gracefully.`, code: `try:\n    result = 10 / 0\nexcept ZeroDivisionError:\n    print("Cannot divide by zero!")\n    result = 0\n\nprint(f"Result: {result}")`, language: 'python' },
      { title: 'Try-Except-Finally', content: `try: code that might fail\nexcept: handle the error\nelse: runs if no error\nfinally: always runs`, code: `def safe_divide(a, b):\n    try:\n        result = a / b\n    except ZeroDivisionError:\n        return None\n    except TypeError:\n        return None\n    else:\n        return result\n    finally:\n        print("Done.")`, language: 'python' },
      { title: 'Raising Exceptions', content: `Raise your own exceptions when something goes wrong.`, code: `def set_age(age):\n    if age < 0:\n        raise ValueError("Age cannot be negative!")\n    return age\n\ntry:\n    user_age = set_age(-5)\nexcept ValueError as e:\n    print(f"Error: {e}")`, language: 'python' }
    ]
  },
  {
    id: 'week11', day: 71, tier: 'foundation', title: 'The File', subtitle: 'Reading and Writing',
    icon: 'document', color: '#8B5CF6', unlocked: true, estimatedTime: '50 min',
    sections: [
      { title: 'Reading Files', content: `Use the with statement to safely handle files.`, code: `# Reading entire file\nwith open("data.txt", "r") as file:\n    content = file.read()\n    print(content)\n\n# Reading line by line\nwith open("data.txt", "r") as file:\n    for line in file:\n        print(line.strip())`, language: 'python' },
      { title: 'Writing Files', content: `"w" mode overwrites, "a" mode appends.`, code: `# Writing\nwith open("output.txt", "w") as file:\n    file.write("Hello, World!\\n")\n    file.write("Line 2\\n")\n\n# Appending\nwith open("output.txt", "a") as file:\n    file.write("New line\\n")`, language: 'python' },
      { title: 'Working with JSON', content: `JSON is popular for storing and transmitting data.`, code: `import json\n\ndata = {"name": "Alice", "age": 30}\n\n# Save to file\nwith open("data.json", "w") as f:\n    json.dump(data, f, indent=2)\n\n# Load from file\nwith open("data.json", "r") as f:\n    loaded = json.load(f)\n    print(loaded["name"])`, language: 'python' }
    ]
  },
  {
    id: 'week12', day: 78, tier: 'foundation', title: 'The Module', subtitle: 'Organizing Code',
    icon: 'folder-open', color: '#F59E0B', unlocked: true, estimatedTime: '45 min',
    sections: [
      { title: 'Importing Modules', content: `Modules let you organize and reuse code across files.`, code: `# Import entire module\nimport math\nprint(math.sqrt(16))  # 4.0\nprint(math.pi)  # 3.14159...\n\n# Import specific functions\nfrom math import sqrt, pi\nprint(sqrt(16))\nprint(pi)\n\n# Import with alias\nimport math as m\nprint(m.sqrt(16))`, language: 'python' },
      { title: 'Common Standard Library', content: `Python comes with many useful built-in modules.`, code: `import random\nprint(random.randint(1, 10))\nprint(random.choice(["a", "b", "c"]))\n\nimport datetime\nnow = datetime.datetime.now()\nprint(now.strftime("%Y-%m-%d"))\n\nimport os\nprint(os.getcwd())  # Current directory`, language: 'python' }
    ]
  },
  {
    id: 'week13', day: 85, tier: 'foundation', title: 'The String II', subtitle: 'Advanced Text',
    icon: 'text', color: '#EC4899', unlocked: true, estimatedTime: '50 min',
    sections: [
      { title: 'String Methods', content: `Strings have many useful built-in methods.`, code: `text = "  Hello, World!  "\n\nprint(text.upper())  # "  HELLO, WORLD!  "\nprint(text.lower())  # "  hello, world!  "\nprint(text.strip())  # "Hello, World!"\nprint(text.replace("World", "Python"))\nprint(text.split(","))  # ['  Hello', ' World!  ']\nprint("-".join(["a", "b", "c"]))  # "a-b-c"`, language: 'python' },
      { title: 'String Searching', content: `Find and check substrings.`, code: `text = "Hello, World!"\n\nprint("World" in text)  # True\nprint(text.find("World"))  # 7 (index)\nprint(text.startswith("Hello"))  # True\nprint(text.endswith("!"))  # True\nprint(text.count("l"))  # 3`, language: 'python' },
      { title: 'Regular Expressions', content: `Regex for powerful pattern matching.`, code: `import re\n\ntext = "Contact: alice@email.com, bob@test.org"\n\n# Find all emails\nemails = re.findall(r'[\\w]+@[\\w]+\\.[\\w]+', text)\nprint(emails)\n\n# Check if valid email\npattern = r'^[\\w]+@[\\w]+\\.[\\w]+$'\nif re.match(pattern, "test@example.com"):\n    print("Valid email!")`, language: 'python' }
    ]
  },
  {
    id: 'week14', day: 92, tier: 'foundation', title: 'The Set', subtitle: 'Unique Collections',
    icon: 'ellipse', color: '#3B82F6', unlocked: true, estimatedTime: '40 min',
    sections: [
      { title: 'Understanding Sets', content: `Sets store unique values only. Great for removing duplicates.`, code: `numbers = {1, 2, 2, 3, 3, 3}\nprint(numbers)  # {1, 2, 3}\n\n# Remove duplicates from list\nnames = ["Alice", "Bob", "Alice", "Charlie"]\nunique = list(set(names))\nprint(unique)`, language: 'python' },
      { title: 'Set Operations', content: `Sets support mathematical set operations.`, code: `a = {1, 2, 3, 4}\nb = {3, 4, 5, 6}\n\nprint(a | b)  # Union: {1, 2, 3, 4, 5, 6}\nprint(a & b)  # Intersection: {3, 4}\nprint(a - b)  # Difference: {1, 2}\nprint(a ^ b)  # Symmetric diff: {1, 2, 5, 6}`, language: 'python' }
    ]
  },
  {
    id: 'week15', day: 99, tier: 'foundation', title: 'The Tuple', subtitle: 'Immutable Sequences',
    icon: 'lock-closed', color: '#6366F1', unlocked: true, estimatedTime: '35 min',
    sections: [
      { title: 'Understanding Tuples', content: `Tuples are like lists but immutable - they cannot be changed after creation.`, code: `# Creating tuples\npoint = (10, 20)\ncolors = ("red", "green", "blue")\n\n# Accessing elements\nprint(point[0])  # 10\nprint(point[1])  # 20\n\n# Unpacking\nx, y = point\nprint(f"x={x}, y={y}")`, language: 'python' },
      { title: 'When to Use Tuples', content: `Use tuples for data that should not change, like coordinates or RGB values.`, code: `# Returning multiple values\ndef get_dimensions():\n    return (1920, 1080)\n\nwidth, height = get_dimensions()\n\n# As dictionary keys (lists cannot be keys)\nlocations = {\n    (40.7128, -74.0060): "New York",\n    (34.0522, -118.2437): "Los Angeles"\n}`, language: 'python' }
    ]
  },
  {
    id: 'week16', day: 106, tier: 'foundation', title: 'The Lambda', subtitle: 'Anonymous Functions',
    icon: 'flash', color: '#F97316', unlocked: true, estimatedTime: '45 min',
    sections: [
      { title: 'Lambda Functions', content: `Lambdas are small anonymous functions defined in one line.`, code: `# Regular function\ndef square(x):\n    return x ** 2\n\n# Lambda equivalent\nsquare = lambda x: x ** 2\n\nprint(square(5))  # 25\n\n# Lambda with multiple arguments\nadd = lambda a, b: a + b\nprint(add(3, 4))  # 7`, language: 'python' },
      { title: 'Map, Filter, Reduce', content: `Functional programming with lambdas.`, code: `numbers = [1, 2, 3, 4, 5]\n\n# map - apply function to each element\nsquares = list(map(lambda x: x**2, numbers))\nprint(squares)  # [1, 4, 9, 16, 25]\n\n# filter - keep elements that pass test\nevens = list(filter(lambda x: x % 2 == 0, numbers))\nprint(evens)  # [2, 4]\n\n# sorted with key\nwords = ["banana", "apple", "cherry"]\nsorted_words = sorted(words, key=lambda x: len(x))\nprint(sorted_words)  # ['apple', 'banana', 'cherry']`, language: 'python' }
    ]
  },
  // ═══════════════════════════════════════════════════════════════════════════
  // MONTH 5-6: EXPANSION (Weeks 17-24)
  // ═══════════════════════════════════════════════════════════════════════════
  {
    id: 'week17', day: 113, tier: 'intermediate', title: 'The Class', subtitle: 'Object-Oriented Programming',
    icon: 'construct', color: '#8B5CF6', unlocked: true, estimatedTime: '75 min',
    sections: [
      { title: 'What is OOP?', content: `OOP organizes code into objects that combine data (attributes) and behavior (methods).`, code: `class Dog:\n    species = "Canis familiaris"  # Class attribute\n    \n    def __init__(self, name, age):\n        self.name = name  # Instance attribute\n        self.age = age\n    \n    def bark(self):\n        return f"{self.name} says Woof!"\n\nmy_dog = Dog("Max", 3)\nprint(my_dog.bark())  # Max says Woof!`, language: 'python' },
      { title: 'Instance vs Class Attributes', content: `Instance attributes are unique to each object. Class attributes are shared.`, code: `class Counter:\n    count = 0  # Class attribute\n    \n    def __init__(self):\n        Counter.count += 1\n        self.id = Counter.count\n\nc1 = Counter()\nc2 = Counter()\nprint(c1.id, c2.id)  # 1, 2\nprint(Counter.count)  # 2`, language: 'python' }
    ]
  },
  {
    id: 'week18', day: 120, tier: 'intermediate', title: 'The Inheritance', subtitle: 'Code Reuse',
    icon: 'git-network', color: '#EC4899', unlocked: true, estimatedTime: '60 min',
    sections: [
      { title: 'Basic Inheritance', content: `Classes can inherit from other classes, gaining their attributes and methods.`, code: `class Animal:\n    def __init__(self, name):\n        self.name = name\n    \n    def speak(self):\n        raise NotImplementedError\n\nclass Dog(Animal):\n    def speak(self):\n        return f"{self.name} barks!"\n\nclass Cat(Animal):\n    def speak(self):\n        return f"{self.name} meows!"\n\ndog = Dog("Rex")\ncat = Cat("Whiskers")\nprint(dog.speak())  # Rex barks!`, language: 'python' },
      { title: 'Super()', content: `Call the parent class methods using super().`, code: `class Animal:\n    def __init__(self, name, age):\n        self.name = name\n        self.age = age\n\nclass Dog(Animal):\n    def __init__(self, name, age, breed):\n        super().__init__(name, age)\n        self.breed = breed\n\ndog = Dog("Max", 3, "Labrador")\nprint(f"{dog.name} is a {dog.breed}")`, language: 'python' }
    ]
  },
  {
    id: 'week19', day: 127, tier: 'intermediate', title: 'The Encapsulation', subtitle: 'Data Protection',
    icon: 'shield', color: '#F59E0B', unlocked: true, estimatedTime: '50 min',
    sections: [
      { title: 'Private Attributes', content: `Use _ prefix for protected and __ for private attributes.`, code: `class BankAccount:\n    def __init__(self, balance):\n        self._balance = balance  # Protected\n        self.__pin = "1234"  # Private\n    \n    def deposit(self, amount):\n        if amount > 0:\n            self._balance += amount\n    \n    def get_balance(self):\n        return self._balance\n\naccount = BankAccount(100)\naccount.deposit(50)\nprint(account.get_balance())  # 150`, language: 'python' },
      { title: 'Properties', content: `Use @property for controlled attribute access.`, code: `class Circle:\n    def __init__(self, radius):\n        self._radius = radius\n    \n    @property\n    def radius(self):\n        return self._radius\n    \n    @radius.setter\n    def radius(self, value):\n        if value > 0:\n            self._radius = value\n    \n    @property\n    def area(self):\n        return 3.14159 * self._radius ** 2\n\nc = Circle(5)\nprint(c.area)  # 78.54\nc.radius = 10\nprint(c.area)  # 314.16`, language: 'python' }
    ]
  },
  {
    id: 'week20', day: 134, tier: 'intermediate', title: 'The Polymorphism', subtitle: 'Many Forms',
    icon: 'shapes', color: '#3B82F6', unlocked: true, estimatedTime: '55 min',
    sections: [
      { title: 'Duck Typing', content: `If it walks like a duck and quacks like a duck, it is a duck.`, code: `class Dog:\n    def speak(self):\n        return "Woof!"\n\nclass Cat:\n    def speak(self):\n        return "Meow!"\n\nclass Duck:\n    def speak(self):\n        return "Quack!"\n\ndef animal_sound(animal):\n    print(animal.speak())\n\nanimal_sound(Dog())   # Woof!\nanimal_sound(Cat())   # Meow!\nanimal_sound(Duck())  # Quack!`, language: 'python' },
      { title: 'Abstract Classes', content: `Define interfaces that subclasses must implement.`, code: `from abc import ABC, abstractmethod\n\nclass Shape(ABC):\n    @abstractmethod\n    def area(self):\n        pass\n\nclass Rectangle(Shape):\n    def __init__(self, width, height):\n        self.width = width\n        self.height = height\n    \n    def area(self):\n        return self.width * self.height\n\n# shape = Shape()  # ERROR! Cannot instantiate\nrect = Rectangle(4, 5)\nprint(rect.area())  # 20`, language: 'python' }
    ]
  },
  {
    id: 'week21', day: 141, tier: 'intermediate', title: 'The Magic Methods', subtitle: 'Dunder Methods',
    icon: 'sparkles', color: '#6366F1', unlocked: true, estimatedTime: '60 min',
    sections: [
      { title: 'Common Magic Methods', content: `Magic methods (dunder methods) let you customize class behavior.`, code: `class Vector:\n    def __init__(self, x, y):\n        self.x = x\n        self.y = y\n    \n    def __repr__(self):\n        return f"Vector({self.x}, {self.y})"\n    \n    def __add__(self, other):\n        return Vector(self.x + other.x, self.y + other.y)\n    \n    def __eq__(self, other):\n        return self.x == other.x and self.y == other.y\n\nv1 = Vector(1, 2)\nv2 = Vector(3, 4)\nprint(v1 + v2)  # Vector(4, 6)\nprint(v1 == v2)  # False`, language: 'python' },
      { title: 'More Magic Methods', content: `__len__, __getitem__, __iter__ for collection-like behavior.`, code: `class Playlist:\n    def __init__(self):\n        self.songs = []\n    \n    def __len__(self):\n        return len(self.songs)\n    \n    def __getitem__(self, index):\n        return self.songs[index]\n    \n    def __iter__(self):\n        return iter(self.songs)\n    \n    def add(self, song):\n        self.songs.append(song)\n\nplaylist = Playlist()\nplaylist.add("Song A")\nplaylist.add("Song B")\nprint(len(playlist))  # 2\nprint(playlist[0])  # Song A`, language: 'python' }
    ]
  },
  {
    id: 'week22', day: 148, tier: 'intermediate', title: 'The Decorator', subtitle: 'Function Enhancement',
    icon: 'color-wand', color: '#F97316', unlocked: true, estimatedTime: '65 min',
    sections: [
      { title: 'Understanding Decorators', content: `Decorators wrap functions to add functionality.`, code: `def timer(func):\n    import time\n    def wrapper(*args, **kwargs):\n        start = time.time()\n        result = func(*args, **kwargs)\n        end = time.time()\n        print(f"{func.__name__} took {end-start:.4f}s")\n        return result\n    return wrapper\n\n@timer\ndef slow_function():\n    import time\n    time.sleep(1)\n    return "Done"\n\nslow_function()  # slow_function took 1.00XXs`, language: 'python' },
      { title: 'Common Decorators', content: `Python has useful built-in decorators.`, code: `class MyClass:\n    _instance_count = 0\n    \n    def __init__(self):\n        MyClass._instance_count += 1\n    \n    @classmethod\n    def get_count(cls):\n        return cls._instance_count\n    \n    @staticmethod\n    def utility():\n        return "I do not need self or cls"\n    \n    @property\n    def info(self):\n        return "Property decorator"\n\nprint(MyClass.get_count())  # 0\nobj = MyClass()\nprint(MyClass.get_count())  # 1`, language: 'python' }
    ]
  },
  {
    id: 'week23', day: 155, tier: 'intermediate', title: 'The Generator', subtitle: 'Lazy Evaluation',
    icon: 'infinite', color: '#2563EB', unlocked: true, estimatedTime: '50 min',
    sections: [
      { title: 'Generator Functions', content: `Generators yield values one at a time, saving memory.`, code: `def count_up_to(n):\n    i = 1\n    while i <= n:\n        yield i\n        i += 1\n\nfor num in count_up_to(5):\n    print(num)  # 1, 2, 3, 4, 5\n\n# Memory efficient for large datasets\ndef read_large_file(file_path):\n    with open(file_path) as f:\n        for line in f:\n            yield line.strip()`, language: 'python' },
      { title: 'Generator Expressions', content: `Like list comprehensions, but lazy.`, code: `# List comprehension - creates all at once\nsquares_list = [x**2 for x in range(1000000)]\n\n# Generator expression - creates on demand\nsquares_gen = (x**2 for x in range(1000000))\n\nprint(next(squares_gen))  # 0\nprint(next(squares_gen))  # 1\nprint(sum(squares_gen))   # Sum of remaining`, language: 'python' }
    ]
  },
  {
    id: 'week24', day: 162, tier: 'intermediate', title: 'The Context', subtitle: 'Context Managers',
    icon: 'enter', color: '#8B5CF6', unlocked: true, estimatedTime: '45 min',
    sections: [
      { title: 'The With Statement', content: `Context managers handle setup and cleanup automatically.`, code: `# File handling\nwith open("file.txt", "w") as f:\n    f.write("Hello")  # File closed automatically\n\n# Database connection\n# with db.connection() as conn:\n#     conn.execute("...")\n\n# Lock handling\nfrom threading import Lock\nlock = Lock()\nwith lock:\n    # Critical section\n    pass`, language: 'python' },
      { title: 'Custom Context Managers', content: `Create your own using __enter__ and __exit__.`, code: `class Timer:\n    def __enter__(self):\n        import time\n        self.start = time.time()\n        return self\n    \n    def __exit__(self, *args):\n        import time\n        self.elapsed = time.time() - self.start\n        print(f"Elapsed: {self.elapsed:.4f}s")\n\nwith Timer():\n    sum(range(1000000))  # Elapsed: 0.XXXXs`, language: 'python' }
    ]
  },
  // ═══════════════════════════════════════════════════════════════════════════
  // MONTH 7-8: DEPTH (Weeks 25-32)
  // ═══════════════════════════════════════════════════════════════════════════
  {
    id: 'week25', day: 169, tier: 'advanced', title: 'The Algorithm I', subtitle: 'Big O Notation',
    icon: 'analytics', color: '#F59E0B', unlocked: true, estimatedTime: '70 min',
    sections: [
      { title: 'Understanding Big O', content: `Big O describes how performance scales with input size.\n\nO(1) - Constant\nO(log n) - Logarithmic\nO(n) - Linear\nO(n log n) - Linearithmic\nO(n²) - Quadratic`, code: `# O(1) - Constant\ndef get_first(arr):\n    return arr[0]\n\n# O(n) - Linear\ndef find_max(arr):\n    max_val = arr[0]\n    for num in arr:\n        if num > max_val:\n            max_val = num\n    return max_val\n\n# O(n²) - Quadratic\ndef has_duplicate_slow(arr):\n    for i in range(len(arr)):\n        for j in range(i+1, len(arr)):\n            if arr[i] == arr[j]:\n                return True\n    return False`, language: 'python' },
      { title: 'Space Complexity', content: `Memory usage also matters.`, code: `# O(1) space - constant extra memory\ndef sum_array(arr):\n    total = 0\n    for num in arr:\n        total += num\n    return total\n\n# O(n) space - creates new array\ndef double_array(arr):\n    return [x * 2 for x in arr]`, language: 'python' }
    ]
  },
  {
    id: 'week26', day: 176, tier: 'advanced', title: 'The Algorithm II', subtitle: 'Searching',
    icon: 'search', color: '#EC4899', unlocked: true, estimatedTime: '60 min',
    sections: [
      { title: 'Linear Search', content: `Check each element one by one. O(n) time.`, code: `def linear_search(arr, target):\n    for i, val in enumerate(arr):\n        if val == target:\n            return i\n    return -1\n\narr = [4, 2, 7, 1, 9, 3]\nprint(linear_search(arr, 7))  # 2`, language: 'python' },
      { title: 'Binary Search', content: `For sorted arrays, halve the search space each step. O(log n) time.`, code: `def binary_search(arr, target):\n    left, right = 0, len(arr) - 1\n    \n    while left <= right:\n        mid = (left + right) // 2\n        if arr[mid] == target:\n            return mid\n        elif arr[mid] < target:\n            left = mid + 1\n        else:\n            right = mid - 1\n    return -1\n\narr = [1, 2, 3, 4, 5, 6, 7, 8, 9]\nprint(binary_search(arr, 7))  # 6`, language: 'python' }
    ]
  },
  {
    id: 'week27', day: 183, tier: 'advanced', title: 'The Algorithm III', subtitle: 'Sorting',
    icon: 'swap-vertical', color: '#3B82F6', unlocked: true, estimatedTime: '75 min',
    sections: [
      { title: 'Bubble Sort', content: `Simple but slow. O(n²) time.`, code: `def bubble_sort(arr):\n    n = len(arr)\n    for i in range(n):\n        for j in range(0, n-i-1):\n            if arr[j] > arr[j+1]:\n                arr[j], arr[j+1] = arr[j+1], arr[j]\n    return arr\n\narr = [64, 34, 25, 12, 22, 11, 90]\nprint(bubble_sort(arr))`, language: 'python' },
      { title: 'Quick Sort', content: `Efficient divide-and-conquer. O(n log n) average.`, code: `def quick_sort(arr):\n    if len(arr) <= 1:\n        return arr\n    \n    pivot = arr[len(arr) // 2]\n    left = [x for x in arr if x < pivot]\n    middle = [x for x in arr if x == pivot]\n    right = [x for x in arr if x > pivot]\n    \n    return quick_sort(left) + middle + quick_sort(right)\n\narr = [3, 6, 8, 10, 1, 2, 1]\nprint(quick_sort(arr))`, language: 'python' },
      { title: 'Merge Sort', content: `Stable O(n log n) sorting.`, code: `def merge_sort(arr):\n    if len(arr) <= 1:\n        return arr\n    \n    mid = len(arr) // 2\n    left = merge_sort(arr[:mid])\n    right = merge_sort(arr[mid:])\n    \n    return merge(left, right)\n\ndef merge(left, right):\n    result = []\n    i = j = 0\n    while i < len(left) and j < len(right):\n        if left[i] <= right[j]:\n            result.append(left[i])\n            i += 1\n        else:\n            result.append(right[j])\n            j += 1\n    result.extend(left[i:])\n    result.extend(right[j:])\n    return result`, language: 'python' }
    ]
  },
  {
    id: 'week28', day: 190, tier: 'advanced', title: 'The Pattern I', subtitle: 'Two Pointers',
    icon: 'git-compare', color: '#6366F1', unlocked: true, estimatedTime: '55 min',
    sections: [
      { title: 'Two Pointer Technique', content: `Use two pointers to solve problems efficiently.`, code: `# Palindrome check\ndef is_palindrome(s):\n    s = s.lower().replace(" ", "")\n    left, right = 0, len(s) - 1\n    while left < right:\n        if s[left] != s[right]:\n            return False\n        left += 1\n        right -= 1\n    return True\n\nprint(is_palindrome("A man a plan a canal Panama"))  # True`, language: 'python' },
      { title: 'Two Sum (Sorted)', content: `Find two numbers that add to target.`, code: `def two_sum_sorted(nums, target):\n    left, right = 0, len(nums) - 1\n    while left < right:\n        current = nums[left] + nums[right]\n        if current == target:\n            return [left, right]\n        elif current < target:\n            left += 1\n        else:\n            right -= 1\n    return []\n\nprint(two_sum_sorted([1, 2, 3, 4, 6], 6))  # [1, 3]`, language: 'python' }
    ]
  },
  {
    id: 'week29', day: 197, tier: 'advanced', title: 'The Pattern II', subtitle: 'Sliding Window',
    icon: 'browsers', color: '#F97316', unlocked: true, estimatedTime: '60 min',
    sections: [
      { title: 'Fixed Window', content: `Window of fixed size sliding through data.`, code: `def max_sum_subarray(arr, k):\n    if len(arr) < k:\n        return None\n    \n    # Calculate first window\n    window_sum = sum(arr[:k])\n    max_sum = window_sum\n    \n    # Slide the window\n    for i in range(k, len(arr)):\n        window_sum += arr[i] - arr[i-k]\n        max_sum = max(max_sum, window_sum)\n    \n    return max_sum\n\narr = [1, 4, 2, 10, 2, 3, 1, 0, 20]\nprint(max_sum_subarray(arr, 4))  # 24`, language: 'python' },
      { title: 'Dynamic Window', content: `Window that expands and contracts.`, code: `def longest_unique_substring(s):\n    char_set = set()\n    left = 0\n    max_length = 0\n    \n    for right in range(len(s)):\n        while s[right] in char_set:\n            char_set.remove(s[left])\n            left += 1\n        char_set.add(s[right])\n        max_length = max(max_length, right - left + 1)\n    \n    return max_length\n\nprint(longest_unique_substring("abcabcbb"))  # 3`, language: 'python' }
    ]
  },
  {
    id: 'week30', day: 204, tier: 'advanced', title: 'The Pattern III', subtitle: 'Hash Map',
    icon: 'key', color: '#2563EB', unlocked: true, estimatedTime: '55 min',
    sections: [
      { title: 'Two Sum (Unsorted)', content: `Classic interview problem using hash map.`, code: `def two_sum(nums, target):\n    seen = {}  # value -> index\n    \n    for i, num in enumerate(nums):\n        complement = target - num\n        if complement in seen:\n            return [seen[complement], i]\n        seen[num] = i\n    \n    return []\n\nprint(two_sum([2, 7, 11, 15], 9))  # [0, 1]`, language: 'python' },
      { title: 'Group Anagrams', content: `Group words by their sorted characters.`, code: `def group_anagrams(words):\n    groups = {}\n    \n    for word in words:\n        key = "".join(sorted(word))\n        if key not in groups:\n            groups[key] = []\n        groups[key].append(word)\n    \n    return list(groups.values())\n\nwords = ["eat", "tea", "tan", "ate", "nat", "bat"]\nprint(group_anagrams(words))\n# [['eat', 'tea', 'ate'], ['tan', 'nat'], ['bat']]`, language: 'python' }
    ]
  },
  {
    id: 'week31', day: 211, tier: 'advanced', title: 'The Recursion', subtitle: 'Self-Reference',
    icon: 'sync', color: '#8B5CF6', unlocked: true, estimatedTime: '65 min',
    sections: [
      { title: 'Understanding Recursion', content: `A function that calls itself to solve smaller subproblems.`, code: `def factorial(n):\n    # Base case\n    if n <= 1:\n        return 1\n    # Recursive case\n    return n * factorial(n - 1)\n\nprint(factorial(5))  # 120\n\ndef fibonacci(n):\n    if n <= 1:\n        return n\n    return fibonacci(n-1) + fibonacci(n-2)\n\nprint(fibonacci(10))  # 55`, language: 'python' },
      { title: 'Memoization', content: `Cache results to avoid redundant calculations.`, code: `def fibonacci_memo(n, memo={}):\n    if n in memo:\n        return memo[n]\n    if n <= 1:\n        return n\n    \n    memo[n] = fibonacci_memo(n-1, memo) + fibonacci_memo(n-2, memo)\n    return memo[n]\n\nprint(fibonacci_memo(50))  # Fast now!\n\n# Using functools\nfrom functools import lru_cache\n\n@lru_cache(maxsize=None)\ndef fib(n):\n    if n <= 1:\n        return n\n    return fib(n-1) + fib(n-2)`, language: 'python' }
    ]
  },
  {
    id: 'week32', day: 218, tier: 'advanced', title: 'The Data Structure', subtitle: 'Stacks & Queues',
    icon: 'layers', color: '#EC4899', unlocked: true, estimatedTime: '55 min',
    sections: [
      { title: 'Stacks (LIFO)', content: `Last In, First Out - like a stack of plates.`, code: `# Using list as stack\nstack = []\nstack.append(1)  # Push\nstack.append(2)\nstack.append(3)\nprint(stack.pop())  # 3 (Pop)\nprint(stack[-1])    # 2 (Peek)\n\n# Valid parentheses\ndef is_valid(s):\n    stack = []\n    mapping = {")": "(", "}": "{", "]": "["}\n    \n    for char in s:\n        if char in mapping:\n            if not stack or stack.pop() != mapping[char]:\n                return False\n        else:\n            stack.append(char)\n    \n    return len(stack) == 0\n\nprint(is_valid("()[]{}"))  # True`, language: 'python' },
      { title: 'Queues (FIFO)', content: `First In, First Out - like a line of people.`, code: `from collections import deque\n\nqueue = deque()\nqueue.append(1)    # Enqueue\nqueue.append(2)\nqueue.append(3)\nprint(queue.popleft())  # 1 (Dequeue)\nprint(queue[0])         # 2 (Peek)\n\n# BFS uses a queue\ndef bfs(graph, start):\n    visited = set()\n    queue = deque([start])\n    \n    while queue:\n        node = queue.popleft()\n        if node not in visited:\n            visited.add(node)\n            print(node)\n            queue.extend(graph.get(node, []))`, language: 'python' }
    ]
  },
  // ═══════════════════════════════════════════════════════════════════════════
  // MONTH 9-10: MASTERY (Weeks 33-40)
  // ═══════════════════════════════════════════════════════════════════════════
  {
    id: 'week33', day: 225, tier: 'advanced', title: 'The Tree', subtitle: 'Binary Trees',
    icon: 'git-branch', color: '#3B82F6', unlocked: true, estimatedTime: '70 min',
    sections: [
      { title: 'Binary Tree Basics', content: `Trees are hierarchical data structures with nodes and children.`, code: `class TreeNode:\n    def __init__(self, val):\n        self.val = val\n        self.left = None\n        self.right = None\n\n# Create a tree\n#       1\n#      / \\\n#     2   3\n#    / \\\n#   4   5\n\nroot = TreeNode(1)\nroot.left = TreeNode(2)\nroot.right = TreeNode(3)\nroot.left.left = TreeNode(4)\nroot.left.right = TreeNode(5)`, language: 'python' },
      { title: 'Tree Traversals', content: `Different ways to visit all nodes.`, code: `def inorder(node):\n    if node:\n        inorder(node.left)\n        print(node.val)\n        inorder(node.right)\n\ndef preorder(node):\n    if node:\n        print(node.val)\n        preorder(node.left)\n        preorder(node.right)\n\ndef postorder(node):\n    if node:\n        postorder(node.left)\n        postorder(node.right)\n        print(node.val)`, language: 'python' }
    ]
  },
  {
    id: 'week34', day: 232, tier: 'expert', title: 'The Graph', subtitle: 'Networks',
    icon: 'git-network', color: '#6366F1', unlocked: true, estimatedTime: '75 min',
    sections: [
      { title: 'Graph Representation', content: `Graphs model relationships between objects.`, code: `# Adjacency List\ngraph = {\n    'A': ['B', 'C'],\n    'B': ['A', 'D', 'E'],\n    'C': ['A', 'F'],\n    'D': ['B'],\n    'E': ['B', 'F'],\n    'F': ['C', 'E']\n}\n\nprint(graph['A'])  # ['B', 'C']`, language: 'python' },
      { title: 'DFS and BFS', content: `Two fundamental graph traversal algorithms.`, code: `def dfs(graph, start, visited=None):\n    if visited is None:\n        visited = set()\n    \n    visited.add(start)\n    print(start)\n    \n    for neighbor in graph[start]:\n        if neighbor not in visited:\n            dfs(graph, neighbor, visited)\n\ndef bfs(graph, start):\n    visited = {start}\n    queue = [start]\n    \n    while queue:\n        node = queue.pop(0)\n        print(node)\n        for neighbor in graph[node]:\n            if neighbor not in visited:\n                visited.add(neighbor)\n                queue.append(neighbor)`, language: 'python' }
    ]
  },
  {
    id: 'week35', day: 239, tier: 'expert', title: 'The Async', subtitle: 'Concurrent Programming',
    icon: 'flash', color: '#F97316', unlocked: true, estimatedTime: '80 min',
    sections: [
      { title: 'Async/Await', content: `Non-blocking code for I/O operations.`, code: `import asyncio\n\nasync def fetch_data(url, delay):\n    print(f"Fetching {url}...")\n    await asyncio.sleep(delay)\n    print(f"Got {url}")\n    return f"Data from {url}"\n\nasync def main():\n    # Run concurrently\n    results = await asyncio.gather(\n        fetch_data("api/users", 2),\n        fetch_data("api/posts", 2),\n    )\n    print(results)\n\n# asyncio.run(main())`, language: 'python' },
      { title: 'JavaScript Async', content: `Promises and async/await in JavaScript.`, code: `async function fetchUser(id) {\n  const response = await fetch(\`/api/users/\${id}\`);\n  const data = await response.json();\n  return data;\n}\n\nasync function main() {\n  try {\n    const [users, posts] = await Promise.all([\n      fetch('/api/users').then(r => r.json()),\n      fetch('/api/posts').then(r => r.json())\n    ]);\n    console.log(users, posts);\n  } catch (err) {\n    console.error(err);\n  }\n}`, language: 'javascript' }
    ]
  },
  {
    id: 'week36', day: 246, tier: 'expert', title: 'The Testing', subtitle: 'Quality Assurance',
    icon: 'checkmark-done', color: '#2563EB', unlocked: true, estimatedTime: '60 min',
    sections: [
      { title: 'Unit Testing', content: `Test individual components in isolation.`, code: `import unittest\n\ndef add(a, b):\n    return a + b\n\nclass TestAdd(unittest.TestCase):\n    def test_positive(self):\n        self.assertEqual(add(2, 3), 5)\n    \n    def test_negative(self):\n        self.assertEqual(add(-1, -1), -2)\n    \n    def test_zero(self):\n        self.assertEqual(add(0, 0), 0)\n\nif __name__ == '__main__':\n    unittest.main()`, language: 'python' },
      { title: 'Test-Driven Development', content: `Write tests first, then implementation.`, code: `# 1. Write a failing test\ndef test_is_palindrome():\n    assert is_palindrome("racecar") == True\n    assert is_palindrome("hello") == False\n\n# 2. Write minimal code to pass\ndef is_palindrome(s):\n    return s == s[::-1]\n\n# 3. Refactor while tests pass\ndef is_palindrome(s):\n    s = s.lower().replace(" ", "")\n    return s == s[::-1]`, language: 'python' }
    ]
  },
  {
    id: 'week37', day: 253, tier: 'expert', title: 'The API', subtitle: 'Web Services',
    icon: 'cloud', color: '#8B5CF6', unlocked: true, estimatedTime: '70 min',
    sections: [
      { title: 'Making HTTP Requests', content: `Interact with web APIs using requests.`, code: `import requests\n\n# GET request\nresponse = requests.get('https://api.github.com/users/octocat')\nprint(response.status_code)  # 200\nprint(response.json()['name'])  # The Octocat\n\n# POST request\ndata = {'key': 'value'}\nresponse = requests.post('https://httpbin.org/post', json=data)\nprint(response.json())`, language: 'python' },
      { title: 'Building APIs', content: `Create your own REST API with Flask.`, code: `from flask import Flask, jsonify, request\n\napp = Flask(__name__)\ntasks = []\n\n@app.route('/tasks', methods=['GET'])\ndef get_tasks():\n    return jsonify(tasks)\n\n@app.route('/tasks', methods=['POST'])\ndef add_task():\n    task = request.json\n    tasks.append(task)\n    return jsonify(task), 201\n\nif __name__ == '__main__':\n    app.run(debug=True)`, language: 'python' }
    ]
  },
  {
    id: 'week38', day: 260, tier: 'expert', title: 'The Database', subtitle: 'Data Persistence',
    icon: 'server', color: '#EC4899', unlocked: true, estimatedTime: '65 min',
    sections: [
      { title: 'SQL Basics', content: `Structured Query Language for databases.`, code: `import sqlite3\n\n# Connect and create table\nconn = sqlite3.connect('example.db')\nc = conn.cursor()\n\nc.execute('''CREATE TABLE IF NOT EXISTS users\n             (id INTEGER PRIMARY KEY, name TEXT, age INTEGER)''')\n\n# Insert data\nc.execute("INSERT INTO users (name, age) VALUES (?, ?)", ('Alice', 30))\nconn.commit()\n\n# Query data\nc.execute("SELECT * FROM users WHERE age > ?", (25,))\nprint(c.fetchall())\n\nconn.close()`, language: 'python' },
      { title: 'NoSQL with MongoDB', content: `Document-based databases.`, code: `from pymongo import MongoClient\n\nclient = MongoClient('mongodb://localhost:27017/')\ndb = client['mydb']\nusers = db['users']\n\n# Insert\nusers.insert_one({'name': 'Alice', 'age': 30})\n\n# Find\nfor user in users.find({'age': {'$gt': 25}}):\n    print(user)\n\n# Update\nusers.update_one({'name': 'Alice'}, {'$set': {'age': 31}})`, language: 'python' }
    ]
  },
  {
    id: 'week39', day: 267, tier: 'expert', title: 'The Security', subtitle: 'Safe Code',
    icon: 'shield-checkmark', color: '#F59E0B', unlocked: true, estimatedTime: '55 min',
    sections: [
      { title: 'Input Validation', content: `Never trust user input.`, code: `# BAD - SQL Injection vulnerable\nquery = f"SELECT * FROM users WHERE name = '{user_input}'"\n\n# GOOD - Parameterized query\nc.execute("SELECT * FROM users WHERE name = ?", (user_input,))\n\n# Validate and sanitize\ndef validate_email(email):\n    import re\n    pattern = r'^[\\w.-]+@[\\w.-]+\\.\\w+$'\n    if not re.match(pattern, email):\n        raise ValueError("Invalid email")\n    return email`, language: 'python' },
      { title: 'Password Hashing', content: `Never store passwords in plain text.`, code: "import hashlib\nimport secrets\n\ndef hash_password(password):\n    salt = secrets.token_hex(16)\n    hash_obj = hashlib.pbkdf2_hmac(\n        'sha256',\n        password.encode(),\n        salt.encode(),\n        100000\n    )\n    return f\"{salt}${hash_obj.hex()}\"\n\ndef verify_password(password, stored):\n    salt, hash_val = stored.split('$')\n    hash_obj = hashlib.pbkdf2_hmac(\n        'sha256',\n        password.encode(),\n        salt.encode(),\n        100000\n    )\n    return hash_obj.hex() == hash_val", language: 'python' }
    ]
  },
  {
    id: 'week40', day: 274, tier: 'expert', title: 'The Performance', subtitle: 'Optimization',
    icon: 'speedometer', color: '#3B82F6', unlocked: true, estimatedTime: '60 min',
    sections: [
      { title: 'Profiling', content: `Find bottlenecks before optimizing.`, code: `import cProfile\nimport time\n\ndef slow_function():\n    total = 0\n    for i in range(1000000):\n        total += i\n    return total\n\n# Profile the function\ncProfile.run('slow_function()')\n\n# Time it\nstart = time.time()\nresult = slow_function()\nend = time.time()\nprint(f"Took {end - start:.4f}s")`, language: 'python' },
      { title: 'Common Optimizations', content: `Simple changes that make big differences.`, code: `# Use sets for membership testing\n# BAD - O(n) lookup\nif item in big_list:\n\n# GOOD - O(1) lookup\nbig_set = set(big_list)\nif item in big_set:\n\n# Use generators for large data\n# BAD - loads all into memory\ndata = [process(x) for x in huge_list]\n\n# GOOD - processes one at a time\ndata = (process(x) for x in huge_list)\n\n# Use built-in functions\n# BAD\ntotal = 0\nfor x in nums:\n    total += x\n\n# GOOD\ntotal = sum(nums)`, language: 'python' }
    ]
  },
  // ═══════════════════════════════════════════════════════════════════════════
  // MONTH 11-12: TRANSCENDENCE (Weeks 41-52)
  // ═══════════════════════════════════════════════════════════════════════════
  {
    id: 'week41', day: 281, tier: 'expert', title: 'The Pattern: Singleton', subtitle: 'One Instance',
    icon: 'person', color: '#6366F1', unlocked: true, estimatedTime: '45 min',
    sections: [
      { title: 'Singleton Pattern', content: `Ensure a class has only one instance.`, code: `class Database:\n    _instance = None\n    \n    def __new__(cls):\n        if cls._instance is None:\n            cls._instance = super().__new__(cls)\n            cls._instance.connection = "Connected"\n        return cls._instance\n\ndb1 = Database()\ndb2 = Database()\nprint(db1 is db2)  # True`, language: 'python' }
    ]
  },
  {
    id: 'week42', day: 288, tier: 'expert', title: 'The Pattern: Factory', subtitle: 'Object Creation',
    icon: 'build', color: '#F97316', unlocked: true, estimatedTime: '50 min',
    sections: [
      { title: 'Factory Pattern', content: `Create objects without specifying exact classes.`, code: `class Animal:\n    def speak(self): pass\n\nclass Dog(Animal):\n    def speak(self): return "Woof!"\n\nclass Cat(Animal):\n    def speak(self): return "Meow!"\n\nclass AnimalFactory:\n    @staticmethod\n    def create(animal_type):\n        animals = {"dog": Dog, "cat": Cat}\n        return animals.get(animal_type.lower(), Dog)()\n\npet = AnimalFactory.create("cat")\nprint(pet.speak())  # Meow!`, language: 'python' }
    ]
  },
  {
    id: 'week43', day: 295, tier: 'expert', title: 'The Pattern: Observer', subtitle: 'Event Handling',
    icon: 'eye', color: '#2563EB', unlocked: true, estimatedTime: '55 min',
    sections: [
      { title: 'Observer Pattern', content: `Objects subscribe to events and get notified.`, code: `class EventEmitter:\n    def __init__(self):\n        self._listeners = {}\n    \n    def on(self, event, callback):\n        if event not in self._listeners:\n            self._listeners[event] = []\n        self._listeners[event].append(callback)\n    \n    def emit(self, event, data=None):\n        for cb in self._listeners.get(event, []):\n            cb(data)\n\nemitter = EventEmitter()\nemitter.on("login", lambda u: print(f"{u} logged in"))\nemitter.emit("login", "Alice")`, language: 'python' }
    ]
  },
  {
    id: 'week44', day: 302, tier: 'expert', title: 'The Pattern: Strategy', subtitle: 'Interchangeable Algorithms',
    icon: 'options', color: '#8B5CF6', unlocked: true, estimatedTime: '50 min',
    sections: [
      { title: 'Strategy Pattern', content: `Define a family of algorithms and make them interchangeable.`, code: "class PaymentStrategy:\n    def pay(self, amount): pass\n\nclass CreditCard(PaymentStrategy):\n    def pay(self, amount):\n        return f\"Paid ${amount} with credit card\"\n\nclass PayPal(PaymentStrategy):\n    def pay(self, amount):\n        return f\"Paid ${amount} via PayPal\"\n\nclass Cart:\n    def __init__(self):\n        self.strategy = None\n    \n    def checkout(self, amount):\n        return self.strategy.pay(amount)\n\ncart = Cart()\ncart.strategy = PayPal()\nprint(cart.checkout(100))", language: 'python' }
    ]
  },
  {
    id: 'week45', day: 309, tier: 'expert', title: 'The Pattern: Decorator', subtitle: 'Wrapping Behavior',
    icon: 'color-wand', color: '#EC4899', unlocked: true, estimatedTime: '45 min',
    sections: [
      { title: 'Decorator Pattern', content: `Add behavior to objects dynamically.`, code: `class Coffee:\n    def cost(self):\n        return 5\n\nclass MilkDecorator:\n    def __init__(self, coffee):\n        self._coffee = coffee\n    \n    def cost(self):\n        return self._coffee.cost() + 2\n\nclass SugarDecorator:\n    def __init__(self, coffee):\n        self._coffee = coffee\n    \n    def cost(self):\n        return self._coffee.cost() + 1\n\ncoffee = Coffee()\ncoffee = MilkDecorator(coffee)\ncoffee = SugarDecorator(coffee)\nprint(coffee.cost())  # 8`, language: 'python' }
    ]
  },
  {
    id: 'week46', day: 316, tier: 'godtier', title: 'SOLID: Single Responsibility', subtitle: 'One Job',
    icon: 'cube', color: '#FFD700', unlocked: true, estimatedTime: '40 min',
    sections: [
      { title: 'Single Responsibility Principle', content: `A class should have only one reason to change.`, code: `# BAD - Multiple responsibilities\nclass User:\n    def __init__(self, name):\n        self.name = name\n    \n    def save_to_db(self):  # Persistence\n        pass\n    \n    def send_email(self):  # Communication\n        pass\n\n# GOOD - Separated concerns\nclass User:\n    def __init__(self, name):\n        self.name = name\n\nclass UserRepository:\n    def save(self, user):\n        pass\n\nclass EmailService:\n    def send(self, user, message):\n        pass`, language: 'python' }
    ]
  },
  {
    id: 'week47', day: 323, tier: 'godtier', title: 'SOLID: Open/Closed', subtitle: 'Extend, Not Modify',
    icon: 'lock-open', color: '#FFD700', unlocked: true, estimatedTime: '45 min',
    sections: [
      { title: 'Open/Closed Principle', content: `Open for extension, closed for modification.`, code: `# BAD - Must modify to add new shape\nclass AreaCalculator:\n    def calculate(self, shape):\n        if shape.type == "circle":\n            return 3.14 * shape.radius ** 2\n        elif shape.type == "rectangle":\n            return shape.width * shape.height\n\n# GOOD - Extend without modifying\nclass Shape:\n    def area(self): pass\n\nclass Circle(Shape):\n    def __init__(self, radius):\n        self.radius = radius\n    def area(self):\n        return 3.14 * self.radius ** 2\n\nclass Rectangle(Shape):\n    def __init__(self, w, h):\n        self.w, self.h = w, h\n    def area(self):\n        return self.w * self.h`, language: 'python' }
    ]
  },
  {
    id: 'week48', day: 330, tier: 'godtier', title: 'SOLID: Liskov Substitution', subtitle: 'Substitutability',
    icon: 'swap-horizontal', color: '#FFD700', unlocked: true, estimatedTime: '50 min',
    sections: [
      { title: 'Liskov Substitution Principle', content: `Subtypes must be substitutable for their base types.`, code: `# BAD - Square violates LSP\nclass Rectangle:\n    def set_width(self, w): self.width = w\n    def set_height(self, h): self.height = h\n\nclass Square(Rectangle):  # Square is not a Rectangle!\n    def set_width(self, w):\n        self.width = self.height = w\n    def set_height(self, h):\n        self.width = self.height = h\n\n# GOOD - Separate abstractions\nclass Shape:\n    def area(self): pass\n\nclass Rectangle(Shape):\n    def __init__(self, w, h):\n        self.w, self.h = w, h\n    def area(self):\n        return self.w * self.h\n\nclass Square(Shape):\n    def __init__(self, side):\n        self.side = side\n    def area(self):\n        return self.side ** 2`, language: 'python' }
    ]
  },
  {
    id: 'week49', day: 337, tier: 'godtier', title: 'SOLID: Interface Segregation', subtitle: 'Specific Interfaces',
    icon: 'cut', color: '#FFD700', unlocked: true, estimatedTime: '45 min',
    sections: [
      { title: 'Interface Segregation Principle', content: `Many specific interfaces are better than one general interface.`, code: `# BAD - Fat interface\nclass Worker:\n    def work(self): pass\n    def eat(self): pass\n    def sleep(self): pass\n\nclass Robot(Worker):  # Robots do not eat or sleep!\n    def work(self): print("Working")\n    def eat(self): pass  # Forced to implement\n    def sleep(self): pass\n\n# GOOD - Segregated interfaces\nclass Workable:\n    def work(self): pass\n\nclass Eatable:\n    def eat(self): pass\n\nclass Human(Workable, Eatable):\n    def work(self): print("Working")\n    def eat(self): print("Eating")\n\nclass Robot(Workable):\n    def work(self): print("Working")`, language: 'python' }
    ]
  },
  {
    id: 'week50', day: 344, tier: 'godtier', title: 'SOLID: Dependency Inversion', subtitle: 'Depend on Abstractions',
    icon: 'git-pull-request', color: '#FFD700', unlocked: true, estimatedTime: '50 min',
    sections: [
      { title: 'Dependency Inversion Principle', content: `Depend on abstractions, not concretions.`, code: `# BAD - High-level depends on low-level\nclass MySQLDatabase:\n    def save(self, data): pass\n\nclass UserService:\n    def __init__(self):\n        self.db = MySQLDatabase()  # Tight coupling!\n\n# GOOD - Both depend on abstraction\nclass Database:  # Abstraction\n    def save(self, data): pass\n\nclass MySQLDatabase(Database):\n    def save(self, data): print("MySQL save")\n\nclass PostgresDatabase(Database):\n    def save(self, data): print("Postgres save")\n\nclass UserService:\n    def __init__(self, db: Database):  # Inject dependency\n        self.db = db\n\nservice = UserService(PostgresDatabase())`, language: 'python' }
    ]
  },
  {
    id: 'week51', day: 351, tier: 'godtier', title: 'Clean Code', subtitle: 'The Art of Readable Code',
    icon: 'sparkles', color: '#FFD700', unlocked: true, estimatedTime: '60 min',
    sections: [
      { title: 'Clean Code Principles', content: `1. Names reveal intent\n2. Functions do one thing\n3. Comments explain WHY, not WHAT\n4. Handle errors gracefully\n5. Write tests first (TDD)\n6. Refactor continuously\n7. Keep it simple (KISS)\n8. Do not repeat yourself (DRY)\n9. You are not gonna need it (YAGNI)\n10. Leave code better than you found it`, code: `# BAD\ndef calc(a, b, t):\n    if t == 1: return a + b\n    elif t == 2: return a - b\n\n# GOOD\ndef add(first: int, second: int) -> int:\n    """Add two numbers."""\n    return first + second\n\ndef subtract(first: int, second: int) -> int:\n    """Subtract second from first."""\n    return first - second`, language: 'python', tips: ['Code is read more than written', 'Optimize for readability', 'Refactor ruthlessly'] }
    ]
  },
  {
    id: 'week52', day: 365, tier: 'godtier', title: 'The Mastery', subtitle: 'Your Journey Complete',
    icon: 'trophy', color: '#FFD700', unlocked: true, estimatedTime: '∞',
    sections: [
      { title: 'What You Have Learned', content: `Congratulations. You have traveled an incredible journey:\n\n• Fundamentals: Variables, Types, Control Flow\n• Data Structures: Lists, Dicts, Sets, Trees, Graphs\n• Functions and OOP\n• Error Handling and File I/O\n• Algorithms and Complexity\n• Design Patterns\n• SOLID Principles\n• Clean Code\n\nYou are no longer a beginner. You are a developer.`, tips: ['The journey never ends', 'Keep learning, keep building', 'Teach others to master'] },
      { title: 'The Mindset', content: `Technical skills got you here. These principles will take you further:\n\n• Read more code than you write\n• Teach others to deepen your understanding\n• Embrace failure as feedback\n• Build projects that solve real problems\n• Contribute to open source\n• Stay curious - technologies change\n• Code is communication - write for humans\n• Simple is better than complex\n• Done is better than perfect\n\n"First, solve the problem. Then, write the code." - John Johnson` },
      { title: 'Welcome to Godtier', content: `You have completed the 52-week journey.\n\nBut remember - mastery is not a destination. It is a lifelong pursuit.\n\nThe field evolves constantly. New languages emerge. New frameworks appear. New paradigms develop.\n\nKeep building.\nKeep learning.\nKeep growing.\n\n🏆 Welcome to Godtier. 🏆` }
    ]
  }
];

export const getTierColor = (tier: string): string => {
  const colors: Record<string, string> = {
    beginner: '#22C55E',
    foundation: '#3B82F6',
    intermediate: '#8B5CF6',
    advanced: '#F59E0B',
    expert: '#EC4899',
    godtier: '#FFD700',
  };
  return colors[tier] || '#6366F1';
};

export const getBibleStats = (completedChapters: Record<string, boolean>) => {
  const completedCount = Object.values(completedChapters).filter(Boolean).length;
  const totalChapters = CODING_BIBLE.length;
  const percentage = Math.round((completedCount / totalChapters) * 100);
  return { completedCount, totalChapters, percentage };
};

export default CODING_BIBLE;
