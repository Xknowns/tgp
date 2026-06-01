# Contributing to TGP

Thank you for your interest in making TGP better! This document provides guidelines for extending the protocol and reference implementation.

## Getting Started

```bash
git clone https://github.com/yourusername/tgp.git
cd tgp
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Development Workflow

1. **Create a branch**: `git checkout -b feature/your-feature`
2. **Make changes**: Follow the coding standards below
3. **Run tests**: `pytest tests/ -v`
4. **Type check**: `mypy tgp/`
5. **Format**: `black tgp/ tests/`
6. **Submit PR**: Describe the change and its motivation

## Quality Gates

All PRs must pass:

1. **All tests**: `pytest tests/ -v`
2. **Type checking**: `mypy tgp/`
3. **Formatting**: `black --check tgp/ tests/`
4. **Spec compliance**: New features MUST update `SPECIFICATION.md`

## Extending TGP

### Adding a New Executor

Create a new executor by subclassing `BaseExecutor`:

```python
from tgp.executor import BaseExecutor

class MyExecutor(BaseExecutor):
    def execute(self, task, completed_results):
        # Resolve inputs
        # Run task in your environment
        # Capture outputs
        # Return list of output artifact IDs
        pass
```

Register it with the scheduler:

```python
scheduler._executors["myenv"] = MyExecutor(cas)
```

### Adding a New CAS Backend

Implement the CAS interface:

```python
class MyCAS:
    def put(self, data: bytes) -> str:
        ...
    def get(self, obj_id: str) -> bytes:
        ...
    def exists(self, obj_id: str) -> bool:
        ...
    def verify(self, obj_id: str) -> bool:
        ...
```

### Adding Validation Rules

Extend the validator without modifying core:

```python
class ExtendedValidator(TaskValidator):
    @classmethod
    def validate(cls, obj):
        super().validate(obj)
        # Your additional checks
```

## Design Principles

When contributing, keep these principles in mind:

1. **Layer 1 never changes.** The four core invariants are immutable.
2. **Protocol over implementation.** Optimize for adoption.
3. **Backward compatibility.** Support at least 2 major versions.
4. **Boring and correct > exciting and wrong.**

## Adding Tests

Every new feature must include tests. Follow the existing test structure:

- `tests/test_core.py` -- Core invariant tests
- `tests/test_cas.py` -- CAS operation tests
- `tests/test_task.py` -- Validation tests
- `tests/test_scheduler.py` -- Execution tests

## Questions?

Open an issue on GitHub or reach out to the maintainers.

---

*Contracts live. Engines die.*
