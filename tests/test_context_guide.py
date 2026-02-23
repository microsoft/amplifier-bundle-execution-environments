"""Test that env-all-guide.md teaches the instance-based model correctly.

Validates the agent context guide covers all required concepts, tools,
and example workflows for the Phase 4 instance-based environment model,
including Phase 4.2 capabilities (compose, attach, SSH auto-discovery).
"""

from pathlib import Path

GUIDE_PATH = Path(__file__).resolve().parent.parent / "context" / "env-all-guide.md"

# All 11 tools that must appear in the guide
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


def _read_guide() -> str:
    return GUIDE_PATH.read_text()


def _line_count(text: str) -> int:
    return len(text.strip().splitlines())


class TestContextGuideContent:
    """Verify the guide teaches the instance-based model."""

    def test_guide_exists(self):
        assert GUIDE_PATH.exists(), "env-all-guide.md must exist"

    def test_under_120_lines(self):
        text = _read_guide()
        count = _line_count(text)
        assert count <= 120, f"Guide is {count} lines, must be under 120"

    def test_all_11_tools_referenced(self):
        """Every tool must appear in the guide."""
        text = _read_guide()
        for tool in ALL_TOOLS:
            assert tool in text, f"Tool '{tool}' missing from guide"

    def test_instance_parameter_explained(self):
        """Guide must explain the instance parameter."""
        text = _read_guide().lower()
        assert "instance" in text, "Must explain the 'instance' parameter"

    def test_local_default_explained(self):
        """Guide must explain that 'local' instance exists by default."""
        text = _read_guide().lower()
        assert "local" in text, "Must mention the 'local' default instance"
        assert "default" in text, "Must explain 'local' is the default"

    def test_create_use_destroy_workflow(self):
        """Guide must teach the create → use → destroy lifecycle."""
        text = _read_guide()
        assert "env_create" in text
        assert "env_destroy" in text
        # Must show the lifecycle concept
        lower = text.lower()
        assert "create" in lower and "destroy" in lower

    def test_three_environment_types(self):
        """Guide must cover local, docker, and ssh types."""
        text = _read_guide().lower()
        assert "local" in text, "Must cover local type"
        assert "docker" in text, "Must cover docker type"
        assert "ssh" in text, "Must cover ssh type"

    def test_tool_reference_table(self):
        """Guide must have a tool reference table with all 11 tools."""
        text = _read_guide()
        # A markdown table has | delimiters; check tools appear in table rows
        table_lines = [line for line in text.splitlines() if "|" in line]
        assert len(table_lines) >= 13, (
            f"Expected at least 13 table lines (header + separator + 11 tools), "
            f"got {len(table_lines)}"
        )

    def test_example_workflows_present(self):
        """Guide must include example workflows."""
        text = _read_guide()
        # Must have code blocks showing usage
        assert "```" in text, "Must include code examples"
        # Must show local, docker, and ssh examples
        assert 'instance="' in text or "instance=" in text, (
            "Examples must show instance parameter usage"
        )

    def test_no_old_prefix_model(self):
        """Guide must NOT reference the old Phase 3 prefix model."""
        text = _read_guide()
        assert "env.local." not in text, "Must not reference old env.local.* prefix"
        assert "env.docker." not in text, "Must not reference old env.docker.* prefix"
        assert "env.ssh." not in text, "Must not reference old env.ssh.* prefix"
        assert "Tool Prefix" not in text, "Must not have old 'Tool Prefix' column"

    def test_no_decorator_references(self):
        """Guide must not reference old decorator concepts."""
        text = _read_guide()
        assert "Decorator" not in text, "Must not reference old decorator concept"
        assert "AuditTrail" not in text
        assert "ReadOnly" not in text


class TestPhase42Content:
    """Verify the guide documents Phase 4.2 capabilities."""

    def test_compose_support_section(self):
        """Guide must have a compose support section with key params."""
        text = _read_guide()
        lower = text.lower()
        assert "compose" in lower, "Must have compose support section"
        assert "compose_files" in text, "Must mention compose_files param"
        assert "compose_project" in text, "Must mention compose_project param"
        assert "attach_to" in text, "Must mention attach_to param"
        assert "health_check" in text, "Must mention health_check param"

    def test_compose_example(self):
        """Guide must show a compose workflow example."""
        text = _read_guide()
        # Must show compose_files in a code example
        assert "compose_files=" in text, "Must show compose_files usage"
        assert "compose down" in text.lower() or "compose" in text.lower(), (
            "Must explain compose cleanup"
        )

    def test_cross_session_sharing_section(self):
        """Guide must explain cross-session sharing via attach."""
        text = _read_guide()
        lower = text.lower()
        assert "attach" in lower, "Must explain attach pattern"
        # Must explain ownership semantics
        assert "own" in lower, "Must explain ownership (creating session owns)"

    def test_ssh_auto_discovery_section(self):
        """Guide must document SSH auto-discovery."""
        text = _read_guide()
        lower = text.lower()
        assert "auto-discover" in lower or "auto discover" in lower, (
            "Must mention SSH auto-discovery"
        )
        assert ".ssh/config" in text or "ssh/config" in lower, (
            "Must mention ~/.ssh/config"
        )

    def test_env_create_new_params_in_table(self):
        """Tool reference table must mention new env_create params."""
        text = _read_guide()
        # The table row for env_create should reference new capabilities
        table_lines = [line for line in text.splitlines() if "|" in line]
        create_lines = [line for line in table_lines if "env_create" in line]
        assert create_lines, "env_create must appear in the tool table"
        create_text = " ".join(create_lines)
        assert "compose" in create_text.lower() or "attach" in create_text.lower(), (
            "env_create table entry must reference compose or attach capabilities"
        )
