"""Tests for DockerBackend — wraps containers tool exec into EnvironmentBackend."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from amplifier_env_common.backends.docker import DockerBackend
from amplifier_env_common.models import EnvExecResult, EnvFileEntry
from amplifier_env_common.protocol import EnvironmentBackend


# ---------------------------------------------------------------------------
# Fake containers tool
# ---------------------------------------------------------------------------


@dataclass
class FakeToolResult:
    """Mimics the ToolResult shape returned by containers tool."""

    success: bool
    output: dict | str | None = None
    error: dict | None = None


class FakeContainersTool:
    """Records invocations and returns scripted responses for containers tool."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.exec_responses: list[dict] = []

    def add_exec_response(
        self, stdout: str = "", stderr: str = "", exit_code: int = 0
    ) -> None:
        self.exec_responses.append(
            {"stdout": stdout, "stderr": stderr, "exit_code": exit_code}
        )

    async def invoke(self, input_dict: dict) -> FakeToolResult:
        self.calls.append(input_dict)
        if input_dict.get("operation") == "exec":
            if self.exec_responses:
                output = self.exec_responses.pop(0)
            else:
                output = {"stdout": "", "stderr": "", "exit_code": 0}
            return FakeToolResult(success=True, output=output)
        if input_dict.get("operation") == "destroy":
            return FakeToolResult(success=True, output="destroyed")
        return FakeToolResult(success=True, output={})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_tool():
    return FakeContainersTool()


@pytest.fixture
def backend(fake_tool):
    return DockerBackend(
        containers_invoke=fake_tool.invoke,
        container_id="test-container-123",
    )


# ---------------------------------------------------------------------------
# Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    """DockerBackend must satisfy the EnvironmentBackend protocol."""

    def test_isinstance_check(self, backend):
        assert isinstance(backend, EnvironmentBackend)

    def test_env_type_is_docker(self, backend):
        assert backend.env_type == "docker"


# ---------------------------------------------------------------------------
# exec_command
# ---------------------------------------------------------------------------


class TestExecCommand:
    """exec_command sends correct exec operation via containers tool."""

    @pytest.mark.asyncio
    async def test_sends_exec_operation(self, backend, fake_tool):
        fake_tool.add_exec_response(stdout="hello\n", stderr="", exit_code=0)
        result = await backend.exec_command("echo hello")
        assert isinstance(result, EnvExecResult)
        assert result.stdout == "hello\n"
        assert result.stderr == ""
        assert result.exit_code == 0

    @pytest.mark.asyncio
    async def test_captures_stderr_and_exit_code(self, backend, fake_tool):
        fake_tool.add_exec_response(stdout="", stderr="error msg", exit_code=1)
        result = await backend.exec_command("failing_cmd")
        assert result.stderr == "error msg"
        assert result.exit_code == 1

    @pytest.mark.asyncio
    async def test_passes_container_and_command(self, backend, fake_tool):
        fake_tool.add_exec_response(stdout="ok")
        await backend.exec_command("ls -la")
        call = fake_tool.calls[0]
        assert call["operation"] == "exec"
        assert call["container"] == "test-container-123"
        assert call["command"] == "ls -la"

    @pytest.mark.asyncio
    async def test_passes_timeout_and_workdir(self, backend, fake_tool):
        fake_tool.add_exec_response()
        await backend.exec_command("pwd", timeout=30.0, workdir="/tmp")
        call = fake_tool.calls[0]
        assert call["timeout"] == 30.0
        assert call["workdir"] == "/tmp"


# ---------------------------------------------------------------------------
# read_file
# ---------------------------------------------------------------------------


class TestReadFile:
    """read_file translates to cat command."""

    @pytest.mark.asyncio
    async def test_simple_cat(self, backend, fake_tool):
        fake_tool.add_exec_response(stdout="file content\n")
        content = await backend.read_file("/workspace/hello.txt")
        assert content == "file content\n"
        call = fake_tool.calls[0]
        assert "cat" in call["command"]
        assert "/workspace/hello.txt" in call["command"]

    @pytest.mark.asyncio
    async def test_with_offset_and_limit(self, backend, fake_tool):
        fake_tool.add_exec_response(stdout="line2\nline3\n")
        content = await backend.read_file("/workspace/f.txt", offset=2, limit=2)
        assert content == "line2\nline3\n"
        cmd = fake_tool.calls[0]["command"]
        assert "tail -n +2" in cmd
        assert "head -n 2" in cmd

    @pytest.mark.asyncio
    async def test_with_offset_only(self, backend, fake_tool):
        fake_tool.add_exec_response(stdout="line2\nline3\n")
        content = await backend.read_file("/workspace/f.txt", offset=2)
        assert content == "line2\nline3\n"
        cmd = fake_tool.calls[0]["command"]
        assert "tail -n +2" in cmd

    @pytest.mark.asyncio
    async def test_with_limit_only(self, backend, fake_tool):
        fake_tool.add_exec_response(stdout="line1\n")
        content = await backend.read_file("/workspace/f.txt", limit=1)
        assert content == "line1\n"
        cmd = fake_tool.calls[0]["command"]
        assert "head -n 1" in cmd

    @pytest.mark.asyncio
    async def test_shell_quoting(self, backend, fake_tool):
        """Paths with spaces must be shell-quoted."""
        fake_tool.add_exec_response(stdout="data")
        await backend.read_file("/workspace/my file.txt")
        cmd = fake_tool.calls[0]["command"]
        # shlex.quote wraps in single quotes
        assert "'/workspace/my file.txt'" in cmd


# ---------------------------------------------------------------------------
# write_file
# ---------------------------------------------------------------------------


class TestWriteFile:
    """write_file translates to mkdir -p + printf."""

    @pytest.mark.asyncio
    async def test_writes_with_printf(self, backend, fake_tool):
        fake_tool.add_exec_response()
        await backend.write_file("/workspace/a/b/out.txt", "hello world")
        call = fake_tool.calls[0]
        cmd = call["command"]
        assert "printf" in cmd
        assert "mkdir -p" in cmd
        assert "/workspace/a/b/out.txt" in cmd

    @pytest.mark.asyncio
    async def test_no_mkdir_for_root_level_file(self, backend, fake_tool):
        """Files without '/' in path skip mkdir -p."""
        fake_tool.add_exec_response()
        await backend.write_file("simple.txt", "content")
        cmd = fake_tool.calls[0]["command"]
        assert "printf" in cmd
        assert "mkdir" not in cmd


# ---------------------------------------------------------------------------
# edit_file
# ---------------------------------------------------------------------------


class TestEditFile:
    """edit_file reads via cat, patches in Python, writes back."""

    @pytest.mark.asyncio
    async def test_read_modify_write(self, backend, fake_tool):
        # Response 1: cat reads existing content
        fake_tool.add_exec_response(stdout="hello world")
        # Response 2: printf writes patched content
        fake_tool.add_exec_response()
        result = await backend.edit_file("/workspace/edit.txt", "hello", "goodbye")
        assert len(fake_tool.calls) == 2
        # First call: cat to read
        assert "cat" in fake_tool.calls[0]["command"]
        # Second call: printf to write
        assert "printf" in fake_tool.calls[1]["command"]
        assert "Edited" in result or "replaced" in result

    @pytest.mark.asyncio
    async def test_string_not_found_raises(self, backend, fake_tool):
        fake_tool.add_exec_response(stdout="hello world")
        with pytest.raises(ValueError, match="not found"):
            await backend.edit_file("/workspace/edit.txt", "nonexistent", "replacement")

    @pytest.mark.asyncio
    async def test_string_not_unique_raises(self, backend, fake_tool):
        fake_tool.add_exec_response(stdout="aaa bbb aaa")
        with pytest.raises(ValueError, match="not unique"):
            await backend.edit_file("/workspace/edit.txt", "aaa", "ccc")


# ---------------------------------------------------------------------------
# file_exists
# ---------------------------------------------------------------------------


class TestFileExists:
    """file_exists translates to test -e, exit code determines result."""

    @pytest.mark.asyncio
    async def test_exists_returns_true(self, backend, fake_tool):
        fake_tool.add_exec_response(exit_code=0)
        result = await backend.file_exists("/workspace/exists.txt")
        assert result is True
        assert "test -e" in fake_tool.calls[0]["command"]

    @pytest.mark.asyncio
    async def test_not_exists_returns_false(self, backend, fake_tool):
        fake_tool.add_exec_response(exit_code=1)
        result = await backend.file_exists("/workspace/nope.txt")
        assert result is False


# ---------------------------------------------------------------------------
# list_dir
# ---------------------------------------------------------------------------


class TestListDir:
    """list_dir translates to ls -1ap and parses output."""

    @pytest.mark.asyncio
    async def test_parses_ls_output(self, backend, fake_tool):
        fake_tool.add_exec_response(stdout="./\n../\nfile.txt\nsubdir/\n")
        entries = await backend.list_dir("/workspace")
        assert isinstance(entries, list)
        assert all(isinstance(e, EnvFileEntry) for e in entries)
        names = {e.name for e in entries}
        assert "file.txt" in names
        assert "subdir" in names
        # . and .. should be filtered out
        assert "." not in names
        assert ".." not in names

    @pytest.mark.asyncio
    async def test_entry_types(self, backend, fake_tool):
        fake_tool.add_exec_response(stdout="readme.md\nsrc/\n")
        entries = await backend.list_dir("/workspace")
        by_name = {e.name: e for e in entries}
        assert by_name["readme.md"].entry_type == "file"
        assert by_name["src"].entry_type == "dir"

    @pytest.mark.asyncio
    async def test_sends_ls_command(self, backend, fake_tool):
        fake_tool.add_exec_response(stdout="")
        await backend.list_dir("/workspace/subdir")
        cmd = fake_tool.calls[0]["command"]
        assert "ls -1ap" in cmd
        assert "/workspace/subdir" in cmd


# ---------------------------------------------------------------------------
# grep
# ---------------------------------------------------------------------------


class TestGrep:
    """grep translates to grep -rn."""

    @pytest.mark.asyncio
    async def test_finds_matches(self, backend, fake_tool):
        fake_tool.add_exec_response(stdout="/workspace/f.py:1:needle\n")
        result = await backend.grep("needle", path="/workspace")
        assert "needle" in result
        cmd = fake_tool.calls[0]["command"]
        assert "grep" in cmd
        assert "-rn" in cmd

    @pytest.mark.asyncio
    async def test_no_match_returns_message(self, backend, fake_tool):
        fake_tool.add_exec_response(stdout="", exit_code=1)
        result = await backend.grep("nonexistent", path="/workspace")
        assert "No matches" in result

    @pytest.mark.asyncio
    async def test_glob_filter(self, backend, fake_tool):
        fake_tool.add_exec_response(stdout="match\n")
        await backend.grep("pattern", path="/workspace", glob_filter="*.py")
        cmd = fake_tool.calls[0]["command"]
        assert "--include" in cmd
        assert "*.py" in cmd


# ---------------------------------------------------------------------------
# glob_files
# ---------------------------------------------------------------------------


class TestGlobFiles:
    """glob_files translates to find -name."""

    @pytest.mark.asyncio
    async def test_parses_find_output(self, backend, fake_tool):
        fake_tool.add_exec_response(stdout="/workspace/a.py\n/workspace/sub/b.py\n")
        matches = await backend.glob_files("*.py", path="/workspace")
        assert "/workspace/a.py" in matches
        assert "/workspace/sub/b.py" in matches

    @pytest.mark.asyncio
    async def test_strips_recursive_prefix(self, backend, fake_tool):
        """Patterns like **/*.py should strip **/ for find -name."""
        fake_tool.add_exec_response(stdout="")
        await backend.glob_files("**/*.py", path="/workspace")
        cmd = fake_tool.calls[0]["command"]
        assert "find" in cmd
        assert "-name" in cmd
        # The **/ prefix should be stripped since find is already recursive
        assert "**/" not in cmd

    @pytest.mark.asyncio
    async def test_empty_output_returns_empty_list(self, backend, fake_tool):
        fake_tool.add_exec_response(stdout="")
        matches = await backend.glob_files("*.nonexistent", path="/workspace")
        assert matches == []


# ---------------------------------------------------------------------------
# cleanup
# ---------------------------------------------------------------------------


class TestCleanup:
    """cleanup calls containers destroy."""

    @pytest.mark.asyncio
    async def test_calls_destroy(self, backend, fake_tool):
        await backend.cleanup()
        assert len(fake_tool.calls) == 1
        call = fake_tool.calls[0]
        assert call["operation"] == "destroy"
        assert call["container"] == "test-container-123"


# ---------------------------------------------------------------------------
# info
# ---------------------------------------------------------------------------


class TestInfo:
    """info returns dict with container_id."""

    def test_contains_container_id(self, backend):
        info = backend.info()
        assert isinstance(info, dict)
        assert info["container_id"] == "test-container-123"

    def test_contains_env_type(self, backend):
        info = backend.info()
        assert info.get("env_type") == "docker" or backend.env_type == "docker"


# ---------------------------------------------------------------------------
# Metadata methods (NLSpec)
# ---------------------------------------------------------------------------


class TestMetadata:
    """Metadata methods: working_directory, platform, os_version."""

    def test_working_directory_returns_default(self, backend):
        assert backend.working_directory() == "/workspace"

    def test_working_directory_returns_custom(self, fake_tool):
        b = DockerBackend(
            containers_invoke=fake_tool.invoke,
            container_id="c1",
            working_dir="/app",
        )
        assert b.working_directory() == "/app"

    def test_platform_returns_linux(self, backend):
        assert backend.platform() == "linux"

    def test_os_version_returns_string(self, backend):
        result = backend.os_version()
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# exec_command — timing & env_vars (NLSpec)
# ---------------------------------------------------------------------------


class TestExecTiming:
    """exec_command returns timed_out and duration_ms fields."""

    @pytest.mark.asyncio
    async def test_exec_has_duration_ms(self, backend, fake_tool):
        fake_tool.add_exec_response(stdout="ok")
        result = await backend.exec_command("echo ok")
        assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_exec_has_timed_out_false(self, backend, fake_tool):
        fake_tool.add_exec_response(stdout="ok")
        result = await backend.exec_command("echo ok")
        assert result.timed_out is False


class TestExecEnvVars:
    """exec_command with env_vars prepends export statements."""

    @pytest.mark.asyncio
    async def test_exec_with_env_vars(self, backend, fake_tool):
        fake_tool.add_exec_response(stdout="val")
        await backend.exec_command(
            "echo $MY_VAR", env_vars={"MY_VAR": "hello", "OTHER": "world"}
        )
        cmd = fake_tool.calls[0]["command"]
        assert "export MY_VAR=" in cmd
        assert "export OTHER=" in cmd
        assert "echo $MY_VAR" in cmd
        # Exports should come before the actual command
        export_pos = cmd.index("export")
        echo_pos = cmd.index("echo")
        assert export_pos < echo_pos

    @pytest.mark.asyncio
    async def test_exec_without_env_vars_unchanged(self, backend, fake_tool):
        fake_tool.add_exec_response(stdout="ok")
        await backend.exec_command("echo ok")
        cmd = fake_tool.calls[0]["command"]
        assert cmd == "echo ok"

    @pytest.mark.asyncio
    async def test_exec_env_vars_values_are_quoted(self, backend, fake_tool):
        fake_tool.add_exec_response(stdout="ok")
        await backend.exec_command("echo test", env_vars={"KEY": "value with spaces"})
        cmd = fake_tool.calls[0]["command"]
        # shlex.quote wraps in single quotes
        assert "'value with spaces'" in cmd


# ---------------------------------------------------------------------------
# list_dir — depth (NLSpec)
# ---------------------------------------------------------------------------


class TestListDirDepth:
    """list_dir with depth parameter."""

    @pytest.mark.asyncio
    async def test_list_dir_depth_1_uses_ls(self, backend, fake_tool):
        """Default depth=1 still uses ls -1ap (existing behavior)."""
        fake_tool.add_exec_response(stdout="file.txt\nsubdir/\n")
        await backend.list_dir("/workspace")
        cmd = fake_tool.calls[0]["command"]
        assert "ls -1ap" in cmd

    @pytest.mark.asyncio
    async def test_list_dir_depth_2_uses_find(self, backend, fake_tool):
        """depth > 1 uses find -maxdepth."""
        fake_tool.add_exec_response(
            stdout="/workspace/file.txt\n/workspace/sub\n/workspace/sub/inner.py\n"
        )
        await backend.list_dir("/workspace", depth=2)
        cmd = fake_tool.calls[0]["command"]
        assert "find" in cmd
        assert "-maxdepth 2" in cmd
        assert "-mindepth 1" in cmd

    @pytest.mark.asyncio
    async def test_list_dir_depth_2_parses_find_output(self, backend, fake_tool):
        """find output is parsed into EnvFileEntry list."""
        fake_tool.add_exec_response(stdout="/workspace/file.txt\n/workspace/sub\n")
        # We also need a response for the file-type detection command
        fake_tool.add_exec_response(stdout="/workspace/sub\n")
        entries = await backend.list_dir("/workspace", depth=2)
        assert isinstance(entries, list)
        assert all(isinstance(e, EnvFileEntry) for e in entries)


# ---------------------------------------------------------------------------
# grep — case_insensitive & max_results (NLSpec)
# ---------------------------------------------------------------------------


class TestGrepParams:
    """grep with case_insensitive and max_results parameters."""

    @pytest.mark.asyncio
    async def test_grep_case_insensitive(self, backend, fake_tool):
        fake_tool.add_exec_response(stdout="/workspace/f.py:1:Match\n")
        await backend.grep("pattern", path="/workspace", case_insensitive=True)
        cmd = fake_tool.calls[0]["command"]
        assert "-i" in cmd

    @pytest.mark.asyncio
    async def test_grep_case_sensitive_by_default(self, backend, fake_tool):
        fake_tool.add_exec_response(stdout="/workspace/f.py:1:match\n")
        await backend.grep("pattern", path="/workspace")
        cmd = fake_tool.calls[0]["command"]
        # -i should NOT be present when case_insensitive is not set
        parts = cmd.split()
        assert "-i" not in parts

    @pytest.mark.asyncio
    async def test_grep_max_results(self, backend, fake_tool):
        fake_tool.add_exec_response(stdout="/workspace/f.py:1:match\n")
        await backend.grep("pattern", path="/workspace", max_results=5)
        cmd = fake_tool.calls[0]["command"]
        assert "-m" in cmd
        assert "5" in cmd

    @pytest.mark.asyncio
    async def test_grep_no_max_results_by_default(self, backend, fake_tool):
        fake_tool.add_exec_response(stdout="/workspace/f.py:1:match\n")
        await backend.grep("pattern", path="/workspace")
        cmd = fake_tool.calls[0]["command"]
        parts = cmd.split()
        assert "-m" not in parts


# ---------------------------------------------------------------------------
# compose_project support
# ---------------------------------------------------------------------------


class TestDockerComposeCleanup:
    """Verify compose-aware cleanup in DockerBackend."""

    @pytest.mark.asyncio
    async def test_cleanup_with_compose_project_passes_project(self):
        """When compose_project is set, cleanup passes it to the destroy call."""
        fake = FakeContainersTool()
        backend = DockerBackend(
            containers_invoke=fake.invoke,
            container_id="myproj-web-1",
            compose_project="myproj",
        )
        await backend.cleanup()
        destroy_call = [c for c in fake.calls if c.get("operation") == "destroy"]
        assert len(destroy_call) == 1
        assert destroy_call[0].get("compose_project") == "myproj"

    @pytest.mark.asyncio
    async def test_cleanup_without_compose_project_destroys_container(self):
        """When no compose_project, cleanup destroys the single container (existing behavior)."""
        fake = FakeContainersTool()
        backend = DockerBackend(
            containers_invoke=fake.invoke,
            container_id="ctr-123",
        )
        await backend.cleanup()
        destroy_call = [c for c in fake.calls if c.get("operation") == "destroy"]
        assert len(destroy_call) == 1
        assert destroy_call[0].get("container") == "ctr-123"
        assert (
            "compose_project" not in destroy_call[0]
            or destroy_call[0].get("compose_project") is None
        )

    def test_compose_project_stored(self):
        """Verify compose_project is accessible."""
        fake = FakeContainersTool()
        backend = DockerBackend(
            containers_invoke=fake.invoke,
            container_id="ctr-123",
            compose_project="myproj",
        )
        assert backend._compose_project == "myproj"

    def test_compose_project_defaults_to_none(self):
        """Verify compose_project defaults to None when not provided."""
        fake = FakeContainersTool()
        backend = DockerBackend(
            containers_invoke=fake.invoke,
            container_id="ctr-123",
        )
        assert backend._compose_project is None

    def test_info_includes_compose_project_when_set(self):
        """info() should include compose_project when it's set."""
        fake = FakeContainersTool()
        backend = DockerBackend(
            containers_invoke=fake.invoke,
            container_id="ctr-123",
            compose_project="myproj",
        )
        info = backend.info()
        assert info.get("compose_project") == "myproj"

    def test_info_excludes_compose_project_when_not_set(self):
        """info() should not include compose_project when it's None."""
        fake = FakeContainersTool()
        backend = DockerBackend(
            containers_invoke=fake.invoke,
            container_id="ctr-123",
        )
        info = backend.info()
        assert "compose_project" not in info
