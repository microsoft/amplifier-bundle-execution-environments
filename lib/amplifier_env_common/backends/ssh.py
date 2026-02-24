"""SSHBackendWrapper — executes operations on a remote host via an SSH exec function.

Implements EnvironmentBackend by translating each operation into shell commands
sent through an async exec callable (typically wrapping an SSHConnection).

Translation map (same pattern as DockerBackend):
- exec_command: direct passthrough (workdir → cd <dir> && <cmd>)
- read_file: cat <path> (+ tail/head for offset/limit)
- write_file: mkdir -p <parent> && printf '%s' <content> > <path>
- edit_file: cat to read, patch in Python, printf to write back
- file_exists: test -e <path>
- list_dir: ls -1ap <path>
- grep: grep -rn <pattern> <path>
- glob_files: find <path> -name '<pattern>'
- cleanup: calls disconnect_fn if provided

Does NOT import from amplifier_module_tools_env_ssh — takes only a callable
exec function and a host string.  The actual SSHConnection wiring happens
in env_create.
"""

from __future__ import annotations

import dataclasses
import shlex
import time
from typing import Any, Callable

from ..models import EnvExecResult, EnvFileEntry


# ---------------------------------------------------------------------------
# SSH connection classes (depend on asyncssh at runtime, not import time)
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class SSHConnectionConfig:
    """Configuration for an SSH connection."""

    host: str
    port: int = 22
    username: str | None = None
    key_file: str | None = None
    known_hosts: Any = None
    connect_timeout: float = 30


class AsyncSSHBackend:
    """Low-level SSH backend that wraps asyncssh.connect().

    The ``asyncssh`` library is imported lazily inside :meth:`connect` so
    that importing this class does **not** require asyncssh to be installed.
    """

    def __init__(self, config: SSHConnectionConfig) -> None:
        self._config = config

    async def connect(self) -> Any:
        """Open an asyncssh connection using the stored config."""
        import asyncssh  # lazy — ImportError caught by callers

        connect_kwargs: dict[str, Any] = {
            "host": self._config.host,
            "port": self._config.port,
            "known_hosts": self._config.known_hosts,
        }
        if self._config.username:
            connect_kwargs["username"] = self._config.username
        if self._config.key_file:
            connect_kwargs["client_keys"] = [self._config.key_file]
        if self._config.connect_timeout:
            connect_kwargs["login_timeout"] = self._config.connect_timeout

        return await asyncssh.connect(**connect_kwargs)


class SSHConnection:
    """High-level SSH connection that provides exec_command / disconnect.

    Wraps an :class:`AsyncSSHBackend` connection and exposes the interface
    expected by :class:`SSHBackendWrapper` (``exec_fn`` / ``disconnect_fn``).
    """

    def __init__(
        self,
        config: SSHConnectionConfig,
        backend: AsyncSSHBackend,
    ) -> None:
        self._config = config
        self._backend = backend
        self._conn: Any = None

    async def connect(self) -> None:
        """Establish the SSH connection."""
        self._conn = await self._backend.connect()

    async def exec_command(
        self, cmd: str, timeout: float | None = None
    ) -> EnvExecResult:
        """Execute *cmd* on the remote host and return structured output."""
        if self._conn is None:
            raise RuntimeError("SSHConnection is not connected; call connect() first")
        result = await self._conn.run(cmd, timeout=timeout)
        return EnvExecResult(
            stdout=str(result.stdout) if result.stdout else "",
            stderr=str(result.stderr) if result.stderr else "",
            exit_code=result.exit_status if result.exit_status is not None else 0,
        )

    async def disconnect(self) -> None:
        """Close the SSH connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None


# ---------------------------------------------------------------------------
# SSHBackendWrapper — exec-function based backend (no asyncssh dependency)
# ---------------------------------------------------------------------------


class SSHBackendWrapper:
    """Execution environment backend for remote hosts via SSH.

    Talks to a remote host through an async exec callable that runs
    shell commands over SSH.

    Args:
        exec_fn: Async callable that executes a command on the remote host.
            Signature: async (cmd: str, timeout: float | None = None)
            -> object with .stdout, .stderr, .exit_code attributes.
        host: Remote host identifier (for display / info).
        disconnect_fn: Optional async callable to close the SSH connection.
    """

    def __init__(
        self,
        exec_fn: Callable[..., Any],
        host: str,
        disconnect_fn: Callable[..., Any] | None = None,
    ) -> None:
        self._exec = exec_fn
        self._host = host
        self._disconnect = disconnect_fn
        self._cached_platform: str | None = None
        self._cached_os_version: str | None = None

    @property
    def env_type(self) -> str:
        return "ssh"

    def working_directory(self) -> str:
        return "~"

    def platform(self) -> str:
        if self._cached_platform is None:
            self._cached_platform = "linux"
        return self._cached_platform

    def os_version(self) -> str:
        if self._cached_os_version is None:
            self._cached_os_version = "unknown"
        return self._cached_os_version

    # ------------------------------------------------------------------
    # EnvironmentBackend interface
    # ------------------------------------------------------------------

    async def exec_command(
        self,
        cmd: str,
        timeout: float | None = None,
        workdir: str | None = None,
        env_vars: dict[str, str] | None = None,
    ) -> EnvExecResult:
        full_cmd = cmd
        if env_vars:
            exports = " && ".join(
                f"export {k}={shlex.quote(v)}" for k, v in env_vars.items()
            )
            full_cmd = f"{exports} && {cmd}"
        if workdir:
            full_cmd = f"cd {shlex.quote(workdir)} && {full_cmd}"
        start = time.monotonic()
        result = await self._exec(full_cmd, timeout=timeout)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return EnvExecResult(
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
            timed_out=False,
            duration_ms=elapsed_ms,
        )

    async def read_file(
        self, path: str, offset: int | None = None, limit: int | None = None
    ) -> str:
        quoted = shlex.quote(path)

        if offset is not None and limit is not None:
            cmd = f"tail -n +{offset} {quoted} | head -n {limit}"
        elif offset is not None:
            cmd = f"tail -n +{offset} {quoted}"
        elif limit is not None:
            cmd = f"head -n {limit} {quoted}"
        else:
            cmd = f"cat {quoted}"

        result = await self._exec(cmd)
        return result.stdout

    async def write_file(self, path: str, content: str) -> None:
        quoted_path = shlex.quote(path)
        quoted_content = shlex.quote(content)

        if "/" in path:
            parent = shlex.quote(path.rsplit("/", 1)[0])
            cmd = f"mkdir -p {parent} && printf '%s' {quoted_content} > {quoted_path}"
        else:
            cmd = f"printf '%s' {quoted_content} > {quoted_path}"

        await self._exec(cmd)

    async def edit_file(self, path: str, old_string: str, new_string: str) -> str:
        # Step 1: Read current content via cat
        quoted = shlex.quote(path)
        result = await self._exec(f"cat {quoted}")
        content = result.stdout

        # Step 2: Patch in Python
        count = content.count(old_string)
        if count == 0:
            msg = f"String not found in {path}"
            raise ValueError(msg)
        if count > 1:
            msg = f"String not unique in {path} (found {count} times)"
            raise ValueError(msg)
        new_content = content.replace(old_string, new_string, 1)

        # Step 3: Write back via printf
        await self.write_file(path, new_content)
        return f"Edited {path}: replaced 1 occurrence"

    async def file_exists(self, path: str) -> bool:
        quoted = shlex.quote(path)
        result = await self._exec(f"test -e {quoted}")
        return result.exit_code == 0

    async def list_dir(self, path: str, depth: int = 1) -> list[EnvFileEntry]:
        quoted = shlex.quote(path)

        if depth == 1:
            result = await self._exec(f"ls -1ap {quoted}")
            stdout = result.stdout

            entries: list[EnvFileEntry] = []
            for line in stdout.splitlines():
                line = line.strip()
                if not line or line in (".", "..", "./", "../"):
                    continue
                if line.endswith("/"):
                    name = line.rstrip("/")
                    entries.append(EnvFileEntry(name=name, entry_type="dir", size=None))
                else:
                    entries.append(
                        EnvFileEntry(name=line, entry_type="file", size=None)
                    )
            return entries

        # Use find for recursive listing (depth > 1)
        find_cmd = f"find {quoted} -maxdepth {depth} -mindepth 1"
        result = await self._exec(find_cmd)
        stdout = result.stdout

        # Detect directories with a second command
        dir_cmd = f"find {quoted} -maxdepth {depth} -mindepth 1 -type d"
        dir_result = await self._exec(dir_cmd)
        dir_lines = set(dir_result.stdout.splitlines())

        entries = []
        for line in stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            entry_type = "dir" if line in dir_lines else "file"
            # Make path relative to the search root
            name = line.removeprefix(path.rstrip("/") + "/")
            entries.append(EnvFileEntry(name=name, entry_type=entry_type, size=None))
        return entries

    async def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob_filter: str | None = None,
        case_insensitive: bool = False,
        max_results: int | None = None,
    ) -> str:
        search_path = shlex.quote(path) if path else "."
        quoted_pattern = shlex.quote(pattern)

        parts = ["grep", "-rn"]
        if case_insensitive:
            parts.append("-i")
        if max_results is not None:
            parts.extend(["-m", str(max_results)])
        parts.extend([quoted_pattern, search_path])
        if glob_filter:
            parts.extend(["--include", shlex.quote(glob_filter)])

        cmd = " ".join(parts)
        result = await self._exec(cmd)

        # grep exit code 1 = no matches
        if result.exit_code == 1:
            return "No matches found."
        return result.stdout

    async def glob_files(self, pattern: str, path: str | None = None) -> list[str]:
        search_path = shlex.quote(path) if path else "."

        # Strip leading **/ — find -name is already recursive
        clean_pattern = pattern
        while clean_pattern.startswith("**/"):
            clean_pattern = clean_pattern[3:]
        quoted_pattern = shlex.quote(clean_pattern)

        cmd = f"find {search_path} -name {quoted_pattern}"
        result = await self._exec(cmd)
        stdout = result.stdout

        if not stdout.strip():
            return []
        return [line for line in stdout.splitlines() if line.strip()]

    async def cleanup(self) -> None:
        """Disconnect the SSH connection if a disconnect function was provided."""
        if self._disconnect:
            await self._disconnect()

    def info(self) -> dict[str, Any]:
        return {
            "host": self._host,
            "env_type": self.env_type,
        }
