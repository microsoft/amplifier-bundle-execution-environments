"""Test that behavior variants and additive context guides exist and are correct.

Phase 4.4 Slice C: The monolithic env-all-guide.md is split into 4 additive
context guides, and 4 new behavior YAMLs select subsets of tools + guides.
"""

from pathlib import Path

import yaml

ENV_ALL = Path(__file__).resolve().parent.parent
BEHAVIORS = ENV_ALL / "behaviors"
CONTEXT = ENV_ALL / "context"
BUNDLE_MD = ENV_ALL / "bundle.md"


def _load_yaml(path: Path) -> dict:
    """Load a YAML file."""
    return yaml.safe_load(path.read_text())


def _parse_frontmatter(path: Path) -> dict:
    """Extract YAML frontmatter from a markdown file."""
    content = path.read_text()
    parts = content.split("---", 2)
    assert len(parts) >= 3, f"{path.name} missing YAML frontmatter delimiters"
    return yaml.safe_load(parts[1])


# ── C.2: Behavior YAML existence ──────────────────────────────────────


class TestBehaviorYAMLsExist:
    """Verify the 4 new behavior YAMLs exist."""

    def test_env_core_yaml_exists(self):
        assert (BEHAVIORS / "env-core.yaml").exists(), "env-core.yaml must exist"

    def test_env_docker_yaml_exists(self):
        assert (BEHAVIORS / "env-docker.yaml").exists(), "env-docker.yaml must exist"

    def test_env_ssh_yaml_exists(self):
        assert (BEHAVIORS / "env-ssh.yaml").exists(), "env-ssh.yaml must exist"

    def test_env_security_yaml_exists(self):
        assert (BEHAVIORS / "env-security.yaml").exists(), (
            "env-security.yaml must exist"
        )


# ── C.1: Context guide existence ──────────────────────────────────────


class TestContextGuidesExist:
    """Verify all 4 additive context guide files exist."""

    def test_all_context_guides_exist(self):
        guides = [
            "env-core-guide.md",
            "env-docker-guide.md",
            "env-ssh-guide.md",
            "env-security-guide.md",
        ]
        for guide in guides:
            assert (CONTEXT / guide).exists(), f"{guide} must exist"

    def test_old_monolithic_guide_removed(self):
        assert not (CONTEXT / "env-all-guide.md").exists(), (
            "Old monolithic env-all-guide.md must be removed"
        )


# ── C.3: env-all.yaml includes all guides ────────────────────────────


class TestEnvAllYAMLUpdated:
    """Verify env-all.yaml references all 4 guides and has config."""

    def test_env_all_yaml_includes_all_guides(self):
        data = _load_yaml(BEHAVIORS / "env-all.yaml")
        includes = data.get("context", {}).get("include", [])
        expected = [
            "env-all:context/env-core-guide.md",
            "env-all:context/env-docker-guide.md",
            "env-all:context/env-ssh-guide.md",
            "env-all:context/env-security-guide.md",
        ]
        for guide in expected:
            assert guide in includes, (
                f"env-all.yaml must include {guide}, got {includes}"
            )

    def test_env_all_yaml_has_all_backends(self):
        data = _load_yaml(BEHAVIORS / "env-all.yaml")
        config = data["tools"][0].get("config", {})
        backends = config.get("backends", [])
        assert "local" in backends
        assert "docker" in backends
        assert "ssh" in backends

    def test_env_all_yaml_has_security_enabled(self):
        data = _load_yaml(BEHAVIORS / "env-all.yaml")
        config = data["tools"][0].get("config", {})
        assert config.get("enable_security") is True


# ── Behavior content correctness ──────────────────────────────────────


class TestBehaviorContent:
    """Verify each behavior YAML has correct config and context includes."""

    def test_env_core_yaml_only_includes_core_guide(self):
        data = _load_yaml(BEHAVIORS / "env-core.yaml")
        includes = data.get("context", {}).get("include", [])
        assert includes == ["env-all:context/env-core-guide.md"], (
            f"env-core.yaml must include only core guide, got {includes}"
        )

    def test_env_core_yaml_has_local_only(self):
        data = _load_yaml(BEHAVIORS / "env-core.yaml")
        config = data["tools"][0].get("config", {})
        assert config.get("backends") == ["local"]
        assert config.get("enable_security") is False

    def test_env_docker_yaml_includes_core_and_docker(self):
        data = _load_yaml(BEHAVIORS / "env-docker.yaml")
        includes = data.get("context", {}).get("include", [])
        assert "env-all:context/env-core-guide.md" in includes
        assert "env-all:context/env-docker-guide.md" in includes
        assert len(includes) == 2

    def test_env_docker_yaml_has_local_and_docker(self):
        data = _load_yaml(BEHAVIORS / "env-docker.yaml")
        config = data["tools"][0].get("config", {})
        assert config.get("backends") == ["local", "docker"]

    def test_env_ssh_yaml_includes_core_and_ssh(self):
        data = _load_yaml(BEHAVIORS / "env-ssh.yaml")
        includes = data.get("context", {}).get("include", [])
        assert "env-all:context/env-core-guide.md" in includes
        assert "env-all:context/env-ssh-guide.md" in includes
        assert len(includes) == 2

    def test_env_ssh_yaml_has_local_and_ssh(self):
        data = _load_yaml(BEHAVIORS / "env-ssh.yaml")
        config = data["tools"][0].get("config", {})
        assert config.get("backends") == ["local", "ssh"]

    def test_env_security_yaml_includes_only_security_guide(self):
        data = _load_yaml(BEHAVIORS / "env-security.yaml")
        includes = data.get("context", {}).get("include", [])
        assert includes == ["env-all:context/env-security-guide.md"]

    def test_env_security_yaml_has_security_enabled(self):
        data = _load_yaml(BEHAVIORS / "env-security.yaml")
        config = data["tools"][0].get("config", {})
        assert config.get("enable_security") is True


# ── C.4: bundle.md selective comments ─────────────────────────────────


class TestBundleMDUpdated:
    """Verify bundle.md documents selective behavior inclusion."""

    def test_bundle_md_has_selective_comments(self):
        content = BUNDLE_MD.read_text()
        assert "env-core" in content, "bundle.md must mention env-core behavior"
        assert "env-docker" in content, "bundle.md must mention env-docker behavior"
        assert "env-ssh" in content, "bundle.md must mention env-ssh behavior"
        assert "env-security" in content, "bundle.md must mention env-security behavior"

    def test_bundle_md_has_selective_installation_section(self):
        content = BUNDLE_MD.read_text()
        assert "Selective" in content or "selective" in content, (
            "bundle.md must have a Selective Installation section"
        )
