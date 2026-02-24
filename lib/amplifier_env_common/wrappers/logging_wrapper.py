"""LoggingWrapper — composable logging for execution environments.

Wraps any EnvironmentBackend, logging operations as they pass through.
NLSpec Section 4.4: LoggingExecutionEnvironment pattern.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from ..models import EnvExecResult, EnvFileEntry
from ..protocol import EnvironmentBackend


class LoggingWrapper:
    """Logs operations passing through an environment backend.

    Wraps any EnvironmentBackend and delegates all calls to the inner backend
    while logging before/after at appropriate levels. Noisy read-only metadata
    operations (file_exists, list_dir, glob_files) are not logged.
    """

    def __init__(self, inner: EnvironmentBackend, logger_name: str = "env") -> None:
        self._inner = inner
        self._logger = logging.getLogger(logger_name)

    # -- Metadata passthrough (no logging) ----------------------------------

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

    # -- Logged operations ---------------------------------------------------

    async def exec_command(
        self,
        cmd: str,
        timeout: float | None = None,
        workdir: str | None = None,
        env_vars: dict[str, str] | None = None,
    ) -> EnvExecResult:
        instance = self.env_type
        self._logger.info("env [%s]: exec %r", instance, cmd)
        t0 = time.monotonic()
        result = await self._inner.exec_command(
            cmd, timeout=timeout, workdir=workdir, env_vars=env_vars
        )
        duration_ms = int((time.monotonic() - t0) * 1000)
        self._logger.info(
            "env [%s]: exec %r → exit %d in %dms",
            instance,
            cmd,
            result.exit_code,
            duration_ms,
        )
        return result

    async def read_file(
        self, path: str, offset: int | None = None, limit: int | None = None
    ) -> str:
        instance = self.env_type
        self._logger.debug("env [%s]: read %s", instance, path)
        return await self._inner.read_file(path, offset=offset, limit=limit)

    async def write_file(self, path: str, content: str) -> None:
        instance = self.env_type
        self._logger.info("env [%s]: write %s (%d chars)", instance, path, len(content))
        await self._inner.write_file(path, content)

    async def edit_file(self, path: str, old_string: str, new_string: str) -> str:
        instance = self.env_type
        self._logger.info("env [%s]: edit %s", instance, path)
        return await self._inner.edit_file(path, old_string, new_string)

    async def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob_filter: str | None = None,
        case_insensitive: bool = False,
        max_results: int | None = None,
    ) -> str:
        instance = self.env_type
        self._logger.debug("env [%s]: grep %r", instance, pattern)
        return await self._inner.grep(
            pattern,
            path=path,
            glob_filter=glob_filter,
            case_insensitive=case_insensitive,
            max_results=max_results,
        )

    async def cleanup(self) -> None:
        instance = self.env_type
        self._logger.info("env [%s]: cleanup", instance)
        await self._inner.cleanup()

    # -- Silent operations (too noisy to log) --------------------------------

    async def file_exists(self, path: str) -> bool:
        return await self._inner.file_exists(path)

    async def list_dir(self, path: str, depth: int = 1) -> list[EnvFileEntry]:
        return await self._inner.list_dir(path, depth=depth)

    async def glob_files(self, pattern: str, path: str | None = None) -> list[str]:
        return await self._inner.glob_files(pattern, path=path)
