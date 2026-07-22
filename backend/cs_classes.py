"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                 COMPLETE COMPUTER SCIENCE CLASSES                             ║
║                                                                               ║
║  Advanced University-Level Courses:                                           ║
║  • Data Structures & Algorithms                                               ║
║  • Object-Oriented Programming                                                ║
║  • Database Systems                                                           ║
║                                                                               ║
║  Each course: 15 weeks, 60+ hours, comprehensive curriculum                   ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

from typing import Dict, List, Any

# Import advanced classes
from cs_classes_advanced import (
    ADVANCED_CS_CLASSES, 
    get_advanced_class, 
    get_all_advanced_classes,
    get_game_dev_track
)

# ============================================================================
# DATA STRUCTURES & ALGORITHMS - COMPLETE COURSE
# ============================================================================

DATA_STRUCTURES_COURSE = {
    "id": "ds_complete",
    "code": "CS 201",
    "title": "Data Structures & Algorithms",
    "subtitle": "The Foundation of Efficient Programming",
    "credits": 4,
    "hours": 75,
    "weeks": 15,
    "level": "intermediate",
    "prerequisites": ["Programming Fundamentals", "Discrete Mathematics"],
    "description": """Master the fundamental data structures and algorithms that form the backbone
of all software systems. This comprehensive course covers everything from basic arrays to advanced
graph algorithms, with a focus on both theoretical understanding and practical implementation.""",
    
    "learning_objectives": [
        "Analyze algorithm complexity using Big-O, Big-Theta, and Big-Omega notation",
        "Implement and optimize fundamental data structures from scratch",
        "Apply appropriate data structures to solve real-world problems",
        "Design efficient algorithms using divide-and-conquer, greedy, and dynamic programming",
        "Understand trade-offs between different data structure implementations",
        "Master graph algorithms and their applications",
        "Write clean, efficient, and well-documented code",
        "Solve complex algorithmic problems under time constraints"
    ],
    
    "weeks": [
        # WEEK 1: Foundations
        {
            "week": 1,
            "title": "Algorithm Analysis & Complexity",
            "topics": [
                "What are data structures and algorithms?",
                "Why algorithm efficiency matters",
                "Big-O Notation - Upper bounds",
                "Big-Omega (Ω) - Lower bounds",
                "Big-Theta (Θ) - Tight bounds",
                "Best, Average, and Worst case analysis",
                "Space complexity vs Time complexity",
                "Amortized analysis introduction"
            ],
            "code_examples": [
                {
                    "title": "Complexity Analysis Examples",
                    "language": "python",
                    "code": '''# O(1) - Constant Time
def get_first(arr):
    """Access first element - always one operation"""
    return arr[0] if arr else None

# O(n) - Linear Time
def find_max(arr):
    """Find maximum - must check each element"""
    if not arr:
        return None
    max_val = arr[0]
    for item in arr:  # n iterations
        if item > max_val:
            max_val = item
    return max_val

# O(n²) - Quadratic Time
def has_duplicate_pairs(arr):
    """Check all pairs - nested loops"""
    n = len(arr)
    for i in range(n):          # n iterations
        for j in range(i+1, n):  # n-1, n-2, ... iterations
            if arr[i] == arr[j]:
                return True
    return False

# O(log n) - Logarithmic Time
def binary_search(arr, target):
    """Divide search space in half each time"""
    left, right = 0, len(arr) - 1
    while left <= right:
        mid = (left + right) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            left = mid + 1  # Eliminate left half
        else:
            right = mid - 1  # Eliminate right half
    return -1

# O(n log n) - Linearithmic Time
def merge_sort(arr):
    """Divide and conquer sorting"""
    if len(arr) <= 1:
        return arr
    
    mid = len(arr) // 2
    left = merge_sort(arr[:mid])   # T(n/2)
    right = merge_sort(arr[mid:])  # T(n/2)
    
    return merge(left, right)       # O(n)

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

# Complexity Comparison
"""
n        O(1)    O(log n)   O(n)      O(n log n)   O(n²)        O(2^n)
10       1       3          10        33           100          1,024
100      1       7          100       664          10,000       1.27e30
1,000    1       10         1,000     9,966        1,000,000    ∞
10,000   1       13         10,000    132,877      100,000,000  ∞
"""'''
                }
            ],
            "exercises": [
                "Analyze the complexity of finding the second largest element",
                "Prove that O(log n) + O(n) = O(n)",
                "Write a function that runs in O(n) but uses O(1) space"
            ]
        },
        
        # WEEK 2: Arrays and Dynamic Arrays
        {
            "week": 2,
            "title": "Arrays & Dynamic Arrays",
            "topics": [
                "Static arrays - fixed size, contiguous memory",
                "Dynamic arrays - resizing strategies",
                "Amortized analysis of append operations",
                "Array slicing and views",
                "Multi-dimensional arrays",
                "Sparse arrays",
                "Circular arrays/buffers",
                "Array-based problems and patterns"
            ],
            "code_examples": [
                {
                    "title": "Dynamic Array Implementation",
                    "language": "python",
                    "code": '''class DynamicArray:
    """
    Dynamic array implementation with amortized O(1) append.
    
    Doubles capacity when full (geometric growth).
    This gives amortized O(1) time for append operations.
    """
    
    def __init__(self, initial_capacity=8):
        self._capacity = initial_capacity
        self._size = 0
        self._data = [None] * self._capacity
    
    def __len__(self):
        return self._size
    
    def __getitem__(self, index):
        """O(1) random access"""
        if not 0 <= index < self._size:
            raise IndexError(f"Index {index} out of bounds")
        return self._data[index]
    
    def __setitem__(self, index, value):
        """O(1) random access modification"""
        if not 0 <= index < self._size:
            raise IndexError(f"Index {index} out of bounds")
        self._data[index] = value
    
    def append(self, value):
        """
        Amortized O(1) append.
        
        Worst case O(n) when resize needed, but happens
        infrequently enough that amortized cost is O(1).
        """
        if self._size == self._capacity:
            self._resize(2 * self._capacity)  # Double capacity
        
        self._data[self._size] = value
        self._size += 1
    
    def _resize(self, new_capacity):
        """O(n) - copy all elements to new array"""
        new_data = [None] * new_capacity
        for i in range(self._size):
            new_data[i] = self._data[i]
        self._data = new_data
        self._capacity = new_capacity
    
    def insert(self, index, value):
        """
        O(n) - must shift elements.
        
        Insert at index 0 is worst case (shift all n elements).
        Insert at end is O(1) amortized (same as append).
        """
        if not 0 <= index <= self._size:
            raise IndexError(f"Index {index} out of bounds")
        
        if self._size == self._capacity:
            self._resize(2 * self._capacity)
        
        # Shift elements right
        for i in range(self._size, index, -1):
            self._data[i] = self._data[i-1]
        
        self._data[index] = value
        self._size += 1
    
    def remove(self, index):
        """
        O(n) - must shift elements.
        
        Remove from index 0 is worst case.
        Remove from end is O(1).
        """
        if not 0 <= index < self._size:
            raise IndexError(f"Index {index} out of bounds")
        
        value = self._data[index]
        
        # Shift elements left
        for i in range(index, self._size - 1):
            self._data[i] = self._data[i+1]
        
        self._data[self._size - 1] = None
        self._size -= 1
        
        # Shrink if too empty (optional)
        if self._size < self._capacity // 4:
            self._resize(self._capacity // 2)
        
        return value
    
    def __repr__(self):
        return f"DynamicArray({[self._data[i] for i in range(self._size)]})"


# Classic Array Problems

def two_sum(nums, target):
    """
    Find two numbers that add to target.
    O(n) time, O(n) space using hash map.
    """
    seen = {}
    for i, num in enumerate(nums):
        complement = target - num
        if complement in seen:
            return [seen[complement], i]
        seen[num] = i
    return []


def max_subarray_sum(arr):
    """
    Kadane's Algorithm - Maximum subarray sum.
    O(n) time, O(1) space.
    """
    if not arr:
        return 0
    
    max_sum = current_sum = arr[0]
    
    for num in arr[1:]:
        current_sum = max(num, current_sum + num)
        max_sum = max(max_sum, current_sum)
    
    return max_sum


def rotate_array(arr, k):
    """
    Rotate array right by k positions.
    O(n) time, O(1) space using reversal.
    """
    n = len(arr)
    k = k % n  # Handle k > n
    
    def reverse(start, end):
        while start < end:
            arr[start], arr[end] = arr[end], arr[start]
            start += 1
            end -= 1
    
    # Reverse entire array
    reverse(0, n - 1)
    # Reverse first k elements
    reverse(0, k - 1)
    # Reverse remaining elements
    reverse(k, n - 1)
    
    return arr'''
                }
            ]
        },
        
        # WEEK 3: Linked Lists
        {
            "week": 3,
            "title": "Linked Lists",
            "topics": [
                "Singly linked lists",
                "Doubly linked lists",
                "Circular linked lists",
                "Sentinel/dummy nodes",
                "Two-pointer techniques",
                "Floyd's cycle detection",
                "Reversing linked lists",
                "Merge operations"
            ],
            "code_examples": [
                {
                    "title": "Complete Linked List Implementation",
                    "language": "python",
                    "code": '''class ListNode:
    """Node for singly linked list"""
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next
    
    def __repr__(self):
        return f"ListNode({self.val})"


class DoublyListNode:
    """Node for doubly linked list"""
    def __init__(self, val=0, prev=None, next=None):
        self.val = val
        self.prev = prev
        self.next = next


class LinkedList:
    """
    Singly Linked List with comprehensive operations.
    
    Time Complexities:
    - Access by index: O(n)
    - Insert at head: O(1)
    - Insert at tail: O(1) with tail pointer
    - Delete by value: O(n)
    - Search: O(n)
    """
    
    def __init__(self):
        self.head = None
        self.tail = None
        self._size = 0
    
    def __len__(self):
        return self._size
    
    def is_empty(self):
        return self._size == 0
    
    def append(self, val):
        """Add to end - O(1)"""
        new_node = ListNode(val)
        
        if self.is_empty():
            self.head = self.tail = new_node
        else:
            self.tail.next = new_node
            self.tail = new_node
        
        self._size += 1
    
    def prepend(self, val):
        """Add to beginning - O(1)"""
        new_node = ListNode(val)
        new_node.next = self.head
        self.head = new_node
        
        if self.tail is None:
            self.tail = new_node
        
        self._size += 1
    
    def insert_at(self, index, val):
        """Insert at specific index - O(n)"""
        if index < 0 or index > self._size:
            raise IndexError("Index out of bounds")
        
        if index == 0:
            self.prepend(val)
        elif index == self._size:
            self.append(val)
        else:
            new_node = ListNode(val)
            current = self.head
            
            for _ in range(index - 1):
                current = current.next
            
            new_node.next = current.next
            current.next = new_node
            self._size += 1
    
    def delete_at(self, index):
        """Delete at specific index - O(n)"""
        if index < 0 or index >= self._size:
            raise IndexError("Index out of bounds")
        
        if index == 0:
            val = self.head.val
            self.head = self.head.next
            if self.head is None:
                self.tail = None
        else:
            current = self.head
            for _ in range(index - 1):
                current = current.next
            
            val = current.next.val
            current.next = current.next.next
            
            if current.next is None:
                self.tail = current
        
        self._size -= 1
        return val
    
    def find(self, val):
        """Find index of value - O(n)"""
        current = self.head
        index = 0
        
        while current:
            if current.val == val:
                return index
            current = current.next
            index += 1
        
        return -1
    
    def reverse(self):
        """Reverse in place - O(n) time, O(1) space"""
        prev = None
        current = self.head
        self.tail = self.head
        
        while current:
            next_node = current.next
            current.next = prev
            prev = current
            current = next_node
        
        self.head = prev
    
    def to_list(self):
        """Convert to Python list - O(n)"""
        result = []
        current = self.head
        while current:
            result.append(current.val)
            current = current.next
        return result
    
    def __repr__(self):
        return f"LinkedList({self.to_list()})"


# Classic Linked List Algorithms

def has_cycle(head):
    """
    Floyd's Cycle Detection (Tortoise and Hare).
    O(n) time, O(1) space.
    """
    if not head:
        return False
    
    slow = fast = head
    
    while fast and fast.next:
        slow = slow.next        # Move 1 step
        fast = fast.next.next   # Move 2 steps
        
        if slow == fast:
            return True
    
    return False


def find_cycle_start(head):
    """
    Find the start of cycle (if exists).
    O(n) time, O(1) space.
    """
    if not head:
        return None
    
    slow = fast = head
    
    # Find meeting point
    while fast and fast.next:
        slow = slow.next
        fast = fast.next.next
        if slow == fast:
            break
    else:
        return None  # No cycle
    
    # Find cycle start
    slow = head
    while slow != fast:
        slow = slow.next
        fast = fast.next
    
    return slow


def merge_sorted_lists(l1, l2):
    """
    Merge two sorted linked lists.
    O(n + m) time, O(1) space.
    """
    dummy = ListNode(0)
    current = dummy
    
    while l1 and l2:
        if l1.val <= l2.val:
            current.next = l1
            l1 = l1.next
        else:
            current.next = l2
            l2 = l2.next
        current = current.next
    
    current.next = l1 or l2
    
    return dummy.next


def find_middle(head):
    """
    Find middle node using slow/fast pointers.
    O(n) time, O(1) space.
    """
    slow = fast = head
    
    while fast and fast.next:
        slow = slow.next
        fast = fast.next.next
    
    return slow


def reverse_between(head, left, right):
    """
    Reverse nodes between positions left and right.
    O(n) time, O(1) space.
    """
    if not head or left == right:
        return head
    
    dummy = ListNode(0, head)
    prev = dummy
    
    # Move to position before left
    for _ in range(left - 1):
        prev = prev.next
    
    # Reverse from left to right
    current = prev.next
    for _ in range(right - left):
        next_node = current.next
        current.next = next_node.next
        next_node.next = prev.next
        prev.next = next_node
    
    return dummy.next'''
                }
            ]
        },
        
        # WEEK 4: Stacks and Queues
        {
            "week": 4,
            "title": "Stacks & Queues",
            "topics": [
                "Stack ADT - LIFO principle",
                "Queue ADT - FIFO principle",
                "Array-based implementations",
                "Linked list implementations",
                "Deque (Double-ended queue)",
                "Priority Queue introduction",
                "Monotonic stacks and queues",
                "Stack-based expression evaluation"
            ],
            "code_examples": [
                {
                    "title": "Stack and Queue Implementations",
                    "language": "python",
                    "code": '''from collections import deque

class Stack:
    """
    LIFO Stack implementation.
    All operations O(1).
    """
    
    def __init__(self):
        self._items = []
    
    def push(self, item):
        """Add item to top"""
        self._items.append(item)
    
    def pop(self):
        """Remove and return top item"""
        if self.is_empty():
            raise IndexError("Stack is empty")
        return self._items.pop()
    
    def peek(self):
        """Return top item without removing"""
        if self.is_empty():
            raise IndexError("Stack is empty")
        return self._items[-1]
    
    def is_empty(self):
        return len(self._items) == 0
    
    def __len__(self):
        return len(self._items)


class Queue:
    """
    FIFO Queue implementation using deque.
    All operations O(1).
    """
    
    def __init__(self):
        self._items = deque()
    
    def enqueue(self, item):
        """Add item to back"""
        self._items.append(item)
    
    def dequeue(self):
        """Remove and return front item"""
        if self.is_empty():
            raise IndexError("Queue is empty")
        return self._items.popleft()
    
    def front(self):
        """Return front item without removing"""
        if self.is_empty():
            raise IndexError("Queue is empty")
        return self._items[0]
    
    def is_empty(self):
        return len(self._items) == 0
    
    def __len__(self):
        return len(self._items)


class MinStack:
    """
    Stack that supports getMin() in O(1).
    Uses auxiliary stack to track minimums.
    """
    
    def __init__(self):
        self.stack = []
        self.min_stack = []
    
    def push(self, val):
        self.stack.append(val)
        if not self.min_stack or val <= self.min_stack[-1]:
            self.min_stack.append(val)
    
    def pop(self):
        val = self.stack.pop()
        if val == self.min_stack[-1]:
            self.min_stack.pop()
        return val
    
    def top(self):
        return self.stack[-1]
    
    def getMin(self):
        return self.min_stack[-1]


# Classic Stack/Queue Problems

def valid_parentheses(s):
    """
    Check if parentheses are balanced.
    O(n) time, O(n) space.
    """
    stack = []
    mapping = {")": "(", "}": "{", "]": "["}
    
    for char in s:
        if char in mapping:
            if not stack or stack.pop() != mapping[char]:
                return False
        else:
            stack.append(char)
    
    return len(stack) == 0


def evaluate_rpn(tokens):
    """
    Evaluate Reverse Polish Notation.
    O(n) time, O(n) space.
    """
    stack = []
    operators = {
        "+": lambda a, b: a + b,
        "-": lambda a, b: a - b,
        "*": lambda a, b: a * b,
        "/": lambda a, b: int(a / b)  # Truncate toward zero
    }
    
    for token in tokens:
        if token in operators:
            b, a = stack.pop(), stack.pop()
            stack.append(operators[token](a, b))
        else:
            stack.append(int(token))
    
    return stack[0]


def daily_temperatures(temperatures):
    """
    Find days until warmer temperature.
    Monotonic decreasing stack approach.
    O(n) time, O(n) space.
    """
    n = len(temperatures)
    result = [0] * n
    stack = []  # Stack of indices
    
    for i in range(n):
        # Pop while current temp is warmer
        while stack and temperatures[i] > temperatures[stack[-1]]:
            prev_index = stack.pop()
            result[prev_index] = i - prev_index
        
        stack.append(i)
    
    return result


def sliding_window_maximum(nums, k):
    """
    Maximum in each sliding window of size k.
    Monotonic decreasing deque approach.
    O(n) time, O(k) space.
    """
    from collections import deque
    
    result = []
    dq = deque()  # Store indices
    
    for i in range(len(nums)):
        # Remove indices outside window
        while dq and dq[0] < i - k + 1:
            dq.popleft()
        
        # Remove smaller elements
        while dq and nums[dq[-1]] < nums[i]:
            dq.pop()
        
        dq.append(i)
        
        # Window is complete
        if i >= k - 1:
            result.append(nums[dq[0]])
    
    return result'''
                }
            ]
        },
        
        # WEEK 5: Trees - Binary Trees & BST
        {
            "week": 5,
            "title": "Binary Trees & Binary Search Trees",
            "topics": [
                "Tree terminology and properties",
                "Binary tree representations",
                "Tree traversals (preorder, inorder, postorder, level-order)",
                "Binary Search Tree property",
                "BST operations (insert, delete, search)",
                "BST validation",
                "Tree height and balance",
                "Recursive vs iterative approaches"
            ],
            "code_examples": [
                {
                    "title": "Binary Search Tree Implementation",
                    "language": "python",
                    "code": '''class TreeNode:
    """Binary tree node"""
    def __init__(self, val=0, left=None, right=None):
        self.val = val
        self.left = left
        self.right = right


class BinarySearchTree:
    """
    Binary Search Tree with all standard operations.
    
    BST Property: For each node N:
    - All values in left subtree < N.val
    - All values in right subtree > N.val
    
    Average case: O(log n) for all operations
    Worst case (unbalanced): O(n)
    """
    
    def __init__(self):
        self.root = None
    
    def insert(self, val):
        """Insert value maintaining BST property"""
        self.root = self._insert_recursive(self.root, val)
    
    def _insert_recursive(self, node, val):
        if not node:
            return TreeNode(val)
        
        if val < node.val:
            node.left = self._insert_recursive(node.left, val)
        elif val > node.val:
            node.right = self._insert_recursive(node.right, val)
        # Duplicate values not inserted
        
        return node
    
    def search(self, val):
        """Search for value - O(log n) average"""
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
    
    def delete(self, val):
        """Delete value from BST"""
        self.root = self._delete_recursive(self.root, val)
    
    def _delete_recursive(self, node, val):
        if not node:
            return None
        
        if val < node.val:
            node.left = self._delete_recursive(node.left, val)
        elif val > node.val:
            node.right = self._delete_recursive(node.right, val)
        else:
            # Node to delete found
            
            # Case 1: Leaf node
            if not node.left and not node.right:
                return None
            
            # Case 2: One child
            if not node.left:
                return node.right
            if not node.right:
                return node.left
            
            # Case 3: Two children
            # Find inorder successor (smallest in right subtree)
            successor = self._find_min(node.right)
            node.val = successor.val
            node.right = self._delete_recursive(node.right, successor.val)
        
        return node
    
    def _find_min(self, node):
        """Find minimum value node"""
        while node.left:
            node = node.left
        return node
    
    def _find_max(self, node):
        """Find maximum value node"""
        while node.right:
            node = node.right
        return node


# Tree Traversals

def inorder_traversal(root):
    """Left -> Root -> Right (gives sorted order for BST)"""
    result = []
    
    def inorder(node):
        if node:
            inorder(node.left)
            result.append(node.val)
            inorder(node.right)
    
    inorder(root)
    return result


def preorder_traversal(root):
    """Root -> Left -> Right"""
    result = []
    
    def preorder(node):
        if node:
            result.append(node.val)
            preorder(node.left)
            preorder(node.right)
    
    preorder(root)
    return result


def postorder_traversal(root):
    """Left -> Right -> Root"""
    result = []
    
    def postorder(node):
        if node:
            postorder(node.left)
            postorder(node.right)
            result.append(node.val)
    
    postorder(root)
    return result


def level_order_traversal(root):
    """BFS - Level by level"""
    if not root:
        return []
    
    from collections import deque
    
    result = []
    queue = deque([root])
    
    while queue:
        level = []
        level_size = len(queue)
        
        for _ in range(level_size):
            node = queue.popleft()
            level.append(node.val)
            
            if node.left:
                queue.append(node.left)
            if node.right:
                queue.append(node.right)
        
        result.append(level)
    
    return result


# Classic Tree Problems

def is_valid_bst(root):
    """
    Validate BST property.
    O(n) time, O(h) space.
    """
    def validate(node, min_val, max_val):
        if not node:
            return True
        
        if node.val <= min_val or node.val >= max_val:
            return False
        
        return (validate(node.left, min_val, node.val) and
                validate(node.right, node.val, max_val))
    
    return validate(root, float("-inf"), float("inf"))


def max_depth(root):
    """Tree height/maximum depth"""
    if not root:
        return 0
    return 1 + max(max_depth(root.left), max_depth(root.right))


def is_balanced(root):
    """
    Check if tree is height-balanced.
    A tree is balanced if heights of subtrees differ by at most 1.
    """
    def check(node):
        if not node:
            return 0
        
        left = check(node.left)
        right = check(node.right)
        
        if left == -1 or right == -1 or abs(left - right) > 1:
            return -1
        
        return 1 + max(left, right)
    
    return check(root) != -1


def lowest_common_ancestor(root, p, q):
    """
    Find LCA of two nodes in BST.
    O(log n) average using BST property.
    """
    while root:
        if p.val < root.val and q.val < root.val:
            root = root.left
        elif p.val > root.val and q.val > root.val:
            root = root.right
        else:
            return root
    
    return None'''
                }
            ]
        },
        
        # WEEK 6: Heaps & Priority Queues
        {
            "week": 6,
            "title": "Heaps & Priority Queues",
            "topics": [
                "Heap property (min-heap, max-heap)",
                "Array representation of heaps",
                "Heapify operations",
                "Insert and extract operations",
                "Build heap from array",
                "Heap sort algorithm",
                "Priority queue ADT",
                "Applications: Top-K, Median finding"
            ],
            "code_examples": [
                {
                    "title": "Binary Heap Implementation",
                    "language": "python",
                    "code": '''class MinHeap:
    """
    Binary Min-Heap implementation.
    
    Heap Property: Parent <= Children
    
    Array representation:
    - Parent of i: (i - 1) // 2
    - Left child of i: 2*i + 1
    - Right child of i: 2*i + 2
    
    Time Complexities:
    - Insert: O(log n)
    - Extract min: O(log n)
    - Get min: O(1)
    - Build heap: O(n)
    """
    
    def __init__(self):
        self.heap = []
    
    def __len__(self):
        return len(self.heap)
    
    def is_empty(self):
        return len(self.heap) == 0
    
    def _parent(self, i):
        return (i - 1) // 2
    
    def _left_child(self, i):
        return 2 * i + 1
    
    def _right_child(self, i):
        return 2 * i + 2
    
    def _swap(self, i, j):
        self.heap[i], self.heap[j] = self.heap[j], self.heap[i]
    
    def _sift_up(self, i):
        """Restore heap property upward"""
        while i > 0 and self.heap[self._parent(i)] > self.heap[i]:
            self._swap(i, self._parent(i))
            i = self._parent(i)
    
    def _sift_down(self, i):
        """Restore heap property downward"""
        min_index = i
        size = len(self.heap)
        
        left = self._left_child(i)
        if left < size and self.heap[left] < self.heap[min_index]:
            min_index = left
        
        right = self._right_child(i)
        if right < size and self.heap[right] < self.heap[min_index]:
            min_index = right
        
        if min_index != i:
            self._swap(i, min_index)
            self._sift_down(min_index)
    
    def insert(self, val):
        """Insert value - O(log n)"""
        self.heap.append(val)
        self._sift_up(len(self.heap) - 1)
    
    def extract_min(self):
        """Remove and return minimum - O(log n)"""
        if self.is_empty():
            raise IndexError("Heap is empty")
        
        min_val = self.heap[0]
        
        # Move last element to root
        self.heap[0] = self.heap[-1]
        self.heap.pop()
        
        # Restore heap property
        if self.heap:
            self._sift_down(0)
        
        return min_val
    
    def peek(self):
        """Return minimum without removing - O(1)"""
        if self.is_empty():
            raise IndexError("Heap is empty")
        return self.heap[0]
    
    @classmethod
    def heapify(cls, arr):
        """
        Build heap from array - O(n)
        
        Start from last non-leaf node and sift down.
        """
        heap = cls()
        heap.heap = arr[:]
        
        # Start from last non-leaf node
        for i in range(len(arr) // 2 - 1, -1, -1):
            heap._sift_down(i)
        
        return heap


def heap_sort(arr):
    """
    Heap Sort - O(n log n) time, O(1) space.
    
    1. Build max-heap
    2. Repeatedly extract max and place at end
    """
    def heapify(arr, n, i):
        largest = i
        left = 2 * i + 1
        right = 2 * i + 2
        
        if left < n and arr[left] > arr[largest]:
            largest = left
        if right < n and arr[right] > arr[largest]:
            largest = right
        
        if largest != i:
            arr[i], arr[largest] = arr[largest], arr[i]
            heapify(arr, n, largest)
    
    n = len(arr)
    
    # Build max-heap
    for i in range(n // 2 - 1, -1, -1):
        heapify(arr, n, i)
    
    # Extract elements
    for i in range(n - 1, 0, -1):
        arr[0], arr[i] = arr[i], arr[0]
        heapify(arr, i, 0)
    
    return arr


# Classic Heap Problems

def find_kth_largest(nums, k):
    """
    Find kth largest using min-heap of size k.
    O(n log k) time, O(k) space.
    """
    import heapq
    
    # Keep k largest elements (min at top)
    heap = []
    
    for num in nums:
        if len(heap) < k:
            heapq.heappush(heap, num)
        elif num > heap[0]:
            heapq.heapreplace(heap, num)  # Pop min, push num
    
    return heap[0]


class MedianFinder:
    """
    Find median from data stream.
    Use two heaps: max-heap for left half, min-heap for right half.
    """
    
    def __init__(self):
        import heapq
        self.left = []   # Max-heap (negate values)
        self.right = []  # Min-heap
    
    def addNum(self, num):
        import heapq
        
        # Add to appropriate heap
        if not self.left or num <= -self.left[0]:
            heapq.heappush(self.left, -num)
        else:
            heapq.heappush(self.right, num)
        
        # Balance heaps (left can have at most 1 more)
        if len(self.left) > len(self.right) + 1:
            heapq.heappush(self.right, -heapq.heappop(self.left))
        elif len(self.right) > len(self.left):
            heapq.heappush(self.left, -heapq.heappop(self.right))
    
    def findMedian(self):
        if len(self.left) > len(self.right):
            return -self.left[0]
        return (-self.left[0] + self.right[0]) / 2


def merge_k_sorted_lists(lists):
    """
    Merge k sorted linked lists using min-heap.
    O(n log k) time, where n = total nodes.
    """
    import heapq
    
    heap = []
    
    # Add first node from each list
    for i, lst in enumerate(lists):
        if lst:
            heapq.heappush(heap, (lst.val, i, lst))
    
    dummy = ListNode(0)
    current = dummy
    
    while heap:
        val, i, node = heapq.heappop(heap)
        current.next = node
        current = current.next
        
        if node.next:
            heapq.heappush(heap, (node.next.val, i, node.next))
    
    return dummy.next'''
                }
            ]
        },
        
        # WEEK 7-8: Hash Tables
        {
            "week": 7,
            "title": "Hash Tables - Part 1",
            "topics": [
                "Hash function design principles",
                "Collision resolution: Chaining",
                "Collision resolution: Open addressing",
                "Linear probing, Quadratic probing",
                "Double hashing",
                "Load factor and rehashing",
                "Hash table analysis"
            ]
        },
        {
            "week": 8,
            "title": "Hash Tables - Part 2 & Applications",
            "topics": [
                "Perfect hashing",
                "Cuckoo hashing",
                "Bloom filters",
                "Count-min sketch",
                "Hash table applications",
                "Designing hash functions for custom objects",
                "Consistent hashing"
            ],
            "code_examples": [
                {
                    "title": "Hash Table Implementation",
                    "language": "python",
                    "code": '''class HashTable:
    """
    Hash Table with chaining for collision resolution.
    
    Average case: O(1) for all operations
    Worst case: O(n) when many collisions
    
    Load factor α = n/m (items/buckets)
    Keep α < 0.75 for good performance
    """
    
    def __init__(self, initial_capacity=16):
        self.capacity = initial_capacity
        self.size = 0
        self.buckets = [[] for _ in range(self.capacity)]
        self.LOAD_FACTOR_THRESHOLD = 0.75
    
    def _hash(self, key):
        """Hash function - maps key to bucket index"""
        return hash(key) % self.capacity
    
    def _resize(self):
        """Double capacity and rehash all items"""
        old_buckets = self.buckets
        self.capacity *= 2
        self.buckets = [[] for _ in range(self.capacity)]
        self.size = 0
        
        for bucket in old_buckets:
            for key, value in bucket:
                self.put(key, value)
    
    def put(self, key, value):
        """Insert or update key-value pair"""
        # Check load factor
        if self.size / self.capacity >= self.LOAD_FACTOR_THRESHOLD:
            self._resize()
        
        index = self._hash(key)
        bucket = self.buckets[index]
        
        # Update if key exists
        for i, (k, v) in enumerate(bucket):
            if k == key:
                bucket[i] = (key, value)
                return
        
        # Insert new key
        bucket.append((key, value))
        self.size += 1
    
    def get(self, key, default=None):
        """Retrieve value by key"""
        index = self._hash(key)
        bucket = self.buckets[index]
        
        for k, v in bucket:
            if k == key:
                return v
        
        return default
    
    def remove(self, key):
        """Remove key-value pair"""
        index = self._hash(key)
        bucket = self.buckets[index]
        
        for i, (k, v) in enumerate(bucket):
            if k == key:
                del bucket[i]
                self.size -= 1
                return v
        
        raise KeyError(key)
    
    def __contains__(self, key):
        """Check if key exists"""
        index = self._hash(key)
        bucket = self.buckets[index]
        return any(k == key for k, v in bucket)
    
    def __len__(self):
        return self.size
    
    def keys(self):
        """Return all keys"""
        for bucket in self.buckets:
            for k, v in bucket:
                yield k
    
    def values(self):
        """Return all values"""
        for bucket in self.buckets:
            for k, v in bucket:
                yield v
    
    def items(self):
        """Return all key-value pairs"""
        for bucket in self.buckets:
            for item in bucket:
                yield item


class HashTableOpenAddressing:
    """
    Hash Table with open addressing (linear probing).
    """
    
    DELETED = object()  # Tombstone marker
    
    def __init__(self, initial_capacity=16):
        self.capacity = initial_capacity
        self.size = 0
        self.keys = [None] * self.capacity
        self.values = [None] * self.capacity
    
    def _hash(self, key):
        return hash(key) % self.capacity
    
    def _probe(self, key):
        """Linear probing - find slot for key"""
        index = self._hash(key)
        
        while self.keys[index] is not None:
            if self.keys[index] == key:
                return index
            if self.keys[index] is self.DELETED:
                # Can insert here
                return index
            
            index = (index + 1) % self.capacity
        
        return index
    
    def put(self, key, value):
        if self.size / self.capacity >= 0.5:
            self._resize()
        
        index = self._probe(key)
        
        if self.keys[index] is None or self.keys[index] is self.DELETED:
            self.size += 1
        
        self.keys[index] = key
        self.values[index] = value
    
    def get(self, key, default=None):
        index = self._hash(key)
        
        while self.keys[index] is not None:
            if self.keys[index] == key:
                return self.values[index]
            index = (index + 1) % self.capacity
        
        return default
    
    def remove(self, key):
        index = self._hash(key)
        
        while self.keys[index] is not None:
            if self.keys[index] == key:
                value = self.values[index]
                self.keys[index] = self.DELETED
                self.values[index] = None
                self.size -= 1
                return value
            index = (index + 1) % self.capacity
        
        raise KeyError(key)
    
    def _resize(self):
        old_keys = self.keys
        old_values = self.values
        
        self.capacity *= 2
        self.keys = [None] * self.capacity
        self.values = [None] * self.capacity
        self.size = 0
        
        for i, key in enumerate(old_keys):
            if key is not None and key is not self.DELETED:
                self.put(key, old_values[i])


# Hash Table Applications

def two_sum_hash(nums, target):
    """O(n) using hash table"""
    seen = {}
    for i, num in enumerate(nums):
        complement = target - num
        if complement in seen:
            return [seen[complement], i]
        seen[num] = i
    return []


def group_anagrams(strs):
    """Group strings that are anagrams"""
    from collections import defaultdict
    
    groups = defaultdict(list)
    
    for s in strs:
        # Use sorted string as key
        key = tuple(sorted(s))
        groups[key].append(s)
    
    return list(groups.values())


def longest_consecutive_sequence(nums):
    """
    Find longest consecutive sequence.
    O(n) using hash set.
    """
    num_set = set(nums)
    longest = 0
    
    for num in num_set:
        # Only start counting from sequence start
        if num - 1 not in num_set:
            current_num = num
            current_length = 1
            
            while current_num + 1 in num_set:
                current_num += 1
                current_length += 1
            
            longest = max(longest, current_length)
    
    return longest


def subarray_sum_equals_k(nums, k):
    """
    Count subarrays with sum = k.
    O(n) using prefix sum + hash map.
    """
    from collections import defaultdict
    
    count = 0
    prefix_sum = 0
    sum_count = defaultdict(int)
    sum_count[0] = 1  # Empty prefix
    
    for num in nums:
        prefix_sum += num
        
        # Check if (prefix_sum - k) exists
        count += sum_count[prefix_sum - k]
        
        sum_count[prefix_sum] += 1
    
    return count'''
                }
            ]
        },
        
        # WEEK 9-10: Graphs
        {
            "week": 9,
            "title": "Graph Fundamentals & Traversals",
            "topics": [
                "Graph terminology",
                "Graph representations (adjacency list, matrix)",
                "Breadth-First Search (BFS)",
                "Depth-First Search (DFS)",
                "Connected components",
                "Cycle detection",
                "Topological sorting"
            ]
        },
        {
            "week": 10,
            "title": "Graph Algorithms",
            "topics": [
                "Shortest paths: Dijkstra's algorithm",
                "Shortest paths: Bellman-Ford",
                "All-pairs shortest paths: Floyd-Warshall",
                "Minimum Spanning Trees: Prim's and Kruskal's",
                "Union-Find data structure",
                "Network flow introduction"
            ],
            "code_examples": [
                {
                    "title": "Graph Algorithms",
                    "language": "python",
                    "code": '''from collections import defaultdict, deque
import heapq

class Graph:
    """
    Graph implementation using adjacency list.
    Supports both directed and undirected graphs.
    """
    
    def __init__(self, directed=False):
        self.graph = defaultdict(list)
        self.directed = directed
    
    def add_edge(self, u, v, weight=1):
        """Add edge u -> v with optional weight"""
        self.graph[u].append((v, weight))
        if not self.directed:
            self.graph[v].append((u, weight))
    
    def add_vertex(self, v):
        """Add isolated vertex"""
        if v not in self.graph:
            self.graph[v] = []
    
    def get_vertices(self):
        """Return all vertices"""
        return list(self.graph.keys())
    
    def get_neighbors(self, v):
        """Return neighbors of vertex v"""
        return self.graph[v]


def bfs(graph, start):
    """
    Breadth-First Search.
    O(V + E) time and space.
    
    Applications:
    - Shortest path in unweighted graph
    - Level-order traversal
    - Finding connected components
    """
    visited = set()
    queue = deque([start])
    visited.add(start)
    result = []
    
    while queue:
        vertex = queue.popleft()
        result.append(vertex)
        
        for neighbor, _ in graph.get_neighbors(vertex):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
    
    return result


def dfs(graph, start, visited=None):
    """
    Depth-First Search (recursive).
    O(V + E) time, O(V) space.
    
    Applications:
    - Cycle detection
    - Topological sorting
    - Finding strongly connected components
    """
    if visited is None:
        visited = set()
    
    visited.add(start)
    result = [start]
    
    for neighbor, _ in graph.get_neighbors(start):
        if neighbor not in visited:
            result.extend(dfs(graph, neighbor, visited))
    
    return result


def dfs_iterative(graph, start):
    """DFS using explicit stack"""
    visited = set()
    stack = [start]
    result = []
    
    while stack:
        vertex = stack.pop()
        
        if vertex not in visited:
            visited.add(vertex)
            result.append(vertex)
            
            for neighbor, _ in graph.get_neighbors(vertex):
                if neighbor not in visited:
                    stack.append(neighbor)
    
    return result


def dijkstra(graph, start):
    """
    Dijkstra's Shortest Path Algorithm.
    O((V + E) log V) with binary heap.
    
    Works for non-negative edge weights only.
    """
    distances = {v: float('inf') for v in graph.get_vertices()}
    distances[start] = 0
    predecessors = {v: None for v in graph.get_vertices()}
    
    # Min-heap: (distance, vertex)
    heap = [(0, start)]
    visited = set()
    
    while heap:
        dist, u = heapq.heappop(heap)
        
        if u in visited:
            continue
        visited.add(u)
        
        for v, weight in graph.get_neighbors(u):
            if v not in visited:
                new_dist = dist + weight
                
                if new_dist < distances[v]:
                    distances[v] = new_dist
                    predecessors[v] = u
                    heapq.heappush(heap, (new_dist, v))
    
    return distances, predecessors


def bellman_ford(graph, start):
    """
    Bellman-Ford Algorithm.
    O(V * E) time.
    
    Works with negative edge weights.
    Can detect negative cycles.
    """
    vertices = graph.get_vertices()
    distances = {v: float('inf') for v in vertices}
    distances[start] = 0
    
    # Relax edges V-1 times
    for _ in range(len(vertices) - 1):
        for u in vertices:
            for v, weight in graph.get_neighbors(u):
                if distances[u] + weight < distances[v]:
                    distances[v] = distances[u] + weight
    
    # Check for negative cycles
    for u in vertices:
        for v, weight in graph.get_neighbors(u):
            if distances[u] + weight < distances[v]:
                raise ValueError("Graph contains negative cycle")
    
    return distances


def topological_sort(graph):
    """
    Topological Sort using Kahn's Algorithm (BFS).
    O(V + E) time.
    
    For DAGs only. Returns order such that
    for every edge u->v, u comes before v.
    """
    # Calculate in-degrees
    in_degree = defaultdict(int)
    for u in graph.get_vertices():
        for v, _ in graph.get_neighbors(u):
            in_degree[v] += 1
    
    # Start with vertices having no incoming edges
    queue = deque([v for v in graph.get_vertices() if in_degree[v] == 0])
    result = []
    
    while queue:
        u = queue.popleft()
        result.append(u)
        
        for v, _ in graph.get_neighbors(u):
            in_degree[v] -= 1
            if in_degree[v] == 0:
                queue.append(v)
    
    if len(result) != len(graph.get_vertices()):
        raise ValueError("Graph has cycle - no topological order")
    
    return result


class UnionFind:
    """
    Union-Find (Disjoint Set Union) data structure.
    
    With path compression and union by rank:
    - Find: O(α(n)) ≈ O(1) amortized
    - Union: O(α(n)) ≈ O(1) amortized
    
    Applications:
    - Kruskal's MST
    - Connected components
    - Cycle detection
    """
    
    def __init__(self, n):
        self.parent = list(range(n))
        self.rank = [0] * n
        self.count = n  # Number of components
    
    def find(self, x):
        """Find with path compression"""
        if self.parent[x] != x:
            self.parent[x] = self.find(self.parent[x])
        return self.parent[x]
    
    def union(self, x, y):
        """Union by rank"""
        root_x = self.find(x)
        root_y = self.find(y)
        
        if root_x == root_y:
            return False  # Already in same set
        
        # Attach smaller tree to larger tree
        if self.rank[root_x] < self.rank[root_y]:
            self.parent[root_x] = root_y
        elif self.rank[root_x] > self.rank[root_y]:
            self.parent[root_y] = root_x
        else:
            self.parent[root_y] = root_x
            self.rank[root_x] += 1
        
        self.count -= 1
        return True
    
    def connected(self, x, y):
        """Check if x and y are in same component"""
        return self.find(x) == self.find(y)


def kruskal_mst(edges, n):
    """
    Kruskal's Minimum Spanning Tree Algorithm.
    O(E log E) time.
    
    edges: list of (weight, u, v)
    n: number of vertices
    """
    # Sort edges by weight
    edges.sort()
    
    uf = UnionFind(n)
    mst = []
    mst_weight = 0
    
    for weight, u, v in edges:
        if uf.union(u, v):
            mst.append((u, v, weight))
            mst_weight += weight
            
            if len(mst) == n - 1:
                break
    
    return mst, mst_weight'''
                }
            ]
        },
        
        # WEEK 11-12: Sorting and Searching
        {
            "week": 11,
            "title": "Sorting Algorithms",
            "topics": [
                "Comparison-based sorting lower bound",
                "Quick Sort and partitioning",
                "Merge Sort",
                "Heap Sort",
                "Counting Sort, Radix Sort, Bucket Sort",
                "Stability in sorting",
                "External sorting"
            ]
        },
        {
            "week": 12,
            "title": "Searching & Advanced Techniques",
            "topics": [
                "Binary search variations",
                "Ternary search",
                "Exponential search",
                "Search in rotated arrays",
                "Interpolation search",
                "Pattern matching algorithms"
            ]
        },
        
        # WEEK 13-14: Dynamic Programming
        {
            "week": 13,
            "title": "Dynamic Programming - Part 1",
            "topics": [
                "DP principles: Optimal substructure, overlapping subproblems",
                "Memoization (top-down)",
                "Tabulation (bottom-up)",
                "1D DP problems",
                "Fibonacci, climbing stairs",
                "House robber, coin change"
            ]
        },
        {
            "week": 14,
            "title": "Dynamic Programming - Part 2",
            "topics": [
                "2D DP problems",
                "Grid-based DP",
                "String DP (LCS, Edit Distance)",
                "Knapsack problems",
                "Matrix chain multiplication",
                "DP optimization techniques"
            ],
            "code_examples": [
                {
                    "title": "Dynamic Programming Patterns",
                    "language": "python",
                    "code": '''# 1D DP PROBLEMS

def fibonacci(n):
    """
    Fibonacci with memoization and tabulation.
    """
    # Memoization (top-down)
    def fib_memo(n, memo={}):
        if n in memo:
            return memo[n]
        if n <= 1:
            return n
        memo[n] = fib_memo(n-1, memo) + fib_memo(n-2, memo)
        return memo[n]
    
    # Tabulation (bottom-up)
    def fib_tab(n):
        if n <= 1:
            return n
        dp = [0] * (n + 1)
        dp[1] = 1
        for i in range(2, n + 1):
            dp[i] = dp[i-1] + dp[i-2]
        return dp[n]
    
    # Space optimized
    def fib_opt(n):
        if n <= 1:
            return n
        prev, curr = 0, 1
        for _ in range(2, n + 1):
            prev, curr = curr, prev + curr
        return curr
    
    return fib_opt(n)


def coin_change(coins, amount):
    """
    Minimum coins to make amount.
    O(n * amount) time, O(amount) space.
    """
    dp = [float('inf')] * (amount + 1)
    dp[0] = 0
    
    for i in range(1, amount + 1):
        for coin in coins:
            if coin <= i and dp[i - coin] + 1 < dp[i]:
                dp[i] = dp[i - coin] + 1
    
    return dp[amount] if dp[amount] != float('inf') else -1


def longest_increasing_subsequence(nums):
    """
    LIS length.
    O(n log n) using binary search.
    """
    from bisect import bisect_left
    
    tails = []
    
    for num in nums:
        pos = bisect_left(tails, num)
        if pos == len(tails):
            tails.append(num)
        else:
            tails[pos] = num
    
    return len(tails)


def house_robber(nums):
    """
    Maximum money without robbing adjacent houses.
    O(n) time, O(1) space.
    """
    if not nums:
        return 0
    if len(nums) == 1:
        return nums[0]
    
    prev2, prev1 = 0, nums[0]
    
    for i in range(1, len(nums)):
        current = max(prev1, prev2 + nums[i])
        prev2, prev1 = prev1, current
    
    return prev1


# 2D DP PROBLEMS

def longest_common_subsequence(text1, text2):
    """
    LCS length.
    O(m * n) time and space.
    """
    m, n = len(text1), len(text2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if text1[i-1] == text2[j-1]:
                dp[i][j] = dp[i-1][j-1] + 1
            else:
                dp[i][j] = max(dp[i-1][j], dp[i][j-1])
    
    return dp[m][n]


def edit_distance(word1, word2):
    """
    Minimum edit operations (insert, delete, replace).
    O(m * n) time and space.
    """
    m, n = len(word1), len(word2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    
    # Base cases
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if word1[i-1] == word2[j-1]:
                dp[i][j] = dp[i-1][j-1]
            else:
                dp[i][j] = 1 + min(
                    dp[i-1][j],      # Delete
                    dp[i][j-1],      # Insert
                    dp[i-1][j-1]     # Replace
                )
    
    return dp[m][n]


def knapsack_01(weights, values, capacity):
    """
    0/1 Knapsack - maximize value within weight capacity.
    O(n * capacity) time and space.
    """
    n = len(weights)
    dp = [[0] * (capacity + 1) for _ in range(n + 1)]
    
    for i in range(1, n + 1):
        for w in range(capacity + 1):
            # Don't take item i
            dp[i][w] = dp[i-1][w]
            
            # Take item i if it fits
            if weights[i-1] <= w:
                dp[i][w] = max(
                    dp[i][w],
                    dp[i-1][w - weights[i-1]] + values[i-1]
                )
    
    return dp[n][capacity]


def unique_paths(m, n):
    """
    Count paths from top-left to bottom-right.
    Can only move right or down.
    O(m * n) time, O(n) space.
    """
    dp = [1] * n
    
    for _ in range(1, m):
        for j in range(1, n):
            dp[j] += dp[j-1]
    
    return dp[n-1]


def max_profit_stock(prices):
    """
    Best time to buy and sell stock.
    O(n) time, O(1) space.
    """
    if not prices:
        return 0
    
    min_price = prices[0]
    max_profit = 0
    
    for price in prices:
        min_price = min(min_price, price)
        max_profit = max(max_profit, price - min_price)
    
    return max_profit'''
                }
            ]
        },
        
        # WEEK 15: Advanced Topics & Review
        {
            "week": 15,
            "title": "Advanced Topics & Final Review",
            "topics": [
                "Tries (Prefix trees)",
                "Segment trees",
                "Fenwick trees (Binary Indexed Trees)",
                "Advanced string algorithms",
                "Computational geometry basics",
                "Final review and exam preparation"
            ]
        }
    ],
    
    "projects": [
        {
            "name": "LRU Cache Implementation",
            "description": "Build an LRU cache using hash map and doubly linked list",
            "difficulty": "medium",
            "skills": ["Hash tables", "Linked lists", "System design"]
        },
        {
            "name": "Text Autocomplete System",
            "description": "Build autocomplete using Trie data structure",
            "difficulty": "hard",
            "skills": ["Tries", "Priority queues", "String algorithms"]
        },
        {
            "name": "Social Network Graph Analysis",
            "description": "Analyze connections using graph algorithms",
            "difficulty": "hard",
            "skills": ["Graphs", "BFS/DFS", "Union-Find"]
        },
        {
            "name": "Algorithmic Trading Simulator",
            "description": "Apply DP to find optimal trading strategies",
            "difficulty": "expert",
            "skills": ["Dynamic programming", "Arrays", "Optimization"]
        }
    ],
    
    "assessment": {
        "weekly_quizzes": 14,
        "coding_assignments": 10,
        "midterm_exam": True,
        "final_exam": True,
        "final_project": True,
        "grading": {
            "quizzes": "20%",
            "assignments": "30%",
            "midterm": "15%",
            "final_exam": "20%",
            "final_project": "15%"
        }
    }
}

# ============================================================================
# OBJECT-ORIENTED PROGRAMMING - COMPLETE COURSE  
# ============================================================================

OOP_COURSE = {
    "id": "oop_complete",
    "code": "CS 202",
    "title": "Object-Oriented Programming & Design",
    "subtitle": "Mastering Software Design Principles",
    "credits": 4,
    "hours": 75,
    "weeks": 15,
    "level": "intermediate",
    "prerequisites": ["Programming Fundamentals"],
    "description": """Master object-oriented programming principles and design patterns.
Learn to design maintainable, extensible, and robust software systems using proven
OOP techniques and industry best practices.""",
    
    "learning_objectives": [
        "Apply the four pillars of OOP: Encapsulation, Inheritance, Polymorphism, Abstraction",
        "Design classes following SOLID principles",
        "Implement common design patterns (Creational, Structural, Behavioral)",
        "Write clean, maintainable, and testable code",
        "Use UML for software design documentation",
        "Apply refactoring techniques to improve code quality",
        "Design systems using composition over inheritance",
        "Implement proper error handling and validation"
    ],
    
    "weeks_summary": [
        {"week": 1, "title": "OOP Fundamentals", "topics": ["Classes and Objects", "Constructors", "Properties", "Methods"]},
        {"week": 2, "title": "Encapsulation", "topics": ["Access modifiers", "Getters/Setters", "Data hiding", "Immutability"]},
        {"week": 3, "title": "Inheritance", "topics": ["Class hierarchies", "Method overriding", "super()", "Abstract classes"]},
        {"week": 4, "title": "Polymorphism", "topics": ["Method overloading", "Dynamic dispatch", "Duck typing", "Interfaces"]},
        {"week": 5, "title": "Abstraction & Interfaces", "topics": ["Abstract classes", "Interfaces", "Protocols", "Contracts"]},
        {"week": 6, "title": "SOLID Principles I", "topics": ["Single Responsibility", "Open/Closed", "Liskov Substitution"]},
        {"week": 7, "title": "SOLID Principles II", "topics": ["Interface Segregation", "Dependency Inversion", "Dependency Injection"]},
        {"week": 8, "title": "Creational Patterns", "topics": ["Singleton", "Factory", "Abstract Factory", "Builder", "Prototype"]},
        {"week": 9, "title": "Structural Patterns", "topics": ["Adapter", "Bridge", "Composite", "Decorator", "Facade", "Proxy"]},
        {"week": 10, "title": "Behavioral Patterns I", "topics": ["Observer", "Strategy", "Command", "State"]},
        {"week": 11, "title": "Behavioral Patterns II", "topics": ["Template Method", "Iterator", "Chain of Responsibility", "Mediator"]},
        {"week": 12, "title": "UML & Design", "topics": ["Class diagrams", "Sequence diagrams", "Use case diagrams", "Design documentation"]},
        {"week": 13, "title": "Testing & TDD", "topics": ["Unit testing", "Mocking", "Test-Driven Development", "Code coverage"]},
        {"week": 14, "title": "Refactoring", "topics": ["Code smells", "Refactoring techniques", "Legacy code", "Technical debt"]},
        {"week": 15, "title": "Advanced Topics", "topics": ["Composition vs Inheritance", "Mixins", "Metaclasses", "Final review"]}
    ],
    
    "key_content": {
        "solid_principles": {
            "S": "Single Responsibility - A class should have only one reason to change",
            "O": "Open/Closed - Open for extension, closed for modification",
            "L": "Liskov Substitution - Subtypes must be substitutable for base types",
            "I": "Interface Segregation - Many specific interfaces > one general interface",
            "D": "Dependency Inversion - Depend on abstractions, not concretions"
        },
        "design_patterns": {
            "creational": ["Singleton", "Factory Method", "Abstract Factory", "Builder", "Prototype"],
            "structural": ["Adapter", "Bridge", "Composite", "Decorator", "Facade", "Flyweight", "Proxy"],
            "behavioral": ["Chain of Responsibility", "Command", "Iterator", "Mediator", "Memento", "Observer", "State", "Strategy", "Template Method", "Visitor"]
        }
    }
}

# ============================================================================
# DATABASE SYSTEMS - COMPLETE COURSE
# ============================================================================

DATABASE_COURSE = {
    "id": "db_complete",
    "code": "CS 203",
    "title": "Database Systems",
    "subtitle": "From Fundamentals to Advanced Data Management",
    "credits": 4,
    "hours": 75,
    "weeks": 15,
    "level": "intermediate",
    "prerequisites": ["Data Structures", "Programming Fundamentals"],
    "description": """Comprehensive study of database systems including relational databases,
SQL, normalization, transactions, indexing, query optimization, and NoSQL systems.
Learn to design, implement, and optimize database solutions for real-world applications.""",
    
    "learning_objectives": [
        "Design normalized relational database schemas",
        "Write complex SQL queries including joins, subqueries, and window functions",
        "Understand and apply ACID properties and transaction management",
        "Design and use indexes for query optimization",
        "Apply query optimization techniques",
        "Understand NoSQL databases and when to use them",
        "Implement database security best practices",
        "Design scalable database architectures"
    ],
    
    "weeks_summary": [
        {"week": 1, "title": "Database Fundamentals", "topics": ["DBMS concepts", "Data models", "Database architecture"]},
        {"week": 2, "title": "Relational Model", "topics": ["Relations", "Keys", "Relational algebra", "Integrity constraints"]},
        {"week": 3, "title": "SQL Basics", "topics": ["SELECT", "INSERT", "UPDATE", "DELETE", "Data types"]},
        {"week": 4, "title": "Advanced SQL", "topics": ["JOINs", "Subqueries", "Set operations", "CASE expressions"]},
        {"week": 5, "title": "Aggregation & Grouping", "topics": ["GROUP BY", "HAVING", "Aggregate functions", "Window functions"]},
        {"week": 6, "title": "Database Design", "topics": ["ER diagrams", "Entity relationships", "Cardinality", "Schema design"]},
        {"week": 7, "title": "Normalization", "topics": ["1NF", "2NF", "3NF", "BCNF", "Denormalization trade-offs"]},
        {"week": 8, "title": "Indexing", "topics": ["B-tree indexes", "Hash indexes", "Covering indexes", "Index selection"]},
        {"week": 9, "title": "Query Optimization", "topics": ["Query plans", "Cost estimation", "Optimization strategies", "EXPLAIN"]},
        {"week": 10, "title": "Transactions", "topics": ["ACID properties", "Isolation levels", "Concurrency control", "Deadlocks"]},
        {"week": 11, "title": "Stored Procedures", "topics": ["Functions", "Procedures", "Triggers", "Cursors"]},
        {"week": 12, "title": "NoSQL Databases", "topics": ["Document stores", "Key-value", "Column-family", "Graph databases"]},
        {"week": 13, "title": "Database Security", "topics": ["Authentication", "Authorization", "SQL injection", "Encryption"]},
        {"week": 14, "title": "Distributed Databases", "topics": ["Replication", "Sharding", "CAP theorem", "Consistency models"]},
        {"week": 15, "title": "Advanced Topics", "topics": ["Data warehousing", "OLAP", "Big data", "Final review"]}
    ],
    
    "key_content": {
        "normalization": {
            "1NF": "Atomic values only, no repeating groups",
            "2NF": "1NF + No partial dependencies on composite key",
            "3NF": "2NF + No transitive dependencies",
            "BCNF": "3NF + Every determinant is a candidate key"
        },
        "acid_properties": {
            "A": "Atomicity - All or nothing",
            "C": "Consistency - Valid state transitions only",
            "I": "Isolation - Transactions don't interfere",
            "D": "Durability - Committed data persists"
        },
        "isolation_levels": [
            "READ UNCOMMITTED - Allows dirty reads",
            "READ COMMITTED - Prevents dirty reads",
            "REPEATABLE READ - Prevents non-repeatable reads",
            "SERIALIZABLE - Full isolation"
        ]
    }
}

# ============================================================================
# COMPLETE CS CLASSES REGISTRY
# ============================================================================

# Import advanced classes
from cs_classes_advanced import (
    OPERATING_SYSTEMS_COURSE,
    COMPUTER_NETWORKS_COURSE,
    COMPILER_DESIGN_COURSE,
    GAME_DEV_FUNDAMENTALS_COURSE,
    GAME_ENGINE_COURSE,
    GRAPHICS_PROGRAMMING_COURSE,
    GAME_AI_PHYSICS_COURSE
)

CS_CLASSES = {
    # Core CS Courses
    "data_structures": DATA_STRUCTURES_COURSE,
    "oop": OOP_COURSE,
    "databases": DATABASE_COURSE,
    
    # Advanced CS Courses
    "operating_systems": OPERATING_SYSTEMS_COURSE,
    "networks": COMPUTER_NETWORKS_COURSE,
    "compilers": COMPILER_DESIGN_COURSE,
    
    # Game Development Track
    "gamedev_fundamentals": GAME_DEV_FUNDAMENTALS_COURSE,
    "game_engine": GAME_ENGINE_COURSE,
    "graphics_programming": GRAPHICS_PROGRAMMING_COURSE,
    "game_ai_physics": GAME_AI_PHYSICS_COURSE
}

def get_class(class_id: str) -> dict:
    """Get a specific CS class by ID.
    
    Accepts EITHER the registry key (e.g. 'data_structures') OR the class
    document's own 'id' field (e.g. 'ds_complete'). The list endpoint exposes
    the latter, so lookup must support both — otherwise every detail click
    returns a 404, which the user sees as a 'broken promise'.
    """
    # 1) registry-key match
    direct = CS_CLASSES.get(class_id)
    if direct:
        return direct
    # 2) inner-id match
    for c in CS_CLASSES.values():
        if isinstance(c, dict) and c.get("id") == class_id:
            return c
    # 3) case-insensitive fallback on either
    lower = class_id.lower()
    for key, c in CS_CLASSES.items():
        if key.lower() == lower:
            return c
        if isinstance(c, dict) and str(c.get("id", "")).lower() == lower:
            return c
    return None

def get_all_classes() -> list:
    """Get all available CS classes"""
    return list(CS_CLASSES.values())

def get_class_summary() -> dict:
    """Get summary of all classes"""
    return {
        "total_classes": len(CS_CLASSES),
        "total_hours": sum(c["hours"] for c in CS_CLASSES.values()),
        "classes": [
            {
                "id": c["id"],
                "code": c["code"],
                "title": c["title"],
                "hours": c["hours"],
                "weeks": c["weeks"]
            }
            for c in CS_CLASSES.values()
        ]
    }
