"""Verify all repo URLs and references use the consolidated repo name.

After Phase 4.4 Task A.4, all GitHub URLs must point to
microsoft/amplifier-bundle-execution-environments (the consolidated repo).
No references to old personal (bkrabach/) or old repo names
(amplifier-bundle-env-all, amplifier-env-common as a separate repo) should remain.
"""

import subprocess
from pathlib import Path

ENV_ALL = Path(__file__).resolve().parent.parent


class TestNoStaleRepoReferences:
    """No stale GitHub repo references should remain in env-all/."""

    def test_no_bkrabach_references(self):
        """Verify no personal GitHub references remain."""
        result = subprocess.run(
            [
                "grep",
                "-rn",
                "--include=*.md",
                "--include=*.yaml",
                "--include=*.toml",
                "--include=*.py",
                "bkrabach/",
                str(ENV_ALL),
            ],
            capture_output=True,
            text=True,
        )
        # Filter out hits from this test file itself
        hits = [
            line
            for line in result.stdout.splitlines()
            if "test_repo_references.py" not in line
        ]
        assert not hits, "Found bkrabach/ references:\n" + "\n".join(hits)

    def test_no_old_bundle_repo_name_in_urls(self):
        """No git+https or github.com URLs should reference the old repo name."""
        result = subprocess.run(
            [
                "grep",
                "-rn",
                r"github\.com/[^)\"' ]*/amplifier-bundle-env-all",
                str(ENV_ALL),
                "--include=*.md",
                "--include=*.yaml",
                "--include=*.toml",
                "--include=*.py",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1, (
            f"Found old amplifier-bundle-env-all repo URLs:\n{result.stdout}"
        )

    def test_no_old_env_common_repo_url(self):
        """No github.com URLs should reference amplifier-env-common as a separate repo."""
        result = subprocess.run(
            [
                "grep",
                "-rn",
                r"github\.com/[^)\"' ]*/amplifier-env-common",
                str(ENV_ALL),
                "--include=*.md",
                "--include=*.yaml",
                "--include=*.toml",
                "--include=*.py",
            ],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1, (
            f"Found old amplifier-env-common repo URLs:\n{result.stdout}"
        )

    def test_readme_install_url_uses_new_repo(self):
        """README installation command must use the consolidated repo name."""
        readme = (ENV_ALL / "README.md").read_text()
        assert "microsoft/amplifier-bundle-execution-environments" in readme, (
            "README.md does not contain the new consolidated repo URL"
        )
