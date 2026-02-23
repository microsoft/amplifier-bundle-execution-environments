"""Test that env-all-guide.md teaches the instance-based model correctly.

Validates the agent context guide covers all required concepts, tools,
and example workflows for the Phase 4 instance-based environment model,
including Phase 4.2 (compose, attach, SSH auto-discovery) and
Phase 4.3 (security, composable wrappers) capabilities.
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

    def test_under_140_lines(self):
        text = _read_guide()
        count = _line_count(text)
        assert count <= 140, f"Guide is {count} lines, must be under 140"

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


class TestPhase43Content:
    """Verify the guide documents Phase 4.3 security and wrapper capabilities."""

    def test_security_section_exists(self):
        """Guide must have a security section covering env var filtering."""
        text = _read_guide()
        lower = text.lower()
        assert "security" in lower, "Must have a security section"
        assert "env_policy" in text, "Must mention env_policy parameter"

    def test_env_var_policies_documented(self):
        """Guide must document all three env var policies."""
        text = _read_guide()
        assert "core_only" in text, "Must document core_only policy"
        assert "inherit_all" in text, "Must document inherit_all policy"
        assert "inherit_none" in text, "Must document inherit_none policy"

    def test_core_only_is_default(self):
        """Guide must indicate core_only is the default policy."""
        text = _read_guide()
        # core_only and default must appear near each other
        assert "core_only" in text and "default" in text.lower(), (
            "Must indicate core_only is the default"
        )

    def test_filtered_patterns_mentioned(self):
        """Guide must mention what patterns are filtered."""
        text = _read_guide()
        # Must mention the sensitive patterns that get filtered
        assert "API_KEY" in text or "SECRET" in text or "TOKEN" in text, (
            "Must mention filtered env var patterns (API_KEY, SECRET, TOKEN, etc.)"
        )

    def test_wrappers_section_exists(self):
        """Guide must have a composable wrappers section."""
        text = _read_guide()
        lower = text.lower()
        assert "wrapper" in lower, "Must have a wrappers section"
        assert "logging" in lower, "Must document logging wrapper"
        assert "readonly" in lower, "Must document readonly wrapper"

    def test_wrappers_creation_example(self):
        """Guide must show how to apply wrappers at creation time."""
        text = _read_guide()
        assert "wrappers=" in text, "Must show wrappers parameter usage"
        assert 'wrappers=["logging"' in text or "wrappers=['logging'" in text, (
            "Must show logging wrapper example"
        )

    def test_wrapper_behaviors_documented(self):
        """Guide must explain what each wrapper does."""
        text = _read_guide()
        lower = text.lower()
        # logging wrapper logs operations
        assert "log" in lower, "Must explain logging wrapper behavior"
        # readonly wrapper blocks writes
        assert "block" in lower or "permissionerror" in lower, (
            "Must explain readonly wrapper blocks writes"
        )

    def test_env_create_table_has_phase43_params(self):
        """Tool reference table for env_create must mention env_policy and wrappers."""
        text = _read_guide()
        table_lines = [line for line in text.splitlines() if "|" in line]
        create_lines = [line for line in table_lines if "env_create" in line]
        assert create_lines, "env_create must appear in the tool table"
        create_text = " ".join(create_lines)
        assert "env_policy" in create_text, (
            "env_create table entry must mention env_policy param"
        )
        assert "wrappers" in create_text, (
            "env_create table entry must mention wrappers param"
        )
