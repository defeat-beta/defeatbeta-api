import subprocess
import sys
import textwrap
import unittest


class TestPackageImport(unittest.TestCase):

    def test_import_has_no_network_or_output_side_effects(self):
        script = textwrap.dedent(
            """
            import requests.sessions

            def reject_network(*args, **kwargs):
                raise AssertionError("Package import attempted a network request")

            requests.sessions.Session.request = reject_network

            import defeatbeta_api
            from defeatbeta_api import HuggingFaceClient
            from defeatbeta_api.data.ticker import Ticker

            assert defeatbeta_api.__version__
            assert HuggingFaceClient
            assert Ticker
            """
        )

        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
