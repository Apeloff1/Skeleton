"""Reverse-mode tape. No torch."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Node:
    value: float
    parents: tuple["Node", ...] = ()
    op: str = "leaf"
    extra: float = 0.0
    grad: float = 0.0


@dataclass
class Tape:
    nodes: list[Node] = field(default_factory=list)

    def leaf(self, value: float) -> Node:
        n = Node(float(value))
        self.nodes.append(n)
        return n

    def add(self, a: Node, b: Node) -> Node:
        n = Node(a.value + b.value, (a, b), "add")
        self.nodes.append(n)
        return n

    def mul(self, a: Node, b: Node) -> Node:
        n = Node(a.value * b.value, (a, b), "mul")
        self.nodes.append(n)
        return n

    def relu(self, a: Node) -> Node:
        n = Node(a.value if a.value > 0.0 else 0.0, (a,), "relu")
        self.nodes.append(n)
        return n

    def backward(self, out: Node) -> None:
        for n in self.nodes:
            n.grad = 0.0
        out.grad = 1.0
        for n in reversed(self.nodes):
            if n.op == "add":
                n.parents[0].grad += n.grad
                n.parents[1].grad += n.grad
            elif n.op == "mul":
                n.parents[0].grad += n.grad * n.parents[1].value
                n.parents[1].grad += n.grad * n.parents[0].value
            elif n.op == "relu":
                if n.parents[0].value > 0.0:
                    n.parents[0].grad += n.grad
