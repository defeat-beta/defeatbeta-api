import unittest
from pathlib import Path
import tomllib


class DependencyConstraintTests(unittest.TestCase):
    def test_mcp_dependency_uses_v2_release_line(self):
        pyproject_path = Path(__file__).parents[1] / "pyproject.toml"
        pyproject = pyproject_path.read_text(encoding="utf-8")

        self.assertIn('"mcp>=2.0.0,<3"', pyproject)

    def test_api_dependency_requires_us_data_layout_release(self):
        pyproject_path = Path(__file__).parents[1] / "pyproject.toml"
        project = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))["project"]
        self.assertIn("defeatbeta-api>=0.0.61", project["dependencies"])

    def test_installer_installs_mcp_project_dependencies(self):
        installer_path = Path(__file__).parents[1] / "install"
        installer = installer_path.read_text(encoding="utf-8")

        self.assertIn('pip install "$INSTALL_DIR/mcp"', installer)


if __name__ == "__main__":
    unittest.main()
