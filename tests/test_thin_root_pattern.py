"""Test that the consolidated repo follows the thin-root pattern.

The thin-root pattern means the root bundle.md should ONLY contain:
- bundle: metadata (name, version, description)
- includes: references to behaviors

It should NOT declare tools:, hooks:, or context: — those belong in the
behavior YAML files under behaviors/.

The consolidated repo has a single root bundle.md (env-all) that includes
behaviors, and each behavior YAML carries its own tools/hooks/context.
"""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

BEHAVIOR_FILES = [
    "env-all.yaml",
    "env-core.yaml",
    "env-docker.yaml",
    "env-ssh.yaml",
    "env-security.yaml",
]

EXPECTED_SOURCE_REPO = "microsoft/amplifier-bundle-execution-environments"


def _parse_frontmatter() -> dict:
    """Extract YAML frontmatter from the root bundle.md."""
    p = REPO_ROOT / "bundle.md"
    content = p.read_text()
    parts = content.split("---", 2)
    assert len(parts) >= 3, "bundle.md missing YAML frontmatter delimiters"
    return yaml.safe_load(parts[1])


def _load_behavior(filename: str) -> dict:
    """Load a behavior YAML file."""
    p = REPO_ROOT / "behaviors" / filename
    return yaml.safe_load(p.read_text())


class TestThinRootPattern:
    """Verify root bundle.md follows the thin-root pattern."""

    def test_root_bundle_has_metadata(self):
        """Root bundle.md must have bundle: metadata with name and version."""
        fm = _parse_frontmatter()
        assert "bundle" in fm, "bundle.md missing 'bundle:' metadata"
        bundle_meta = fm["bundle"]
        assert "name" in bundle_meta, "bundle.md missing bundle name"
        assert "version" in bundle_meta, "bundle.md missing bundle version"
        assert "description" in bundle_meta, "bundle.md missing bundle description"

    def test_root_bundle_has_includes(self):
        """Root bundle.md must include at least one behavior."""
        fm = _parse_frontmatter()
        assert "includes" in fm, "bundle.md missing 'includes:'"
        includes = fm["includes"]
        assert len(includes) >= 1, "bundle.md has empty includes list"

    def test_root_no_tools_in_frontmatter(self):
        """Root bundle.md must not declare tools: (behaviors carry them)."""
        fm = _parse_frontmatter()
        assert "tools" not in fm, (
            "bundle.md has 'tools:' in frontmatter — "
            "this duplicates the behaviors. Remove it (thin-root pattern)."
        )

    def test_root_no_hooks_in_frontmatter(self):
        """Root bundle.md must not declare hooks: (behaviors carry them)."""
        fm = _parse_frontmatter()
        assert "hooks" not in fm, (
            "bundle.md has 'hooks:' in frontmatter — "
            "this duplicates the behaviors. Remove it (thin-root pattern)."
        )

    def test_root_no_context_in_frontmatter(self):
        """Root bundle.md must not declare context: (behaviors carry it)."""
        fm = _parse_frontmatter()
        assert "context" not in fm, (
            "bundle.md has 'context:' in frontmatter — "
            "this duplicates the behaviors. Remove it (thin-root pattern)."
        )


class TestBehaviorStructure:
    """Verify each behavior YAML has proper structure."""

    def test_all_behavior_files_exist(self):
        """All expected behavior YAML files must exist."""
        for filename in BEHAVIOR_FILES:
            p = REPO_ROOT / "behaviors" / filename
            assert p.exists(), f"behaviors/{filename} does not exist"

    def test_behaviors_have_bundle_metadata(self):
        """Each behavior must have bundle: metadata with name and version."""
        for filename in BEHAVIOR_FILES:
            beh = _load_behavior(filename)
            assert "bundle" in beh, f"behaviors/{filename} missing 'bundle:' metadata"
            meta = beh["bundle"]
            assert "name" in meta, f"behaviors/{filename} missing bundle name"
            assert "version" in meta, f"behaviors/{filename} missing bundle version"

    def test_behaviors_have_tools(self):
        """Each behavior must declare tools: with source fields."""
        for filename in BEHAVIOR_FILES:
            beh = _load_behavior(filename)
            assert "tools" in beh, f"behaviors/{filename} missing 'tools:'"
            tools = beh["tools"]
            assert len(tools) >= 1, f"behaviors/{filename} has empty tools list"
            for tool in tools:
                assert "source" in tool, (
                    f"behaviors/{filename} tool missing 'source:' field"
                )
                assert EXPECTED_SOURCE_REPO in tool["source"], (
                    f"behaviors/{filename} tool source does not reference "
                    f"{EXPECTED_SOURCE_REPO}"
                )

    def test_behaviors_have_hooks_section(self):
        """Each behavior must have a hooks: section (may be empty list)."""
        for filename in BEHAVIOR_FILES:
            beh = _load_behavior(filename)
            assert "hooks" in beh, f"behaviors/{filename} missing 'hooks:'"

    def test_behavior_hook_sources(self):
        """Behaviors with non-empty hooks must have proper source fields."""
        for filename in BEHAVIOR_FILES:
            beh = _load_behavior(filename)
            hooks = beh.get("hooks", [])
            for hook in hooks:
                assert "source" in hook, (
                    f"behaviors/{filename} hook missing 'source:' field"
                )
                assert EXPECTED_SOURCE_REPO in hook["source"], (
                    f"behaviors/{filename} hook source does not reference "
                    f"{EXPECTED_SOURCE_REPO}"
                )
