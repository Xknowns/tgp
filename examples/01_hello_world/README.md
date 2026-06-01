# Example 01: Hello World

The simplest possible TGP task: write "hello world" to a file.

## Files

- `task.json` -- The task definition

## Running

```bash
# Initialize TGP
tgp init

# Create and run the task
tgp task create task.json
# Note the task ID output, then run it via a graph
```

## What It Demonstrates

- Minimal task structure
- No inputs (source task)
- Single output
- Native execution
