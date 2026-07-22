"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                ADVANCED CS CLASSES - EXPANDED CURRICULUM                      ║
║                                                                               ║
║  New Courses:                                                                 ║
║  • Operating Systems                                                          ║
║  • Computer Networks                                                          ║
║  • Compiler Design                                                            ║
║  • Game Development Fundamentals                                              ║
║  • Game Engine Architecture                                                   ║
║  • Graphics Programming                                                       ║
║  • Game AI & Physics                                                          ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from typing import Dict, List, Any

# ============================================================================
# OPERATING SYSTEMS - COMPLETE COURSE
# ============================================================================

OPERATING_SYSTEMS_COURSE = {
    "id": "os_complete",
    "code": "CS 301",
    "title": "Operating Systems",
    "subtitle": "Design and Implementation of Modern OS",
    "credits": 4,
    "hours": 75,
    "weeks": 15,
    "level": "advanced",
    "prerequisites": ["Data Structures", "Computer Architecture", "C Programming"],
    "description": """Deep dive into operating system internals. Learn how operating systems
manage hardware resources, provide abstractions for processes and memory, and enable
concurrent execution. Includes hands-on kernel programming projects.""",
    
    "learning_objectives": [
        "Understand the role and structure of operating systems",
        "Implement process management and scheduling algorithms",
        "Design memory management systems including virtual memory",
        "Develop file systems and I/O management",
        "Implement synchronization primitives and handle deadlocks",
        "Write kernel-level code in C",
        "Understand security and protection mechanisms"
    ],
    
    "weeks_summary": [
        {"week": 1, "title": "OS Overview", "topics": ["OS History", "System Calls", "OS Structure", "Kernel vs User Mode"]},
        {"week": 2, "title": "Processes", "topics": ["Process Concept", "Process States", "PCB", "Context Switching"]},
        {"week": 3, "title": "Threads", "topics": ["Thread Models", "User vs Kernel Threads", "Pthreads", "Thread Pools"]},
        {"week": 4, "title": "CPU Scheduling", "topics": ["FCFS", "SJF", "Priority", "Round Robin", "Multilevel Queues"]},
        {"week": 5, "title": "Synchronization I", "topics": ["Critical Section", "Peterson's Solution", "Semaphores", "Monitors"]},
        {"week": 6, "title": "Synchronization II", "topics": ["Classic Problems", "Producer-Consumer", "Readers-Writers", "Dining Philosophers"]},
        {"week": 7, "title": "Deadlocks", "topics": ["Deadlock Conditions", "Prevention", "Avoidance", "Detection", "Recovery"]},
        {"week": 8, "title": "Memory Management I", "topics": ["Address Binding", "Logical vs Physical", "Paging", "Page Tables"]},
        {"week": 9, "title": "Memory Management II", "topics": ["Segmentation", "Virtual Memory", "Demand Paging", "Page Replacement"]},
        {"week": 10, "title": "Storage Management", "topics": ["Disk Structure", "Disk Scheduling", "RAID", "SSD"]},
        {"week": 11, "title": "File Systems I", "topics": ["File Concept", "Directory Structure", "File System Implementation"]},
        {"week": 12, "title": "File Systems II", "topics": ["Allocation Methods", "Free Space Management", "Journaling", "VFS"]},
        {"week": 13, "title": "I/O Systems", "topics": ["I/O Hardware", "I/O Subsystem", "Device Drivers", "DMA"]},
        {"week": 14, "title": "Security", "topics": ["Security Goals", "Authentication", "Access Control", "Security Attacks"]},
        {"week": 15, "title": "Advanced Topics", "topics": ["Distributed Systems", "Virtualization", "Containers", "Modern OS"]}
    ],
    
    "projects": [
        {"name": "Shell Implementation", "description": "Build a Unix-like shell", "difficulty": "medium"},
        {"name": "Thread Library", "description": "Implement user-level threads", "difficulty": "hard"},
        {"name": "Memory Allocator", "description": "Build malloc/free", "difficulty": "hard"},
        {"name": "Mini File System", "description": "Implement a simple file system", "difficulty": "expert"}
    ],
    
    "code_examples": [
        {
            "title": "Process Fork Example",
            "language": "c",
            "code": '''#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <sys/wait.h>

int main() {
    pid_t pid;
    int status;
    
    printf("Parent process: PID = %d\\n", getpid());
    
    pid = fork();  // Create child process
    
    if (pid < 0) {
        // Fork failed
        perror("Fork failed");
        exit(1);
    }
    else if (pid == 0) {
        // Child process
        printf("Child process: PID = %d, Parent PID = %d\\n", 
               getpid(), getppid());
        
        // Execute another program
        execlp("/bin/ls", "ls", "-la", NULL);
        
        // Only reached if exec fails
        perror("Exec failed");
        exit(1);
    }
    else {
        // Parent process
        printf("Parent: Created child with PID = %d\\n", pid);
        
        // Wait for child to complete
        waitpid(pid, &status, 0);
        
        if (WIFEXITED(status)) {
            printf("Child exited with status %d\\n", 
                   WEXITSTATUS(status));
        }
    }
    
    return 0;
}'''
        },
        {
            "title": "Semaphore Producer-Consumer",
            "language": "c",
            "code": '''#include <stdio.h>
#include <pthread.h>
#include <semaphore.h>
#include <unistd.h>

#define BUFFER_SIZE 5

int buffer[BUFFER_SIZE];
int in = 0, out = 0;

sem_t empty;  // Counts empty slots
sem_t full;   // Counts full slots
pthread_mutex_t mutex;

void* producer(void* arg) {
    int item = 0;
    while (1) {
        item++;
        
        sem_wait(&empty);  // Wait for empty slot
        pthread_mutex_lock(&mutex);
        
        buffer[in] = item;
        printf("Producer: Produced %d at position %d\\n", item, in);
        in = (in + 1) % BUFFER_SIZE;
        
        pthread_mutex_unlock(&mutex);
        sem_post(&full);  // Signal that buffer has item
        
        sleep(1);
    }
    return NULL;
}

void* consumer(void* arg) {
    int item;
    while (1) {
        sem_wait(&full);  // Wait for item
        pthread_mutex_lock(&mutex);
        
        item = buffer[out];
        printf("Consumer: Consumed %d from position %d\\n", item, out);
        out = (out + 1) % BUFFER_SIZE;
        
        pthread_mutex_unlock(&mutex);
        sem_post(&empty);  // Signal empty slot
        
        sleep(2);
    }
    return NULL;
}

int main() {
    pthread_t prod_thread, cons_thread;
    
    sem_init(&empty, 0, BUFFER_SIZE);
    sem_init(&full, 0, 0);
    pthread_mutex_init(&mutex, NULL);
    
    pthread_create(&prod_thread, NULL, producer, NULL);
    pthread_create(&cons_thread, NULL, consumer, NULL);
    
    pthread_join(prod_thread, NULL);
    pthread_join(cons_thread, NULL);
    
    return 0;
}'''
        }
    ]
}

# ============================================================================
# COMPUTER NETWORKS - COMPLETE COURSE
# ============================================================================

COMPUTER_NETWORKS_COURSE = {
    "id": "networks_complete",
    "code": "CS 302",
    "title": "Computer Networks",
    "subtitle": "Protocols, Architecture, and Implementation",
    "credits": 4,
    "hours": 75,
    "weeks": 15,
    "level": "advanced",
    "prerequisites": ["Operating Systems", "Data Structures"],
    "description": """Comprehensive study of computer networking from physical layer to
application layer. Learn TCP/IP protocols, network programming, security, and
build real networking applications.""",
    
    "learning_objectives": [
        "Understand the OSI and TCP/IP network models",
        "Implement socket programming for network applications",
        "Analyze and design network protocols",
        "Configure and troubleshoot networks",
        "Understand network security fundamentals",
        "Build distributed applications"
    ],
    
    "weeks_summary": [
        {"week": 1, "title": "Network Fundamentals", "topics": ["Internet Architecture", "Protocol Layers", "OSI vs TCP/IP"]},
        {"week": 2, "title": "Application Layer I", "topics": ["HTTP", "DNS", "Email Protocols", "P2P"]},
        {"week": 3, "title": "Application Layer II", "topics": ["Socket Programming", "Client-Server", "APIs"]},
        {"week": 4, "title": "Transport Layer I", "topics": ["UDP", "TCP Basics", "Reliable Data Transfer"]},
        {"week": 5, "title": "Transport Layer II", "topics": ["TCP Congestion Control", "Flow Control", "Connection Management"]},
        {"week": 6, "title": "Network Layer I", "topics": ["IP Addressing", "Subnetting", "CIDR", "NAT"]},
        {"week": 7, "title": "Network Layer II", "topics": ["Routing Algorithms", "OSPF", "BGP", "SDN"]},
        {"week": 8, "title": "Data Link Layer", "topics": ["Error Detection", "Multiple Access", "Ethernet", "Switches"]},
        {"week": 9, "title": "Wireless Networks", "topics": ["WiFi", "Cellular", "Mobility", "IoT"]},
        {"week": 10, "title": "Network Security I", "topics": ["Cryptography Basics", "TLS/SSL", "Authentication"]},
        {"week": 11, "title": "Network Security II", "topics": ["Firewalls", "IDS/IPS", "VPN", "Network Attacks"]},
        {"week": 12, "title": "Network Programming", "topics": ["TCP Sockets", "UDP Sockets", "Select/Poll", "Async I/O"]},
        {"week": 13, "title": "Web Technologies", "topics": ["REST APIs", "WebSockets", "gRPC", "GraphQL"]},
        {"week": 14, "title": "Cloud Networking", "topics": ["Load Balancing", "CDN", "Microservices", "Service Mesh"]},
        {"week": 15, "title": "Advanced Topics", "topics": ["5G", "Edge Computing", "Network Automation"]}
    ],
    
    "code_examples": [
        {
            "title": "TCP Server and Client",
            "language": "python",
            "code": '''import socket
import threading

# TCP Server
class TCPServer:
    def __init__(self, host='localhost', port=8888):
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    def handle_client(self, client_socket, address):
        """Handle individual client connection"""
        print(f"[+] Connection from {address}")
        
        try:
            while True:
                data = client_socket.recv(1024)
                if not data:
                    break
                
                message = data.decode('utf-8')
                print(f"[{address}] Received: {message}")
                
                # Echo back with acknowledgment
                response = f"Server received: {message}"
                client_socket.send(response.encode('utf-8'))
        
        except Exception as e:
            print(f"[-] Error handling {address}: {e}")
        
        finally:
            client_socket.close()
            print(f"[-] Connection closed: {address}")
    
    def start(self):
        """Start the server"""
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        print(f"[*] Server listening on {self.host}:{self.port}")
        
        try:
            while True:
                client_socket, address = self.server_socket.accept()
                
                # Handle each client in a new thread
                client_thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_socket, address)
                )
                client_thread.start()
        
        except KeyboardInterrupt:
            print("\\n[*] Server shutting down")
        
        finally:
            self.server_socket.close()


# TCP Client
class TCPClient:
    def __init__(self, host='localhost', port=8888):
        self.host = host
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    def connect(self):
        """Connect to server"""
        self.socket.connect((self.host, self.port))
        print(f"[+] Connected to {self.host}:{self.port}")
    
    def send(self, message):
        """Send message and receive response"""
        self.socket.send(message.encode('utf-8'))
        response = self.socket.recv(1024).decode('utf-8')
        return response
    
    def close(self):
        """Close connection"""
        self.socket.close()


# Usage example
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "server":
        server = TCPServer()
        server.start()
    else:
        client = TCPClient()
        client.connect()
        
        try:
            while True:
                message = input("Enter message: ")
                if message.lower() == 'quit':
                    break
                
                response = client.send(message)
                print(f"Server response: {response}")
        
        finally:
            client.close()'''
        }
    ]
}

# ============================================================================
# COMPILER DESIGN - COMPLETE COURSE
# ============================================================================

COMPILER_DESIGN_COURSE = {
    "id": "compilers_complete",
    "code": "CS 303",
    "title": "Compiler Design",
    "subtitle": "Building Programming Language Implementations",
    "credits": 4,
    "hours": 75,
    "weeks": 15,
    "level": "expert",
    "prerequisites": ["Data Structures", "Theory of Computation", "Assembly Language"],
    "description": """Learn to design and implement compilers and interpreters. Covers
lexical analysis, parsing, semantic analysis, optimization, and code generation.
Build a complete compiler for a programming language.""",
    
    "learning_objectives": [
        "Design and implement lexical analyzers",
        "Build parsers using various techniques",
        "Perform semantic analysis and type checking",
        "Generate intermediate representations",
        "Apply optimization techniques",
        "Generate target machine code",
        "Build a complete compiler from scratch"
    ],
    
    "weeks_summary": [
        {"week": 1, "title": "Introduction", "topics": ["Compiler Structure", "Phases", "Passes", "Front-end vs Back-end"]},
        {"week": 2, "title": "Lexical Analysis I", "topics": ["Regular Expressions", "Finite Automata", "DFA/NFA"]},
        {"week": 3, "title": "Lexical Analysis II", "topics": ["Lexer Implementation", "Token Generation", "Error Handling"]},
        {"week": 4, "title": "Syntax Analysis I", "topics": ["Context-Free Grammars", "Parse Trees", "Ambiguity"]},
        {"week": 5, "title": "Syntax Analysis II", "topics": ["Top-Down Parsing", "LL(1)", "Recursive Descent"]},
        {"week": 6, "title": "Syntax Analysis III", "topics": ["Bottom-Up Parsing", "LR(0)", "SLR", "LALR"]},
        {"week": 7, "title": "Semantic Analysis", "topics": ["Symbol Tables", "Type Systems", "Type Checking"]},
        {"week": 8, "title": "Intermediate Code", "topics": ["Three-Address Code", "SSA Form", "Control Flow Graphs"]},
        {"week": 9, "title": "Runtime Environments", "topics": ["Stack Frames", "Heap Management", "Garbage Collection"]},
        {"week": 10, "title": "Optimization I", "topics": ["Local Optimization", "Peephole", "Constant Folding"]},
        {"week": 11, "title": "Optimization II", "topics": ["Global Optimization", "Data Flow Analysis", "Loop Optimization"]},
        {"week": 12, "title": "Code Generation", "topics": ["Instruction Selection", "Register Allocation", "Instruction Scheduling"]},
        {"week": 13, "title": "Advanced Topics", "topics": ["JIT Compilation", "Garbage Collection", "Parallel Compilation"]},
        {"week": 14, "title": "Interpreter Design", "topics": ["Tree-Walking", "Bytecode", "Virtual Machines"]},
        {"week": 15, "title": "Final Project", "topics": ["Complete Compiler Implementation"]}
    ],
    
    "code_examples": [
        {
            "title": "Simple Lexer Implementation",
            "language": "python",
            "code": '''from enum import Enum, auto
from dataclasses import dataclass
from typing import List, Optional
import re

class TokenType(Enum):
    # Literals
    INTEGER = auto()
    FLOAT = auto()
    STRING = auto()
    IDENTIFIER = auto()
    
    # Keywords
    IF = auto()
    ELSE = auto()
    WHILE = auto()
    FOR = auto()
    FUNCTION = auto()
    RETURN = auto()
    LET = auto()
    CONST = auto()
    
    # Operators
    PLUS = auto()
    MINUS = auto()
    MULTIPLY = auto()
    DIVIDE = auto()
    ASSIGN = auto()
    EQUALS = auto()
    NOT_EQUALS = auto()
    LESS = auto()
    GREATER = auto()
    LESS_EQ = auto()
    GREATER_EQ = auto()
    
    # Delimiters
    LPAREN = auto()
    RPAREN = auto()
    LBRACE = auto()
    RBRACE = auto()
    LBRACKET = auto()
    RBRACKET = auto()
    COMMA = auto()
    SEMICOLON = auto()
    COLON = auto()
    
    # Special
    EOF = auto()
    NEWLINE = auto()

@dataclass
class Token:
    type: TokenType
    value: any
    line: int
    column: int
    
    def __repr__(self):
        return f"Token({self.type.name}, {self.value!r}, {self.line}:{self.column})"

class Lexer:
    KEYWORDS = {
        'if': TokenType.IF,
        'else': TokenType.ELSE,
        'while': TokenType.WHILE,
        'for': TokenType.FOR,
        'function': TokenType.FUNCTION,
        'return': TokenType.RETURN,
        'let': TokenType.LET,
        'const': TokenType.CONST,
    }
    
    SINGLE_CHAR_TOKENS = {
        '+': TokenType.PLUS,
        '-': TokenType.MINUS,
        '*': TokenType.MULTIPLY,
        '/': TokenType.DIVIDE,
        '(': TokenType.LPAREN,
        ')': TokenType.RPAREN,
        '{': TokenType.LBRACE,
        '}': TokenType.RBRACE,
        '[': TokenType.LBRACKET,
        ']': TokenType.RBRACKET,
        ',': TokenType.COMMA,
        ';': TokenType.SEMICOLON,
        ':': TokenType.COLON,
    }
    
    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.column = 1
        self.tokens: List[Token] = []
    
    def current_char(self) -> Optional[str]:
        if self.pos >= len(self.source):
            return None
        return self.source[self.pos]
    
    def peek(self, offset: int = 1) -> Optional[str]:
        pos = self.pos + offset
        if pos >= len(self.source):
            return None
        return self.source[pos]
    
    def advance(self) -> str:
        char = self.current_char()
        self.pos += 1
        if char == '\\n':
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return char
    
    def add_token(self, token_type: TokenType, value: any = None):
        self.tokens.append(Token(token_type, value, self.line, self.column))
    
    def skip_whitespace(self):
        while self.current_char() and self.current_char() in ' \\t\\r':
            self.advance()
    
    def skip_comment(self):
        if self.current_char() == '/' and self.peek() == '/':
            while self.current_char() and self.current_char() != '\\n':
                self.advance()
    
    def read_number(self) -> Token:
        start_col = self.column
        num_str = ''
        is_float = False
        
        while self.current_char() and (self.current_char().isdigit() or self.current_char() == '.'):
            if self.current_char() == '.':
                if is_float:
                    break
                is_float = True
            num_str += self.advance()
        
        if is_float:
            return Token(TokenType.FLOAT, float(num_str), self.line, start_col)
        return Token(TokenType.INTEGER, int(num_str), self.line, start_col)
    
    def read_string(self) -> Token:
        start_col = self.column
        quote_char = self.advance()  # Skip opening quote
        string_val = ''
        
        while self.current_char() and self.current_char() != quote_char:
            if self.current_char() == '\\\\':
                self.advance()
                escape_char = self.advance()
                escape_map = {'n': '\\n', 't': '\\t', 'r': '\\r', '\\\\': '\\\\'}
                string_val += escape_map.get(escape_char, escape_char)
            else:
                string_val += self.advance()
        
        self.advance()  # Skip closing quote
        return Token(TokenType.STRING, string_val, self.line, start_col)
    
    def read_identifier(self) -> Token:
        start_col = self.column
        ident = ''
        
        while self.current_char() and (self.current_char().isalnum() or self.current_char() == '_'):
            ident += self.advance()
        
        # Check if it's a keyword
        token_type = self.KEYWORDS.get(ident, TokenType.IDENTIFIER)
        return Token(token_type, ident, self.line, start_col)
    
    def tokenize(self) -> List[Token]:
        while self.current_char():
            self.skip_whitespace()
            self.skip_comment()
            
            char = self.current_char()
            if not char:
                break
            
            # Handle newlines
            if char == '\\n':
                self.add_token(TokenType.NEWLINE)
                self.advance()
                continue
            
            # Numbers
            if char.isdigit():
                self.tokens.append(self.read_number())
                continue
            
            # Strings
            if char in '"\\\'':
                self.tokens.append(self.read_string())
                continue
            
            # Identifiers and keywords
            if char.isalpha() or char == '_':
                self.tokens.append(self.read_identifier())
                continue
            
            # Two-character operators
            if char == '=' and self.peek() == '=':
                self.add_token(TokenType.EQUALS, '==')
                self.advance()
                self.advance()
                continue
            
            if char == '!' and self.peek() == '=':
                self.add_token(TokenType.NOT_EQUALS, '!=')
                self.advance()
                self.advance()
                continue
            
            if char == '<' and self.peek() == '=':
                self.add_token(TokenType.LESS_EQ, '<=')
                self.advance()
                self.advance()
                continue
            
            if char == '>' and self.peek() == '=':
                self.add_token(TokenType.GREATER_EQ, '>=')
                self.advance()
                self.advance()
                continue
            
            # Single-character operators
            if char == '=':
                self.add_token(TokenType.ASSIGN, '=')
                self.advance()
                continue
            
            if char == '<':
                self.add_token(TokenType.LESS, '<')
                self.advance()
                continue
            
            if char == '>':
                self.add_token(TokenType.GREATER, '>')
                self.advance()
                continue
            
            # Other single-character tokens
            if char in self.SINGLE_CHAR_TOKENS:
                self.add_token(self.SINGLE_CHAR_TOKENS[char], char)
                self.advance()
                continue
            
            # Unknown character
            raise SyntaxError(f"Unknown character '{char}' at {self.line}:{self.column}")
        
        self.add_token(TokenType.EOF)
        return self.tokens


# Example usage
if __name__ == "__main__":
    code = """
    let x = 42;
    let name = "hello";
    
    function add(a, b) {
        return a + b;
    }
    
    if (x > 10) {
        x = x + 1;
    }
    """
    
    lexer = Lexer(code)
    tokens = lexer.tokenize()
    
    for token in tokens:
        print(token)'''
        }
    ]
}

# ============================================================================
# GAME DEVELOPMENT FUNDAMENTALS
# ============================================================================

GAME_DEV_FUNDAMENTALS_COURSE = {
    "id": "gamedev_fundamentals",
    "code": "GAME 101",
    "title": "Game Development Fundamentals",
    "subtitle": "From Concept to Playable Game",
    "credits": 4,
    "hours": 75,
    "weeks": 15,
    "level": "intermediate",
    "prerequisites": ["OOP", "Data Structures"],
    "description": """Introduction to game development covering game design principles,
game loops, input handling, collision detection, and basic game AI. Build several
complete games from scratch.""",
    
    "learning_objectives": [
        "Understand game development lifecycle",
        "Implement core game systems (loop, input, rendering)",
        "Design and implement game mechanics",
        "Create basic game AI",
        "Handle collision detection and response",
        "Build complete, polished games"
    ],
    
    "weeks_summary": [
        {"week": 1, "title": "Game Design Principles", "topics": ["Game Genres", "Core Mechanics", "Player Experience", "GDD"]},
        {"week": 2, "title": "The Game Loop", "topics": ["Main Loop", "Fixed vs Variable Timestep", "Frame Rate Independence"]},
        {"week": 3, "title": "Input Handling", "topics": ["Keyboard", "Mouse", "Gamepad", "Touch Input"]},
        {"week": 4, "title": "2D Graphics", "topics": ["Sprites", "Animation", "Sprite Sheets", "Rendering Order"]},
        {"week": 5, "title": "Collision Detection", "topics": ["AABB", "Circle Collision", "Pixel Perfect", "Spatial Partitioning"]},
        {"week": 6, "title": "Game Physics", "topics": ["Velocity", "Acceleration", "Gravity", "Basic Rigid Body"]},
        {"week": 7, "title": "Game States", "topics": ["State Machines", "Menus", "Pause", "Game Over"]},
        {"week": 8, "title": "Audio", "topics": ["Sound Effects", "Music", "Audio Mixing", "Spatial Audio"]},
        {"week": 9, "title": "Tilemaps", "topics": ["Tile-based Games", "Map Editors", "Collision Maps", "Scrolling"]},
        {"week": 10, "title": "Basic Game AI", "topics": ["State Machines", "Pathfinding", "Decision Making"]},
        {"week": 11, "title": "UI/UX", "topics": ["HUD Design", "Menus", "Feedback", "Juice"]},
        {"week": 12, "title": "Platformer Project", "topics": ["Player Controller", "Enemies", "Collectibles", "Levels"]},
        {"week": 13, "title": "Top-Down Game", "topics": ["Movement", "Combat", "Inventory", "NPCs"]},
        {"week": 14, "title": "Polish & Juice", "topics": ["Screen Shake", "Particles", "Sound Design", "Feel"]},
        {"week": 15, "title": "Publishing", "topics": ["Build Process", "Optimization", "Distribution", "Marketing"]}
    ],
    
    "code_examples": [
        {
            "title": "Basic Game Loop with Pygame",
            "language": "python",
            "code": '''import pygame
import sys
from dataclasses import dataclass
from typing import List
import math

# Initialize Pygame
pygame.init()

# Constants
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
FPS = 60
PLAYER_SPEED = 5
BULLET_SPEED = 10

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)

@dataclass
class Vector2:
    x: float
    y: float
    
    def __add__(self, other):
        return Vector2(self.x + other.x, self.y + other.y)
    
    def __mul__(self, scalar):
        return Vector2(self.x * scalar, self.y * scalar)
    
    def magnitude(self):
        return math.sqrt(self.x ** 2 + self.y ** 2)
    
    def normalize(self):
        mag = self.magnitude()
        if mag > 0:
            return Vector2(self.x / mag, self.y / mag)
        return Vector2(0, 0)

class Entity:
    def __init__(self, x, y, width, height, color):
        self.position = Vector2(x, y)
        self.velocity = Vector2(0, 0)
        self.width = width
        self.height = height
        self.color = color
        self.active = True
    
    @property
    def rect(self):
        return pygame.Rect(self.position.x, self.position.y, 
                          self.width, self.height)
    
    def update(self, dt):
        self.position = self.position + self.velocity * dt
    
    def draw(self, screen):
        pygame.draw.rect(screen, self.color, self.rect)
    
    def collides_with(self, other):
        return self.rect.colliderect(other.rect)

class Player(Entity):
    def __init__(self, x, y):
        super().__init__(x, y, 40, 40, GREEN)
        self.speed = PLAYER_SPEED
        self.shoot_cooldown = 0
        self.health = 100
        self.score = 0
    
    def handle_input(self, keys):
        self.velocity = Vector2(0, 0)
        
        if keys[pygame.K_LEFT] or keys[pygame.K_a]:
            self.velocity.x = -self.speed
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
            self.velocity.x = self.speed
        if keys[pygame.K_UP] or keys[pygame.K_w]:
            self.velocity.y = -self.speed
        if keys[pygame.K_DOWN] or keys[pygame.K_s]:
            self.velocity.y = self.speed
        
        # Normalize diagonal movement
        if self.velocity.magnitude() > 0:
            self.velocity = self.velocity.normalize() * self.speed
    
    def update(self, dt):
        super().update(dt)
        
        # Keep player in bounds
        self.position.x = max(0, min(SCREEN_WIDTH - self.width, self.position.x))
        self.position.y = max(0, min(SCREEN_HEIGHT - self.height, self.position.y))
        
        # Update cooldown
        if self.shoot_cooldown > 0:
            self.shoot_cooldown -= dt
    
    def shoot(self):
        if self.shoot_cooldown <= 0:
            self.shoot_cooldown = 0.2  # 200ms between shots
            return Bullet(self.position.x + self.width // 2, self.position.y)
        return None

class Bullet(Entity):
    def __init__(self, x, y):
        super().__init__(x, y, 5, 10, WHITE)
        self.velocity = Vector2(0, -BULLET_SPEED)
    
    def update(self, dt):
        super().update(dt)
        if self.position.y < -10:
            self.active = False

class Enemy(Entity):
    def __init__(self, x, y):
        super().__init__(x, y, 30, 30, RED)
        self.velocity = Vector2(0, 2)
    
    def update(self, dt):
        super().update(dt)
        if self.position.y > SCREEN_HEIGHT:
            self.active = False

class Game:
    def __init__(self):
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Space Shooter")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 36)
        
        self.player = Player(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 60)
        self.bullets: List[Bullet] = []
        self.enemies: List[Enemy] = []
        self.enemy_spawn_timer = 0
        self.running = True
        self.game_over = False
    
    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    bullet = self.player.shoot()
                    if bullet:
                        self.bullets.append(bullet)
                
                if event.key == pygame.K_r and self.game_over:
                    self.reset()
    
    def spawn_enemy(self):
        import random
        x = random.randint(0, SCREEN_WIDTH - 30)
        self.enemies.append(Enemy(x, -30))
    
    def update(self, dt):
        if self.game_over:
            return
        
        # Handle input
        keys = pygame.key.get_pressed()
        self.player.handle_input(keys)
        
        # Update entities
        self.player.update(dt)
        
        for bullet in self.bullets:
            bullet.update(dt)
        
        for enemy in self.enemies:
            enemy.update(dt)
        
        # Remove inactive entities
        self.bullets = [b for b in self.bullets if b.active]
        self.enemies = [e for e in self.enemies if e.active]
        
        # Check collisions
        for bullet in self.bullets:
            for enemy in self.enemies:
                if bullet.collides_with(enemy):
                    bullet.active = False
                    enemy.active = False
                    self.player.score += 10
        
        for enemy in self.enemies:
            if enemy.collides_with(self.player):
                self.player.health -= 10
                enemy.active = False
                if self.player.health <= 0:
                    self.game_over = True
        
        # Spawn enemies
        self.enemy_spawn_timer += dt
        if self.enemy_spawn_timer > 1.0:  # Every second
            self.spawn_enemy()
            self.enemy_spawn_timer = 0
    
    def draw(self):
        self.screen.fill(BLACK)
        
        # Draw entities
        self.player.draw(self.screen)
        
        for bullet in self.bullets:
            bullet.draw(self.screen)
        
        for enemy in self.enemies:
            enemy.draw(self.screen)
        
        # Draw UI
        score_text = self.font.render(f"Score: {self.player.score}", True, WHITE)
        health_text = self.font.render(f"Health: {self.player.health}", True, WHITE)
        
        self.screen.blit(score_text, (10, 10))
        self.screen.blit(health_text, (10, 50))
        
        if self.game_over:
            game_over_text = self.font.render("GAME OVER - Press R to restart", True, RED)
            text_rect = game_over_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2))
            self.screen.blit(game_over_text, text_rect)
        
        pygame.display.flip()
    
    def reset(self):
        self.player = Player(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 60)
        self.bullets = []
        self.enemies = []
        self.game_over = False
    
    def run(self):
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0  # Delta time in seconds
            
            self.handle_events()
            self.update(dt)
            self.draw()
        
        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    game = Game()
    game.run()'''
        }
    ]
}

# ============================================================================
# GAME ENGINE ARCHITECTURE
# ============================================================================

GAME_ENGINE_COURSE = {
    "id": "game_engine",
    "code": "GAME 201",
    "title": "Game Engine Architecture",
    "subtitle": "Building the Foundation of Games",
    "credits": 4,
    "hours": 75,
    "weeks": 15,
    "level": "advanced",
    "prerequisites": ["Game Development Fundamentals", "Data Structures", "Computer Graphics"],
    "description": """Deep dive into game engine architecture. Learn to build core engine
systems including rendering, physics, audio, scripting, and resource management.
Create a complete 2D/3D game engine.""",
    
    "learning_objectives": [
        "Design modular game engine architecture",
        "Implement efficient rendering pipelines",
        "Build physics systems with collision detection",
        "Create resource management systems",
        "Implement scene graphs and entity-component systems",
        "Design scripting and event systems"
    ],
    
    "weeks_summary": [
        {"week": 1, "title": "Engine Overview", "topics": ["Architecture Patterns", "Runtime vs Tool", "Platform Abstraction"]},
        {"week": 2, "title": "Memory Management", "topics": ["Custom Allocators", "Pool Allocators", "Stack Allocators"]},
        {"week": 3, "title": "Math Library", "topics": ["Vectors", "Matrices", "Quaternions", "Transforms"]},
        {"week": 4, "title": "Rendering I", "topics": ["Rendering Pipeline", "Shaders", "Draw Calls", "Batching"]},
        {"week": 5, "title": "Rendering II", "topics": ["Materials", "Lighting", "Shadow Mapping", "Post-Processing"]},
        {"week": 6, "title": "Scene Management", "topics": ["Scene Graphs", "Spatial Partitioning", "Culling"]},
        {"week": 7, "title": "Entity-Component-System", "topics": ["ECS Architecture", "Components", "Systems", "Data-Oriented"]},
        {"week": 8, "title": "Physics Engine I", "topics": ["Rigid Bodies", "Forces", "Integration Methods"]},
        {"week": 9, "title": "Physics Engine II", "topics": ["Collision Detection", "Collision Response", "Constraints"]},
        {"week": 10, "title": "Audio Engine", "topics": ["Audio Playback", "Mixing", "3D Audio", "DSP"]},
        {"week": 11, "title": "Resource Management", "topics": ["Asset Pipeline", "Streaming", "Caching", "Hot Reloading"]},
        {"week": 12, "title": "Scripting System", "topics": ["Scripting Languages", "Binding", "Visual Scripting"]},
        {"week": 13, "title": "Animation System", "topics": ["Skeletal Animation", "Blend Trees", "State Machines"]},
        {"week": 14, "title": "Networking", "topics": ["Client-Server", "Replication", "Lag Compensation"]},
        {"week": 15, "title": "Tools & Editor", "topics": ["Level Editor", "Debugging Tools", "Profiling"]}
    ]
}

# ============================================================================
# GRAPHICS PROGRAMMING
# ============================================================================

GRAPHICS_PROGRAMMING_COURSE = {
    "id": "graphics_programming",
    "code": "GAME 202",
    "title": "Graphics Programming",
    "subtitle": "Real-Time Rendering Techniques",
    "credits": 4,
    "hours": 75,
    "weeks": 15,
    "level": "advanced",
    "prerequisites": ["Linear Algebra", "C++", "Data Structures"],
    "description": """Master modern real-time graphics programming. Learn OpenGL/WebGL,
shader programming, and advanced rendering techniques used in AAA games.""",
    
    "learning_objectives": [
        "Understand the graphics pipeline",
        "Write vertex and fragment shaders",
        "Implement lighting models (Phong, PBR)",
        "Create post-processing effects",
        "Implement shadow mapping",
        "Optimize rendering performance"
    ],
    
    "weeks_summary": [
        {"week": 1, "title": "Graphics Pipeline", "topics": ["Vertex Processing", "Rasterization", "Fragment Processing"]},
        {"week": 2, "title": "OpenGL Basics", "topics": ["Context", "Buffers", "VAO/VBO", "Drawing"]},
        {"week": 3, "title": "Shader Programming", "topics": ["GLSL", "Vertex Shaders", "Fragment Shaders", "Uniforms"]},
        {"week": 4, "title": "Textures", "topics": ["Texture Mapping", "Mipmaps", "Filtering", "Sampling"]},
        {"week": 5, "title": "Transformations", "topics": ["Model Matrix", "View Matrix", "Projection", "MVP"]},
        {"week": 6, "title": "Lighting I", "topics": ["Phong Model", "Ambient", "Diffuse", "Specular"]},
        {"week": 7, "title": "Lighting II", "topics": ["Multiple Lights", "Attenuation", "Spotlights", "Normal Mapping"]},
        {"week": 8, "title": "Shadows", "topics": ["Shadow Mapping", "PCF", "Cascaded Shadows", "VSM"]},
        {"week": 9, "title": "Advanced Shading", "topics": ["PBR", "IBL", "BRDF", "HDR"]},
        {"week": 10, "title": "Post-Processing", "topics": ["Framebuffers", "Bloom", "DOF", "Motion Blur"]},
        {"week": 11, "title": "Deferred Rendering", "topics": ["G-Buffer", "Light Volumes", "SSAO"]},
        {"week": 12, "title": "Particles", "topics": ["Billboard", "GPU Particles", "Instancing"]},
        {"week": 13, "title": "Optimization", "topics": ["Culling", "LOD", "Batching", "Profiling"]},
        {"week": 14, "title": "Advanced Topics", "topics": ["Ray Tracing Intro", "Compute Shaders", "Vulkan Intro"]},
        {"week": 15, "title": "Final Project", "topics": ["Complete Rendering Engine"]}
    ]
}

# ============================================================================
# GAME AI & PHYSICS
# ============================================================================

GAME_AI_PHYSICS_COURSE = {
    "id": "game_ai_physics",
    "code": "GAME 203",
    "title": "Game AI & Physics",
    "subtitle": "Intelligent Agents and Realistic Simulation",
    "credits": 4,
    "hours": 75,
    "weeks": 15,
    "level": "advanced",
    "prerequisites": ["Game Development Fundamentals", "Algorithms", "Linear Algebra"],
    "description": """Advanced game AI and physics simulation. Learn pathfinding, behavior
trees, steering behaviors, physics simulation, and advanced collision detection.""",
    
    "learning_objectives": [
        "Implement pathfinding algorithms (A*, Navigation Meshes)",
        "Create behavior trees and decision systems",
        "Implement steering behaviors",
        "Build physics simulations",
        "Handle complex collision scenarios",
        "Create believable NPC behaviors"
    ],
    
    "weeks_summary": [
        {"week": 1, "title": "AI Overview", "topics": ["Game AI vs Traditional AI", "Agent Architecture", "Decision Making"]},
        {"week": 2, "title": "Movement", "topics": ["Steering Behaviors", "Seek", "Flee", "Arrive", "Wander"]},
        {"week": 3, "title": "Pathfinding I", "topics": ["Graph Search", "A* Algorithm", "Heuristics", "Optimization"]},
        {"week": 4, "title": "Pathfinding II", "topics": ["Navigation Meshes", "Hierarchical Pathfinding", "Dynamic Obstacles"]},
        {"week": 5, "title": "Decision Making I", "topics": ["Finite State Machines", "Transitions", "Hierarchical FSM"]},
        {"week": 6, "title": "Decision Making II", "topics": ["Behavior Trees", "Nodes", "Composites", "Decorators"]},
        {"week": 7, "title": "Advanced AI", "topics": ["GOAP", "Utility AI", "Monte Carlo", "Machine Learning"]},
        {"week": 8, "title": "Physics Basics", "topics": ["Newtonian Mechanics", "Integration", "Forces", "Impulses"]},
        {"week": 9, "title": "Rigid Body Dynamics", "topics": ["Linear Dynamics", "Angular Dynamics", "Inertia Tensors"]},
        {"week": 10, "title": "Collision Detection I", "topics": ["Broad Phase", "AABB Trees", "Spatial Hashing"]},
        {"week": 11, "title": "Collision Detection II", "topics": ["Narrow Phase", "GJK", "SAT", "Continuous Collision"]},
        {"week": 12, "title": "Collision Response", "topics": ["Impulse Resolution", "Friction", "Restitution"]},
        {"week": 13, "title": "Constraints", "topics": ["Joint Systems", "Ragdoll Physics", "Constraint Solvers"]},
        {"week": 14, "title": "Soft Bodies", "topics": ["Mass-Spring", "Cloth Simulation", "Fluids Intro"]},
        {"week": 15, "title": "Integration Project", "topics": ["Complete AI + Physics System"]}
    ],
    
    "code_examples": [
        {
            "title": "A* Pathfinding Implementation",
            "language": "python",
            "code": '''import heapq
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional, Set
import math

@dataclass
class Node:
    x: int
    y: int
    g: float = float('inf')  # Cost from start
    h: float = 0  # Heuristic to goal
    parent: Optional['Node'] = None
    
    @property
    def f(self) -> float:
        return self.g + self.h
    
    def __lt__(self, other):
        return self.f < other.f
    
    def __eq__(self, other):
        return self.x == other.x and self.y == other.y
    
    def __hash__(self):
        return hash((self.x, self.y))

class Grid:
    def __init__(self, width: int, height: int):
        self.width = width
        self.height = height
        self.obstacles: Set[Tuple[int, int]] = set()
    
    def set_obstacle(self, x: int, y: int):
        self.obstacles.add((x, y))
    
    def is_walkable(self, x: int, y: int) -> bool:
        return (0 <= x < self.width and 
                0 <= y < self.height and 
                (x, y) not in self.obstacles)
    
    def get_neighbors(self, node: Node) -> List[Node]:
        neighbors = []
        
        # 8-directional movement
        directions = [
            (0, 1), (1, 0), (0, -1), (-1, 0),  # Cardinal
            (1, 1), (1, -1), (-1, 1), (-1, -1)  # Diagonal
        ]
        
        for dx, dy in directions:
            new_x, new_y = node.x + dx, node.y + dy
            
            if self.is_walkable(new_x, new_y):
                # For diagonal movement, check corners
                if dx != 0 and dy != 0:
                    if not (self.is_walkable(node.x + dx, node.y) and 
                            self.is_walkable(node.x, node.y + dy)):
                        continue
                
                neighbors.append(Node(new_x, new_y))
        
        return neighbors

class AStar:
    def __init__(self, grid: Grid):
        self.grid = grid
    
    def heuristic(self, a: Node, b: Node) -> float:
        # Octile distance (allows diagonal movement)
        dx = abs(a.x - b.x)
        dy = abs(a.y - b.y)
        D = 1  # Cardinal cost
        D2 = math.sqrt(2)  # Diagonal cost
        return D * max(dx, dy) + (D2 - D) * min(dx, dy)
    
    def get_movement_cost(self, from_node: Node, to_node: Node) -> float:
        dx = abs(from_node.x - to_node.x)
        dy = abs(from_node.y - to_node.y)
        
        if dx + dy == 2:  # Diagonal
            return math.sqrt(2)
        return 1  # Cardinal
    
    def find_path(self, start: Tuple[int, int], 
                  goal: Tuple[int, int]) -> Optional[List[Tuple[int, int]]]:
        
        start_node = Node(start[0], start[1], g=0)
        goal_node = Node(goal[0], goal[1])
        
        start_node.h = self.heuristic(start_node, goal_node)
        
        open_set: List[Node] = [start_node]
        closed_set: Set[Tuple[int, int]] = set()
        all_nodes: Dict[Tuple[int, int], Node] = {(start[0], start[1]): start_node}
        
        while open_set:
            current = heapq.heappop(open_set)
            
            # Goal reached
            if current == goal_node:
                return self.reconstruct_path(current)
            
            closed_set.add((current.x, current.y))
            
            for neighbor in self.grid.get_neighbors(current):
                if (neighbor.x, neighbor.y) in closed_set:
                    continue
                
                tentative_g = current.g + self.get_movement_cost(current, neighbor)
                
                # Check if we already have this node
                key = (neighbor.x, neighbor.y)
                if key in all_nodes:
                    neighbor = all_nodes[key]
                else:
                    all_nodes[key] = neighbor
                
                if tentative_g < neighbor.g:
                    neighbor.parent = current
                    neighbor.g = tentative_g
                    neighbor.h = self.heuristic(neighbor, goal_node)
                    
                    if neighbor not in open_set:
                        heapq.heappush(open_set, neighbor)
        
        return None  # No path found
    
    def reconstruct_path(self, node: Node) -> List[Tuple[int, int]]:
        path = []
        current = node
        
        while current:
            path.append((current.x, current.y))
            current = current.parent
        
        return list(reversed(path))

# Behavior Tree Implementation
class BTNode:
    def tick(self) -> str:
        raise NotImplementedError

class BTSelector(BTNode):
    """Returns SUCCESS if any child succeeds"""
    def __init__(self, children: List[BTNode]):
        self.children = children
    
    def tick(self) -> str:
        for child in self.children:
            result = child.tick()
            if result != "FAILURE":
                return result
        return "FAILURE"

class BTSequence(BTNode):
    """Returns SUCCESS only if all children succeed"""
    def __init__(self, children: List[BTNode]):
        self.children = children
    
    def tick(self) -> str:
        for child in self.children:
            result = child.tick()
            if result != "SUCCESS":
                return result
        return "SUCCESS"

class BTCondition(BTNode):
    """Checks a condition"""
    def __init__(self, condition_fn):
        self.condition_fn = condition_fn
    
    def tick(self) -> str:
        return "SUCCESS" if self.condition_fn() else "FAILURE"

class BTAction(BTNode):
    """Executes an action"""
    def __init__(self, action_fn):
        self.action_fn = action_fn
    
    def tick(self) -> str:
        return self.action_fn()


# Example usage
if __name__ == "__main__":
    # A* Example
    grid = Grid(10, 10)
    grid.set_obstacle(3, 3)
    grid.set_obstacle(3, 4)
    grid.set_obstacle(3, 5)
    grid.set_obstacle(4, 5)
    
    pathfinder = AStar(grid)
    path = pathfinder.find_path((0, 0), (6, 6))
    
    print("Path found:", path)
    
    # Visualize
    for y in range(10):
        row = ""
        for x in range(10):
            if (x, y) in grid.obstacles:
                row += "X "
            elif path and (x, y) in path:
                row += "* "
            else:
                row += ". "
        print(row)'''
        }
    ]
}

# ============================================================================
# ADVANCED CLASSES REGISTRY
# ============================================================================

ADVANCED_CS_CLASSES = {
    "operating_systems": OPERATING_SYSTEMS_COURSE,
    "networks": COMPUTER_NETWORKS_COURSE,
    "compilers": COMPILER_DESIGN_COURSE,
    "gamedev_fundamentals": GAME_DEV_FUNDAMENTALS_COURSE,
    "game_engine": GAME_ENGINE_COURSE,
    "graphics_programming": GRAPHICS_PROGRAMMING_COURSE,
    "game_ai_physics": GAME_AI_PHYSICS_COURSE
}

def get_advanced_class(class_id: str) -> dict:
    """Get a specific advanced CS class by ID"""
    return ADVANCED_CS_CLASSES.get(class_id)

def get_all_advanced_classes() -> list:
    """Get all available advanced CS classes"""
    return list(ADVANCED_CS_CLASSES.values())

def get_game_dev_track() -> list:
    """Get all game development classes"""
    return [
        GAME_DEV_FUNDAMENTALS_COURSE,
        GAME_ENGINE_COURSE,
        GRAPHICS_PROGRAMMING_COURSE,
        GAME_AI_PHYSICS_COURSE
    ]
