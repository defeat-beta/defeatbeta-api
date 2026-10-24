"""Ensure shared measurement helpers do not preload product modules."""

import subprocess
import sys
import unittest

from benchmark.common import percentile


class TestSharedQueryBenchmark(unittest.TestCase):
    def test_empirical_p95_uses_nearest_rank(self):
        self.assertEqual(percentile(list(range(1, 21)), 0.95), 19)
        self.assertEqual(percentile([3], 0.95), 3)
    def test_import_does_not_preload_product_modules(self):
        result = subprocess.run([
            sys.executable, "-c",
            "import sys; import benchmark.common; "
            "assert not any(name.startswith('defeatbeta_api') for name in sys.modules)",
        ], capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
