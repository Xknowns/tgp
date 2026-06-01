#!/usr/bin/env python3
"""
tests/test_core.py -- Tests for TGP Core Invariants (Layer 1)

Validates the four bedrock principles that NEVER CHANGE:
    1. IDENTITY -- Content-addressed identity
    2. CAUSALITY -- Implicit in DAG structure (tested via scheduler)
    3. IMMUTABILITY -- Append-only store (tested via CAS)
    4. DETERMINISM -- Same object = same canonical form = same ID

These tests must pass on every platform, every Python version, forever.
"""

import json
import hashlib
import pytest
from tgp.core import (
    canonicalize,
    compute_id,
    verify_id,
    TGP_VERSION,
    HASH_ALGO,
    ValidationError,
)


class TestCanonicalization:
    """Test canonical JSON serialization per spec Section 4."""

    def test_empty_dict(self):
        """Empty dict canonicalizes to '{}'."""
        assert canonicalize({}) == "{}"

    def test_empty_list(self):
        """Empty list canonicalizes to '[]'."""
        assert canonicalize([]) == "[]"

    def test_simple_dict(self):
        """Dict with single key."""
        assert canonicalize({"a": 1}) == '{"a":1}'

    def test_dict_key_ordering(self):
        """Keys are sorted lexicographically ascending."""
        assert canonicalize({"b": 2, "a": 1}) == '{"a":1,"b":2}'
        assert canonicalize({"z": 26, "a": 1, "m": 13}) == '{"a":1,"m":13,"z":26}'

    def test_nested_dict(self):
        """Nested dicts are canonicalized recursively."""
        obj = {"outer": {"b": 2, "a": 1}}
        assert canonicalize(obj) == '{"outer":{"a":1,"b":2}}'

    def test_list_ordering(self):
        """List order is preserved (not sorted)."""
        assert canonicalize([3, 1, 2]) == "[3,1,2]"

    def test_mixed_structure(self):
        """Complex nested structure."""
        obj = {
            "tasks": [
                {"name": "build", "stage": 1},
                {"name": "test", "stage": 2},
            ],
            "version": "1.0.0",
        }
        expected = '{"tasks":[{"name":"build","stage":1},{"name":"test","stage":2}],"version":"1.0.0"}'
        assert canonicalize(obj) == expected

    def test_id_field_excluded(self):
        """The 'id' field is excluded from canonicalization."""
        obj_without_id = {"kind": "task", "command": ["echo"]}
        obj_with_id = {"kind": "task", "id": "sha256:abc123", "command": ["echo"]}
        assert canonicalize(obj_without_id) == canonicalize(obj_with_id)

    def test_signature_field_excluded(self):
        """The 'signature' field is excluded from canonicalization."""
        obj_without_sig = {"kind": "task", "command": ["echo"]}
        obj_with_sig = {"kind": "task", "signature": "ed25519:sig", "command": ["echo"]}
        assert canonicalize(obj_without_sig) == canonicalize(obj_with_sig)

    def test_both_id_and_signature_excluded(self):
        """Both 'id' and 'signature' are excluded."""
        base = {"kind": "task", "command": ["echo"]}
        full = {"kind": "task", "id": "sha256:abc", "signature": "ed25519:sig", "command": ["echo"]}
        assert canonicalize(base) == canonicalize(full)

    def test_string_escaping(self):
        """Strings are properly JSON-escaped."""
        assert canonicalize("hello") == '"hello"'
        assert canonicalize("line\\nbreak") == '"line\\\\nbreak"'
        assert canonicalize('quote"here') == '"quote\\"here"'

    def test_integer(self):
        """Integers are serialized without decimal point."""
        assert canonicalize(42) == "42"
        assert canonicalize(0) == "0"
        assert canonicalize(-1) == "-1"

    def test_float(self):
        """Floats are serialized naturally."""
        assert canonicalize(3.14) == "3.14"
        assert canonicalize(0.0) == "0.0"

    def test_boolean(self):
        """Booleans serialize to lowercase."""
        assert canonicalize(True) == "true"
        assert canonicalize(False) == "false"

    def test_none(self):
        """None serializes to null."""
        assert canonicalize(None) == "null"

    def test_list_of_strings(self):
        """List of strings."""
        assert canonicalize(["a", "b", "c"]) == '["a","b","c"]'

    def test_unsupported_type_raises(self):
        """Unsupported types raise ValidationError."""
        with pytest.raises(ValidationError):
            canonicalize(object())
        with pytest.raises(ValidationError):
            canonicalize(set())


class TestDeterminism:
    """Test that canonicalization is deterministic (Core Invariant 2.4)."""

    def test_same_object_same_canonical_form(self):
        """The same logical object always produces the same canonical form."""
        obj1 = {"z": 1, "a": 2, "m": 3}
        obj2 = {"a": 2, "m": 3, "z": 1}  # Different key order
        assert canonicalize(obj1) == canonicalize(obj2)

    def test_determinism_with_nested(self):
        """Determinism holds for deeply nested structures."""
        obj1 = {"outer": {"z": 1, "a": 2}, "list": [{"b": 2, "a": 1}]}
        obj2 = {"outer": {"a": 2, "z": 1}, "list": [{"a": 1, "b": 2}]}
        assert canonicalize(obj1) == canonicalize(obj2)

    def test_multiple_calls_same_result(self):
        """Multiple canonicalization calls produce identical output."""
        obj = {"kind": "task", "inputs": [{"name": "src", "ref": "sha256:abc"}]}
        result1 = canonicalize(obj)
        result2 = canonicalize(obj)
        result3 = canonicalize(obj)
        assert result1 == result2 == result3


class TestIdComputation:
    """Test content-addressed ID computation (Core Invariant 2.1)."""

    def test_id_format(self):
        """ID has correct format: sha256:64-hex-chars."""
        obj = {"kind": "task", "command": ["echo", "hello"]}
        obj_id = compute_id(obj)
        assert obj_id.startswith("sha256:")
        assert len(obj_id) == 7 + 64  # "sha256:" + 64 hex chars

    def test_id_is_sha256_of_canonical(self):
        """ID = sha256(canonical_json(obj))."""
        obj = {"kind": "task", "command": ["echo"]}
        expected = HASH_ALGO + ":" + hashlib.sha256(canonicalize(obj).encode("utf-8")).hexdigest()
        assert compute_id(obj) == expected

    def test_different_objects_different_ids(self):
        """Different objects have different IDs."""
        obj1 = {"kind": "task", "command": ["echo", "hello"]}
        obj2 = {"kind": "task", "command": ["echo", "world"]}
        assert compute_id(obj1) != compute_id(obj2)

    def test_same_object_same_id(self):
        """Same object (different key order) produces same ID."""
        obj1 = {"kind": "task", "command": ["echo"], "z": 1, "a": 2}
        obj2 = {"a": 2, "z": 1, "kind": "task", "command": ["echo"]}
        assert compute_id(obj1) == compute_id(obj2)

    def test_id_excludes_id_and_signature(self):
        """ID computation excludes id and signature fields."""
        base = {"kind": "task", "command": ["echo"]}
        with_id = {"kind": "task", "id": "sha256:fake", "command": ["echo"]}
        with_sig = {"kind": "task", "signature": "ed25519:fakesig", "command": ["echo"]}
        with_both = {
            "kind": "task",
            "id": "sha256:fake",
            "signature": "ed25519:fakesig",
            "command": ["echo"],
        }
        expected_id = compute_id(base)
        assert compute_id(with_id) == expected_id
        assert compute_id(with_sig) == expected_id
        assert compute_id(with_both) == expected_id


class TestIdVerification:
    """Test ID verification for tampering detection."""

    def test_valid_id(self):
        """Correct ID passes verification."""
        obj = {"kind": "task", "command": ["echo"]}
        obj["id"] = compute_id(obj)
        assert verify_id(obj) is True

    def test_tampered_content_fails(self):
        """Tampered content fails ID verification."""
        obj = {"kind": "task", "command": ["echo", "hello"]}
        obj["id"] = compute_id(obj)
        # Tamper with content
        obj["command"] = ["echo", "tampered"]
        assert verify_id(obj) is False

    def test_missing_id(self):
        """Object without 'id' field fails verification."""
        obj = {"kind": "task", "command": ["echo"]}
        assert verify_id(obj) is False

    def test_wrong_id(self):
        """Object with incorrect ID fails verification."""
        obj = {"kind": "task", "command": ["echo"], "id": "sha256:" + "0" * 64}
        assert verify_id(obj) is False


class TestSpecCompliance:
    """Test compliance with specific spec examples and edge cases."""

    def test_task_example_from_spec(self):
        """Canonicalization matches the spec's task example structure."""
        task = {
            "tgp_version": "1.0.0",
            "kind": "task",
            "inputs": [{"name": "source", "ref": "sha256:def456", "required": True}],
            "environment": {"type": "container", "image": "sha256:ghi789", "platform": "linux/amd64"},
            "command": ["compile", "--opt", "-o", "/out/binary"],
            "outputs": [{"path": "/out/binary", "expected_hash": "sha256:expected", "optional": False}],
            "resources": {"cpu": "2", "memory": "4Gi", "timeout": "300s"},
            "labels": {"project": "myapp", "stage": "build"},
            "created_at": 1717200000,
        }
        # Just verify it canonicalizes without error and produces consistent ID
        cid = canonicalize(task)
        assert isinstance(cid, str)
        assert len(cid) > 0
        obj_id = compute_id(task)
        assert obj_id.startswith("sha256:")
        assert len(obj_id) == 71

    def test_deeply_nested(self):
        """Handle deeply nested structures."""
        obj = {"a": {"b": {"c": {"d": {"e": [1, 2, 3]}}}}}
        result = canonicalize(obj)
        assert result == '{"a":{"b":{"c":{"d":{"e":[1,2,3]}}}}}'

    def test_unicode_strings(self):
        """Handle unicode strings correctly."""
        obj = {"message": "Hello, \u4e16\u754c!"}
        result = canonicalize(obj)
        assert result == '{"message":"Hello, \\u4e16\\u754c!"}'

    def test_large_list(self):
        """Handle large lists efficiently."""
        obj = {"items": list(range(1000))}
        result = canonicalize(obj)
        assert result.startswith('{"items":[')
        assert result.endswith(']}')

    def test_version_constant(self):
        """TGP_VERSION is correct."""
        assert TGP_VERSION == "1.0.0"

    def test_hash_algo_constant(self):
        """HASH_ALGO is sha256."""
        assert HASH_ALGO == "sha256"
