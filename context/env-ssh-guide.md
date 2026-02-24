# Environment Toolkit — SSH

SSH instances connect to remote hosts. Provide `host` and optionally `username` and `key_file`.

## Creating SSH Instances

```
env_create(type="ssh", name="pi", host="voicebox")
env_exec(instance="pi", command="uname -a")
env_read_file(instance="pi", path="/etc/hostname")
env_destroy(instance="pi")
```

Key parameters: `host` (required), `username`, `key_file`.

## Auto-Discovery

SSH credentials are auto-discovered when not explicitly provided:
```
env_create(type="ssh", name="pi", host="voicebox")
# Auto-discovers username and key from ~/.ssh/config and default keys
```
Explicit params always override auto-discovered values.

## Multi-Environment Example

```
env_create(type="docker", name="build", purpose="rust")
env_create(type="ssh", name="deploy", host="staging.example.com")
env_exec(instance="build", command="cargo build --release")
env_exec(instance="deploy", command="systemctl restart app")
env_destroy(instance="build")
```
