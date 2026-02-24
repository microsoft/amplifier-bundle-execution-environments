"""ReadOnlyWrapper — rejects write operations on execution environments.

Wraps any EnvironmentBackend, blocking write_file and edit_file while
allowing all read and exec operations to pass through.
NLSpec Section 4.4: ReadOnlyExecutionEnvironment pattern.
"""

from __future__ import annotations

from typing import Any

from ..models import EnvExecResult, EnvFileEntry
from ..protocol import EnvironmentBackend


class ReadOnlyWrapper:
    """Rejects all write operations. Read and exec pass through."""

    def __init__(self, inner: EnvironmentBackend) -> None:
        self._inner = inner

    # -- Metadata passthrough --------------------------------------------------

    @property
    def env_type(self) -> str:
        return self._inner.env_type

    def working_directory(self) -> str:
        return self._inner.working_directory()

    def platform(self) -> str:
        return self._inner.platform()

    def os_version(self) -> str:
        return self._inner.os_version()

    def info(self) -> dict[str, Any]:
        return self._inner.info()

    # -- Blocked operations (write) --------------------------------------------

    async def write_file(self, path: str, content: str) -> None:
        raise PermissionError("Write operations disabled in read-only mode")

    async def edit_file(self, path: str, old_string: str, new_string: str) -> str:
        raise PermissionError("Write operations disabled in read-only mode")

    # -- Passthrough operations (read + exec) ----------------------------------

    async def exec_command(
        self,
        cmd: str,
        timeout: float | None = None,
        workdir: str | None = None,
        env_vars: dict[str, str] | None = None,
    ) -> EnvExecResult:
        return await self._inner.exec_command(
            cmd, timeout=timeout, workdir=workdir, env_vars=env_vars
        )

    async def read_file(
        self, path: str, offset: int | None = None, limit: int | None = None
    ) -> str:
        return await self._inner.read_file(path, offset=offset, limit=limit)

    async def file_exists(self, path: str) -> bool:
        return await self._inner.file_exists(path)

    async def list_dir(self, path: str, depth: int = 1) -> list[EnvFileEntry]:
        return await self._inner.list_dir(path, depth=depth)

    async def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob_filter: str | None = None,
        case_insensitive: bool = False,
        max_results: int | None = None,
    ) -> str:
        return await self._inner.grep(
            pattern,
            path=path,
            glob_filter=glob_filter,
            case_insensitive=case_insensitive,
            max_results=max_results,
        )

    async def glob_files(self, pattern: str, path: str | None = None) -> list[str]:
        return await self._inner.glob_files(pattern, path=path)

    async def cleanup(self) -> None:
        await self._inner.cleanup()
