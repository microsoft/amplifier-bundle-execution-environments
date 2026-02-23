# Amplifier Bundle: env-all

Instance-based execution environment toolkit for [Amplifier](https://github.com/microsoft/amplifier).

Provides 11 tools for creating and managing named environment instances on demand. The agent creates Docker containers, SSH connections, or local directories, targets specific instances by name, and destroys them when done.

## Installation

```bash
amplifier bundle add "git+https://github.com/microsoft/amplifier-bundle-env-all@main#subdirectory=behaviors/env-all.yaml" --app
```

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

## Quick Start

```python
# No setup needed — local instance is always available
env_exec(command="ls src/")
env_read_file(path="src/main.py")

# Create an isolated Docker environment
env_create(type="docker", name="build", purpose="python")
env_exec(instance="build", command="pip install -r requirements.txt")
env_exec(instance="build", command="pytest tests/")
env_destroy(instance="build")

# Connect to a remote host
env_create(type="ssh", name="pi", host="192.168.1.100", username="pi")
env_exec(instance="pi", command="uname -a")
env_destroy(instance="pi")
```

## Architecture

This bundle follows the [thin bundle pattern](https://github.com/microsoft/amplifier):

- **`bundle.md`** — Root manifest (includes the behavior)
- **`behaviors/env-all.yaml`** — Behavior bundle (declares tools, hooks, context)
- **`modules/tools-env-all/`** — Tool module (11 tools, dispatches to backends)
- **`modules/hooks-env-all/`** — Hook module (session cleanup)
- **`context/env-all-guide.md`** — Agent context guide
- **[`amplifier-env-common`](https://github.com/microsoft/amplifier-env-common)** — Shared library (protocol, models, backends)

## Testing

```bash
# Unit tests
cd modules/tools-env-all && uv run pytest
cd modules/hooks-env-all && uv run pytest

# Integration tests (require Docker)
uv run pytest tests/integration/
```

## Contributing

> [!NOTE]
> This project is not currently accepting external contributions, but we're actively working toward opening this up. We value community input and look forward to collaborating in the future. For now, feel free to fork and experiment!

Most contributions require you to agree to a
Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us
the rights to use your contribution. For details, visit [Contributor License Agreements](https://cla.opensource.microsoft.com).

When you submit a pull request, a CLA bot will automatically determine whether you need to provide
a CLA and decorate the PR appropriately (e.g., status check, comment). Simply follow the instructions
provided by the bot. You will only need to do this once across all repos using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or
contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft
trademarks or logos is subject to and must follow
[Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/legal/intellectualproperty/trademarks/usage/general).
Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship.
Any use of third-party trademarks or logos are subject to those third-party's policies.
