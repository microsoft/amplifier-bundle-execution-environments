"""LocalBackend — executes operations on the host filesystem.

Implements EnvironmentBackend using Python stdlib:
- exec_command: asyncio.create_subprocess_shell
- read_file/write_file/edit_file: pathlib
- file_exists/list_dir: os/pathlib
- grep: asyncio.create_subprocess_shell running grep
- glob_files: pathlib.glob
"""

from __future__ import annotations

import asyncio
import os
import platform as platform_mod
import signal
import sys
import time
from pathlib import Path
from typing import Any

from ..env_filter import EnvVarPolicy, filter_env_vars
from ..models import EnvExecResult, EnvFileEntry


class LocalBackend:
    """Execution environment backend for the local host filesystem."""

    def __init__(self, working_dir: str = ".", env_policy: str = "core_only") -> None:
        self._working_dir = os.path.abspath(working_dir)
        self._env_policy = env_policy

    @property
    def env_type(self) -> str:
        return "local"

    def working_directory(self) -> str:
        return self._working_dir

    def platform(self) -> str:
        p = sys.platform
        if p.startswith("linux"):
            return "linux"
        if p == "darwin":
            return "darwin"
        if p.startswith("win"):
            return "windows"
        return p

    def os_version(self) -> str:
        return platform_mod.platform()

    def _resolve(self, path: str) -> Path:
        """Resolve a path relative to working_dir. Validates it stays inside."""
        p = Path(path)
        if p.is_absolute():
            resolved = p.resolve()
        else:
            resolved = (Path(self._working_dir) / p).resolve()
        working = Path(self._working_dir).resolve()
        if not resolved.is_relative_to(working):
            raise ValueError(f"Path escapes working directory: {path}")
        return resolved

    async def exec_command(
        self,
        cmd: str,
        timeout: float | None = None,
        workdir: str | None = None,
        env_vars: dict[str, str] | None = None,
    ) -> EnvExecResult:
        cwd = workdir or self._working_dir
        policy = EnvVarPolicy(self._env_policy)
        env = filter_env_vars(policy, dict(os.environ), env_vars)
        start = time.monotonic()
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
            start_new_session=True,  # NLSpec 4.2: own process group
        )
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            # NLSpec 4.2 graceful shutdown: SIGTERM → 2s grace → SIGKILL
            try:
                pgid = os.getpgid(proc.pid)
                os.killpg(pgid, signal.SIGTERM)
            except (ProcessLookupError, OSError):
                pass
            try:
                await asyncio.wait_for(proc.communicate(), timeout=2.0)
            except asyncio.TimeoutError:
                try:
                    pgid = os.getpgid(proc.pid)
                    os.killpg(pgid, signal.SIGKILL)
                except (ProcessLookupError, OSError):
                    pass
                try:
                    await proc.communicate()
                except Exception:
                    pass
            return EnvExecResult(
                stdout="",
                stderr=f"Command timed out after {timeout}s: {cmd}",
                exit_code=-1,
                timed_out=True,
                duration_ms=elapsed_ms,
            )
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return EnvExecResult(
            stdout=stdout.decode("utf-8", errors="replace") if stdout else "",
            stderr=stderr.decode("utf-8", errors="replace") if stderr else "",
            exit_code=proc.returncode or 0,
            timed_out=False,
            duration_ms=elapsed_ms,
        )

    async def read_file(
        self, path: str, offset: int | None = None, limit: int | None = None
    ) -> str:
        full_path = self._resolve(path)
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        content = full_path.read_text(encoding="utf-8", errors="replace")
        if offset is not None or limit is not None:
            lines = content.splitlines(keepends=True)
            start = (offset - 1) if offset else 0  # 1-indexed
            end = (start + limit) if limit else len(lines)
            content = "".join(lines[start:end])
        return content

    async def write_file(self, path: str, content: str) -> None:
        full_path = self._resolve(path)
        full_path.parent.mkdir(parents=True, exist_ok=True)
        full_path.write_text(content, encoding="utf-8")

    async def edit_file(self, path: str, old_string: str, new_string: str) -> str:
        full_path = self._resolve(path)
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        content = full_path.read_text(encoding="utf-8")
        count = content.count(old_string)
        if count == 0:
            raise ValueError(f"String not found in {path}")
        if count > 1:
            raise ValueError(f"String not unique in {path} (found {count} times)")
        new_content = content.replace(old_string, new_string, 1)
        full_path.write_text(new_content, encoding="utf-8")
        return f"Edited {path}: replaced 1 occurrence"

    async def file_exists(self, path: str) -> bool:
        return self._resolve(path).exists()

    async def list_dir(self, path: str, depth: int = 1) -> list[EnvFileEntry]:
        resolved = self._resolve(path)
        if not resolved.is_dir():
            raise FileNotFoundError(f"Directory not found: {path}")
        entries: list[EnvFileEntry] = []

        def _walk(dir_path: Path, current_depth: int) -> None:
            for item in sorted(dir_path.iterdir(), key=lambda p: p.name):
                rel_name = str(item.relative_to(resolved))
                entries.append(
                    EnvFileEntry(
                        name=rel_name if current_depth > 1 else item.name,
                        entry_type="dir" if item.is_dir() else "file",
                        size=item.stat().st_size if item.is_file() else None,
                    )
                )
                if item.is_dir() and current_depth < depth:
                    _walk(item, current_depth + 1)

        _walk(resolved, 1)
        return entries

    async def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob_filter: str | None = None,
        case_insensitive: bool = False,
        max_results: int | None = None,
    ) -> str:
        search_path = str(self._resolve(path or "."))
        cmd_parts = ["grep", "-rn"]
        if case_insensitive:
            cmd_parts.append("-i")
        if max_results is not None:
            cmd_parts.extend(["-m", str(max_results)])
        cmd_parts.extend([pattern, search_path])
        if glob_filter:
            cmd_parts.extend(["--include", glob_filter])
        proc = await asyncio.create_subprocess_exec(
            *cmd_parts,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 1:  # grep returns 1 for no matches
            return "No matches found."
        if proc.returncode and proc.returncode > 1:
            raise RuntimeError(
                f"grep failed (exit {proc.returncode}): {stderr.decode()}"
            )
        return stdout.decode("utf-8", errors="replace")

    async def glob_files(self, pattern: str, path: str | None = None) -> list[str]:
        base = self._resolve(path or ".")
        matches = sorted(str(p.relative_to(base)) for p in base.glob(pattern))
        return matches

    async def cleanup(self) -> None:
        """Local backend has no resources to clean up."""

    def info(self) -> dict[str, Any]:
        return {"working_dir": self._working_dir}
