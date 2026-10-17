"""Prepare complete product-native disk caches outside all timed queries."""

import hashlib
import os
from pathlib import Path
import re
import shutil
import time
from copy import deepcopy

from benchmark.e2e.plan import checksum


_EXTENT = re.compile(r"(\d+)-(\d+)\.(block|footer)$")
RESERVE_BYTES = 512 * 1024**2


def verify_coverage(filesystem, path, size):
    """Stream-validate native cache blocks and prove coverage of [0, size)."""
    key, _ = filesystem._key_and_url(path)
    prefix = filesystem._object_name(key) + "-"
    intervals = []
    for block in filesystem.directory.iterdir():
        if not block.name.startswith(prefix):
            continue
        match = _EXTENT.fullmatch(block.name[len(prefix):])
        if match is None:
            continue
        start, length = int(match[1]), int(match[2])
        if block.is_symlink() or not block.is_file() or length <= 0 or start + length > size:
            raise ValueError("Invalid seed cache extent")
        with block.open("rb") as stream:
            digest = stream.read(32)
            actual, count = hashlib.sha256(), 0
            while chunk := stream.read(1024 * 1024):
                actual.update(chunk)
                count += len(chunk)
        if count != length or digest != actual.digest():
            raise ValueError("Corrupt seed cache block")
        intervals.append((start, start + length))
    cursor = 0
    for start, end in sorted(intervals):
        if start > cursor:
            raise ValueError("Incomplete seed cache coverage")
        cursor = max(cursor, end)
    if cursor != size:
        raise ValueError("Incomplete seed cache coverage")
    return len(intervals)


class CompleteCache:
    """Keep one seed per variant/phase; share only immutable block contents."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self.files = {}
        self.evidence = None

    def build(self, filesystem, urls, dataset):
        if self.evidence is not None or self.directory.exists():
            raise ValueError("Cache seed must be created exactly once")
        started = time.perf_counter()
        dataset = deepcopy(dataset)
        objects = []
        for url in sorted(set(urls)):
            path = filesystem.register(url)
            size = filesystem.info(path)["size"]
            if type(size) is not int or size <= 0:
                raise ValueError("Cache seed requires a positive file size")
            objects.append((url, path, size))
        if not objects:
            raise ValueError("Cache seed requires remote files")
        total = sum(size for _, _, size in objects)
        if (filesystem.max_disk_bytes < total
                or shutil.disk_usage(filesystem.directory).free < total + RESERVE_BYTES):
            raise RuntimeError("Insufficient disk space for the complete cache seed")
        coverage = []
        for url, path, size in objects:
            if url.endswith(".parquet"):
                filesystem.prepare_footer(path)
            filesystem.prefetch_ranges(path, [(0, size)])
            if filesystem.await_pending()["errors"]:
                raise RuntimeError("Complete cache preparation failed")
            blocks = verify_coverage(filesystem, path, size)
            coverage.append({"file": url.rsplit("/data/", 1)[-1], "size": size,
                             "covered_bytes": size, "validated_extents": blocks})
        if filesystem.version != dataset["update_time"] or filesystem._footer_index != dataset["footer_index"]:
            raise ValueError("Dataset identity changed while preparing the cache seed")
        # Locks and mutable metadata must never share inodes with a live cache.
        self.directory.mkdir(parents=True)
        for source in sorted(filesystem.directory.iterdir()):
            if source.is_symlink() or not source.is_file():
                continue
            if source.suffix not in (".block", ".footer", ".json"):
                continue
            target = self.directory / source.name
            if source.suffix in (".block", ".footer"):
                os.link(source, target)
            else:
                shutil.copyfile(source, target)
            self.files[source.name] = {"size": source.stat().st_size,
                                       "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
        self.evidence = {"strategy": "complete_files", "status": "ready", "dataset": dataset,
                         "files": coverage, "total_bytes": total,
                         "manifest": self.files.copy(), "manifest_sha256": checksum(self.files),
                         "elapsed_seconds": time.perf_counter() - started}
        self.evidence["sha256"] = checksum(self.evidence)
        return self.evidence

    def restore(self, directory):
        if self.evidence is None:
            raise ValueError("Cache seed has not been validated")
        directory = Path(directory)
        for name, expected in self.files.items():
            source, target = self.directory / name, directory / name
            if source.is_symlink() or not source.is_file() or source.stat().st_size != expected["size"]:
                raise ValueError("Cache seed files changed after validation")
            if source.suffix in (".block", ".footer"):
                os.link(source, target)
            else:
                shutil.copyfile(source, target)
        return self.evidence["sha256"]

    def validate(self):
        """Recheck seed contents once after measurement, outside timing."""
        for name, expected in self.files.items():
            source = self.directory / name
            if (source.is_symlink() or not source.is_file()
                    or hashlib.sha256(source.read_bytes()).hexdigest() != expected["sha256"]):
                raise ValueError("Cache seed contents changed after validation")

    def assert_identity(self, dataset):
        if self.evidence is None or self.evidence["dataset"] != dataset:
            raise ValueError("Dataset identity differs from the complete cache seed")
