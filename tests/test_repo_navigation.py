"""End-to-end regression coverage for sharded repository navigation."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / "scripts/build_repo_navigation.py"
SPEC = importlib.util.spec_from_file_location("repo_navigation", MODULE)
assert SPEC and SPEC.loader
nav = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(nav)

class NavigationTests(unittest.TestCase):
    def fixture(self):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)
        (root / ".machine").mkdir()
        (root / ".machine/repository.toml").write_text(
            '[[zone]]\nname="app"\nprefixes=["app/"]\nowner="app"\npurpose="app code"\ncriticality="high"\nlifecycle="canonical"\n'
            '[[zone]]\nname="legacy"\nprefixes=["legacy/"]\nowner="legacy"\npurpose="mirror"\ncriticality="low"\nlifecycle="transitional"\n'
        )
        for path, content in {
            "app/run.py": "def execute(arg):\n    return arg + 1\n",
            "legacy/run.py": "def execute(arg):\n    return arg + 1\n",
            "app/feature.py": "def draw(arg):\n    return arg + 1\n",
            "legacy/feature.py": "def draw(arg):\n    return arg  +   1\n",
            "other.bin": "\x00binary",
        }.items():
            dest = root / path
            dest.parent.mkdir(exist_ok=True, parents=True)
            dest.write_text(content)
        for cmd in (
            ["git", "init", "-q"],
            ["git", "-c", "user.email=a@example.com", "-c", "user.name=Tests", "add", "."],
            ["git", "-c", "user.email=a@example.com", "-c", "user.name=Tests", "commit", "-qm", "fixture"],
        ):
            subprocess.run(cmd, check=True, cwd=root, capture_output=True)
        return tmp

    def test_complete_deterministic_and_grouped(self):
        with self.fixture() as temp:
            root = Path(temp)
            output = nav.build(root)
            meta = json.loads(output["manifest.json"])
            self.assertEqual(meta["tracked_objects"], 6)
            self.assertEqual(meta["exact_duplicate_groups"], 1)
            self.assertEqual(meta["extra_exact_copies"], 1)
            self.assertEqual(meta["near_duplicate_candidates"], 1)
            self.assertEqual(meta["unclassified_count"], 2)
            self.assertEqual(output, nav.build(root))
            self.assertEqual(len(output["files/app.jsonl"].splitlines()), 2)

    def test_index_is_not_self_referential(self):
        with self.fixture() as temp:
            root = Path(temp)
            out = root / nav.OUTPUT
            nav.write_index(root, out)
            first = (out / "manifest.json").read_bytes()
            subprocess.run(["git", "add", "machine"], check=True, cwd=root)
            subprocess.run(["git", "-c", "user.email=a@example.com", "-c", "user.name=Tests", "commit", "-qm", "generated"], check=True, cwd=root)
            nav.write_index(root, out)
            self.assertEqual(first, (out / "manifest.json").read_bytes())

    def test_feature_groups_are_directories_not_files(self):
        self.assertEqual(nav.feature_of("skeleton/ai/webcrawler/dragon.py"), "skeleton/ai/webcrawler")
        self.assertEqual(nav.feature_of("skeleton/ai/runtime/policy/control.py"), "skeleton/ai/runtime/policy")
        self.assertEqual(nav.feature_of("backend/routes/health.py"), "backend/routes")
        self.assertEqual(nav.feature_of("tests/test_repo_navigation.py"), "tests")

    def test_zone_prefix_boundary(self):
        with self.fixture() as temp:
            rules = nav.zones(Path(temp))
            self.assertEqual(nav.placement("app/run.py", rules)["name"], "app")
            self.assertEqual(nav.placement("app2/run.py", rules)["name"], "unclassified")

if __name__ == "__main__":
    unittest.main()
