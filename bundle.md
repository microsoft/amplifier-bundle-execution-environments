---
bundle:
  name: env-all
  version: 0.2.0
  description: |
    Instance-based execution environment toolkit.
    
    Provides 11 tools for creating and managing named environment instances on demand.
    The agent creates Docker containers, SSH connections, or local directories,
    targets specific instances by name, and destroys them when done.

includes:
  - bundle: env-all:behaviors/env-all
---

# env-all

Instance-based execution environment toolkit for Amplifier.

## Tools Provided (11)

| Tool | Purpose |
|------|---------|
| `env_create` | Create a new environment instance (local, docker, ssh) |
| `env_destroy` | Tear down an environment instance |
| `env_list` | List all active environment instances |
| `env_exec` | Execute command in a named instance |
| `env_read_file` | Read file from a named instance |
| `env_write_file` | Write file to a named instance |
| `env_edit_file` | Edit file in a named instance |
| `env_grep` | Search files in a named instance |
| `env_glob` | Find files in a named instance |
| `env_list_dir` | List directory in a named instance |
| `env_file_exists` | Check path in a named instance |

## How It Works

1. A "local" instance is auto-created at session start
2. Agent calls `env_create(type="docker", name="build")` to spin up more
3. Agent targets instances: `env_exec(instance="build", command="cargo build")`
4. All instances are destroyed at session end (unless persistent)

See `context/env-all-guide.md` for the full agent guide.
