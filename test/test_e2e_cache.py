"""Prove complete cache coverage, integrity, capacity, and isolated restoration."""

import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from benchmark.e2e.cache import CompleteCache, RESERVE_BYTES, verify_coverage


class DiskFixture:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.version, self._footer_index = "v1", {}
        self.max_disk_bytes = 1024
        self.errors = 0
        (self.directory / ".dataset-version.json").write_text('{"version":"v1"}', encoding="utf-8")

    def register(self, url):
        return url

    def info(self, path):
        return {"size": 64}

    def _key_and_url(self, path):
        return "object", path

    def _object_name(self, key):
        return key

    def prepare_footer(self, path):
        pass

    def prefetch_ranges(self, path, ranges):
        for start, end in ranges:
            content = bytes(range(start, end))
            (self.directory / f"object-{start}-{end - start}.block").write_bytes(
                hashlib.sha256(content).digest() + content)

    def await_pending(self):
        return {"errors": self.errors}


class TestCompleteCache(unittest.TestCase):
    def test_complete_seed_serves_a_never_warmed_range_with_independent_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            active = directory / "active"
            active.mkdir()
            filesystem = DiskFixture(active)
            seed = CompleteCache(directory / "seed")
            evidence = seed.build(filesystem, ["https://example.test/data/input.parquet"],
                                  {"update_time": "v1", "footer_index": {}})
            self.assertEqual(evidence["total_bytes"], 64)
            for name in ("first", "second"):
                restored = directory / name
                restored.mkdir()
                self.assertEqual(seed.restore(restored), evidence["sha256"])
                block = restored / "object-0-64.block"
                self.assertEqual(block.read_bytes()[32 + 40:32 + 48], bytes(range(40, 48)))
                self.assertEqual(block.stat().st_ino, (seed.directory / block.name).stat().st_ino)
                metadata = restored / ".dataset-version.json"
                self.assertNotEqual(metadata.stat().st_ino,
                                    (seed.directory / metadata.name).stat().st_ino)
                metadata.write_text("changed", encoding="utf-8")
                self.assertNotEqual(metadata.read_bytes(), (seed.directory / metadata.name).read_bytes())
            seed.assert_identity({"update_time": "v1", "footer_index": {}})
            seed.validate()
            block = seed.directory / "object-0-64.block"
            block.write_bytes(b"x" * block.stat().st_size)
            with self.assertRaisesRegex(ValueError, "contents changed"):
                seed.validate()
            with self.assertRaisesRegex(ValueError, "Dataset identity"):
                seed.assert_identity({"update_time": "v2", "footer_index": {}})

    def test_gaps_and_corruption_are_rejected_before_readiness(self):
        with tempfile.TemporaryDirectory() as temporary:
            filesystem = DiskFixture(temporary)
            filesystem.prefetch_ranges("input", [(0, 16), (32, 64)])
            with self.assertRaisesRegex(ValueError, "Incomplete"):
                verify_coverage(filesystem, "input", 64)
            filesystem.prefetch_ranges("input", [(16, 32)])
            self.assertEqual(verify_coverage(filesystem, "input", 64), 3)
            path = Path(temporary) / "object-16-16.block"
            path.write_bytes(b"x" * path.stat().st_size)
            with self.assertRaisesRegex(ValueError, "Corrupt"):
                verify_coverage(filesystem, "input", 64)

    def test_capacity_and_prefetch_errors_never_produce_seed_evidence(self):
        for failure in ("disk", "budget", "prefetch", "identity"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temporary:
                filesystem = DiskFixture(temporary)
                seed = CompleteCache(Path(temporary) / "seed")
                free = RESERVE_BYTES if failure == "disk" else RESERVE_BYTES * 2
                filesystem.max_disk_bytes = 32 if failure == "budget" else 1024
                filesystem.errors = int(failure == "prefetch")
                dataset = {"update_time": "v2" if failure == "identity" else "v1", "footer_index": {}}
                with patch("benchmark.e2e.cache.shutil.disk_usage", return_value=SimpleNamespace(free=free)):
                    with self.assertRaises((RuntimeError, ValueError)):
                        seed.build(filesystem, ["input.parquet"], dataset)
                self.assertIsNone(seed.evidence)

    def test_missing_seed_block_is_not_silently_redownloaded(self):
        with tempfile.TemporaryDirectory() as temporary:
            filesystem = DiskFixture(temporary)
            seed = CompleteCache(Path(temporary) / "seed")
            seed.build(filesystem, ["input.parquet"], {"update_time": "v1", "footer_index": {}})
            (seed.directory / "object-0-64.block").unlink()
            restored = Path(temporary) / "restored"
            restored.mkdir()
            with self.assertRaisesRegex(ValueError, "changed after validation"):
                seed.restore(restored)
