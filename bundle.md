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
  - bundle: env-all:behaviors/env-all     # Everything (default)
  # Individual behaviors (for selective inclusion):
  #   - bundle: env-all:behaviors/env-core      # Local only — no Docker/SSH deps
  #   - bundle: env-all:behaviors/env-docker    # Local + Docker (with compose)
  #   - bundle: env-all:behaviors/env-ssh       # Local + SSH (with auto-discovery)
  #   - bundle: env-all:behaviors/env-security  # Add-on: env var filtering + wrappers
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

## Selective Installation

The default `env-all` behavior includes everything. For lighter configurations,
include individual behaviors instead:

| Behavior | What it includes |
|----------|-----------------|
| `env-core` | Local execution only — no Docker or SSH dependencies |
| `env-docker` | Local + Docker containers with compose support |
| `env-ssh` | Local + SSH connections with credential auto-discovery |
| `env-security` | Add-on: environment variable filtering and composable wrappers |

Behaviors are additive — each includes `env-core` plus its own context guide.
The `env-security` behavior is a standalone add-on that enables `env_policy` and `wrappers` parameters.
