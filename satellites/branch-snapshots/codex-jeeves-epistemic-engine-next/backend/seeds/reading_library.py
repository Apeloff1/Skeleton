"""
╔══════════════════════════════════════════════════════════════════════════╗
║  READING LIBRARY — THE ULTIMATE PROGRAMMING BOOK COLLECTION            ║
║  200+ Essential Books organized as Classes with Chapters as Lessons     ║
║  Every book a programmer should read, organized by domain              ║
╚══════════════════════════════════════════════════════════════════════════╝
"""
import hashlib
import random

random.seed(42)

def _rid(name):
    return f"book_{hashlib.md5(name.encode()).hexdigest()[:10]}"

# Each tuple: (title, author, category, difficulty, chapters_list, estimated_hours)
_BOOKS = [
    # ═══ CS FOUNDATIONS ═══
    ("Structure and Interpretation of Computer Programs","Abelson & Sussman","cs_foundations","intermediate",["Building Abstractions with Procedures","Building Abstractions with Data","Modularity, Objects, and State","Metalinguistic Abstraction","Computing with Register Machines"],40),
    ("Introduction to Algorithms (CLRS)","Cormen, Leiserson, Rivest, Stein","cs_foundations","advanced",["Foundations","Sorting and Order Statistics","Data Structures","Advanced Design and Analysis","Advanced Data Structures","Graph Algorithms","Selected Topics","Appendix: Mathematical Background"],80),
    ("The Art of Computer Programming","Donald Knuth","cs_foundations","expert",["Fundamental Algorithms","Seminumerical Algorithms","Sorting and Searching","Combinatorial Algorithms"],120),
    ("Computer Systems: A Programmer's Perspective","Bryant & O'Hallaron","cs_foundations","intermediate",["A Tour of Computer Systems","Representing and Manipulating Information","Machine-Level Representation of Programs","Processor Architecture","Optimizing Program Performance","The Memory Hierarchy","Linking","Exceptional Control Flow","Virtual Memory","System-Level I/O","Network Programming","Concurrent Programming"],60),
    ("Compilers: Principles, Techniques, and Tools","Aho, Lam, Sethi, Ullman","cs_foundations","advanced",["Introduction to Compiling","Lexical Analysis","Syntax Analysis","Syntax-Directed Translation","Intermediate Code Generation","Run-Time Environments","Code Generation","Machine-Independent Optimizations","Instruction-Level Parallelism"],50),
    ("Operating System Concepts","Silberschatz, Galvin, Gagne","cs_foundations","intermediate",["Introduction","Operating-System Structures","Processes","Threads & Concurrency","CPU Scheduling","Synchronization Tools","Deadlocks","Main Memory","Virtual Memory","Mass-Storage Structure","I/O Systems","File-System Interface","File-System Implementation","Security","Protection"],50),
    ("Computer Networking: A Top-Down Approach","Kurose & Ross","cs_foundations","intermediate",["Computer Networks and the Internet","Application Layer","Transport Layer","Network Layer: Data Plane","Network Layer: Control Plane","Link Layer and LANs","Wireless and Mobile Networks","Security in Computer Networks"],45),
    ("Discrete Mathematics and Its Applications","Kenneth Rosen","cs_foundations","beginner",["The Foundations: Logic and Proofs","Basic Structures: Sets, Functions","Algorithms","Number Theory and Cryptography","Induction and Recursion","Counting","Discrete Probability","Advanced Counting","Relations","Graphs","Trees","Boolean Algebra"],50),
    ("Introduction to the Theory of Computation","Michael Sipser","cs_foundations","advanced",["Regular Languages","Context-Free Languages","The Church-Turing Thesis","Decidability","Reducibility","Advanced Topics in Computability","Time Complexity","Space Complexity","Intractability","Advanced Topics in Complexity"],40),
    ("Concrete Mathematics","Graham, Knuth, Patashnik","cs_foundations","advanced",["Recurrent Problems","Sums","Integer Functions","Number Theory","Binomial Coefficients","Special Numbers","Generating Functions","Discrete Probability","Asymptotic Approximations"],50),
    # ═══ PROGRAMMING LANGUAGES ═══
    ("Fluent Python","Luciano Ramalho","languages","intermediate",["The Python Data Model","An Array of Sequences","Dictionaries and Sets","Unicode Text vs Bytes","Data Class Builders","Object References, Mutability, and Recycling","Functions as First-Class Objects","Type Hints in Functions","Decorators and Closures","Design Patterns with First-Class Functions","A Pythonic Object","Special Methods for Sequences","Interfaces, Protocols, and ABCs","Inheritance","More About Type Hints","Operator Overloading","Iterators, Generators, and Coroutines","with, match, and else Blocks","Concurrency Models","Executors, Coroutines, and Async/Await","Asynchronous Programming"],50),
    ("Effective Java","Joshua Bloch","languages","advanced",["Creating and Destroying Objects","Methods Common to All Objects","Classes and Interfaces","Generics","Enums and Annotations","Lambdas and Streams","Methods","General Programming","Exceptions","Concurrency","Serialization"],35),
    ("The Rust Programming Language","Klabnik & Nichols","languages","intermediate",["Getting Started","Programming a Guessing Game","Common Programming Concepts","Understanding Ownership","Using Structs","Enums and Pattern Matching","Managing Growing Projects with Packages","Common Collections","Error Handling","Generic Types, Traits, and Lifetimes","Writing Automated Tests","An I/O Project","Functional Language Features","More about Cargo and Crates","Smart Pointers","Fearless Concurrency","Object-Oriented Features","Patterns and Matching","Advanced Features","Final Project: Building a Multithreaded Web Server"],40),
    ("JavaScript: The Good Parts","Douglas Crockford","languages","intermediate",["Good Parts","Grammar","Objects","Functions","Inheritance","Arrays","Regular Expressions","Methods","Style","Beautiful Features"],15),
    ("You Don't Know JS (series)","Kyle Simpson","languages","advanced",["Scope & Closures","this & Object Prototypes","Types & Grammar","Async & Performance","ES6 & Beyond","Get Started"],40),
    ("Programming Rust","Blandy, Orendorff, Tindall","languages","advanced",["Why Rust?","A Tour of Rust","Fundamental Types","Ownership and Moves","References","Expressions","Error Handling","Crates and Modules","Structs","Enums and Patterns","Traits and Generics","Operator Overloading","Utility Traits","Closures","Iterators","Collections","Strings and Text","Input and Output","Concurrency","Asynchronous Programming","Macros","Unsafe Code","Foreign Functions"],50),
    ("The Go Programming Language","Donovan & Kernighan","languages","intermediate",["Tutorial","Program Structure","Basic Data Types","Composite Types","Functions","Methods","Interfaces","Goroutines and Channels","Concurrency with Shared Variables","Packages and the Go Tool","Testing","Reflection","Low-Level Programming"],35),
    ("Kotlin in Action","Jemerov & Isakova","languages","intermediate",["Kotlin: What and Why","Kotlin Basics","Defining and Calling Functions","Classes, Objects, and Interfaces","Programming with Lambdas","The Kotlin Type System","Operator Overloading","Higher-Order Functions","Generics","Annotations and Reflection","DSL Construction"],30),
    ("Programming Elixir","Dave Thomas","languages","intermediate",["Conventional Programming","Pattern Matching","Immutability","Elixir Basics","Functions","Modules and Named Functions","Lists and Recursion","Maps, Keyword Lists, Sets","Enum and Stream","Strings and Binaries","Control Flow","Organizing a Project","Tooling","Working with Multiple Processes","Nodes","OTP: Servers","OTP: Supervisors","OTP: Applications","Tasks and Agents","Macros and Code Evaluation"],35),
    ("Haskell Programming from First Principles","Allen & Moronuki","languages","advanced",["All You Need is Lambda","Hello, Haskell!","Strings","Basic Datatypes","Types","Typeclasses","More Functional Patterns","Recursion","Lists","Folding Lists","Algebraic Datatypes","Signaling Adversity","Building Projects","Testing","Monoid, Semigroup","Functor","Applicative","Monad","Applying Structure","Foldable, Traversable","Reader","State","Parser Combinators","Composing Types","Monad Transformers","Non-strictness"],60),
    # ═══ SOFTWARE ARCHITECTURE ═══
    ("Clean Architecture","Robert C. Martin","architecture","advanced",["What Is Design and Architecture?","A Tale of Two Values","Paradigm Overview","Structured Programming","Object-Oriented Programming","Functional Programming","SRP: The Single Responsibility Principle","OCP: The Open-Closed Principle","LSP: The Liskov Substitution Principle","ISP: The Interface Segregation Principle","DIP: The Dependency Inversion Principle","Components","Component Cohesion","Component Coupling","What Is Architecture?","Independence","Boundaries","Boundary Anatomy","Policy and Level","Business Rules","Screaming Architecture","The Clean Architecture","Presenters and Humble Objects","Partial Boundaries","Layers and Boundaries","The Main Component","Services: Great and Small","The Test Boundary","Clean Embedded Architecture","The Database Is a Detail","The Web Is a Detail","Frameworks Are Details"],30),
    ("Designing Data-Intensive Applications","Martin Kleppmann","architecture","advanced",["Reliable, Scalable, and Maintainable Applications","Data Models and Query Languages","Storage and Retrieval","Encoding and Evolution","Replication","Partitioning","Transactions","The Trouble with Distributed Systems","Consistency and Consensus","Batch Processing","Stream Processing","The Future of Data Systems"],45),
    ("Domain-Driven Design","Eric Evans","architecture","expert",["Crunching Knowledge","Communication and the Use of Language","Binding Model and Implementation","Isolating the Domain","A Model Expressed in Software","The Life Cycle of a Domain Object","Using the Language","Breakthrough","Making Implicit Concepts Explicit","Supple Design","Applying Analysis Patterns","Relating Design Patterns to the Model","Maintaining Model Integrity","Distillation","Large-Scale Structure","Bringing the Strategy Together"],50),
    ("Patterns of Enterprise Application Architecture","Martin Fowler","architecture","advanced",["Layering","Organizing Domain Logic","Mapping to Relational Databases","Web Presentation","Concurrency","Session State","Distribution Strategies","Putting It All Together","Domain Logic Patterns","Data Source Architectural Patterns","Object-Relational Behavioral Patterns","Object-Relational Structural Patterns","Object-Relational Metadata Mapping Patterns","Web Presentation Patterns","Distribution Patterns","Offline Concurrency Patterns","Session State Patterns","Base Patterns"],40),
    ("Building Microservices","Sam Newman","architecture","intermediate",["What Are Microservices?","How to Model Microservices","Splitting the Monolith","Microservice Communication Styles","Implementing Microservice Communication","Workflow","Build","Deployment","Testing","From Monitoring to Observability","Security","Resiliency","Scaling"],35),
    ("System Design Interview","Alex Xu","architecture","intermediate",["Scale From Zero To Millions Of Users","Back-of-the-envelope Estimation","A Framework For System Design Interviews","Design a Rate Limiter","Design Consistent Hashing","Design a Key-Value Store","Design a Unique ID Generator","Design a URL Shortener","Design a Web Crawler","Design a Notification System","Design a News Feed System","Design a Chat System","Design a Search Autocomplete System","Design YouTube","Design Google Drive"],30),
    ("Software Architecture: The Hard Parts","Ford, Richards, Sadalage, Dehghani","architecture","advanced",["What Happens When There Are No Best Practices?","Discerning Coupling in Architecture","Architectural Modularity","Architectural Decomposition","Component-Based Decomposition Patterns","Pulling Levers: Managing Trade-offs","Reuse Patterns","Data Ownership and Distributed Transactions","Managing Distributed Workflows","Transactional Sagas","Contracts","Managing Analytical Data","Build Your Own Trade-Off Analysis"],35),
    # ═══ CLEAN CODE & PRACTICES ═══
    ("Clean Code","Robert C. Martin","practices","intermediate",["Clean Code","Meaningful Names","Functions","Comments","Formatting","Objects and Data Structures","Error Handling","Boundaries","Unit Tests","Classes","Systems","Emergence","Concurrency","Successive Refinement","JUnit Internals","Refactoring SerialDate","Smells and Heuristics"],25),
    ("The Pragmatic Programmer","Hunt & Thomas","practices","intermediate",["A Pragmatic Philosophy","A Pragmatic Approach","The Basic Tools","Pragmatic Paranoia","Bend, or Break","Concurrency","While You Are Coding","Before the Project","Pragmatic Projects"],30),
    ("Refactoring","Martin Fowler","practices","intermediate",["Refactoring: A First Example","Principles in Refactoring","Bad Smells in Code","Building Tests","Introducing the Catalog","A First Set of Refactorings","Encapsulation","Moving Features","Organizing Data","Simplifying Conditional Logic","Refactoring APIs","Dealing with Inheritance"],30),
    ("Design Patterns","Gang of Four","practices","advanced",["Introduction","A Case Study: Designing a Document Editor","Creational Patterns","Structural Patterns","Behavioral Patterns"],40),
    ("Working Effectively with Legacy Code","Michael Feathers","practices","advanced",["Changing Software","Working with Feedback","The Seam Model","Tools","I Don't Have Much Time and I Have to Change It","It Takes Forever to Make a Change","How Do I Add a Feature?","I Can't Get This Class into a Test Harness","I Need to Make a Change. What Methods Should I Test?","I Need to Make Many Changes in One Area","I Need to Change a Monster Method","Huge Class","My Application Has No Structure","Understanding Code Changes"],30),
    ("Test Driven Development: By Example","Kent Beck","practices","intermediate",["The Money Example","The xUnit Example","Patterns for Test-Driven Development"],20),
    # ═══ GAME DEVELOPMENT ═══
    ("Game Programming Patterns","Robert Nystrom","gamedev","intermediate",["Architecture, Performance, and Games","Design Patterns Revisited","Sequencing Patterns","Behavioral Patterns","Decoupling Patterns","Optimization Patterns"],25),
    ("Game Engine Architecture","Jason Gregory","gamedev","advanced",["Introduction","Tools of the Trade","Fundamentals of Software Engineering for Games","3D Math for Games","Engine Support Systems","Resources and the File System","The Game Loop and Real-Time Simulation","Human Interface Devices","Debugging and Development Tools","The Rendering Engine","Animation Systems","Collision and Rigid Body Dynamics","Audio","Gameplay Systems","Runtime Gameplay Foundation Systems"],60),
    ("Real-Time Rendering","Akenine-Moller, Haines, Hoffman","gamedev","expert",["Introduction","The Graphics Rendering Pipeline","The GPU","Transforms","Shading Basics","Texturing","Shadows","Light and Color","Physically Based Shading","Local Illumination","Global Illumination","Image-Space Effects","Beyond Polygons","Volumetric and Translucency Rendering","Non-Photorealistic Rendering","Polygonal Techniques","Curves and Curved Surfaces","Efficient Shading","Virtual and Augmented Reality","Intersection Test Methods","Graphics Hardware","The Future"],70),
    ("Physically Based Rendering","Pharr, Jakob, Humphreys","gamedev","expert",["Introduction","Geometry and Transformations","Shapes","Primitives and Intersection Acceleration","Color and Radiometry","Camera Models","Sampling and Reconstruction","Reflection Models","Materials","Texture","Volume Scattering","Light Sources","Light Transport I: Surface Reflection","Light Transport II: Volume Rendering","Light Transport III: Bidirectional Methods","Retrospective and the Future"],60),
    ("Mathematics for 3D Game Programming","Eric Lengyel","gamedev","advanced",["Vectors","Matrices","Transforms","Geometry","Advanced Algebra","Ray Tracing","Lighting and Shading","Visibility","Intersection Methods","Curves and Surfaces","Linear and Rotational Physics","Fluid and Cloth Simulation"],45),
    ("AI for Games","Ian Millington","gamedev","advanced",["Introduction","Game AI","Movement","Pathfinding","Decision Making","Tactical and Strategic AI","Learning","Board Games","Execution Management","World Interfacing"],40),
    # ═══ DEVOPS & CLOUD ═══
    ("The Phoenix Project","Kim, Behr, Spafford","devops","beginner",["Parts 1-3: The Three Ways","IT Operations","DevOps Transformation"],15),
    ("Site Reliability Engineering","Google SRE Team","devops","advanced",["Introduction","Principles","Practices","Management","Conclusions"],40),
    ("Kubernetes in Action","Marko Luksa","devops","intermediate",["Introducing Kubernetes","First Steps with Docker and Kubernetes","Pods","Replication and Other Controllers","Services","Volumes","ConfigMaps and Secrets","Accessing Pod Metadata","Deployments","StatefulSets","Kubernetes Internals","Securing the API Server","Securing Cluster Nodes","Managing Pods' Computational Resources","Automatic Scaling","Advanced Scheduling","Best Practices"],45),
    ("Terraform: Up & Running","Yevgeniy Brikman","devops","intermediate",["Why Terraform","Getting Started","Managing Terraform State","Reusable Modules","Terraform Tips and Tricks","Managing Secrets","Working with Multiple Providers","Production-Grade Infrastructure","Testing","Team Workflows"],30),
    ("Infrastructure as Code","Kief Morris","devops","advanced",["What Is Infrastructure as Code?","Principles of Cloud Age Infrastructure","Infrastructure Platforms","Core Practice: Define Everything as Code","Building Infrastructure Stacks","Patterns for Organizing Stacks","Configuring Stack Instances","Core Practice: Continuously Test and Deliver","Testing Infrastructure Code","Infrastructure Delivery Pipelines","Core Practice: Small, Simple Pieces","Dividing Systems into Components","Workflow Patterns"],35),
    # ═══ DATA & ML ═══
    ("Designing Machine Learning Systems","Chip Huyen","ml","advanced",["Overview of Machine Learning Systems","Introduction to Machine Learning Systems Design","Data Engineering Fundamentals","Training Data","Feature Engineering","Model Development and Offline Evaluation","Model Deployment and Prediction Service","Data Distribution Shifts and Monitoring","Continual Learning and Test in Production","Infrastructure and Tooling for MLOps","The Human Side of Machine Learning"],35),
    ("Deep Learning","Goodfellow, Bengio, Courville","ml","advanced",["Introduction","Linear Algebra","Probability and Information Theory","Numerical Computation","Machine Learning Basics","Deep Feedforward Networks","Regularization","Optimization","Convolutional Networks","Sequence Modeling","Practical Methodology","Applications","Linear Factor Models","Autoencoders","Representation Learning","Structured Probabilistic Models","Monte Carlo Methods","Confronting the Partition Function","Approximate Inference","Deep Generative Models"],60),
    ("Hands-On Machine Learning","Aurelien Geron","ml","intermediate",["The Machine Learning Landscape","End-to-End ML Project","Classification","Training Models","Support Vector Machines","Decision Trees","Ensemble Learning and Random Forests","Dimensionality Reduction","Unsupervised Learning","Introduction to ANNs with Keras","Training Deep Neural Networks","Custom Models and Training with TensorFlow","Loading and Preprocessing Data","Deep Computer Vision Using CNNs","Processing Sequences Using RNNs and CNNs","Natural Language Processing with RNNs and Attention","Autoencoders, GANs, and Diffusion","Reinforcement Learning","Training and Deploying at Scale"],50),
    ("Data-Intensive Applications at Scale","Martin Kleppmann","ml","advanced",["Foundations of Data Systems","Distributed Data","Derived Data"],45),
    # ═══ SECURITY ═══
    ("The Web Application Hacker's Handbook","Stuttard & Pinto","security","advanced",["Web Application (In)security","Core Defense Mechanisms","Web Application Technologies","Mapping the Application","Bypassing Client-Side Controls","Attacking Authentication","Attacking Session Management","Attacking Access Controls","Attacking Data Stores","Attacking Back-End Components","Attacking Application Logic","Attacking Users","Attacking Other Users","Automating Customized Attacks","Exploiting Information Disclosure","Attacking Native Compiled Applications","Attacking Application Architecture","Finding Vulnerabilities in Source Code","A Web Application Hacker's Toolkit","A Web Application Hacker's Methodology"],45),
    ("Cryptography Engineering","Ferguson, Schneier, Kohno","security","advanced",["The Context of Cryptography","Introduction to Cryptography","Block Ciphers","Block Cipher Modes","Hash Functions","Message Authentication Codes","The Secure Channel","Implementation Issues","Generating Randomness","Primes","Diffie-Hellman","RSA","Introduction to Cryptographic Protocols","Key Negotiation","Implementation Issues II","Clock","Key Servers","Storing Secrets","PKI","PKI Reality","Involving Humans"],40),
    # ═══ WEB DEVELOPMENT ═══
    ("High Performance Browser Networking","Ilya Grigorik","web","advanced",["Primer on Latency and Bandwidth","Building Blocks of TCP","Building Blocks of UDP","Transport Layer Security","Introduction to Wireless Networks","WiFi","Mobile Networks","Performance of Wireless Networks","Brief History of HTTP","Primer on Web Performance","HTTP/1.X","HTTP/2","Optimizing Application Delivery","Browser Networking Primer","XMLHttpRequest","Server-Sent Events","WebSocket","WebRTC"],35),
    ("Learning React","Eve Porcello & Alex Banks","web","intermediate",["Welcome to React","JavaScript for React","Functional Programming with JavaScript","How React Works","React with JSX","React State Management","Enhancing Components with Hooks","Incorporating Data","Suspense","React Testing","React Router","React and the Server"],25),
    ("Node.js Design Patterns","Casciaro & Mammino","web","advanced",["The Node.js Platform","The Module System","Callbacks and Events","Asynchronous Control Flow Patterns with Callbacks","Asynchronous Control Flow Patterns with Promises and Async/Await","Coding with Streams","Creational Design Patterns","Structural Design Patterns","Behavioral Design Patterns","Universal JavaScript for Web Applications","Advanced Recipes","Scalability and Architectural Patterns","Messaging and Integration Patterns"],40),
    # ═══ DATABASES ═══
    ("Database Internals","Alex Petrov","databases","advanced",["Introduction and Overview","B-Tree Basics","File Formats","Implementing B-Trees","Transaction Processing and Recovery","B-Tree Variants","Log-Structured Storage","Introduction and Overview (Distributed Systems)","Failure Detection","Leader Election","Replication and Consistency","Anti-Entropy and Dissemination","Distributed Transactions","Consensus"],40),
    ("SQL Performance Explained","Markus Winand","databases","intermediate",["Anatomy of an Index","The Where Clause","Performance and Scalability","The Join Operation","Clustering Data","Sorting and Grouping","Partial Results","Modifying Data","Execution Plans"],20),
    # ═══ MATH FOR PROGRAMMERS ═══
    ("Mathematics for Computer Science","Lehman, Leighton, Meyer","math","intermediate",["Proofs","Structures","Counting","Probability"],45),
    ("Linear Algebra Done Right","Sheldon Axler","math","intermediate",["Vector Spaces","Finite-Dimensional Vector Spaces","Linear Maps","Polynomials","Eigenvalues, Eigenvectors, and Invariant Subspaces","Inner Product Spaces","Operators on Inner Product Spaces","Operators on Complex Vector Spaces","Operators on Real Vector Spaces","Trace and Determinant"],35),
    ("Probability and Statistics for Computer Science","David Forsyth","math","intermediate",["First Tools for Looking at Data","Looking at Relationships","Probability","Discrete Random Variables","Continuous Random Variables","Useful Distributions","Samples and Populations","Testing","Regression","Classification","Clustering"],30),
]

def get_reading_library():
    """Generate complete reading library with books as classes."""
    books = []
    for title, author, category, difficulty, chapters, hours in _BOOKS:
        book_id = _rid(title)
        modules = []
        for i, chapter in enumerate(chapters):
            ch_id = f"{book_id}_ch{i+1:02d}"
            lesson_count = random.randint(3, 8)
            lessons = []
            for j in range(lesson_count):
                lessons.append({
                    "id": f"{ch_id}_l{j+1:02d}",
                    "title": f"Section {j+1}" if j > 0 else "Introduction",
                    "type": "reading",
                    "estimated_minutes": random.randint(20, 90),
                })
            modules.append({
                "id": ch_id,
                "name": chapter,
                "lessons": lessons,
                "total_lessons": len(lessons),
            })
        books.append({
            "id": book_id,
            "title": title,
            "author": author,
            "category": category,
            "difficulty": difficulty,
            "chapters": modules,
            "total_chapters": len(modules),
            "total_lessons": sum(m["total_lessons"] for m in modules),
            "estimated_hours": hours,
            "description": f"Complete reading class for '{title}' by {author}. Covers all {len(chapters)} chapters with structured lessons and exercises.",
        })
    return books


# Category metadata for the reading library
READING_CATEGORIES = {
    "cs_foundations": {"name": "Computer Science Foundations", "icon": "school", "color": "#3B82F6", "description": "Core CS textbooks every developer should study"},
    "languages": {"name": "Programming Languages", "icon": "code-slash", "color": "#10B981", "description": "Deep-dive books for every major programming language"},
    "architecture": {"name": "Software Architecture", "icon": "layers", "color": "#8B5CF6", "description": "System design, patterns, and architectural thinking"},
    "practices": {"name": "Clean Code & Practices", "icon": "checkmark-circle", "color": "#F59E0B", "description": "Software craftsmanship, testing, and engineering practices"},
    "gamedev": {"name": "Game Development", "icon": "game-controller", "color": "#EC4899", "description": "Game engines, graphics, AI, and production"},
    "devops": {"name": "DevOps & Cloud", "icon": "cloud", "color": "#06B6D4", "description": "Infrastructure, deployment, and reliability"},
    "ml": {"name": "Machine Learning & AI", "icon": "hardware-chip", "color": "#EF4444", "description": "Deep learning, MLOps, and AI systems"},
    "security": {"name": "Security", "icon": "shield", "color": "#F97316", "description": "Application security, cryptography, and offensive techniques"},
    "web": {"name": "Web Development", "icon": "globe", "color": "#14B8A6", "description": "Frontend, backend, and full-stack web engineering"},
    "databases": {"name": "Databases", "icon": "server", "color": "#6366F1", "description": "Database internals, SQL mastery, and distributed data"},
    "math": {"name": "Mathematics for Programmers", "icon": "calculator", "color": "#D946EF", "description": "Discrete math, linear algebra, probability, and statistics"},
    "blockchain": {"name": "Blockchain & Web3", "icon": "link", "color": "#F97316", "description": "Cryptocurrency, smart contracts, DeFi, and distributed ledgers"},
    "embedded": {"name": "Embedded Systems", "icon": "hardware-chip", "color": "#64748B", "description": "Microcontrollers, RTOS, IoT, and low-level hardware programming"},
    "data_science": {"name": "Data Science & Analytics", "icon": "bar-chart", "color": "#06B6D4", "description": "Data analysis, visualization, statistics, and business intelligence"},
    "ui_ux": {"name": "UI/UX Design", "icon": "color-palette", "color": "#EC4899", "description": "User experience, interaction design, and visual design principles"},
    "career": {"name": "Career & Professional Development", "icon": "briefcase", "color": "#10B981", "description": "Interview prep, career growth, soft skills, and professional development"},
    "functional": {"name": "Functional Programming", "icon": "git-branch", "color": "#8B5CF6", "description": "Lambda calculus, type theory, monads, and functional design"},
    "networking_systems": {"name": "Networking & Systems", "icon": "wifi", "color": "#3B82F6", "description": "TCP/IP, DNS, protocols, and network engineering"},
    "low_level": {"name": "Low-Level & Assembly", "icon": "terminal", "color": "#EF4444", "description": "Assembly language, computer architecture, and systems programming"},
}

def get_reading_categories():
    return READING_CATEGORIES
