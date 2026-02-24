# Environment Toolkit — Security

Environment variable filtering and composable wrappers protect against secret leakage.

## Environment Variable Policies

Control which host env vars are visible via `env_policy`:
```
env_create(type="local", name="safe", env_policy="core_only")  # default
```
Policies:
- `core_only` (default): Filters `*_API_KEY`, `*_SECRET`, `*_TOKEN`, `*_PASSWORD`, `*_CREDENTIAL` from host env. Keeps PATH, HOME, SHELL, language paths.
- `inherit_all`: No filtering (backward compat)
- `inherit_none`: Clean slate — only explicit env_vars visible

Explicit env_vars always override the filter:
`env_exec(instance="safe", command="echo $KEY", env_vars={"KEY": "value"})`

## Composable Wrappers

Apply wrappers at creation time for cross-cutting behavior:
```
env_create(type="docker", name="build", wrappers=["logging"])
env_create(type="docker", name="prod-view", wrappers=["readonly"])
env_create(type="docker", name="audited", wrappers=["logging", "readonly"])
```

- `logging`: Logs exec commands (with exit code + duration), read/write paths, grep patterns
- `readonly`: Blocks write_file and edit_file (raises PermissionError). Exec passes through.

When both applied, logging wraps readonly — logging captures readonly errors (useful for audit trails).
