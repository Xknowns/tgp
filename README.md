# TGP -- Task Graph Protocol

> **Contracts live. Engines die.**

TGP is an immutable execution layer designed to outlive frameworks. It is a **protocol** for describing, executing, and verifying computational work as a directed acyclic graph (DAG) of tasks.

## Why TGP?

If you describe computation as a pure graph of immutable, content-addressed nodes, you get:

- **Reproducibility** -- same graph = same result, always
- **Deduplication** -- identical work is never repeated
- **Distribution** -- any node can run anywhere
- **Observability** -- the entire execution is inspectable as data
- **Time-travel** -- replay any past computation exactly

## Quick Start

```bash
# Clone the repository
git clone https://github.com/yourusername/tgp.git
cd tgp

# Install (editable for development)
pip install -e ".[dev]"

# Initialize a TGP repository
tgp init

# Store a file in CAS
echo "hello world" > hello.txt
tgp cas put hello.txt
# sha256:7509e5bda0c762d2bac7f90d758b5b2263fa01ccbc542ab5e3df163be08e6ca9

# Retrieve from CAS
tgp cas get sha256:7509e5bda0c762d2bac7f90d758b5b2263fa01ccbc542ab5e3df163be08e6ca9
# hello world

# Run a task graph
tgp run examples/01_hello_world/task.json
```

## Architecture

TGP has a 4-layer architecture:

```
Layer 4: Developer Experience (CLI, IDE plugins, dashboards)
Layer 3: Orchestration (Scheduler, cache, retry, distribution)
Layer 2: Execution Protocol (Task graph schema, wire format, verification)
Layer 1: Core Invariants (Identity, Causality, Immutability, Determinism)
```

Layer 1 **never changes**. It defines what it means to be TGP-compliant.

## Core Invariants

1. **IDENTITY** -- Content-addressed: `id = sha256(canonical_json(object))`
2. **CAUSALITY** -- Partial ordering via DAG structure
3. **IMMUTABILITY** -- Append-only store, objects never modified
4. **DETERMINISM** -- Same inputs always produce same outputs

## Reference Implementation

This repository provides a Python reference implementation with:

| Module | Purpose |
|--------|---------|
| `tgp/core.py` | Canonicalization, ID computation, verification |
| `tgp/cas.py` | Content-addressed store with filesystem backend |
| `tgp/task.py` | Task model and validation |
| `tgp/scheduler.py` | DAG execution engine |
| `tgp/executor.py` | Native/container/WASM task execution |
| `tgp/crypto.py` | Ed25519 signing and verification |
| `tgp/cli.py` | Command-line interface |

## Project Structure

```
tgp/
├── tgp/              # Reference implementation
├── tests/            # Comprehensive test suite
├── examples/         # Example projects
│   ├── 01_hello_world/
│   ├── 02_build_pipeline/
│   ├── 03_container_task/
│   └── 04_distributed/
├── docs/             # Documentation
│   ├── architecture.md
│   ├── protocol.md
│   └── roadmap.md
├── README.md
├── SPECIFICATION.md  # Full protocol spec
├── CONTRIBUTING.md   # How to extend TGP
└── LICENSE           # MIT
```

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=tgp --cov-report=term-missing

# Type checking
mypy tgp/

# Formatting
black tgp/ tests/
```

## Documentation

- [Architecture](docs/architecture.md) -- System design and module relationships
- [Protocol](docs/protocol.md) -- Wire format, storage layout, validation rules
- [Roadmap](docs/roadmap.md) -- Future plans and extension points
- [SPECIFICATION.md](SPECIFICATION.md) -- Full protocol specification v1.0.0

## Examples

### Hello World

```json
{
  "kind": "task",
  "inputs": [],
  "environment": {"type": "native"},
  "command": ["sh", "-c", "echo 'Hello, World!' > /out/hello.txt"],
  "outputs": [{"path": "/out/hello.txt"}]
}
```

Run: `tgp task create task.json && tgp run task.json`

### Build Pipeline

See `examples/02_build_pipeline/` for a multi-stage C compilation pipeline.

## Philosophy

> "The most powerful position in software isn't being the best engine. It's being the protocol that every engine eventually has to speak."

Optimize for adoption. Boring and correct beats exciting and wrong.

## License

MIT License. See [LICENSE](LICENSE).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

---

*The best time to plant a tree was 20 years ago. The best time to define an immutable protocol is now.*
