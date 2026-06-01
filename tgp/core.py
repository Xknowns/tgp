#!/usr/bin/env python3
"""
tgp/core.py -- Core Invariants (Layer 1: NEVER CHANGES)

This module implements the four bedrock principles of TGP:
    1. IDENTITY -- Content-addressed: id = sha256(canonical_json(obj))
    2. CAUSALITY -- Partial ordering via DAG structure
    3. IMMUTABILITY -- Write-once, append-only store
    4. DETERMINISM -- Same inputs always produce same outputs

The canonicalization algorithm ensures that the same logical object always
produces the same content hash across all implementations, platforms, and time.

Specification reference: Section 2 (Core Invariants) and Section 4 (Canonical Serialization)
"""

import json
import hashlib
from typing import Any, Dict

# ============================================================================
# PROTOCOL CONSTANTS
# ============================================================================

TGP_VERSION = "1.0.0"
HASH_ALGO = "sha256"
SIGN_ALGO = "ed25519"


# ============================================================================
# EXCEPTIONS
# ============================================================================

class TGPError(Exception):
    """Base exception for all TGP errors.

    All TGP-specific exceptions inherit from this class, allowing callers
    to catch any protocol-related error with a single except clause.
    """
    pass


class ValidationError(TGPError):
    """Object validation failed against TGP specification.

    Raised when:
        - Required fields are missing
        - Field values have invalid format (e.g., non-sha256 refs)
        - ID verification fails (content doesn't match hash)
        - Kind is not one of the supported values
    """
    pass


class CASError(TGPError):
    """Content-addressed store operation failed.

    Raised when:
        - Object not found in store
        - ID format is invalid
        - Stored data is corrupted (doesn't match its ID)
        - Atomic write operations fail
    """
    pass


class ExecutionError(TGPError):
    """Task execution failed.

    Raised when:
        - Command returns non-zero exit code
        - Task times out
        - Output hash doesn't match expected hash
        - Cycle detected in dependency graph
        - Required output artifact not produced
    """
    pass


# ============================================================================
# CANONICAL SERIALIZATION
# ============================================================================

def canonicalize(obj: Any) -> str:
    """Canonical JSON serialization per TGP specification v1.0.0.

    Produces a deterministic string representation of any JSON-serializable
    object. The same logical object always produces the same canonical form,
    regardless of key ordering in the original or whitespace formatting.

    Rules (per Section 4 of the specification):
        1. Format: JSON (RFC 8259)
        2. Encoding: UTF-8
        3. Key Ordering: Lexicographic ascending (sorted alphabetically)
        4. Whitespace: No insignificant whitespace (no spaces, no newlines)
        5. Numbers: No trailing zeros, no scientific notation for integers
        6. Omit for hashing: 'id' and 'signature' fields are EXCLUDED

    Args:
        obj: Any JSON-serializable Python object (dict, list, str, int, float, bool, None)

    Returns:
        A deterministic string representation suitable for content hashing.

    Raises:
        ValidationError: If obj contains an unsupported type.

    Examples:
        >>> canonicalize({"b": 2, "a": 1})
        '{"a":1,"b":2}'
        >>> canonicalize({"id": "xxx", "kind": "task"})
        '{"kind":"task"}'
    """
    if isinstance(obj, dict):
        items = []
        for k in sorted(obj.keys()):
            if k in ("id", "signature"):
                continue
            items.append('"' + k + '":' + canonicalize(obj[k]))
        return "{" + ",".join(items) + "}"
    elif isinstance(obj, list):
        return "[" + ",".join(canonicalize(v) for v in obj) + "]"
    elif isinstance(obj, str):
        return json.dumps(obj)
    elif isinstance(obj, bool):
        return "true" if obj else "false"
    elif obj is None:
        return "null"
    elif isinstance(obj, (int, float)):
        # Integers: no decimal point, no scientific notation
        # Floats: natural string representation
        return str(obj)
    else:
        raise ValidationError(
            "Unsupported type in canonicalization: " + str(type(obj)) +
            ". Supported types: dict, list, str, int, float, bool, None"
        )


# ============================================================================
# CONTENT-ADDRESSED IDENTITY
# ============================================================================

def compute_id(obj: Dict[str, Any]) -> str:
    """Compute content-addressed ID for a TGP object.

    The ID is the SHA-256 hash of the canonical JSON form of the object,
    with 'id' and 'signature' fields excluded from the hash input.

    Per Section 2.1 (IDENTITY invariant):
        id(object) = sha256(canonical_json(object))

    Args:
        obj: A TGP object (task, artifact, environment, or graph) as a dict.
             Must NOT include 'id' or 'signature' fields, or they will be
             excluded from the hash computation.

    Returns:
        A content-addressed ID string in the format 'sha256:hexdigest'.

    Examples:
        >>> obj = {"kind": "task", "command": ["echo", "hi"]}
        >>> compute_id(obj)
        'sha256:3f2a...'
    """
    canonical = canonicalize(obj)
    hash_bytes = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return HASH_ALGO + ":" + hash_bytes


def verify_id(obj: Dict[str, Any]) -> bool:
    """Verify that a TGP object's id field matches its content hash.

    Recomputes the content hash from the object's canonical form and
    compares it to the stored id field. This detects any tampering with
    the object's content after its ID was computed.

    Per Section 3.1 (Task field rules):
        id: MUST equal sha256 of canonical JSON without id and signature fields

    Args:
        obj: A TGP object containing an 'id' field to verify.

    Returns:
        True if the id matches the computed content hash, False otherwise.
        Also returns False if the object has no 'id' field.

    Examples:
        >>> obj = {"kind": "task", "id": "sha256:abc123...", "command": ["echo"]}
        >>> verify_id(obj)
        True  # if the id matches the content hash
    """
    if "id" not in obj:
        return False
    expected = compute_id(obj)
    return obj["id"] == expected
