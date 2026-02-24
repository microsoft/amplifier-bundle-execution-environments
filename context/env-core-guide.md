# Environment Toolkit — Core

You have 11 `env_*` tools for working with named environment instances.

## Key Concept: Instances

Every tool takes an `instance` parameter targeting a named environment. A **"local"** instance exists by default — no setup needed for host operations. Create additional instances on demand with `env_create`.

## Tools

| Tool | Purpose | Key Params |
|------|---------|------------|
| `env_create` | Create a new environment instance | type, name |
| `env_destroy` | Tear down an instance | instance |
| `env_list` | List all active instances | (none) |
| `env_exec` | Execute shell command | instance, command, timeout, workdir |
| `env_read_file` | Read file content | instance, path, offset, limit |
| `env_write_file` | Write file content | instance, path, content |
| `env_edit_file` | Edit file (string replace) | instance, path, old_string, new_string |
| `env_grep` | Search file contents | instance, pattern, path, glob |
| `env_glob` | Find files by pattern | instance, pattern, path |
| `env_list_dir` | List directory | instance, path |
| `env_file_exists` | Check path exists | instance, path |

The `instance` parameter defaults to `"local"`, so simple calls just work on the host.

## Lifecycle: Create → Use → Destroy

1. **Local** — already there, use it directly
2. **Create** — `env_create(type="docker", name="build")` for isolation
3. **Use** — target by name: `env_exec(instance="build", command="pytest")`
4. **Destroy** — `env_destroy(instance="build")` when done (also auto-destroyed at session end)

Choose meaningful instance names: "build", "pi", "staging-db", "test-runner".

## Example: Local Only (no setup needed)

```
env_exec(command="ls src/")
env_read_file(path="src/main.py")
env_edit_file(path="config.yaml", old_string="debug: false", new_string="debug: true")
```
