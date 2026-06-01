# Example 02: Build Pipeline

A multi-stage C build pipeline: compile source code, then run the binary.

## Files

- `main.c` -- Source code
- `compile.json` -- Compilation task
- `run.json` -- Execution task
- `graph.json` -- Pipeline graph linking both tasks

## Running

```bash
# Initialize TGP
tgp init

# Run the complete pipeline
tgp run graph.json
```

## What It Demonstrates

- Task dependencies (run depends on compile)
- File inputs/outputs
- Multi-task graphs
- Content-addressed caching (re-run is instant)
