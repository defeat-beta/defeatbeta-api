import unittest
from pathlib import Path


class DependencyConstraintTests(unittest.TestCase):
    def test_mcp_dependency_uses_v2_release_line(self):
        pyproject_path = Path(__file__).parents[1] / "pyproject.toml"
        pyproject = pyproject_path.read_text(encoding="utf-8")

        self.assertIn('"mcp>=2.0.0,<3"', pyproject)


if __name__ == "__main__":
    unittest.main()
