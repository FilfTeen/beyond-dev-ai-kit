"""Unit tests for hongzhi_ai_kit.snapshot module."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from hongzhi_ai_kit.snapshot import (
    SNAPSHOT_EXCLUDES,
    SNAPSHOT_EXT_EXCLUDES,
    take_snapshot,
    diff_snapshots,
    enforce_read_only,
)


class TestTakeSnapshot(unittest.TestCase):
    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as td:
            snap = take_snapshot(td)
            self.assertEqual(snap, {})

    def test_captures_files(self):
        with tempfile.TemporaryDirectory() as td:
            Path(td, "a.txt").write_text("hello")
            Path(td, "b.py").write_text("world")
            snap = take_snapshot(td)
            self.assertEqual(len(snap), 2)
            self.assertIn("a.txt", snap)
            self.assertIn("b.py", snap)

    def test_excludes_pycache(self):
        with tempfile.TemporaryDirectory() as td:
            cache_dir = Path(td, "__pycache__")
            cache_dir.mkdir()
            Path(cache_dir, "foo.pyc").write_text("x")
            Path(td, "real.py").write_text("y")
            snap = take_snapshot(td)
            self.assertEqual(len(snap), 1)
            self.assertIn("real.py", snap)

    def test_excludes_class_files(self):
        with tempfile.TemporaryDirectory() as td:
            Path(td, "Main.class").write_text("bytecode")
            Path(td, "Main.java").write_text("source")
            snap = take_snapshot(td)
            self.assertEqual(len(snap), 1)
            self.assertIn("Main.java", snap)

    def test_max_files_limit(self):
        with tempfile.TemporaryDirectory() as td:
            for i in range(20):
                Path(td, f"file{i}.txt").write_text(f"content{i}")
            snap = take_snapshot(td, max_files=5)
            self.assertLessEqual(len(snap), 5)

    def test_snapshot_values_format(self):
        with tempfile.TemporaryDirectory() as td:
            Path(td, "test.txt").write_text("hello")
            snap = take_snapshot(td)
            size, mtime_ns = snap["test.txt"]
            self.assertEqual(size, 5)  # len("hello")
            self.assertIsInstance(mtime_ns, int)


class TestDiffSnapshots(unittest.TestCase):
    def test_no_changes(self):
        snap = {"a.txt": (10, 100)}
        delta = diff_snapshots(snap, snap)
        self.assertEqual(delta["created"], [])
        self.assertEqual(delta["deleted"], [])
        self.assertEqual(delta["modified"], [])

    def test_created_file(self):
        before = {"a.txt": (10, 100)}
        after = {"a.txt": (10, 100), "b.txt": (20, 200)}
        delta = diff_snapshots(before, after)
        self.assertEqual(delta["created"], ["b.txt"])
        self.assertEqual(delta["deleted"], [])

    def test_deleted_file(self):
        before = {"a.txt": (10, 100), "b.txt": (20, 200)}
        after = {"a.txt": (10, 100)}
        delta = diff_snapshots(before, after)
        self.assertEqual(delta["deleted"], ["b.txt"])

    def test_modified_file(self):
        before = {"a.txt": (10, 100)}
        after = {"a.txt": (15, 200)}
        delta = diff_snapshots(before, after)
        self.assertEqual(delta["modified"], ["a.txt"])

    def test_combined_changes(self):
        before = {"a.txt": (10, 100), "b.txt": (20, 200)}
        after = {"a.txt": (15, 300), "c.txt": (30, 400)}
        delta = diff_snapshots(before, after)
        self.assertEqual(delta["created"], ["c.txt"])
        self.assertEqual(delta["deleted"], ["b.txt"])
        self.assertEqual(delta["modified"], ["a.txt"])


class TestEnforceReadOnly(unittest.TestCase):
    def test_empty_delta_passes(self):
        delta = {"created": [], "deleted": [], "modified": []}
        self.assertTrue(enforce_read_only(delta, write_ok=False))

    def test_write_ok_allows_changes(self):
        delta = {"created": ["new.txt"], "deleted": [], "modified": []}
        self.assertTrue(enforce_read_only(delta, write_ok=True))

    def test_violation_exits(self):
        delta = {"created": ["new.txt"], "deleted": [], "modified": []}
        with self.assertRaises(SystemExit) as ctx:
            enforce_read_only(delta, write_ok=False)
        self.assertEqual(ctx.exception.code, 3)


class TestConstants(unittest.TestCase):
    def test_excludes_are_sets(self):
        self.assertIsInstance(SNAPSHOT_EXCLUDES, set)
        self.assertIsInstance(SNAPSHOT_EXT_EXCLUDES, set)

    def test_common_excludes_present(self):
        self.assertIn("__pycache__", SNAPSHOT_EXCLUDES)
        self.assertIn(".git", SNAPSHOT_EXCLUDES)
        self.assertIn("node_modules", SNAPSHOT_EXCLUDES)

    def test_ext_excludes(self):
        self.assertIn(".class", SNAPSHOT_EXT_EXCLUDES)
        self.assertIn(".pyc", SNAPSHOT_EXT_EXCLUDES)


if __name__ == "__main__":
    unittest.main()
