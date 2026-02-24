"""DockerBackend — executes operations inside a Docker container via the containers tool.

Implements EnvironmentBackend by translating each operation into shell commands
sent through a containers_invoke callable (the containers tool's exec operation).

Translation map:
- exec_command: direct passthrough
- read_file: cat <path> (+ tail/head for offset/limit)
- write_file: mkdir -p <parent> && printf '%s' <content> > <path>
- edit_file: cat to read, patch in Python, printf to write back
- file_exists: test -e <path>
- list_dir: ls -1ap <path>
- grep: grep -rn <pattern> <path>
- glob_files: find <path> -name '<pattern>'
- cleanup: containers(operation="destroy")
"""

from __future__ import annotations

import shlex
import time
from typing import Any, Callable

from ..models import EnvExecResult, EnvFileEntry


class DockerBackend:
    """Execution environment backend for Docker containers.

    Talks to a running container through the containers tool's exec operation.

    Args:
        containers_invoke: Async callable that invokes the containers tool.
            Signature: async (input: dict) -> ToolResult-like object with
            .success, .output (dict with stdout/stderr/exit_code), .error.
        container_id: The target container identifier.
        working_dir: Default working directory inside the container.
    """

    def __init__(
        self,
        containers_invoke: Callable[..., Any],
        container_id: str,
        working_dir: str = "/workspace",
        compose_project: str | None = None,
    ) -> None:
        self._invoke = containers_invoke
        self._container_id = container_id
        self._working_dir = working_dir
        self._compose_project = compose_project

    @property
    def env_type(self) -> str:
        return "docker"

    def working_directory(self) -> str:
        return self._working_dir

    def platform(self) -> str:
        # Docker containers are almost always Linux; detecting the actual
        # platform would require an async exec which can't run in a sync
        # method, so we use a sensible default.
        return "linux"

    def os_version(self) -> str:
        return "Docker container"

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _exec(
        self,
        command: str,
        timeout: float | None = None,
        workdir: str | None = None,
    ) -> dict:
        """Execute a command in the container and return the output dict."""
        input_dict: dict[str, Any] = {
            "operation": "exec",
            "container": self._container_id,
            "command": command,
        }
        if timeout is not None:
            input_dict["timeout"] = timeout
        if workdir is not None:
            input_dict["workdir"] = workdir
        result = await self._invoke(input_dict)
        output = result.output
        if isinstance(output, dict):
            return output
        return {"stdout": "", "stderr": "", "exit_code": 0}

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
        start = time.monotonic()
        output = await self._exec(full_cmd, timeout=timeout, workdir=workdir)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return EnvExecResult(
            stdout=output.get("stdout", ""),
            stderr=output.get("stderr", ""),
            exit_code=output.get("exit_code", 0),
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

        output = await self._exec(cmd)
        return output.get("stdout", "")

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
        read_output = await self._exec(f"cat {quoted}")
        content = read_output.get("stdout", "")

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
        output = await self._exec(f"test -e {quoted}")
        return output.get("exit_code", 1) == 0

    async def list_dir(self, path: str, depth: int = 1) -> list[EnvFileEntry]:
        quoted = shlex.quote(path)

        if depth == 1:
            # Keep existing ls -1ap logic for depth=1 (more reliable)
            output = await self._exec(f"ls -1ap {quoted}")
            stdout = output.get("stdout", "")

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
        output = await self._exec(find_cmd)
        stdout = output.get("stdout", "")

        # Detect directories with a second command
        dir_cmd = f"find {quoted} -maxdepth {depth} -mindepth 1 -type d"
        dir_output = await self._exec(dir_cmd)
        dir_lines = set(dir_output.get("stdout", "").splitlines())

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
        search_path = shlex.quote(path) if path else shlex.quote(self._working_dir)
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
        output = await self._exec(cmd)

        # grep exit code 1 = no matches
        if output.get("exit_code", 0) == 1:
            return "No matches found."
        return output.get("stdout", "")

    async def glob_files(self, pattern: str, path: str | None = None) -> list[str]:
        search_path = shlex.quote(path) if path else shlex.quote(self._working_dir)

        # Strip leading **/ — find -name is already recursive
        clean_pattern = pattern
        while clean_pattern.startswith("**/"):
            clean_pattern = clean_pattern[3:]
        quoted_pattern = shlex.quote(clean_pattern)

        cmd = f"find {search_path} -name {quoted_pattern}"
        output = await self._exec(cmd)
        stdout = output.get("stdout", "")

        if not stdout.strip():
            return []
        return [line for line in stdout.splitlines() if line.strip()]

    async def cleanup(self) -> None:
        """Destroy the container or compose stack."""
        if self._compose_project:
            await self._invoke(
                {
                    "operation": "destroy",
                    "container": self._container_id,
                    "compose_project": self._compose_project,
                }
            )
        else:
            await self._invoke(
                {
                    "operation": "destroy",
                    "container": self._container_id,
                }
            )

    def info(self) -> dict[str, Any]:
        result = {
            "container_id": self._container_id,
            "env_type": self.env_type,
            "working_dir": self._working_dir,
        }
        if self._compose_project:
            result["compose_project"] = self._compose_project
        return result
