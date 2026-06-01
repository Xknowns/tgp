# TGP Protocol Details

## Wire Format

TGP objects are serialized as JSON (RFC 8259) with UTF-8 encoding. The canonical form is used for content hashing and MUST be produced as follows:

1. **Dicts**: Keys sorted ascending, format as `{"key":value}`
2. **Lists**: Preserve order, format as `[value1,value2]`
3. **Strings**: JSON-escaped with double quotes
4. **Integers**: Decimal, no trailing zeros, no scientific notation
5. **Floats**: Natural string representation
6. **Booleans**: `true` or `false`
7. **None**: `null`
8. **Excluded fields**: `id` and `signature` are never included in the canonical form

## Content Addressing

```
sha256_id = "sha256:" + hex(sha256(canonical_json(object)))
```

The `sha256:` prefix allows future algorithm migration. The 64 hex characters are lowercase.

## Storage Layout (Local Filesystem)

```
.tgp/
  objects/          # Content-addressed object store
    ab/             # First 2 chars of hash = prefix directory
      cd1234...     # Remaining 62 chars = filename
    ef/
      567890...
  refs/             # Named references (like git branches/tags)
    heads/
      main -> sha256:...
    tags/
      v1.0.0 -> sha256:...
```

### Atomic Writes

All writes use the temp-file + rename pattern:
1. Write data to `objects/ab/cd1234...tmp`
2. Atomic rename to `objects/ab/cd1234...`

This ensures readers never see partially-written data.

## CAS Interface

```python
class CAS:
    def put(self, data: bytes) -> str:
        """Store bytes, return sha256:id"""

    def get(self, id: str) -> bytes:
        """Retrieve bytes by id. Raise NotFound if missing."""

    def exists(self, id: str) -> bool:
        """Check if id exists without fetching."""

    def verify(self, id: str) -> bool:
        """Verify that stored data matches its id."""
```

## Validation Rules

### Task (`kind: "task"`)
- Required: `kind`, `inputs`, `environment`, `command`, `outputs`
- `inputs[].ref`: MUST be `sha256:...`
- `environment.type`: MUST be one of `container`, `native`, `wasm`
- `environment.image`: MUST be `sha256:...` for containers
- `outputs[].path`: Required

### Artifact (`kind: "artifact"`)
- Required: `kind`, `type`, `size`
- `type`: MUST be one of `blob`, `tree`, `exec`
- `size`: Non-negative integer

### Environment (`kind: "environment"`)
- Required: `kind`, `type`
- `layers`: Required for containers, MUST be list of `sha256:...`

### Graph (`kind: "graph"`)
- Required: `kind`, `root`, `tasks`
- `tasks`: Non-empty list of `sha256:...`

## Signing

```
signature = ed25519_sign(private_key, sha256(canonical_json(object)))
```

Signature format: `ed25519:<base64-encoded-signature>`

## Failure Handling

| Failure Type | Behavior |
|-------------|----------|
| Task timeout | Mark failed, propagate to dependents |
| Output hash mismatch | Mark failed, DO NOT cache |
| Missing input artifact | Mark failed, propagate |
| Worker crash | Retry with exponential backoff (max 3) |
| Non-deterministic declared | Warn, do not cache |
