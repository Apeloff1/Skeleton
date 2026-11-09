from __future__ import annotations

import unittest

from skeleton.automation.build_contracts import (
    ArchitecturePlan,
    FileIntent,
)
from skeleton.automation.build_graph import (
    BuildGraph,
    BuildGraphError,
)


def plan(
    intents: tuple[FileIntent, ...],
) -> ArchitecturePlan:
    return ArchitecturePlan(
        objective="build graph",
        rationale="dependency-aware execution",
        files=intents,
        test_intents=("cover graph",),
        acceptance=("graph is deterministic",),
        risks=(),
        assumptions=(),
    )


class BuildGraphTests(unittest.TestCase):
    def test_independent_paths_are_deterministic(self) -> None:
        graph = BuildGraph.from_architecture(
            plan(
                (
                    FileIntent(
                        path="skeleton/c.py",
                        purpose="c",
                        operation="create",
                    ),
                    FileIntent(
                        path="skeleton/a.py",
                        purpose="a",
                        operation="create",
                    ),
                    FileIntent(
                        path="skeleton/b.py",
                        purpose="b",
                        operation="create",
                    ),
                )
            )
        )
        self.assertEqual(
            [node.path for node in graph.nodes],
            [
                "skeleton/a.py",
                "skeleton/b.py",
                "skeleton/c.py",
            ],
        )
        self.assertEqual(len(graph.fingerprint), 64)

    def test_planned_dependency_orders_dependency_first(self) -> None:
        graph = BuildGraph.from_architecture(
            plan(
                (
                    FileIntent(
                        path="skeleton/service.py",
                        purpose="service",
                        operation="create",
                        dependencies=("skeleton/model.py",),
                    ),
                    FileIntent(
                        path="skeleton/model.py",
                        purpose="model",
                        operation="create",
                    ),
                )
            )
        )
        ordered_paths = [
            component.paths
            for component in graph.components
        ]
        self.assertEqual(
            ordered_paths,
            [
                ("skeleton/model.py",),
                ("skeleton/service.py",),
            ],
        )

    def test_cycle_becomes_single_strong_component(self) -> None:
        graph = BuildGraph.from_architecture(
            plan(
                (
                    FileIntent(
                        path="skeleton/a.py",
                        purpose="a",
                        operation="create",
                        dependencies=("skeleton/b.py",),
                    ),
                    FileIntent(
                        path="skeleton/b.py",
                        purpose="b",
                        operation="create",
                        dependencies=("skeleton/a.py",),
                    ),
                )
            )
        )
        self.assertEqual(len(graph.components), 1)
        self.assertEqual(
            graph.components[0].paths,
            ("skeleton/a.py", "skeleton/b.py"),
        )
        self.assertEqual(
            graph.components[0].depends_on,
            (),
        )

    def test_external_dependencies_do_not_create_graph_edges(self) -> None:
        graph = BuildGraph.from_architecture(
            plan(
                (
                    FileIntent(
                        path="skeleton/a.py",
                        purpose="a",
                        operation="create",
                        dependencies=("pyproject.toml",),
                    ),
                )
            )
        )
        self.assertEqual(
            graph.nodes[0].planned_dependencies,
            (),
        )
        self.assertEqual(
            graph.nodes[0].external_dependencies,
            ("pyproject.toml",),
        )

    def test_transitive_dependency_closure(self) -> None:
        graph = BuildGraph.from_architecture(
            plan(
                (
                    FileIntent(
                        path="skeleton/a.py",
                        purpose="a",
                        operation="create",
                    ),
                    FileIntent(
                        path="skeleton/b.py",
                        purpose="b",
                        operation="create",
                        dependencies=("skeleton/a.py",),
                    ),
                    FileIntent(
                        path="skeleton/c.py",
                        purpose="c",
                        operation="create",
                        dependencies=("skeleton/b.py",),
                    ),
                )
            )
        )
        self.assertEqual(
            graph.dependency_closure(("skeleton/c.py",)),
            ("skeleton/a.py", "skeleton/b.py"),
        )

    def test_shards_never_split_cycle(self) -> None:
        graph = BuildGraph.from_architecture(
            plan(
                (
                    FileIntent(
                        path="skeleton/a.py",
                        purpose="a",
                        operation="create",
                        dependencies=("skeleton/b.py",),
                    ),
                    FileIntent(
                        path="skeleton/b.py",
                        purpose="b",
                        operation="create",
                        dependencies=("skeleton/a.py",),
                    ),
                    FileIntent(
                        path="skeleton/c.py",
                        purpose="c",
                        operation="create",
                    ),
                )
            )
        )
        shards = graph.shards(max_shards=3)
        containing_a = [
            shard
            for shard in shards
            if "skeleton/a.py" in shard.paths
        ]
        self.assertEqual(len(containing_a), 1)
        self.assertIn(
            "skeleton/b.py",
            containing_a[0].paths,
        )

    def test_shards_preserve_predecessor_evidence(self) -> None:
        graph = BuildGraph.from_architecture(
            plan(
                (
                    FileIntent(
                        path="skeleton/model.py",
                        purpose="model",
                        operation="create",
                    ),
                    FileIntent(
                        path="skeleton/service.py",
                        purpose="service",
                        operation="create",
                        dependencies=("skeleton/model.py",),
                    ),
                    FileIntent(
                        path="tests/test_service.py",
                        purpose="test",
                        operation="create",
                        dependencies=("skeleton/service.py",),
                    ),
                )
            )
        )
        shards = graph.shards(max_shards=3)
        self.assertEqual(len(shards), 3)
        self.assertEqual(
            shards[0].paths,
            ("skeleton/model.py",),
        )
        self.assertEqual(
            shards[1].predecessor_shards,
            ("build_shard_001",),
        )
        self.assertEqual(
            shards[2].predecessor_shards,
            ("build_shard_002",),
        )

    def test_shard_count_is_bounded(self) -> None:
        graph = BuildGraph.from_architecture(
            plan(
                tuple(
                    FileIntent(
                        path=f"skeleton/file_{index}.py",
                        purpose="file",
                        operation="create",
                    )
                    for index in range(20)
                )
            )
        )
        shards = graph.shards(max_shards=4)
        self.assertLessEqual(len(shards), 4)
        self.assertEqual(
            sum(len(shard.paths) for shard in shards),
            20,
        )

    def test_every_planned_path_appears_once_across_shards(self) -> None:
        graph = BuildGraph.from_architecture(
            plan(
                tuple(
                    FileIntent(
                        path=f"skeleton/file_{index}.py",
                        purpose="file",
                        operation="create",
                    )
                    for index in range(12)
                )
            )
        )
        paths = [
            path
            for shard in graph.shards(max_shards=5)
            for path in shard.paths
        ]
        self.assertEqual(len(paths), len(set(paths)))
        self.assertEqual(
            set(paths),
            {
                f"skeleton/file_{index}.py"
                for index in range(12)
            },
        )

    def test_invalid_shard_budget_rejected(self) -> None:
        graph = BuildGraph.from_architecture(
            plan(
                (
                    FileIntent(
                        path="skeleton/a.py",
                        purpose="a",
                        operation="create",
                    ),
                )
            )
        )
        for value in (0, -1, True, 33):
            with self.subTest(value=value):
                with self.assertRaises(BuildGraphError):
                    graph.shards(max_shards=value)


if __name__ == "__main__":
    unittest.main()
