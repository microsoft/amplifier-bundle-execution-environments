"""Test that bundle.md files follow the thin-root pattern.

The thin-root pattern means the root bundle.md should ONLY contain:
- bundle: metadata (name, version, description, config, extensions, dependencies)
- includes: references to behaviors
- context: (only if env-all which has its own guide separate from sub-bundles)

It should NOT re-declare tools:, hooks:, or context: that the included
behavior already provides. Duplication causes potential double-mounting.

env-all is excluded because it's a pure composition bundle (no behavior of its own,
just includes other bundles + its own context guide).
"""

from pathlib import Path

import yaml

# Bundles that include a behavior and must NOT duplicate its declarations
THIN_ROOT_BUNDLES = ["env-local", "env-docker", "env-ssh", "env-decorators"]

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _parse_frontmatter(bundle_dir: str) -> dict:
    """Extract YAML frontmatter from a bundle.md file."""
    p = REPO_ROOT / bundle_dir / "bundle.md"
    content = p.read_text()
    parts = content.split("---", 2)
    assert len(parts) >= 3, f"{bundle_dir}/bundle.md missing YAML frontmatter delimiters"
    return yaml.safe_load(parts[1])


class TestThinRootPattern:
    """Verify bundle.md files don't duplicate what their behaviors declare."""

    def test_no_tools_in_root_frontmatter(self):
        """Root bundle.md must not declare tools: (behavior carries them)."""
        for bundle_dir in THIN_ROOT_BUNDLES:
            fm = _parse_frontmatter(bundle_dir)
            assert "tools" not in fm, (
                f"{bundle_dir}/bundle.md has 'tools:' in frontmatter — "
                f"this duplicates the behavior. Remove it (thin-root pattern)."
            )

    def test_no_hooks_in_root_frontmatter(self):
        """Root bundle.md must not declare hooks: (behavior carries them)."""
        for bundle_dir in THIN_ROOT_BUNDLES:
            fm = _parse_frontmatter(bundle_dir)
            assert "hooks" not in fm, (
                f"{bundle_dir}/bundle.md has 'hooks:' in frontmatter — "
                f"this duplicates the behavior. Remove it (thin-root pattern)."
            )

    def test_no_context_in_root_frontmatter(self):
        """Root bundle.md must not declare context: (behavior carries it)."""
        for bundle_dir in THIN_ROOT_BUNDLES:
            fm = _parse_frontmatter(bundle_dir)
            assert "context" not in fm, (
                f"{bundle_dir}/bundle.md has 'context:' in frontmatter — "
                f"this duplicates the behavior. Remove it (thin-root pattern)."
            )

    def test_includes_present(self):
        """Root bundle.md must include its behavior."""
        for bundle_dir in THIN_ROOT_BUNDLES:
            fm = _parse_frontmatter(bundle_dir)
            assert "includes" in fm, (
                f"{bundle_dir}/bundle.md missing 'includes:' — "
                f"must include its behavior."
            )
            includes = fm["includes"]
            assert len(includes) >= 1, (
                f"{bundle_dir}/bundle.md has empty includes list."
            )

    def test_bundle_metadata_present(self):
        """Root bundle.md must have bundle: metadata."""
        for bundle_dir in THIN_ROOT_BUNDLES:
            fm = _parse_frontmatter(bundle_dir)
            assert "bundle" in fm, f"{bundle_dir}/bundle.md missing 'bundle:' metadata"
            bundle_meta = fm["bundle"]
            assert "name" in bundle_meta, f"{bundle_dir}/bundle.md missing bundle name"
            assert "version" in bundle_meta, f"{bundle_dir}/bundle.md missing bundle version"

    def test_env_docker_keeps_dependencies(self):
        """env-docker must retain its dependencies declaration."""
        fm = _parse_frontmatter("env-docker")
        bundle_meta = fm["bundle"]
        assert "dependencies" in bundle_meta, (
            "env-docker/bundle.md must keep dependencies: [containers]"
        )
