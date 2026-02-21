# Multi-Environment Guide

You have access to **three execution environments** and **composable decorators**. All environments share the same 8-tool interface — learn once, use everywhere.

## Available Environments

| Environment | Tool Prefix | Backend | Best For |
|-------------|------------|---------|----------|
| **Local** | `env_local_*` | Host filesystem + shell | Simple tasks, file editing, scripting |
| **Docker** | `env_docker_*` | Container via `containers` bundle | Isolated builds, untrusted code, reproducible envs |
| **SSH** | `env_ssh_*` | Remote host via asyncssh/SFTP | Remote servers, GPU hardware, production ops |

## Choosing an Environment

- **Default to local** for file reads, edits, and simple commands.
- **Use Docker** when you need isolation (untrusted code, dependency conflicts, clean builds).
- **Use SSH** when the work must happen on a specific remote machine (GPU server, staging host).
- **Combine them** for cross-environment workflows (read locally, build in Docker, deploy via SSH).

## Common Shape (8 Tools)

Every environment provides these tools with identical schemas:

| Tool | Purpose |
|------|---------|
| `env_{env}_read_file` | Read file content (supports offset/limit) |
| `env_{env}_write_file` | Write file content (creates parent dirs) |
| `env_{env}_edit_file` | Replace exact string in file |
| `env_{env}_exec` | Execute shell command |
| `env_{env}_grep` | Search file contents with regex |
| `env_{env}_glob` | Find files by glob pattern |
| `env_{env}_list_dir` | List directory entries |
| `env_{env}_file_exists` | Check if path exists |

When only one environment is loaded, tools use the `env_*` prefix (no qualifier).
When multiple environments are loaded, each uses its qualified prefix: `env_local_*`, `env_docker_*`, `env_ssh_*`.

## Environment-Specific Extensions

Beyond the common 8 tools, each environment offers unique capabilities:

- **Docker**: `docker.copy_in`, `docker.copy_out`, `docker.container_id`
- **SSH**: `ssh.reconnect`, `ssh.upload`, `ssh.download`, `ssh.tunnel`

## Decorators

Decorators wrap any environment's tools via hook-based interception:

| Decorator | Effect |
|-----------|--------|
| **Logging** | Logs all env.* calls with timing — purely observational |
| **ReadOnly** | Blocks write_file, edit_file, exec — allows reads only |
| **AuditTrail** | Records all operations to a JSONL audit log |

Decorators apply automatically to all loaded environments. They compose:
Logging + ReadOnly means writes are blocked AND the block is logged.

## Error Model

All environments return structured errors with two categories:

- **Transport errors** (`retriable: true`): Environment itself is broken — connection lost, daemon down, container stopped. Retry may help.
- **Operation errors** (`retriable: false`): Work failed within a working environment — file not found, permission denied, command failed. Fix the input.

Every error includes `environment` ("local", "docker", "ssh") so you know which backend failed.
