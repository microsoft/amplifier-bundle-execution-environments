"""Common shape data models for execution environments.

These models define the shared types used across all env-* bundles:
- EnvError: Consistent error structure (transport vs operation)
- EnvExecResult: Structured command execution output
- EnvFileEntry: Directory listing entry

Reference: research/DESIGN-execution-environments.md, Section 8 (Error Model)
"""

from typing import Literal

from pydantic import BaseModel, Field


class EnvError(BaseModel):
    """Consistent error structure for all env.* tool failures.

    Two categories:
    - transport: Environment itself is broken (connection lost, daemon down)
    - operation: Work failed within a working environment (file not found, permission denied)
    """

    error_type: Literal["transport", "operation"] = Field(
        ...,
        description="Error category: 'transport' (env broken) or 'operation' (work failed)",
    )
    error_code: str = Field(
        ...,
        description="Machine-readable error code (e.g., 'file_not_found', 'connection_lost')",
    )
    message: str = Field(..., description="Human-readable error description")
    retriable: bool = Field(
        default=False, description="Whether the operation can be retried"
    )
    environment: str = Field(
        ...,
        description="Environment that produced the error (e.g., 'local', 'docker', 'ssh')",
    )

    def to_tool_error(self) -> dict:
        """Convert to the dict format expected by ToolResult.error."""
        return {
            "error_type": self.error_type,
            "error_code": self.error_code,
            "message": self.message,
            "retriable": self.retriable,
            "environment": self.environment,
        }


class EnvExecResult(BaseModel):
    """Structured result from env.exec command execution."""

    stdout: str = Field(default="", description="Standard output")
    stderr: str = Field(default="", description="Standard error")
    exit_code: int = Field(..., description="Process exit code")
    timed_out: bool = Field(default=False, description="Whether the command timed out")
    duration_ms: int = Field(
        default=0, description="Wall-clock duration in milliseconds"
    )


class EnvFileEntry(BaseModel):
    """A single entry in a directory listing from env.list_dir."""

    name: str = Field(..., description="File or directory name")
    entry_type: Literal["file", "dir"] = Field(..., description="Entry type")
    size: int | None = Field(
        default=None, description="File size in bytes (None for directories)"
    )
