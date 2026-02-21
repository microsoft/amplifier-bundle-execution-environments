---
bundle:
  name: env-all
  version: 0.1.0
  description: |
    Complete execution environment toolkit — includes all environments and decorators.
    
    Composes env-local, env-docker, env-ssh, and env-decorators into a single bundle
    for teams that want the full set of execution environments available to agents.
    Each environment provides the same 8 env.* tools with environment-specific backends.

includes:
  - bundle: git+https://github.com/bkrabach/amplifier-bundle-env-local@main
  - bundle: git+https://github.com/bkrabach/amplifier-bundle-env-docker@main
  - bundle: git+https://github.com/bkrabach/amplifier-bundle-env-ssh@main
  - bundle: git+https://github.com/bkrabach/amplifier-bundle-env-decorators@main

context:
  include:
    - env-all:context/env-all-guide.md
---

# env-all

Complete execution environment toolkit for Amplifier. Includes all environment backends
and cross-cutting decorators in a single bundle.

## What's Included

| Bundle | Purpose |
|--------|---------|
| `env-local` | Local filesystem and shell execution (reference implementation) |
| `env-docker` | Container-isolated execution via Docker |
| `env-ssh` | Remote execution via SSH/SFTP |
| `env-decorators` | Logging, ReadOnly, AuditTrail decorators for any environment |

## When to Use

Use `env-all` when your agents need access to multiple execution environments in a single
session. For single-environment use cases, include the specific bundle directly instead.

See `context/env-all-guide.md` for the multi-environment agent guide.
