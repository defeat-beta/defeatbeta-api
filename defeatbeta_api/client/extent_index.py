"""Process-local interval inventory; reconstruct once from retained disk files."""

from bisect import bisect_left, bisect_right
import hashlib
import re
from threading import RLock
from weakref import WeakValueDictionary


_RECORD = re.compile(
    r"(?P<object>(?P<tag>[0-9a-f]{16})-[0-9a-f]{64}-[A-Za-z0-9_.-]+)-"
    r"(?P<start>\d+)-(?P<length>\d+)\.(?P<kind>block|footer)"
)
_INDEXES = WeakValueDictionary()
_INDEX_LOCK = RLock()


class ExtentIndex:
    def __init__(self, directory, version):
        self.directory = directory
        self.tag = hashlib.sha256(version.encode()).hexdigest()[:16]
        self._lock = RLock()
        self._loaded = False
        self._objects = {}
        self._sorted = {}

    @classmethod
    def shared(cls, directory, version):
        key = (str(directory.resolve()), version)
        with _INDEX_LOCK:
            index = _INDEXES.get(key)
            if index is None:
                index = cls(directory, version)
                _INDEXES[key] = index
            return index

    @classmethod
    def retire_other_versions(cls, directory, version):
        root = str(directory.resolve())
        with _INDEX_LOCK:
            for (path, generation), index in list(_INDEXES.items()):
                if path == root and generation != version:
                    with index._lock:
                        index._objects.clear()
                        index._sorted.clear()

    def add(self, name):
        match = _RECORD.fullmatch(name)
        if match is None or match["tag"] != self.tag or int(match["length"]) < 1:
            return
        start = int(match["start"])
        with self._lock:
            self._objects.setdefault(match["object"], {})[name] = (
                start, start + int(match["length"]), match["kind"], name)
            self._sorted.pop(match["object"], None)

    def initialize(self, names):
        with self._lock:
            if self._loaded:
                return
            for name in names:
                self.add(name)
            self._loaded = True

    def overlapping(self, owner, start, end):
        with self._lock:
            if owner not in self._sorted:
                rows = sorted(self._objects.get(owner, {}).values())
                starts, maximums, maximum = [], [], 0
                for left, right, _, _ in rows:
                    starts.append(left)
                    maximum = max(maximum, right)
                    maximums.append(maximum)
                self._sorted[owner] = starts, maximums, rows
            starts, maximums, rows = self._sorted[owner]
            return [row for row in rows[bisect_right(maximums, start):bisect_left(starts, end)]
                    if row[1] > start]
