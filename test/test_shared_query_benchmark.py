"""Ensure baseline module selection happens before any product import."""

import subprocess
import sys
import unittest

from benchmark.workloads.shared_query_benchmark import percentile


class TestSharedQueryBenchmark(unittest.TestCase):
    def test_empirical_p95_uses_nearest_rank(self):
        self.assertEqual(percentile(list(range(1, 21)), 0.95), 19)
        self.assertEqual(percentile([3], 0.95), 3)
    def test_import_does_not_preload_product_modules(self):
        result = subprocess.run([
            sys.executable, "-c",
            "import sys; import benchmark.workloads.shared_query_benchmark; "
            "assert not any(name.startswith('defeatbeta_api') for name in sys.modules)",
        ], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
