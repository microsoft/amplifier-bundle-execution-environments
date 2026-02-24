"""Test that the additive context guides teach the instance-based model correctly.

Validates the split context guides cover all required concepts, tools,
and example workflows for the Phase 4 instance-based environment model,
including Phase 4.2 (compose, attach, SSH auto-discovery) and
Phase 4.3 (security, composable wrappers) capabilities.

Phase 4.4 Slice C split the monolithic env-all-guide.md into 4 additive
guides: core, docker, ssh, and security.
"""

from pathlib import Path

CONTEXT_DIR = Path(__file__).resolve().parent.parent / "context"

CORE_GUIDE = CONTEXT_DIR / "env-core-guide.md"
DOCKER_GUIDE = CONTEXT_DIR / "env-docker-guide.md"
SSH_GUIDE = CONTEXT_DIR / "env-ssh-guide.md"
SECURITY_GUIDE = CONTEXT_DIR / "env-security-guide.md"

# All 11 tools that must appear in the core guide
ALL_TOOLS = [
    "env_create",
    "env_destroy",
    "env_list",
    "env_exec",
    "env_read_file",
    "env_write_file",
    "env_edit_file",
    "env_grep",
    "env_glob",
    "env_list_dir",
    "env_file_exists",
]


def _read_all_guides() -> str:
    """Read and concatenate all 4 guide files."""
    texts = []
    for guide in [CORE_GUIDE, DOCKER_GUIDE, SSH_GUIDE, SECURITY_GUIDE]:
        texts.append(guide.read_text())
    return "\n".join(texts)


def _line_count(text: str) -> int:
    return len(text.strip().splitlines())


class TestContextGuideContent:
    """Verify the core guide teaches the instance-based model."""

    def test_guide_exists(self):
        assert CORE_GUIDE.exists(), "env-core-guide.md must exist"

    def test_core_guide_concise(self):
        text = CORE_GUIDE.read_text()
        count = _line_count(text)
        assert count <= 50, f"Core guide is {count} lines, should be concise (<= 50)"

    def test_all_11_tools_referenced(self):
        """Every tool must appear in the core guide."""
        text = CORE_GUIDE.read_text()
        for tool in ALL_TOOLS:
            assert tool in text, f"Tool '{tool}' missing from core guide"

    def test_instance_parameter_explained(self):
        """Guide must explain the instance parameter."""
        text = CORE_GUIDE.read_text().lower()
        assert "instance" in text, "Must explain the 'instance' parameter"

    def test_local_default_explained(self):
        """Guide must explain that 'local' instance exists by default."""
        text = CORE_GUIDE.read_text().lower()
        assert "local" in text, "Must mention the 'local' default instance"
        assert "default" in text, "Must explain 'local' is the default"

    def test_create_use_destroy_workflow(self):
        """Guide must teach the create -> use -> destroy lifecycle."""
        text = CORE_GUIDE.read_text()
        assert "env_create" in text
        assert "env_destroy" in text
        lower = text.lower()
        assert "create" in lower and "destroy" in lower

    def test_three_environment_types(self):
        """Across all guides, local, docker, and ssh types are covered."""
        text = _read_all_guides().lower()
        assert "local" in text, "Must cover local type"
        assert "docker" in text, "Must cover docker type"
        assert "ssh" in text, "Must cover ssh type"

    def test_tool_reference_table(self):
        """Core guide must have a tool reference table with all 11 tools."""
        text = CORE_GUIDE.read_text()
        table_lines = [line for line in text.splitlines() if "|" in line]
        assert len(table_lines) >= 13, (
            f"Expected at least 13 table lines (header + separator + 11 tools), "
            f"got {len(table_lines)}"
        )

    def test_example_workflows_present(self):
        """Core guide must include example workflows."""
        text = CORE_GUIDE.read_text()
        assert "```" in text, "Must include code examples"

    def test_no_old_prefix_model(self):
        """Guides must NOT reference the old Phase 3 prefix model."""
        text = _read_all_guides()
        assert "env.local." not in text, "Must not reference old env.local.* prefix"
        assert "env.docker." not in text, "Must not reference old env.docker.* prefix"
        assert "env.ssh." not in text, "Must not reference old env.ssh.* prefix"
        assert "Tool Prefix" not in text, "Must not have old 'Tool Prefix' column"

    def test_no_decorator_references(self):
        """Guides must not reference old decorator concepts."""
        text = _read_all_guides()
        assert "Decorator" not in text, "Must not reference old decorator concept"
        assert "AuditTrail" not in text
        assert "ReadOnly" not in text


class TestPhase42Content:
    """Verify the docker and ssh guides document Phase 4.2 capabilities."""

    def test_compose_support_section(self):
        """Docker guide must have compose support with key params."""
        text = DOCKER_GUIDE.read_text()
        lower = text.lower()
        assert "compose" in lower, "Must have compose support section"
        assert "compose_files" in text, "Must mention compose_files param"
        assert "compose_project" in text, "Must mention compose_project param"
        assert "attach_to" in text, "Must mention attach_to param"
        assert "health_check" in text, "Must mention health_check param"

    def test_compose_example(self):
        """Docker guide must show a compose workflow example."""
        text = DOCKER_GUIDE.read_text()
        assert "compose_files=" in text, "Must show compose_files usage"
        assert "compose down" in text.lower() or "compose" in text.lower(), (
            "Must explain compose cleanup"
        )

    def test_cross_session_sharing_section(self):
        """Docker guide must explain cross-session sharing via attach."""
        text = DOCKER_GUIDE.read_text()
        lower = text.lower()
        assert "attach" in lower, "Must explain attach pattern"
        assert "own" in lower, "Must explain ownership (creating session owns)"

    def test_ssh_auto_discovery_section(self):
        """SSH guide must document SSH auto-discovery."""
        text = SSH_GUIDE.read_text()
        lower = text.lower()
        assert "auto-discover" in lower or "auto discover" in lower, (
            "Must mention SSH auto-discovery"
        )
        assert ".ssh/config" in text or "ssh/config" in lower, (
            "Must mention ~/.ssh/config"
        )

    def test_env_create_new_params_in_docker_guide(self):
        """Docker guide must reference compose or attach capabilities."""
        text = DOCKER_GUIDE.read_text()
        lower = text.lower()
        assert "compose" in lower or "attach" in lower, (
            "Docker guide must reference compose or attach capabilities"
        )


class TestPhase43Content:
    """Verify the security guide documents Phase 4.3 capabilities."""

    def test_security_section_exists(self):
        """Security guide must cover env var filtering."""
        text = SECURITY_GUIDE.read_text()
        lower = text.lower()
        assert "security" in lower, "Must have a security section"
        assert "env_policy" in text, "Must mention env_policy parameter"

    def test_env_var_policies_documented(self):
        """Security guide must document all three env var policies."""
        text = SECURITY_GUIDE.read_text()
        assert "core_only" in text, "Must document core_only policy"
        assert "inherit_all" in text, "Must document inherit_all policy"
        assert "inherit_none" in text, "Must document inherit_none policy"

    def test_core_only_is_default(self):
        """Security guide must indicate core_only is the default policy."""
        text = SECURITY_GUIDE.read_text()
        assert "core_only" in text and "default" in text.lower(), (
            "Must indicate core_only is the default"
        )

    def test_filtered_patterns_mentioned(self):
        """Security guide must mention what patterns are filtered."""
        text = SECURITY_GUIDE.read_text()
        assert "API_KEY" in text or "SECRET" in text or "TOKEN" in text, (
            "Must mention filtered env var patterns (API_KEY, SECRET, TOKEN, etc.)"
        )

    def test_wrappers_section_exists(self):
        """Security guide must have a composable wrappers section."""
        text = SECURITY_GUIDE.read_text()
        lower = text.lower()
        assert "wrapper" in lower, "Must have a wrappers section"
        assert "logging" in lower, "Must document logging wrapper"
        assert "readonly" in lower, "Must document readonly wrapper"

    def test_wrappers_creation_example(self):
        """Security guide must show how to apply wrappers at creation time."""
        text = SECURITY_GUIDE.read_text()
        assert "wrappers=" in text, "Must show wrappers parameter usage"
        assert 'wrappers=["logging"' in text or "wrappers=['logging'" in text, (
            "Must show logging wrapper example"
        )

    def test_wrapper_behaviors_documented(self):
        """Security guide must explain what each wrapper does."""
        text = SECURITY_GUIDE.read_text()
        lower = text.lower()
        assert "log" in lower, "Must explain logging wrapper behavior"
        assert "block" in lower or "permissionerror" in lower, (
            "Must explain readonly wrapper blocks writes"
        )

    def test_security_guide_has_env_policy_and_wrappers(self):
        """Security guide must mention env_policy and wrappers."""
        text = SECURITY_GUIDE.read_text()
        assert "env_policy" in text, "Must mention env_policy param"
        assert "wrappers" in text, "Must mention wrappers param"
