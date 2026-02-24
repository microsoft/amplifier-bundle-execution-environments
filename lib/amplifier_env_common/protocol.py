"""EnvironmentBackend protocol — the uniform interface for all execution environments.

Every backend (local, docker, ssh) implements this protocol. The dispatch tools
route calls to the correct backend based on the instance name in the registry.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .models import EnvExecResult, EnvFileEntry


@runtime_checkable
class EnvironmentBackend(Protocol):
    """Uniform interface for all execution environments."""

    @property
    def env_type(self) -> str:
        """Backend type identifier: 'local', 'docker', or 'ssh'."""
        ...

    def working_directory(self) -> str:
        """Return the working directory where operations execute."""
        ...

    def platform(self) -> str:
        """Return the platform: 'linux', 'darwin', 'windows', or 'wasm'."""
        ...

    def os_version(self) -> str:
        """Return the OS version string."""
        ...

    async def exec_command(
        self,
        cmd: str,
        timeout: float | None = None,
        workdir: str | None = None,
        env_vars: dict[str, str] | None = None,
    ) -> EnvExecResult:
        """Execute a shell command and return structured result."""
        ...

    async def read_file(
        self, path: str, offset: int | None = None, limit: int | None = None
    ) -> str:
        """Read file content, optionally with offset and line limit."""
        ...

    async def write_file(self, path: str, content: str) -> None:
        """Write content to a file, creating intermediate directories."""
        ...

    async def edit_file(self, path: str, old_string: str, new_string: str) -> str:
        """Replace exact string in file. Returns confirmation message."""
        ...

    async def file_exists(self, path: str) -> bool:
        """Check if a file or directory exists."""
        ...

    async def list_dir(self, path: str, depth: int = 1) -> list[EnvFileEntry]:
        """List directory contents as structured entries."""
        ...

    async def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob_filter: str | None = None,
        case_insensitive: bool = False,
        max_results: int | None = None,
    ) -> str:
        """Search file contents with regex. Returns formatted matches."""
        ...

    async def glob_files(self, pattern: str, path: str | None = None) -> list[str]:
        """Find files matching a glob pattern."""
        ...

    async def cleanup(self) -> None:
        """Tear down the environment (close connections, destroy containers, etc.)."""
        ...

    def info(self) -> dict[str, Any]:
        """Return metadata about this instance for env_list display."""
        ...
