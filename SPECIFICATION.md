# TGP — Task Graph Protocol
## v1.0.0 Specification

> **Mission:** Define the immutable execution layer that outlives frameworks.
> **Motto:** *Contracts live. Engines die.*

---

## 1. PHILOSOPHY

TGP is not a framework. It is a **protocol** for describing, executing, and verifying computational work as a directed acyclic graph (DAG) of tasks.

The core insight: if you can describe computation as a pure graph of immutable, content-addressed nodes, you get:
- **Reproducibility** — same graph = same result, always
- **Deduplication** — identical work is never repeated
- **Distribution** — any node can run anywhere
- **Observability** — the entire execution is inspectable as data
- **Time-travel** — replay any past computation exactly

---

## 2. CORE INVARIANTS (Layer 1 — NEVER CHANGES)

These four principles are the bedrock. Any TGP-compliant system MUST enforce them.

### 2.1 IDENTITY — Content-Addressed
Every object (task, artifact, environment) is identified by the cryptographic hash of its canonical serialized form.
```
id(object) = sha256(canonical_json(object))
```
Implication: You cannot mutate an object. You create a new one with a new identity.

### 2.2 CAUSALITY — Partial Ordering
Execution order is defined by the DAG structure, not timestamps. If task B depends on task A, A happens-before B. No wall-clock assumptions.

### 2.3 IMMUTABILITY — Write-Once
The content-addressed store (CAS) is append-only. Objects are never deleted or modified. Only new objects are added.

### 2.4 DETERMINISM — Same Inputs, Same Outputs
Given identical task definitions and identical input artifacts, the output artifacts MUST be byte-for-byte identical. Non-determinism (timestamps, randomness) MUST be explicitly declared and handled.

---

## 3. DATA MODEL (Layer 2 — Protocol)

### 3.1 Task

```json
{
  "tgp_version": "1.0.0",
  "id": "sha256:abc123...",
  "kind": "task",
  "inputs": [
    {
      "name": "source",
      "ref": "sha256:def456...",
      "required": true
    }
  ],
  "environment": {
    "type": "container",
    "image": "sha256:ghi789...",
    "platform": "linux/amd64"
  },
  "command": ["compile", "--opt", "-o", "/out/binary"],
  "outputs": [
    {
      "path": "/out/binary",
      "expected_hash": "sha256:expected...",
      "optional": false
    }
  ],
  "resources": {
    "cpu": "2",
    "memory": "4Gi",
    "timeout": "300s"
  },
  "labels": {
    "project": "myapp",
    "stage": "build"
  },
  "created_at": 1717200000,
  "signature": "ed25519:sig..."
}
```

**Field Rules:**
- `id`: MUST equal sha256 of canonical JSON without `id` and `signature` fields
- `inputs[].ref`: MUST be a valid CAS reference (sha256:...)
- `environment.image`: MUST be content-addressed (sha256:...), not tag-based
- `outputs[].expected_hash`: If present, runtime MUST verify match or fail
- `signature`: Cryptographic proof of task authorship

### 3.2 Artifact

```json
{
  "tgp_version": "1.0.0",
  "id": "sha256:def456...",
  "kind": "artifact",
  "type": "blob",
  "size": 1024,
  "content_type": "application/octet-stream",
  "refs": [],
  "created_by": "sha256:task_id...",
  "created_at": 1717200000,
  "signature": "ed25519:sig..."
}
```

**Artifact Types:**
- `blob` — opaque bytes
- `tree` — directory structure (list of named refs)
- `exec` — executable artifact with platform metadata

### 3.3 Environment

```json
{
  "tgp_version": "1.0.0",
  "id": "sha256:env123...",
  "kind": "environment",
  "type": "container",
  "layers": [
    "sha256:layer1...",
    "sha256:layer2..."
  ],
  "config": {
    "entrypoint": [],
    "env": {"KEY": "VALUE"},
    "working_dir": "/workspace"
  },
  "signature": "ed25519:sig..."
}
```

### 3.4 Graph

```json
{
  "tgp_version": "1.0.0",
  "id": "sha256:graph123...",
  "kind": "graph",
  "root": "sha256:root_task...",
  "tasks": [
    "sha256:task_a...",
    "sha256:task_b...",
    "sha256:task_c..."
  ],
  "metadata": {
    "name": "build-myapp",
    "description": "Full build pipeline"
  },
  "signature": "ed25519:sig..."
}
```

---

## 4. CANONICAL SERIALIZATION

To ensure content-addressing works across all implementations:

1. **Format:** JSON (RFC 8259)
2. **Encoding:** UTF-8
3. **Key Ordering:** Lexicographic ascending
4. **Whitespace:** No insignificant whitespace
5. **Numbers:** No trailing zeros, no scientific notation for integers
6. **Omit for hashing:** `id` and `signature` fields

**Canonicalization Algorithm:**
```python
def canonicalize(obj):
    if isinstance(obj, dict):
        return "{" + ",".join(
            f'"{k}":{canonicalize(v)}'
            for k, v in sorted(obj.items())
            if k not in ("id", "signature")
        ) + "}"
    elif isinstance(obj, list):
        return "[" + ",".join(canonicalize(v) for v in obj) + "]"
    elif isinstance(obj, str):
        return json.dumps(obj)
    elif isinstance(obj, (int, float)):
        return str(obj)
    elif obj is None:
        return "null"
    elif isinstance(obj, bool):
        return "true" if obj else "false"
```

---

## 5. CONTENT-ADDRESSED STORE (CAS)

### 5.1 Interface

```python
class CAS:
    def put(self, data: bytes) -> str:
        """Store bytes, return sha256:id"""
        pass

    def get(self, id: str) -> bytes:
        """Retrieve bytes by id. Raise NotFound if missing."""
        pass

    def exists(self, id: str) -> bool:
        """Check if id exists without fetching."""
        pass

    def verify(self, id: str) -> bool:
        """Verify that stored data matches its id."""
        pass
```

### 5.2 Storage Backends
- **Local:** Filesystem (content-addressed directory structure)
- **Remote:** S3-compatible, IPFS, custom
- **Distributed:** Peer-to-peer replication

### 5.3 Directory Structure (Local)
```
.tgp/
  objects/
    ab/
      cd1234...  # First 2 chars = directory prefix
    ef/
      567890...
  refs/
    heads/
      main -> sha256:graph_abc...
    tags/
      v1.0.0 -> sha256:graph_def...
```

---

## 6. EXECUTION SEMANTICS

### 6.1 Graph Reduction

Execution is **graph reduction**: repeatedly replace executable task nodes with their output artifacts until only artifacts remain.

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

### 6.2 Scheduling Rules

1. **A task is ready** when all required input artifacts exist in CAS
2. **Tasks with no dependencies** execute first (in parallel if possible)
3. **Tasks with satisfied dependencies** execute as soon as a worker is free
4. **Execution order** is a topological sort of the DAG
5. **Parallelism** is limited by: worker count, resource constraints, explicit `max_parallel` labels

### 6.3 Caching

Before executing any task:
1. Compute task ID from canonical form
2. Check CAS for existing output artifacts matching `expected_hash`
3. If found, skip execution, use cached result
4. If `expected_hash` mismatch, fail (determinism violation)

### 6.4 Failure Handling

| Failure Type | Behavior |
|-------------|----------|
| Task timeout | Mark failed, propagate to dependents |
| Output hash mismatch | Mark failed, DO NOT cache |
| Missing input artifact | Mark failed, propagate |
| Worker crash | Retry with exponential backoff (max 3) |
| Non-deterministic declared | Warn, do not cache |

---

## 7. SECURITY

### 7.1 Signatures
All objects MUST be signed by the creator's Ed25519 key.

```
signature = ed25519_sign(private_key, sha256(canonical_json(object)))
```

### 7.2 Trust Model
- Each environment image MUST be signed by trusted builder
- Task signatures verify authorship, not safety
- Sandboxing is the responsibility of the runtime (containers, VMs, WASM)

### 7.3 Provenance
Every artifact MUST include `created_by` pointing to the task that produced it. This creates an immutable audit trail from any artifact back to its source inputs.

---

## 8. EXTENSIBILITY

### 8.1 Forward Compatibility
- Unknown fields in JSON objects MUST be preserved but ignored
- New `kind` values MUST be rejected unless explicitly supported
- Version format: `MAJOR.MINOR.PATCH`
  - MAJOR: Breaking protocol changes
  - MINOR: New features, backward compatible
  - PATCH: Clarifications, no behavior change

### 8.2 Custom Extensions
Extensions MUST use reverse-domain namespaced keys:
```json
{
  "com.mycompany.feature": "value"
}
```

---

## 9. REFERENCE IMPLEMENTATION REQUIREMENTS

Any reference implementation MUST provide:

1. **CAS** — Local filesystem backend minimum
2. **Parser** — Validate and canonicalize all object types
3. **Scheduler** — Single-threaded minimum, parallel optional
4. **Executor** — Local process execution minimum
5. **CLI** — `tgp run`, `tgp build`, `tgp verify`, `tgp cache`

---

## 10. GOVERNANCE

- **Protocol Spec:** Open standard, RFC-style process
- **Reference Implementation:** Community-maintained
- **Extensions:** Plugin architecture, no core bloat
- **Changes:** Require backward compatibility for 2 major versions

---

*"The best time to plant a tree was 20 years ago. The best time to define an immutable protocol is now."*
