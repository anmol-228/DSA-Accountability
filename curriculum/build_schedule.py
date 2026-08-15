"""Builds curriculum/schedule.json from the canonical 135-day plan.

This is the single source of truth transcription of the master curriculum.
Run `python build_schedule.py` from this directory to regenerate schedule.json.
Do NOT reorder days. Do NOT add solutions here — only problem references and
learning topics.
"""
from __future__ import annotations

import json
from pathlib import Path

DAYS: list[dict] = []


def LC(number: int, title: str, note: str | None = None) -> dict:
    return {"kind": "leetcode", "leetcode_number": number, "title": title, "note": note}


def REV(number: int, title: str) -> dict:
    return {"kind": "revision", "leetcode_number": number, "title": title}


def _default_pascal_case(title: str) -> str:
    import re
    words = re.split(r"[^A-Za-z0-9]+", title)
    return "".join(w[:1].upper() + w[1:] for w in words if w)


# Explicit canonical filenames for every standalone Java exercise across the
# curriculum. Deliberately NOT purely inferred from the display title at
# runtime — naive PascalCase of "Maximum of 3" would produce
# "MaximumOf3.java", not the correct "MaximumOfThree.java" that the actual
# skeleton file (and the real learner repo) uses. Add new exercise titles
# here as new curriculum days introduce them.
EXERCISE_FILENAMES: dict[str, str] = {
    "Even/Odd": "EvenOdd",
    "Maximum of 3": "MaximumOfThree",
    "Simple Calculator": "SimpleCalculator",
    "Leap Year": "LeapYear",
    "Factorial": "Factorial",
    "Prime check": "PrimeCheck",
    "Fibonacci": "Fibonacci",
    "Reverse a number": "ReverseNumber",
    "Palindrome number": "PalindromeNumber",
    "Bubble Sort": "BubbleSort",
    "Selection Sort": "SelectionSort",
    "Insertion Sort": "InsertionSort",
    "Recursive factorial": "RecursiveFactorial",
    "Recursive Fibonacci": "RecursiveFibonacci",
    "Recursive power": "RecursivePower",
    "Recursive array sum": "RecursiveArraySum",
}


def EX(title: str, filename: str | None = None) -> dict:
    canonical = filename or EXERCISE_FILENAMES.get(title) or _default_pascal_case(title)
    return {"kind": "exercise", "title": title, "filename": canonical}


def LEARN_TASK(title: str) -> dict:
    return {"kind": "learn", "title": title}


def CONCEPT(title: str, bullets: list[str]) -> dict:
    return {"kind": "concept", "title": title, "bullets": bullets}


def OA(title: str, minutes: int, problems: list[dict], note: str | None = None) -> dict:
    return {"kind": "oa", "title": title, "minutes": minutes, "problems": problems, "note": note}


def MOCK(title: str, items: list[dict], note: str | None = None) -> dict:
    return {"kind": "mock", "title": title, "items": items, "note": note}


def REPAIR(title: str, note: str) -> dict:
    return {"kind": "repair", "title": title, "note": note}


def D(day: int, title: str, topic: str, learn: list[str] | None = None,
      exercises: list[str] | None = None, problems: list[dict] | None = None,
      core_cs: dict | None = None, extra: list[dict] | None = None,
      is_oa: bool = False, is_mock: bool = False) -> None:
    items: list[dict] = []
    if learn:
        items.append({"kind": "learn_group", "title": "Learn", "bullets": learn})
    if exercises:
        for e in exercises:
            items.append(EX(e))
    if problems:
        items.extend(problems)
    if extra:
        items.extend(extra)
    if core_cs:
        items.append(core_cs)
    DAYS.append({
        "day": day,
        "title": title,
        "topic": topic,
        "is_oa": is_oa,
        "is_mock": is_mock,
        "items": items,
    })


# ============================================================
# DAYS 1-7 — JAVA / PROGRAMMING FOUNDATION
# ============================================================
D(1, "Java Fundamentals I", "java_foundation",
  learn=["Java program structure", "main", "variables", "primitive data types",
         "operators", "input/output", "Scanner", "if/else"],
  exercises=["Even/Odd", "Maximum of 3", "Simple Calculator", "Leap Year"])

D(2, "Java Fundamentals II", "java_foundation",
  learn=["for", "while", "methods", "basic number logic"],
  exercises=["Factorial", "Prime check", "Fibonacci", "Reverse a number", "Palindrome number"])

D(3, "Arrays I", "java_foundation",
  learn=["arrays", "traversal", "methods with arrays"],
  problems=[LC(1480, "Running Sum of 1d Array"), LC(1672, "Richest Customer Wealth")])

D(4, "Strings I", "java_foundation",
  learn=["String", "char", "StringBuilder"],
  problems=[LC(344, "Reverse String"), LC(125, "Valid Palindrome")])

D(5, "Collections I", "java_foundation",
  learn=["ArrayList", "HashMap", "HashSet"],
  problems=[LC(217, "Contains Duplicate"), LC(242, "Valid Anagram")])

D(6, "Big-O and Sorting Foundations", "java_foundation",
  learn=["Big-O: O(1)", "O(log n)", "O(n)", "O(n log n)", "O(n^2)"],
  exercises=["Bubble Sort", "Selection Sort", "Insertion Sort"])

D(7, "Foundation Revision + Core CS Intro", "java_foundation",
  extra=[REPAIR("Revision", "Re-code selected Day 3-6 work without help.")],
  core_cs=CONCEPT("Core CS Intro", ["OOP", "DBMS", "OS", "Computer Networks"]))

# ============================================================
# DAYS 8-14 — ARRAYS
# ============================================================
D(8, "Arrays II", "arrays", problems=[LC(1, "Two Sum"), LC(121, "Best Time to Buy and Sell Stock")])
D(9, "Arrays III", "arrays", problems=[LC(53, "Maximum Subarray"), LC(88, "Merge Sorted Array")])
D(10, "Arrays IV", "arrays", problems=[LC(283, "Move Zeroes"), LC(26, "Remove Duplicates from Sorted Array")])
D(11, "Arrays V", "arrays", problems=[LC(189, "Rotate Array"), LC(169, "Majority Element")])
D(12, "Arrays VI", "arrays", problems=[LC(268, "Missing Number"), LC(448, "Find All Numbers Disappeared in an Array")])
D(13, "Prefix / Suffix", "arrays", problems=[LC(724, "Find Pivot Index"), LC(238, "Product of Array Except Self")])
D(14, "Arrays Timed Revision", "arrays",
  extra=[REV(1, "Two Sum"), REV(121, "Best Time to Buy and Sell Stock"),
         REV(53, "Maximum Subarray"), REV(238, "Product of Array Except Self")])

# ============================================================
# DAYS 15-21 — TWO POINTERS / SLIDING WINDOW
# ============================================================
D(15, "Two Pointers I", "two_pointers", problems=[LC(167, "Two Sum II - Input Array Is Sorted"), LC(977, "Squares of a Sorted Array")])
D(16, "Two Pointers II", "two_pointers", problems=[LC(11, "Container With Most Water"), LC(15, "3Sum")])
D(17, "Two Pointers III", "two_pointers", problems=[LC(75, "Sort Colors")], extra=[REV(283, "Move Zeroes")])
D(18, "Sliding Window (Fixed)", "sliding_window", problems=[LC(643, "Maximum Average Subarray I"), LC(1456, "Maximum Number of Vowels in a Substring of Given Length")])
D(19, "Sliding Window (Variable)", "sliding_window", problems=[LC(209, "Minimum Size Subarray Sum"), LC(3, "Longest Substring Without Repeating Characters")])
D(20, "Sliding Window II", "sliding_window", problems=[LC(567, "Permutation in String"), LC(424, "Longest Repeating Character Replacement")])
D(21, "Sliding Window Revision", "sliding_window", problems=[LC(1004, "Max Consecutive Ones III")], extra=[REV(3, "Longest Substring Without Repeating Characters"), REV(15, "3Sum")])

# ============================================================
# DAYS 22-28 — HASHING / PREFIX SUM
# ============================================================
D(22, "Hashing I", "hashing", problems=[LC(349, "Intersection of Two Arrays"), LC(350, "Intersection of Two Arrays II")])
D(23, "Hashing II", "hashing", problems=[LC(49, "Group Anagrams"), LC(205, "Isomorphic Strings")])
D(24, "Hashing III", "hashing", problems=[LC(202, "Happy Number"), LC(290, "Word Pattern")],
   core_cs=CONCEPT("OOP Fundamentals", ["class/object", "constructor", "encapsulation"]))
D(25, "Prefix Sum + Hashing", "hashing", problems=[LC(560, "Subarray Sum Equals K")])
D(26, "Prefix Sum + Hashing II", "hashing", problems=[LC(525, "Contiguous Array"), LC(930, "Binary Subarrays With Sum")])
D(27, "Hashing IV", "hashing", problems=[LC(128, "Longest Consecutive Sequence"), LC(36, "Valid Sudoku")],
   core_cs=CONCEPT("OOP Revision", ["inheritance", "polymorphism", "abstraction"]))
D(28, "Hashing Timed Revision", "hashing", extra=[REV(49, "Group Anagrams"), REV(560, "Subarray Sum Equals K"), REV(128, "Longest Consecutive Sequence")])

# ============================================================
# DAYS 29-35 — BINARY SEARCH
# ============================================================
D(29, "Binary Search I", "binary_search", problems=[LC(704, "Binary Search"), LC(35, "Search Insert Position")])
D(30, "Binary Search II", "binary_search", problems=[LC(34, "Find First and Last Position of Element in Sorted Array"), LC(69, "Sqrt(x)")])
D(31, "Binary Search on Rotated Arrays", "binary_search", problems=[LC(153, "Find Minimum in Rotated Sorted Array"), LC(33, "Search in Rotated Sorted Array")])
D(32, "Binary Search III", "binary_search", problems=[LC(162, "Find Peak Element"), LC(74, "Search a 2D Matrix")])
D(33, "Binary Search on Answer I", "binary_search", problems=[LC(875, "Koko Eating Bananas")])
D(34, "Binary Search on Answer II", "binary_search", problems=[LC(1011, "Capacity To Ship Packages Within D Days"), LC(540, "Single Element in a Sorted Array")])
D(35, "Binary Search Revision", "binary_search", extra=[REV(704, "Binary Search"), REV(34, "Find First and Last Position"), REV(33, "Search in Rotated Sorted Array"), REV(875, "Koko Eating Bananas")])

# ============================================================
# DAYS 36-42 — LINKED LISTS
# ============================================================
D(36, "Linked Lists I", "linked_lists", problems=[LC(206, "Reverse Linked List"), LC(876, "Middle of the Linked List")])
D(37, "Fast/Slow Pointers", "linked_lists", problems=[LC(141, "Linked List Cycle"), LC(142, "Linked List Cycle II")])
D(38, "Linked Lists II", "linked_lists", problems=[LC(21, "Merge Two Sorted Lists"), LC(83, "Remove Duplicates from Sorted List")])
D(39, "Linked Lists III", "linked_lists", problems=[LC(19, "Remove Nth Node From End of List"), LC(160, "Intersection of Two Linked Lists")])
D(40, "Linked Lists IV", "linked_lists", problems=[LC(234, "Palindrome Linked List"), LC(203, "Remove Linked List Elements")])
D(41, "Linked Lists V", "linked_lists", problems=[LC(2, "Add Two Numbers"), LC(328, "Odd Even Linked List")])
D(42, "Linked Lists Revision", "linked_lists", extra=[REV(206, "Reverse Linked List"), REV(141, "Linked List Cycle"), REV(19, "Remove Nth Node From End of List"), REV(2, "Add Two Numbers")],
   core_cs=CONCEPT("DBMS Introduction", ["database/table", "keys"]))

# ============================================================
# DAYS 43-49 — STACK / QUEUE
# ============================================================
D(43, "Stack I", "stack_queue", problems=[LC(20, "Valid Parentheses"), LC(155, "Min Stack")])
D(44, "Stack/Queue Interplay", "stack_queue", problems=[LC(225, "Implement Stack using Queues"), LC(232, "Implement Queue using Stacks")])
D(45, "Monotonic Stack I", "stack_queue", problems=[LC(496, "Next Greater Element I"), LC(503, "Next Greater Element II")])
D(46, "Monotonic Stack II", "stack_queue", problems=[LC(739, "Daily Temperatures"), LC(901, "Online Stock Span")])
D(47, "Monotonic Stack Challenge", "stack_queue", problems=[LC(84, "Largest Rectangle in Histogram", note="Treat as a challenge/learning problem.")])
D(48, "Stack Applications", "stack_queue", problems=[LC(150, "Evaluate Reverse Polish Notation"), LC(394, "Decode String")])
D(49, "Stack/Queue Revision", "stack_queue", extra=[REV(20, "Valid Parentheses"), REV(739, "Daily Temperatures"), REV(84, "Largest Rectangle in Histogram")])

# ============================================================
# DAYS 50-56 — RECURSION / BACKTRACKING
# ============================================================
D(50, "Recursion Foundations", "recursion", exercises=["Recursive factorial", "Recursive Fibonacci", "Recursive power", "Recursive array sum"])
D(51, "Backtracking I", "recursion", problems=[LC(78, "Subsets"), LC(46, "Permutations")])
D(52, "Backtracking II", "recursion", problems=[LC(77, "Combinations"), LC(39, "Combination Sum")])
D(53, "Backtracking III", "recursion", problems=[LC(40, "Combination Sum II"), LC(216, "Combination Sum III")])
D(54, "Backtracking IV", "recursion", problems=[LC(17, "Letter Combinations of a Phone Number"), LC(22, "Generate Parentheses")])
D(55, "Backtracking V", "recursion", problems=[LC(79, "Word Search"), LC(131, "Palindrome Partitioning")])
D(56, "Recursion/Backtracking Revision", "recursion", extra=[REV(78, "Subsets"), REV(46, "Permutations"), REV(39, "Combination Sum"), REV(22, "Generate Parentheses")])

# ============================================================
# DAYS 57-63 — TREES I
# ============================================================
D(57, "Trees I", "trees_1", problems=[LC(104, "Maximum Depth of Binary Tree"), LC(100, "Same Tree")])
D(58, "Trees II", "trees_1", problems=[LC(226, "Invert Binary Tree"), LC(101, "Symmetric Tree")])
D(59, "Tree Traversals", "trees_1", problems=[LC(144, "Binary Tree Preorder Traversal"), LC(94, "Binary Tree Inorder Traversal"), LC(145, "Binary Tree Postorder Traversal")])
D(60, "Tree BFS", "trees_1", problems=[LC(102, "Binary Tree Level Order Traversal"), LC(111, "Minimum Depth of Binary Tree")])
D(61, "Trees III", "trees_1", problems=[LC(112, "Path Sum"), LC(543, "Diameter of Binary Tree")])
D(62, "Trees IV", "trees_1", problems=[LC(110, "Balanced Binary Tree"), LC(572, "Subtree of Another Tree")])
D(63, "Trees I Revision", "trees_1", extra=[REV(104, "Maximum Depth of Binary Tree"), REV(102, "Binary Tree Level Order Traversal"), REV(543, "Diameter of Binary Tree"), REV(110, "Balanced Binary Tree")],
   core_cs=CONCEPT("OS Introduction", ["program/process/thread", "scheduling"]))

# ============================================================
# DAYS 64-70 — TREES II
# ============================================================
D(64, "Trees V", "trees_2", problems=[LC(199, "Binary Tree Right Side View"), LC(103, "Binary Tree Zigzag Level Order Traversal")])
D(65, "Tree Construction I", "trees_2", problems=[LC(105, "Construct Binary Tree from Preorder and Inorder Traversal")])
D(66, "Tree Construction II", "trees_2", problems=[LC(106, "Construct Binary Tree from Inorder and Postorder Traversal")])
D(67, "Trees VI", "trees_2", problems=[LC(236, "Lowest Common Ancestor of a Binary Tree"), LC(437, "Path Sum III")])
D(68, "Trees VII", "trees_2", problems=[LC(129, "Sum Root to Leaf Numbers"), LC(662, "Maximum Width of Binary Tree")])
D(69, "Trees VIII", "trees_2", problems=[LC(114, "Flatten Binary Tree to Linked List"), LC(116, "Populating Next Right Pointers in Each Node")])
D(70, "Trees II Revision", "trees_2", extra=[REV(105, "Construct Binary Tree from Preorder and Inorder Traversal"), REV(236, "Lowest Common Ancestor of a Binary Tree"), REV(437, "Path Sum III"), REV(114, "Flatten Binary Tree to Linked List")])

# ============================================================
# DAYS 71-77 — BST
# ============================================================
D(71, "BST I", "bst", problems=[LC(700, "Search in a Binary Search Tree"), LC(701, "Insert into a Binary Search Tree")])
D(72, "BST II", "bst", problems=[LC(98, "Validate Binary Search Tree"), LC(230, "Kth Smallest Element in a BST")])
D(73, "BST III", "bst", problems=[LC(235, "Lowest Common Ancestor of a Binary Search Tree"), LC(530, "Minimum Absolute Difference in BST")])
D(74, "BST IV", "bst", problems=[LC(450, "Delete Node in a BST")])
D(75, "BST V", "bst", problems=[LC(108, "Convert Sorted Array to Binary Search Tree"), LC(653, "Two Sum IV - Input is a BST")])
D(76, "BST VI", "bst", problems=[LC(173, "Binary Search Tree Iterator"), LC(669, "Trim a Binary Search Tree")])
D(77, "Tree Mock + OS", "bst", extra=[REV(102, "Binary Tree Level Order Traversal"), REV(98, "Validate Binary Search Tree"), REV(236, "Lowest Common Ancestor of a Binary Tree")],
   core_cs=CONCEPT("OS Deep Dive", ["deadlock", "semaphore", "mutex", "paging", "virtual memory", "page fault"]))

# ============================================================
# DAYS 78-84 — HEAP / PRIORITY QUEUE
# ============================================================
D(78, "Heap I", "heap", problems=[LC(703, "Kth Largest Element in a Stream"), LC(1046, "Last Stone Weight")])
D(79, "Heap II", "heap", problems=[LC(215, "Kth Largest Element in an Array"), LC(347, "Top K Frequent Elements")])
D(80, "Heap III", "heap", problems=[LC(973, "K Closest Points to Origin"), LC(451, "Sort Characters By Frequency")])
D(81, "Heap IV", "heap", problems=[LC(692, "Top K Frequent Words"), LC(373, "Find K Pairs with Smallest Sums")])
D(82, "Heap V", "heap", problems=[LC(767, "Reorganize String"), LC(621, "Task Scheduler")])
D(83, "Heap VI", "heap", problems=[LC(23, "Merge k Sorted Lists")])
D(84, "Heap Revision", "heap", extra=[REV(215, "Kth Largest Element in an Array"), REV(973, "K Closest Points to Origin"), REV(621, "Task Scheduler")])

# ============================================================
# DAYS 85-91 — GRAPHS I
# ============================================================
D(85, "Graphs I", "graphs_1", problems=[LC(733, "Flood Fill"), LC(200, "Number of Islands")])
D(86, "Graphs II", "graphs_1", problems=[LC(695, "Max Area of Island"), LC(463, "Island Perimeter")])
D(87, "Graphs III", "graphs_1", problems=[LC(994, "Rotting Oranges"), LC(542, "01 Matrix")])
D(88, "Graphs IV", "graphs_1", problems=[LC(547, "Number of Provinces"), LC(841, "Keys and Rooms")])
D(89, "Graphs V", "graphs_1", problems=[LC(797, "All Paths From Source to Target"), LC(1971, "Find if Path Exists in Graph")])
D(90, "Graphs VI (Bipartite)", "graphs_1", problems=[LC(785, "Is Graph Bipartite?"), LC(886, "Possible Bipartition")])
D(91, "Graphs I Revision", "graphs_1", extra=[REV(200, "Number of Islands"), REV(994, "Rotting Oranges"), REV(547, "Number of Provinces"), REV(785, "Is Graph Bipartite?")])

# ============================================================
# DAYS 92-98 — GRAPHS II
# ============================================================
D(92, "Topological Sort", "graphs_2", problems=[LC(207, "Course Schedule"), LC(210, "Course Schedule II")])
D(93, "Union Find", "graphs_2", problems=[LC(684, "Redundant Connection"), LC(1319, "Number of Operations to Make Network Connected")])
D(94, "Graphs VII", "graphs_2", problems=[LC(802, "Find Eventual Safe States"), LC(133, "Clone Graph")])
D(95, "BFS Shortest Path", "graphs_2", problems=[LC(1091, "Shortest Path in Binary Matrix"), LC(752, "Open the Lock")])
D(96, "Dijkstra", "graphs_2", problems=[LC(743, "Network Delay Time")])
D(97, "Weighted Graphs", "graphs_2", problems=[LC(1631, "Path With Minimum Effort"), LC(1514, "Path with Maximum Probability")])
D(98, "Graphs II Revision + CN Intro", "graphs_2", extra=[REV(207, "Course Schedule"), REV(684, "Redundant Connection"), REV(1091, "Shortest Path in Binary Matrix"), REV(743, "Network Delay Time")],
   core_cs=CONCEPT("Computer Networks Intro", ["OSI", "TCP/IP", "IP", "MAC", "DNS", "HTTP", "HTTPS", "TCP vs UDP"]))

# ============================================================
# DAYS 99-105 — GREEDY / INTERVALS
# ============================================================
D(99, "Greedy I", "greedy_intervals", problems=[LC(455, "Assign Cookies"), LC(55, "Jump Game")])
D(100, "Greedy II", "greedy_intervals", problems=[LC(45, "Jump Game II"), LC(860, "Lemonade Change")])
D(101, "Intervals I", "greedy_intervals", problems=[LC(56, "Merge Intervals"), LC(435, "Non-overlapping Intervals")])
D(102, "Intervals II", "greedy_intervals", problems=[LC(57, "Insert Interval"), LC(452, "Minimum Number of Arrows to Burst Balloons")])
D(103, "Greedy III", "greedy_intervals", problems=[LC(763, "Partition Labels"), LC(134, "Gas Station")])
D(104, "Greedy IV", "greedy_intervals", problems=[LC(881, "Boats to Save People"), LC(1029, "Two City Scheduling")])
D(105, "Greedy/Intervals Revision", "greedy_intervals", extra=[REV(55, "Jump Game"), REV(56, "Merge Intervals"), REV(435, "Non-overlapping Intervals"), REV(134, "Gas Station")])

# ============================================================
# DAYS 106-112 — DP I
# ============================================================
D(106, "DP Foundations", "dp_1", learn=["Recursion -> Memoization -> Tabulation -> Space Optimization"], problems=[LC(70, "Climbing Stairs"), LC(746, "Min Cost Climbing Stairs")])
D(107, "DP: House Robber", "dp_1", problems=[LC(198, "House Robber"), LC(213, "House Robber II")])
D(108, "DP: Coin Change", "dp_1", problems=[LC(322, "Coin Change"), LC(518, "Coin Change II")])
D(109, "DP: Strings", "dp_1", problems=[LC(139, "Word Break"), LC(91, "Decode Ways")])
D(110, "DP: LIS", "dp_1", problems=[LC(300, "Longest Increasing Subsequence"), LC(673, "Number of Longest Increasing Subsequence")])
D(111, "DP I Misc", "dp_1", problems=[LC(279, "Perfect Squares"), LC(377, "Combination Sum IV")])
D(112, "DP I Revision", "dp_1", extra=[REV(70, "Climbing Stairs"), REV(198, "House Robber"), REV(322, "Coin Change"), REV(300, "Longest Increasing Subsequence")])

# ============================================================
# DAYS 113-119 — DP II
# ============================================================
D(113, "DP: Grid Paths I", "dp_2", problems=[LC(62, "Unique Paths"), LC(63, "Unique Paths II")])
D(114, "DP: Grid Paths II", "dp_2", problems=[LC(64, "Minimum Path Sum"), LC(120, "Triangle")])
D(115, "DP: LCS Family", "dp_2", problems=[LC(1143, "Longest Common Subsequence"), LC(516, "Longest Palindromic Subsequence")])
D(116, "DP: Subset Sum Family", "dp_2", problems=[LC(416, "Partition Equal Subset Sum"), LC(494, "Target Sum")])
D(117, "DP: Knapsack Variants", "dp_2", problems=[LC(474, "Ones and Zeroes"), LC(1049, "Last Stone Weight II")])
D(118, "DP: 2D Strings", "dp_2", problems=[LC(72, "Edit Distance"), LC(221, "Maximal Square")])
D(119, "DP II Revision", "dp_2", extra=[REV(198, "House Robber"), REV(322, "Coin Change"), REV(1143, "Longest Common Subsequence"), REV(416, "Partition Equal Subset Sum")])

# ============================================================
# DAYS 120-126 — MIXED INTERVIEW MODE
# ============================================================
D(120, "Mixed Interview Mode I", "mixed_interview",
  problems=[LC(219, "Contains Duplicate II"), LC(238, "Product of Array Except Self"), LC(560, "Subarray Sum Equals K", note="Require explanations. Hide topic/pattern until attempt ends.")])
D(121, "Mixed Interview Mode II", "mixed_interview", problems=[LC(148, "Sort List"), LC(143, "Reorder List")],
   core_cs=CONCEPT("OOP Full Revision", ["pillars", "overload vs override", "abstract class vs interface"]))
D(122, "Mixed Interview Mode III", "mixed_interview", problems=[LC(1448, "Count Good Nodes in Binary Tree"), LC(199, "Binary Tree Right Side View")],
   extra=[REV(236, "Lowest Common Ancestor of a Binary Tree")],
   core_cs=CONCEPT("OS Revision", ["process vs thread", "deadlock", "paging"]))
D(123, "Mixed Interview Mode IV", "mixed_interview", problems=[LC(909, "Snakes and Ladders"), LC(399, "Evaluate Division")],
   core_cs=CONCEPT("Networks Revision", ["TCP vs UDP", "HTTP vs HTTPS", "DNS"]))
D(124, "Mixed Interview Mode V", "mixed_interview", problems=[LC(337, "House Robber III")],
   extra=[REV(64, "Minimum Path Sum"), REV(322, "Coin Change")],
   core_cs=CONCEPT("DBMS/SQL", ["joins", "normalization", "ACID", "SELECT/WHERE/GROUP BY/HAVING"]))
D(125, "OA #1", "mixed_interview", is_oa=True,
  extra=[OA("OA #1", 90, [LC(1768, "Merge Strings Alternately"), LC(49, "Group Anagrams"), LC(215, "Kth Largest Element in an Array")], note="No topic hints.")])
D(126, "Repair Day", "mixed_interview",
  extra=[REPAIR("Repair Day", "Automatically choose five highest-priority weak problems based on: 1) Red confidence, 2) repeated failure, 3) important interview pattern, 4) overdue revision. Selected at runtime by recovery_service.")])

# ============================================================
# DAYS 127-133 — INTERVIEW TRAINING
# ============================================================
D(127, "OA #2", "interview_training", is_oa=True,
  extra=[OA("OA #2", 90, [LC(121, "Best Time to Buy and Sell Stock"), LC(739, "Daily Temperatures"), LC(207, "Course Schedule")],
            note="Require: approach, time complexity, space complexity, edge cases.")])
D(128, "Interview Training I", "interview_training", problems=[LC(658, "Find K Closest Elements"), LC(853, "Car Fleet")])
D(129, "Interview Training II", "interview_training", problems=[LC(138, "Copy List with Random Pointer"), LC(146, "LRU Cache", note="Treat as a high-value learning problem.")])
D(130, "Interview Training III", "interview_training", extra=[REV(230, "Kth Smallest Element in a BST"), REV(102, "Binary Tree Level Order Traversal")], problems=[LC(1448, "Count Good Nodes in Binary Tree")])
D(131, "Interview Training IV", "interview_training", problems=[LC(721, "Accounts Merge"), LC(127, "Word Ladder")])
D(132, "Interview Training V", "interview_training", problems=[LC(647, "Palindromic Substrings"), LC(309, "Best Time to Buy and Sell Stock with Cooldown")])
D(133, "OA #3", "interview_training", is_oa=True,
  extra=[OA("OA #3", 90, [LC(53, "Maximum Subarray"), LC(435, "Non-overlapping Intervals"), LC(994, "Rotting Oranges")])])

# ============================================================
# DAYS 134-135 — FINAL MOCK + BENCHMARK
# ============================================================
D(134, "Full Technical Mock", "final_mock", is_mock=True,
  extra=[MOCK("Full Technical Mock", [
      {"problem": LC(15, "3Sum"), "target_minutes": 40, "require": ["brute force", "optimization", "complexity", "implementation", "edge cases"]},
      {"problem": LC(102, "Binary Tree Level Order Traversal"), "target_minutes": 30},
  ], note="Core CS rapid fire: OOP pillars, overload vs override, abstract class vs interface, primary/foreign key, normalization, joins, ACID, process vs thread, deadlock, paging, TCP vs UDP, HTTP vs HTTPS, DNS. Plus: 'Tell me about your strongest project.'")])
D(135, "Final Benchmark", "final_mock", is_oa=True,
  extra=[OA("Final Benchmark OA", 90, [LC(3, "Longest Substring Without Repeating Characters"), LC(215, "Kth Largest Element in an Array"), LC(207, "Course Schedule")],
            note="Internally tests Sliding Window, Heap, Topological Sort. Do not reveal labels before attempt. Produce final report after completion.")])


def main() -> None:
    assert len(DAYS) == 135, f"Expected 135 days, got {len(DAYS)}"
    assert [d["day"] for d in DAYS] == list(range(1, 136)), "Day numbers must be 1..135 in order"
    out_path = Path(__file__).parent / "schedule.json"
    out_path.write_text(json.dumps({"days": DAYS}, indent=2), encoding="utf-8")
    print(f"Wrote {out_path} with {len(DAYS)} days")


if __name__ == "__main__":
    main()
