"""Verify retained disk extents, fast thread sharing, and restart discovery."""

from concurrent.futures import ThreadPoolExecutor
import errno
import hashlib
import os
import random
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from defeatbeta_api.client.dataset_cache_fs import DatasetCacheFileSystem
from defeatbeta_api.client.extent_index import ExtentIndex
from test.test_dataset_cache_fs import FakeRangeClient, PINNED, SIGNED


class TestExtentRetention(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.payload = bytes(range(256)) * 16
        self.clients, self.filesystems = [], []

    def tearDown(self):
        for fs in self.filesystems:
            fs.close()
        self.temporary.cleanup()

    def filesystem(self, client=None, **kwargs):
        client = client or FakeRangeClient(len(self.payload), payload=self.payload)
        kwargs.setdefault("max_memory_bytes", 0)
        fs = DatasetCacheFileSystem(str(self.directory), "retention-v1",
            resolve=lambda url, refresh=False: (SIGNED, len(self.payload)), http_client=client,
            footer_index={"US/stock_prices.parquet": {"file_size": len(self.payload)}}, **kwargs)
        self.filesystems.append(fs)
        self.clients.append(client)
        return fs, fs.register(PINNED)

    def test_all_read_bytes_remain_on_disk_past_legacy_capacity(self):
        fs, path = self.filesystem(max_disk_bytes=42)
        for start in (0, 100, 200, 300):
            self.assertEqual(fs.cat_file(path, start, start + 10), self.payload[start:start + 10])
        self.assertEqual(len(list(self.directory.glob("*.block"))), 4)
        requests = len(self.clients[0].calls)
        for start in (0, 100, 200, 300):
            self.assertEqual(fs.cat_file(path, start, start + 10), self.payload[start:start + 10])
        self.assertEqual(len(self.clients[0].calls), requests)

    def test_hot_reads_and_publication_do_not_scan_directory(self):
        fs, path = self.filesystem()
        fs.cat_file(path, 0, 10)
        with patch.object(Path, "iterdir", side_effect=AssertionError("Unexpected directory scan")), patch(
                "os.scandir", side_effect=AssertionError("Unexpected directory scan")):
            self.assertEqual(fs.cat_file(path, 0, 10), self.payload[:10])
            self.assertEqual(fs.cat_file(path, 100, 110), self.payload[100:110])

    def test_read_does_not_stat_unrelated_files(self):
        fs, path = self.filesystem()
        fs.cat_file(path, 0, 10)
        for index in range(100):
            (self.directory / f"unrelated-{index}.bin").write_bytes(b"user-owned")
        original, visited = Path.stat, []

        def stat(target, *args, **kwargs):
            if target.name.startswith("unrelated-"):
                visited.append(target.name)
            return original(target, *args, **kwargs)

        with patch.object(Path, "stat", stat):
            fs.cat_file(path, 0, 10)
        self.assertEqual(visited, [])

    def test_disk_hits_preserve_modification_time(self):
        fs, path = self.filesystem()
        fs.cat_file(path, 0, 10)
        block = next(self.directory.glob("*.block"))
        os.utime(block, ns=(1_000_000_000, 1_000_000_000))
        before = block.stat().st_mtime_ns
        fs.cat_file(path, 0, 10)
        self.assertEqual(block.stat().st_mtime_ns, before)

    def test_same_process_owners_share_newly_published_extents(self):
        writer, wp = self.filesystem()
        reader, rp = self.filesystem()
        writer.cat_file(wp, 100, 200)
        with patch.object(Path, "iterdir", side_effect=AssertionError("Unexpected directory scan")), patch(
                "os.scandir", side_effect=AssertionError("Unexpected directory scan")):
            self.assertEqual(reader.cat_file(rp, 120, 180), self.payload[120:180])
        self.assertEqual(self.clients[1].calls, [])

    def test_overlapping_threads_store_each_byte_once(self):
        left, lp = self.filesystem()
        with ThreadPoolExecutor(max_workers=2) as workers:
            a = workers.submit(left.cat_file, lp, 0, 100)
            b = workers.submit(left.cat_file, lp, 50, 150)
            self.assertEqual(a.result(timeout=10), self.payload[:100])
            self.assertEqual(b.result(timeout=10), self.payload[50:150])
        blocks = list(self.directory.glob("*.block"))
        self.assertEqual(sum(p.stat().st_size - 32 for p in blocks), 150)
        for block in blocks:
            stored = block.read_bytes()
            self.assertEqual(stored[:32], hashlib.sha256(stored[32:]).digest())
        reader, path = self.filesystem()
        self.assertEqual(reader.cat_file(path, 0, 150), self.payload[:150])
        self.assertEqual(self.clients[-1].calls, [])

    def test_restart_discovers_retained_files_without_a_persistent_index(self):
        fs, path = self.filesystem()
        fs.cat_file(path, 0, 100)
        fs.close()
        self.filesystems.remove(fs)
        reader, path = self.filesystem()
        with patch("os.scandir", side_effect=AssertionError("Unexpected directory scan")):
            self.assertEqual(reader.cat_file(path, 10, 80), self.payload[10:80])
        self.assertEqual(self.clients[-1].calls, [])
        self.assertFalse((self.directory / ".dataset-extents").exists())

    def test_disk_full_returns_validated_download_and_can_recover(self):
        fs, path = self.filesystem()
        original = fs._atomic_write

        def write(target, content):
            if target.suffix == ".block":
                raise OSError(errno.ENOSPC, "Expected full disk")
            return original(target, content)

        with patch.object(fs, "_atomic_write", side_effect=write):
            self.assertEqual(fs.cat_file(path, 0, 10), self.payload[:10])
        self.assertEqual(list(self.directory.glob("*.block")), [])
        self.assertEqual(fs.cat_file(path, 0, 10), self.payload[:10])
        self.assertEqual(len(list(self.directory.glob("*.block"))), 1)

    def test_memory_eviction_does_not_remove_disk_bytes(self):
        fs, path = self.filesystem(max_memory_bytes=128)
        for start in (0, 200, 400):
            fs.cat_file(path, start, start + 128)
        self.assertEqual(len(fs._memory_blocks), 1)
        self.assertEqual(len(list(self.directory.glob("*.block"))), 3)
        requests = len(self.clients[0].calls)
        self.assertEqual(fs.cat_file(path, 0, 128), self.payload[:128])
        self.assertEqual(len(self.clients[0].calls), requests)

    def test_interval_lookup_matches_reference_with_nested_and_overlapping_extents(self):
        index = ExtentIndex.shared(self.directory, "retention-v1")
        owner = f"{index.tag}-{'a' * 64}-stock_prices.parquet"
        rng = random.Random(17)
        ranges = [(0, 1000), (10, 5), (15, 5), (1000, 10)]
        ranges += [(rng.randrange(1100), rng.randrange(1, 200)) for _ in range(100)]
        names = [f"{owner}-{start}-{length}.block" for start, length in ranges]
        index.initialize(names)
        for start in range(0, 1200, 13):
            end = start + 29
            expected = sorted(name for name, (left, length) in zip(names, ranges)
                              if left < end and left + length > start)
            self.assertEqual(sorted(row[3] for row in index.overlapping(owner, start, end)), expected)
        extra = f"{owner}-5000-10.footer"
        index.add(extra)
        self.assertEqual(index.overlapping(owner, 5000, 5010)[0][3], extra)
        self.assertEqual(index.overlapping(owner, 5010, 5020), [])

    def test_replaced_cached_symlink_does_not_read_or_modify_external_data(self):
        fs, path = self.filesystem()
        fs.cat_file(path, 0, 10)
        block = next(self.directory.glob("*.block"))
        external = self.directory / "user-data"
        content = b"external!!"
        stored = hashlib.sha256(content).digest() + content
        external.write_bytes(stored)
        block.unlink()
        try:
            block.symlink_to(external)
        except OSError:
            self.skipTest("Creating symlinks is unavailable")
        self.assertEqual(fs.cat_file(path, 0, 10), self.payload[:10])
        self.assertEqual(external.read_bytes(), stored)
        self.assertFalse(block.is_symlink())
