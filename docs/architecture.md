# TGP Architecture

## Overview

TGP (Task Graph Protocol) is a 4-layer architecture designed for longevity through separation of concerns:

```
Layer 4: Developer Experience (CLI, IDE plugins, dashboards)
    ^
Layer 3: Orchestration (Scheduler, cache, retry, distribution)
    ^
Layer 2: Execution Protocol (Task graph schema, wire format, verification)
    ^
Layer 1: Core Invariants (Identity, Causality, Immutability, Determinism) <- NEVER CHANGES
```

## Layer 1: Core Invariants

These four principles are the bedrock. They define what it means to be "TGP-compliant."

### Identity (Content-Addressed)
Every object is identified by the SHA-256 hash of its canonical serialized form.
```
id(object) = sha256(canonical_json(object))
```
This means you cannot mutate an object — you create a new one with a new identity.

### Causality (Partial Ordering)
Execution order is defined by the DAG structure, not timestamps. If task B depends on task A, A happens-before B. No wall-clock assumptions.

### Immutability (Write-Once)
The CAS is append-only. Objects are never deleted or modified. Only new objects are added.

### Determinism (Same Inputs, Same Outputs)
Given identical task definitions and identical input artifacts, the output artifacts MUST be byte-for-byte identical.

## Layer 2: Execution Protocol

The data model defines four object kinds:

| Kind | Purpose | Key Fields |
|------|---------|------------|
| `task` | Unit of work | inputs, environment, command, outputs |
| `artifact` | Immutable data | type, size, created_by |
| `environment` | Execution context | type, layers (for containers) |
| `graph` | Task collection | root, tasks[] |

### Canonical Serialization
All objects are serialized using a deterministic canonical JSON form:
- Keys sorted lexicographically
- No insignificant whitespace
- No trailing zeros on numbers
- `id` and `signature` fields excluded from hashing

## Layer 3: Orchestration

The scheduler implements graph reduction:
1. Load tasks from CAS
2. Build dependency graph from input/output references
3. Topological sort (Kahn's algorithm)
4. Execute in order, checking cache first
5. Replace task nodes with their output artifacts

### Caching
Before executing any task, the scheduler checks if all expected outputs already exist in the CAS. If so, execution is skipped.

### Executors
The scheduler delegates to environment-specific executors:
- **NativeExecutor**: Runs commands on the host
- **ContainerExecutor**: STUB — falls back to native in v1.0.0
- **WasmExecutor**: STUB — not implemented in v1.0.0

## Layer 4: Developer Experience

The CLI provides a git-like interface:
- `tgp init` — Initialize repository
- `tgp cas put|get|verify` — CAS operations
- `tgp task create|validate` — Task operations
- `tgp run <graph>` — Execute graph
- `tgp verify <id>` — Verify object
- `tgp cache stats` — Show statistics

## Data Flow

```
Input Graph:  [Task A] -> [Task B] -> [Task C]
                     |          |
                [Artifact 1] [Artifact 2]

Step 1: Execute A -> produces Artifact 3
Graph: [Artifact 3] -> [Task B] -> [Task C]

Step 2: Execute B -> produces Artifact 4
Graph: [Artifact 3] -> [Artifact 4] -> [Task C]

Step 3: Execute C -> produces Artifact 5
Graph: [Artifact 3] -> [Artifact 4] -> [Artifact 5]  (DONE)
```

## Module Dependencies

```
cli.py      -> scheduler.py, task.py, cas.py, core.py
scheduler.py -> executor.py, task.py, cas.py, core.py
executor.py  -> cas.py, core.py
task.py      -> core.py
cas.py       -> core.py
crypto.py    -> core.py
core.py      (no dependencies within tgp)
```
