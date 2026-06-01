# TGP Roadmap

## v1.0.0 (Current)

**Status:** Reference implementation complete

**Scope:**
- Core invariants (identity, causality, immutability, determinism)
- Content-addressed store with filesystem backend
- Task model and validation for all object kinds
- DAG execution engine with topological sort
- Native process execution
- Ed25519 signing (requires `cryptography` library)
- Command-line interface
- 100% test coverage for core modules

**Explicitly NOT in v1.0.0:**
- Container execution (stub only)
- WASM execution (stub only)
- Distributed/remote workers
- Web dashboard
- Parallel execution (sequential with correct ordering)

## v1.1.0 (Planned)

- Parallel task execution with thread pool
- LRU cache for CAS hot objects
- Performance benchmarks
- Provenance tracking queries

## v1.2.0 (Planned)

- Full container execution (Docker integration)
- Content-addressed image pulling
- Volume mounting for inputs/outputs
- Platform constraint enforcement

## v2.0.0 (Future)

- WASM execution engine
- WASI interface for sandboxed I/O
- Remote worker protocol (gRPC/HTTP)
- Worker registration and heartbeat
- Task distribution across worker pools

## v3.0.0 (Future)

- Web dashboard for graph visualization
- Real-time execution progress
- Cache hit/miss analytics
- Artifact lineage viewer
- REST API for external integrations

## Extension Points

TGP is designed to be extended without modifying the core:

### Custom Executors
Subclass `BaseExecutor` and register with the scheduler:

```python
from tgp.executor import BaseExecutor

class MyExecutor(BaseExecutor):
    def execute(self, task, completed_results):
        # Your execution logic
        return output_ids

scheduler = Scheduler(cas)
scheduler._executors["myenv"] = MyExecutor(cas)
```

### Custom CAS Backends
Implement the CAS interface for different storage:

```python
class S3CAS:
    def put(self, data: bytes) -> str: ...
    def get(self, obj_id: str) -> bytes: ...
    def exists(self, obj_id: str) -> bool: ...
    def verify(self, obj_id: str) -> bool: ...
```

### Custom Validators
Add validation rules without changing core:

```python
class ExtendedValidator(TaskValidator):
    @classmethod
    def validate(cls, obj):
        super().validate(obj)
        # Additional checks
```

## Design Principles for Future Development

1. **Layer 1 never changes.** The four core invariants are immutable.
2. **Protocol over implementation.** Optimize for adoption, not impressiveness.
3. **Backward compatibility.** Support at least 2 major versions back.
4. **Explicit > implicit.** Non-determinism must be declared.
5. **Boring and correct > exciting and wrong.**

---

*"The best time to plant a tree was 20 years ago. The best time to define an immutable protocol is now."*
